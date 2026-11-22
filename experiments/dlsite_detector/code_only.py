"""PlayDock DLsite 품번 확인기: 파일명/입력문에 코드가 있을 때만 공식 HTML 조회.

DLsite 제목 검색, Bing RSS, DDGS, 원제 추론, 작품명 점수 비교를 전혀 호출하지 않는다.
압축파일 본문을 열지 않으며 파일 경로를 인터넷에 전달하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Iterable
import re

from .detector import CODE_PATTERN, EXACT_CODE, Product
from .no_api_html import fetch_dlsite_html

SUFFIXES = (".zip", ".7z", ".rar")
MAX_BATCH = 1000
MAX_CODES_PER_ITEM = 12


@dataclass(frozen=True)
class InputItem:
    label: str  # 사용자가 보는 파일명/직접 입력 문자열(절대 경로는 잘라냄)
    origin: str  # archive / manual


@dataclass(frozen=True)
class Work:
    code: str
    title: str = ""
    category: str = ""
    url: str = ""
    status: str = "unavailable"  # verified / unavailable


@dataclass(frozen=True)
class Result:
    query: str
    input_origin: str
    status: str  # confirmed / partial / unavailable / no_code
    works: tuple[Work, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def file_name(value: str) -> str:
    """윈도우/Unix 입력 경로에서 파일명만 추출해 외부 노출 방지."""
    return re.split(r"[/\\]", str(value or ""))[-1].strip()


def archive_name(value: str) -> str:
    name = file_name(value)
    return name if len(name) > 4 and name.casefold().endswith(SUFFIXES) else ""


def selected_archives(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(name for path in paths if (name := archive_name(path)))


def folder_archives(directory: str) -> tuple[str, ...]:
    """선택한 폴더 직하위 압축파일명만 읽으며 내부 파일 내용은 미검사."""
    folder = Path(directory)
    if not folder.is_dir():
        return ()
    return tuple(sorted(
        p.name for p in folder.iterdir() if p.is_file() and archive_name(p.name)
    ))


def inputs(text: str, files: Iterable[str], limit: int = MAX_BATCH) -> tuple[InputItem, ...]:
    typed = [file_name(s.strip()) for s in str(text or "").splitlines() if s.strip()]
    chosen = selected_archives(files)
    if len(typed) + len(chosen) > limit:
        raise ValueError(f"한 번에 최대 {limit}개 항목까지 검사할 수 있습니다.")
    return (tuple(InputItem(s, "manual") for s in typed) +
            tuple(InputItem(s, "archive") for s in chosen))


def codes_in(value: str) -> tuple[str, ...]:
    """DLsite 품번만 추출. 다른 숫자·Steam ID·버전은 무시하고 복수 품번 지원."""
    return tuple(dict.fromkeys(m.group(1).upper()
                               for m in CODE_PATTERN.finditer(file_name(value))))


def check(item: InputItem, *,
          fetcher: Callable[[str], Product | None] = fetch_dlsite_html,
          cache: dict[str, Work] | None = None) -> Result:
    """공식 작품 페이지 1개(필요한 경우 매장 2개) 이외에는 네트워크 요청이 없다."""
    codes = codes_in(item.label)
    if not codes:
        return Result(item.label, item.origin, "no_code", warnings=(
            "파일명/입력값에 RJ·VJ·BJ·EJ 품번이 없어 인터넷 조회를 건너뛰었습니다.",))
    warnings = []
    if len(codes) > MAX_CODES_PER_ITEM:
        warnings.append(f"품번이 {len(codes)}개여서 첫 {MAX_CODES_PER_ITEM}개만 조회했습니다.")
    works = []
    for code in codes[:MAX_CODES_PER_ITEM]:
        if cache is not None and code in cache:
            works.append(cache[code])
            continue
        try:
            product = fetcher(code)
            if (product is not None and product.code.upper() == code and
                    product.title.strip() and
                    product.url.startswith("https://www.dlsite.com/")):
                result = Work(code=code, title=product.title,
                              category=product.category, url=product.url,
                              status="verified")
            else:
                result = Work(code=code)
        except Exception as exc:
            warnings.append(f"{code}: 공식 페이지 조회 오류 ({type(exc).__name__})")
            result = Work(code=code)
        if cache is not None:
            cache[code] = result
        works.append(result)
    verified = sum(w.status == "verified" for w in works)
    status = ("confirmed" if verified == len(works) else
              "partial" if verified else "unavailable")
    if verified < len(works):
        warnings.append("일부 품번의 공식 작품명을 확인하지 못했습니다. 미등록을 뜻하지 않습니다.")
    return Result(item.label, item.origin, status, tuple(works), tuple(warnings))
