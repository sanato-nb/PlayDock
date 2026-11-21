"""로컬 게임 압축파일 선택 입력 처리.

압축 파일의 *이름*만 이용한다. 파일 내용/메타데이터/아카이브 목록을
읽거나 열지 않으며 네트워크 검색으로 로컬 경로를 전달하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re

from .detector import CODE_PATTERN
from .reverse_lookup import Lookup, lookup_code, lookup_title

ARCHIVE_SUFFIXES = (".zip", ".7z", ".rar")
MAX_BATCH = 1000


@dataclass(frozen=True)
class SearchInput:
    label: str
    origin: str  # manual / archive
    # Archive name or explicitly typed input, never absolute local paths.
    value: str


def archive_name(value: str) -> str:
    """윈도우·리눅스 경로에서 파일명만 추출. 파일 자체는 읽지 않는다."""
    name = re.split(r"[/\\]", str(value or ""))[-1].strip()
    if not name.casefold().endswith(ARCHIVE_SUFFIXES):
        return ""
    if any(name.casefold() == s for s in ARCHIVE_SUFFIXES):
        return ""
    return name


def selected_archives(paths) -> tuple[str, ...]:
    """파일 선택창 반환값에서 확장자 검증하고 이름만 남긴다."""
    return tuple(name for value in paths if (name := archive_name(value)))


def folder_archive_names(directory: str) -> tuple[str, ...]:
    """폴더 바로 아래의 파일명만 나열. 내부 압축파일은 열지 않음."""
    folder = Path(directory)
    if not folder.is_dir():
        return ()
    return tuple(sorted(
        entry.name for entry in folder.iterdir()
        if entry.is_file() and archive_name(entry.name)
    ))


def extract_one_code(archive: str) -> tuple[str, str]:
    """단일 품번만 자동 선택. 복수/누락은 임의 결정하지 않는다."""
    found = tuple(dict.fromkeys(m.group(1).upper() for m in CODE_PATTERN.finditer(archive)))
    if not found:
        return "", "파일명에 DLsite 품번(RJ/VJ/BJ/EJ)이 없습니다."
    if len(found) != 1:
        return "", "파일명에서 여러 품번이 발견되어 자동 선택하지 않았습니다: " + ", ".join(found)
    return found[0], ""


def batch_inputs(manual_text: str, archive_names, *, limit: int = MAX_BATCH) -> tuple[SearchInput, ...]:
    """직접 입력과 파일 선택을 함께 검색. 결과는 모두 원래 이름과 연결."""
    manual = [line.strip() for line in str(manual_text).splitlines() if line.strip()]
    chosen = selected_archives(archive_names)
    result = [SearchInput(value, "manual", value) for value in manual]
    result.extend(SearchInput(name, "archive", name) for name in chosen)
    if len(result) > limit:
        raise ValueError(f"한 번에 최대 {limit}개까지 검사할 수 있습니다.")
    return tuple(result)


def run_lookup(
    item: SearchInput, mode: str, *,
    title_lookup=lookup_title, code_lookup=lookup_code,
) -> Lookup:
    """선택한 원본 파일명과 검색 결과를 연결해 돌려준다."""
    if mode not in ("title_to_code", "code_to_title"):
        raise ValueError("잘못된 검색 방향")
    if mode == "title_to_code":
        result = title_lookup(item.value)
    else:
        if item.origin == "archive":
            code, warning = extract_one_code(item.value)
            if warning:
                return Lookup("code_to_title", item.label, "invalid", warnings=(warning,))
        else:
            code = item.value
        result = code_lookup(code)
    # 공식 결과는 작업용 검색어가 아니라 사용자가 선택한 파일명에 연결.
    return replace(result, query=item.label)
