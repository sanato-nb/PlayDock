"""압축파일 이름과 압축 내부 근거를 모두 모은 뒤 통합 검색어를 선정하는 계획기.

검색 전 파일명·실행파일·패키지·엔진 설정·작품 ID를 함께 수집한다.
공통 런타임 파일명, 번역 플러그인 및 일반 폴더명은 인터넷 검색 금지.
코드→명시적 게임명→정제된 압축명→게임 EXE 순으로 우선순위를 정한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .archive_inspector import ArchiveInspection
from .detector import normalized_title
from .identity_hints import extract_hints
from .internal_metadata import MetadataInspection
from .search_terms import cleaned_search_title


@dataclass(frozen=True)
class SearchHint:
    stage: int  # 후보 출처: 1=압축파일명, 2=내부 목록, 3=내부 설정
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
})


def _useful_title(value: str) -> str:
    title = cleaned_search_title(value).strip()
    key = title.casefold().strip()
    if (len(title) < 3 or len(title) > 140
            or key in SKIP_TERMS or key.replace("_", " ") in SKIP_TERMS
            or not any(c.isalpha() for c in title)):
        return ""
    return title


def build_search_plan(
    archive_name: str,
    inspection: ArchiveInspection | None,
    metadata: MetadataInspection | None,
    *,
    max_queries: int = 6,
) -> tuple[SearchHint, ...]:
    """네트워크를 사용하지 않는 결정적 검색 계획.

    동일 작품 코드가 파일명과 내부 폴더에서 반복될 때 중복 조회하지 않는다.
    단, 서로 *다른* 작품 코드는 상충 가능성이 있어 모두 조회한다.
    """
    hints = extract_hints(archive_name)
    plan: list[SearchHint] = []
    seen: set[str] = set()

    def append(stage: int, basis: str, query: str, *, title: bool = False) -> None:
        if len(plan) >= max_queries:
            return
        value = (_useful_title(query) if title else query.strip())
        key = normalized_title(value) or value.casefold()
        if not value or key in seen:
            return
        seen.add(key)
        plan.append(SearchHint(stage, basis, value))

    # 높은 식별력을 가진 작품 코드부터. 파일/폴더에 반복된 같은 코드는 1회 조회.
    for code in (metadata.product_codes if metadata is not None else ()):
        append(3, "internal_metadata_code", code)
    for code in hints.dlsite_codes:
        append(1, "archive_filename_code", code)
    for code in (inspection.product_codes if inspection is not None else ()):
        append(2, "internal_product_code", code)

    # Steam은 같은 플랫폼 ID를 공식 API로 조회할 수 있는 명시적 태그 사용.
    for sid in (metadata.steam_app_ids if metadata is not None else ()):
        append(3, "internal_metadata_steam_id", f"Steam App ID: {sid}")
    for sid in hints.steam_app_ids:
        append(1, "archive_filename_steam_id", f"Steam App ID: {sid}")

    # 엔진 설정 제목과 파일명 제목 모두 같은 검색 계획에 포함한다.
    # 'ntr game'처럼 기본 프로젝트명인 항목은 위의 _useful_title에서 제외.
    for title in (metadata.strong_titles if metadata is not None else ()):
        append(3, "internal_metadata_title", title, title=True)
    append(1, "archive_filename", archive_name, title=True)
    for title in hints.title_aliases:
        append(1, "archive_filename_alias", title, title=True)

    # exe/루트 폴더에서 나온 게임명은 마지막 수단. 플러그인 공통 이름 제외.
    if inspection is not None:
        for title in inspection.title_candidates[:12]:
            append(2, "internal_filename", title, title=True)
    if metadata is not None:
        for title in metadata.title_candidates:
            append(3, "internal_metadata_supporting_title", title, title=True)
    return tuple(plan)
