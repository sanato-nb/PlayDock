"""5단계: 엔진/파일 형식별로 *명시적* 제품 정보만 수집하는 파서.

읽은 설정/README를 코드로 실행하지 않는다. 일반 JSON의 name, package.json의
패키지 이름과 README의 임의 문장을 출시 게임명으로 추정하지 않는다.
strength는 로컬 설정값의 근거 성격일 뿐 실제 게임 동일성 신뢰도가 아니다.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import PurePosixPath


@dataclass(frozen=True)
class ExtractedField:
    field: str
    value: str
    kind: str  # title / product_code / steam_app_id / publisher / project_name
    strength: str  # strong / supporting / weak
    parser: str


CODE_FIELD = re.compile(
    r"(?i)^(?:dlsite_?(?:code|id)?|work_?(?:no|id)|product_?id|품번|品番)$"
)
CODE_PATTERN = re.compile(r"(?i)^(?:RJ|VJ|BJ|EJ)\d{6,8}$")
STEAM_FIELD = re.compile(r"(?i)^(?:steam_?app_?id|steam\s*app\s*id|steamappid)$")
STEAM_ID = re.compile(r"^\d{3,10}$")
LABEL_LINE = re.compile(r"^\s*([^=:：]{1,42}?)\s*[:=：]\s*(.*?)\s*$")
RENPY_NAME = re.compile(
    r"(?i)^\s*define\s+config\.name\s*=\s*(?:_\s*\(\s*)?(['\"])(.{2,140}?)\1"
)
README_LABELS = frozenset({
    "title", "game title", "game name", "게임명", "게임 제목",
    "작품명", "作品名", "ゲームタイトル",
})
GENERIC_TITLE_KEYS = frozenset({
    "title", "gametitle", "game_title", "gameName", "game_name",
    "displayName", "productName", "product_name", "work_name",
})
WINDOWS_TITLE_KEYS = ("title",)
CODE_JSON_KEYS = ("dlsite_code", "dlsite_id", "workno", "work_no", "product_id")

# 엔진에서 흔히 사용하는 기본 프로젝트명은 게임 출시 제목의 강한 증거가 아니다.
# 중간 검증에서 Unity app.info의 "ntr game"이 실제 공식 제목과
# 다르다는 이유만으로 잘못된 '근거 충돌'이 발생한 것을 반영한다.
GENERIC_PROJECT_TITLES = frozenset({
    "ntr game", "game", "new game", "new project", "my project",
    "untitled", "untitled game", "project",
    "test game", "test", "rpg maker", "game project",
})


def _generic_project_title(value: str) -> bool:
    name = " ".join(value.casefold().split())
    return (name in GENERIC_PROJECT_TITLES
            or bool(re.fullmatch(r"[a-z]{1,4} game", name)))


def _decode(payload: bytes) -> str | None:
    if b"\x00" in payload[:1024] and not payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        return None
    for codec in ("utf-8-sig", "utf-16", "cp949", "shift_jis"):
        try:
            return payload.decode(codec)
        except (UnicodeDecodeError, ValueError):
            continue
    return None


def parse_metadata_fields(member: str, payload: bytes) -> list[ExtractedField]:
    """내부 파일명을 근거로 역할이 확인된 값만 추출. 일반 파일 전체 스캔 금지."""
    basename = PurePosixPath(member.replace("\\", "/")).name.casefold()
    lowerpath = member.replace("\\", "/").casefold()
    decoded = _decode(payload)
    if decoded is None:
        return []
    out: list[ExtractedField] = []

    if basename == "steam_appid.txt":
        steam_id = decoded.strip().lstrip("\\ufeff")
        if STEAM_ID.fullmatch(steam_id):
            return [ExtractedField(
                "steam_appid", steam_id, "steam_app_id", "strong",
                "steam_appid_file",
            )]
        return []

    def add(field: str, value, kind: str = "title",
            strength: str = "supporting", parser: str = "generic") -> None:
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            return
        if kind == "title" and _generic_project_title(value):
            # 값 자체를 버리지는 않고 약한 프로젝트 이름 근거로 보존.
            strength = "weak"
            kind = "project_name"
        out.append(ExtractedField(field, value.strip(), kind, strength, parser))

    if basename.endswith(".json"):
        try:
            data = json.loads(decoded)
        except (json.JSONDecodeError, ValueError, RecursionError):
            return []
        if not isinstance(data, dict):
            return []
        # RPG Maker MV/MZ의 data/System.json은 별도 규칙으로만 제목을 인정.
        if basename == "system.json":
            if lowerpath.endswith(("/data/system.json", "/www/data/system.json")):
                add("gameTitle", data.get("gameTitle"), strength="strong",
                    parser="rpg_maker_mv_mz")
            return out
        # NW.js의 package.json 'name'은 패키지 식별자. 게임 제목 아님.
        if basename == "package.json":
            window = data.get("window")
            if isinstance(window, dict):
                add("window.title", window.get("title"), strength="supporting",
                    parser="nwjs")
            add("name", data.get("name"), kind="project_name",
                strength="weak", parser="nwjs")
        else:
            for field in ("gameTitle", "game_name", "gameName", "displayName",
                          "productName", "product_name", "work_name", "title"):
                if field in data:
                    add(field, data[field], strength=(
                        "strong" if field in ("gameTitle", "gameName") and basename == "game.json"
                        else "supporting"), parser=basename)
            # 임의 JSON의 name은 게임명이 아니다.
        for key in CODE_JSON_KEYS:
            value = data.get(key)
            if isinstance(value, str) and CODE_PATTERN.fullmatch(value.strip()):
                add(key, value, "product_code", "strong", basename)
        for key in ("steam_appid", "steam_app_id", "steamAppId"):
            value = data.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                steam_id = str(value).strip()
                if STEAM_ID.fullmatch(steam_id):
                    add(key, steam_id, "steam_app_id", "strong", basename)
        return out[:20]

    if basename == "app.info":
        # Unity app.info: 회사명 1행, 제품 이름 2행으로 된 경우만.
        lines = [s.strip() for s in decoded.splitlines()]
        if len(lines) == 2:
            add("product_name", lines[1], "title", "strong", "unity_app_info")
            add("company_name", lines[0], "publisher", "supporting",
                "unity_app_info")
        return out[:20]

    if basename == "options.rpy":
        for line in decoded.splitlines()[:180]:
            if len(line) > 300:
                continue
            match = RENPY_NAME.match(line)
            if match:
                add("config.name", match.group(2), strength="strong", parser="renpy")
        return out[:20]

    if basename == "project.godot":
        section = ""
        for line in decoded.splitlines()[:180]:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].casefold()
                continue
            if section != "application" or len(line) > 300:
                continue
            m = LABEL_LINE.match(line)
            if m and m.group(1).strip().casefold() == "config/name":
                add("application.config/name", m.group(2), strength="strong",
                    parser="godot")
        return out[:20]

    ini = basename in ("game.ini", "rpg_rt.ini")
    readme = basename == "readme" or basename.startswith("readme.")
    for line in decoded.splitlines()[:180]:
        if len(line) > 300 or line.lstrip().startswith(("#", ";", "//")):
            continue
        m = LABEL_LINE.match(line)
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        if CODE_FIELD.fullmatch(key):
            if CODE_PATTERN.fullmatch(value):
                add(key, value, "product_code", "strong",
                    "readme" if readme else "ini" if ini else "text")
            continue
        if STEAM_FIELD.fullmatch(key):
            if STEAM_ID.fullmatch(value):
                add(key, value, "steam_app_id", "strong",
                    "readme" if readme else "ini" if ini else "text")
            continue
        if readme:
            if key.casefold() in README_LABELS:
                add(key, value, "title", "supporting", "readme")
        elif ini and key.casefold() in (
            "title", "gametitle", "gamename", "game_title",
            "game_name", "작품명", "게임명", "게임제목",
        ):
            add(key, value, strength="strong",
                parser="rpg_maker_ini" if basename == "rpg_rt.ini"
                else "game_ini")
    return out[:20]
