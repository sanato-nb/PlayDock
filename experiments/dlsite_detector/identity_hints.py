"""압축파일명에서 외부 작품 식별자와 *파일 종류* 단서를 추출한다.

파일 종류는 이름만으로 추정한 결과다. 외부 작품의 게임 여부와 별개이며
본편/패치/서버팩이 섞인 경우 원본 파일 내용 확인 전에는 확정하지 않는다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from .search_terms import archive_basename

DL_CODE = re.compile(r"(?<![A-Za-z0-9])((?:RJ|BJ|VJ|EJ)\d{6,8})(?![A-Za-z0-9])", re.I)
STEAM_ID = re.compile(
    r"(?<![A-Za-z0-9])steam\s*(?:app\s*(?:id)?|id)?\s*[:#=-]?\s*(\d{3,10})(?!\d)",
    re.I,
)
BRACKET = re.compile(r"\[([^\]]{1,90})\]|\(([^)]{1,90})\)|【([^】]{1,90})】")
PATCH = re.compile(r"(?i)(?:한글\s*패치|한국어\s*패치|번역\s*패치|patch(?:ed)?|translation\s*patch)")
PATCH_ONLY = re.compile(r"(?i)(?:패치\s*(?:파일|전용|단독|만)|(?:translation\s*)?patch\s*only|standalone\s*patch)")
SERVER = re.compile(r"(?i)(?:^|[\s\[\(])server(?:\s|\b)|서버\s*(?:팩|용|버전)")
DLC = re.compile(r"(?i)\bdlc\b|추가\s*컨텐츠|추가\s*콘텐츠")
MODPACK = re.compile(r"(?i)\bmodpack\b|모드팩")
INCLUDES_GAME = re.compile(r"(?i)본편\s*포함|본편\s*동봉|includes?\s*(?:base\s*)?game")
STEAM_TAG = re.compile(r"(?i)^steam\s*(?:app\s*(?:id)?|id)?\s*[:#=-]?\s*\d{3,10}$")
VERSION_TAG = re.compile(r"(?i)^v(?:er(?:sion)?)?\.?\s*\d+(?:[._]\d+)*$")
IGNORED_TAG = re.compile(
    r"(?i)^(?:PC|windows|win64|itch\.io\s*windows|"
    r"한국어|한글|노모|수정\s*\d+|공식\s*한국어|"
    r"\d{4}-\d{2}-\d{2}|\d{6,8}|(?:RJ|VJ|BJ|EJ)\d{6,8})$"
)


@dataclass(frozen=True)
class ArchiveHints:
    dlsite_codes: tuple[str, ...]
    steam_app_ids: tuple[str, ...]
    archive_kind: str
    kind_reason: str
    title_aliases: tuple[str, ...]

    def to_dict(self):
        return asdict(self)


def extract_hints(raw: str) -> ArchiveHints:
    basename = archive_basename(raw)
    dl_codes = tuple(dict.fromkeys(m.upper() for m in DL_CODE.findall(basename)))[:4]
    ids = tuple(dict.fromkeys(STEAM_ID.findall(basename)))[:3]
    tags = [next((g for g in m.groups() if g is not None), "").strip()
            for m in BRACKET.finditer(basename)]
    # 파일명에 명시된 범주만 사용. 일반 실행파일이라는 추측은 하지 않는다.
    notes = " ".join(tags)
    kind, reason = "unknown", "압축파일명만으로 본편·추가 자료 여부를 단정할 수 없음"
    if " + " in basename:
        kind, reason = "bundle_candidate", "파일명에 여러 작품을 연결하는 '+' 표기가 있음"
    elif SERVER.search(notes) or SERVER.search(basename):
        kind, reason = "server_package_candidate", "서버 배포판을 나타내는 파일명 표기"
    elif MODPACK.search(notes) or MODPACK.search(basename):
        kind, reason = "modpack_candidate", "모드팩 표기가 포함됨"
    elif DLC.search(notes) or DLC.search(basename):
        kind, reason = "dlc_candidate", "DLC 표기가 포함됨. 본편 포함 여부는 미확인"
    elif PATCH.search(notes) or PATCH.search(basename):
        if INCLUDES_GAME.search(notes) or INCLUDES_GAME.search(basename):
            kind, reason = "game_with_patch_candidate", "한국어 패치 적용 및 본편 포함이라는 파일명 표시"
        elif PATCH_ONLY.search(notes) or PATCH_ONLY.search(basename):
            kind, reason = "patch_candidate", "패치 단독/전용이라는 명시적 파일명 표시"
        else:
            kind, reason = "localized_release_unknown", (
                "'한글패치'는 한국어가 적용된 게임일 수도 있으므로 패치 파일로 분류하지 않음; "
                "본편 포함 여부는 내부 파일 근거 확인 필요"
            )
    elif re.search(r"(?i)본편|full\s*game", notes):
        kind, reason = "base_game_candidate", "본편 표기가 포함됨"

    aliases = []
    for match in BRACKET.finditer(basename):
        # 일반 대괄호 [AI 번역·기번 수정]은 작품 별칭이 아니라 배포
        # 메타데이터일 가능성이 높다. 제목의 '(영문 원제)' 병기만 인정.
        tag = (match.group(2) or "").strip()
        if (not tag or len(tag) < 3 or STEAM_TAG.fullmatch(tag)
                or DL_CODE.fullmatch(tag) or VERSION_TAG.fullmatch(tag)
                or IGNORED_TAG.fullmatch(tag) or PATCH.search(tag)
                or SERVER.search(tag) or DLC.search(tag) or MODPACK.search(tag)):
            continue
        # 무작위 한글/영문 태그를 정식 게임 별칭이라 단정하지 않는다.
        # '거인의 비보 (Giant Treasure)' 같은 명시적 병기만 후보로 제공.
        if len(tag.split()) <= 8 and re.search(r"[A-Za-z가-힣ぁ-んァ-ヶ一-龯]", tag):
            aliases.append(tag)
    return ArchiveHints(dl_codes, ids, kind, reason, tuple(dict.fromkeys(aliases))[:3])
