"""v0.5: 압축파일명 + 내부 목록 + 설정 메타데이터를 합친 후 검색어를 선정.

수집 단계에서는 외부 검색을 하지 않는다. 모든 후보의 가치·중복을 먼저
평가한 후 공식 작품 ID/강한 제목/파일명을 우선해 요청 수를 제한한다.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .archive_inspector import ArchiveInspection
from .detector import normalized_title
from .identity_hints import extract_hints
from .internal_metadata import MetadataInspection
from .search_terms import cleaned_search_title


@dataclass(frozen=True)
class SearchHint:
    stage: int  # 출처: 1 파일명, 2 내부 파일명, 3 내부 설정
    basis: str
    query: str


SKIP_TERMS = frozenset({
    "notification helper", "notificationhelper", "editor", "save", "locales",
    "swiftshader", "css", "audio", "fonts", "font", "img", "icon", "effects",
    "dataex", "dictionaries", "resources", "package.nw", "package",
    "eztransxp.extprotocol", "lec.extprotocol", "common.extprotocol.executor",
    "databasecleanuptool", "game", "launcher", "readme", "patch", "data",
    "ntr game", "my project", "new game", "new project", "untitled",
    "game project", "test", "sample", "test game",
    "player", "extracted", "bepinex", "monobleedingedge",
    "mono", "dotnet", "d3d12", "licenses", "license",
    "python", "lib", "bin", "binary", "binaries", "common",
    "system", "config", "settings", "crashreporter", "redist",
    "redistributables", "unityplayer", "gameassembly",
    "cg", "fullnet", "resources assets", "plugin", "plugins",
})
SKIP_KEYS = frozenset(
    re.sub(r"[^\w]", "", value.casefold()) for value in SKIP_TERMS
)
ENGINE_SUFFIX = re.compile(
    r"(?i)(?:[_\s-]+(?:data|data[0-9]*|win64[-_ ]?shipping"
    r"|windowsnoeditor|standalonewindows64|windows64))+$"
)
BUILD_SUFFIX = re.compile(
    r"(?i)[-_. ]+(?:v)?\d+(?:[._]\d+){1,5}"
    r"(?:[-_. ]+(?:pc|windows|win64|x64|64bit))?$"
)
CG_RESOURCE = re.compile(r"(?i)^(?:cg|gallery|assets?)\s+\w{2,30}$")


def _useful_title(value: str) -> str:
    title = cleaned_search_title(value).strip()
    title = ENGINE_SUFFIX.sub("", title).strip()
    title = BUILD_SUFFIX.sub("", title).strip()
    key = re.sub(r"[^\w]", "", title.casefold())
    if (len(title) < 3 or len(title) > 140
            or not any(c.isalpha() for c in title)
            or key in SKIP_KEYS or CG_RESOURCE.fullmatch(title)
            or title.casefold().startswith(("system.", "unity.", "mono."))):
        return ""
    return title


def build_search_plan(
    archive_name: str,
    inspection: ArchiveInspection | None,
    metadata: MetadataInspection | None,
    *,
    max_queries: int = 6,
) -> tuple[SearchHint, ...]:
    """파일명과 내부 증거를 수집한 후에만 요청 후보를 정렬한다.

    작품 번호는 항상 가장 우선한다. 검색 상한 때문에 정제된 *파일명*
    및 *강한 내부 게임명*이 공통 실행기/폴더명에 밀리지 않도록 한다.
    """
    hints = extract_hints(archive_name)
    candidates: dict[str, tuple[int, SearchHint, int]] = {}
    insertion = 0

    def append(priority: int, stage: int, basis: str, query: str,
               *, title: bool = False) -> None:
        nonlocal insertion
        value = _useful_title(query) if title else query.strip()
        key = normalized_title(value) or value.casefold()
        if not value:
            return
        item = SearchHint(stage, basis, value)
        old = candidates.get(key)
        if old is None:
            candidates[key] = (priority, item, insertion)
            insertion += 1
        elif priority > old[0]:
            # 같은 검색어라도 더 신뢰할 만한 출처가 나타나면 출처를 갱신.
            candidates[key] = (priority, item, old[2])

    for code in (metadata.product_codes if metadata is not None else ()):
        append(1050, 3, "internal_metadata_code", code)
    for code in hints.dlsite_codes:
        append(1000, 1, "archive_filename_code", code)
    for code in (inspection.product_codes if inspection is not None else ()):
        append(950, 2, "internal_product_code", code)
    for steam_id in (metadata.steam_app_ids if metadata is not None else ()):
        append(925, 3, "internal_metadata_steam_id", f"Steam App ID: {steam_id}")
    for steam_id in hints.steam_app_ids:
        append(900, 1, "archive_filename_steam_id", f"Steam App ID: {steam_id}")

    for title in (metadata.strong_titles if metadata is not None else ()):
        append(800, 3, "internal_metadata_title", title, title=True)
    append(780, 1, "archive_filename", archive_name, title=True)
    for title in hints.title_aliases:
        append(765, 1, "archive_filename_alias", title, title=True)
    for title in (metadata.title_candidates if metadata is not None else ()):
        append(680, 3, "internal_metadata_supporting_title", title, title=True)
    if inspection is not None:
        for title in inspection.title_candidates[:64]:
            append(540, 2, "internal_filename", title, title=True)

    ranked = sorted(candidates.values(), key=lambda row: (-row[0], row[2]))
    return tuple(item for _, item, _ in ranked[:max(1, min(max_queries, 12))])
