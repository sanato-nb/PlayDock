"""DLsite → Steam 식별번호 전용 확인기.

* DLsite 품번(RJ/VJ/BJ/EJ)이 있으면 공식 DLsite HTML부터 확인한다.
* 하나라도 DLsite 공식 이름을 확인하면 Steam보다 DLsite를 우선 선택한다.
* DLsite 공식 확인이 전부 실패하거나 품번이 없으면 명시된 Steam App ID를
  공개 Store 상품정보(JSON, 키 불필요) 우선·공식 HTML 폴백으로 확인한다.
* 둘 다 확인할 수 없으면 'excluded'로 분류한다(미등록·비게임 판정 아님).
* 이름 검색, Bing RSS, DDGS, 번역 및 압축파일 내용 읽기는 수행하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit
import re

from .detector import CODE_PATTERN, Product, product_page_candidate
from .no_api_html import fetch_dlsite_html, fetch_steam_html
from .steam_client import STEAM_ID, SteamProduct, fetch_steam_product

SUFFIXES = (".zip", ".7z", ".rar")
MAX_BATCH = 1000
MAX_CODES_PER_ITEM = 12

# Steam ID는 명시된 경우에만 추출. 일반 버전·빌드번호는 ID로 오인하지 않는다.
# Steam 1091500 / SteamAppID=1091500 / Steam ID 1091500 / AppID: 1091500
from models.game_codes import STEAM_MARKED


@dataclass(frozen=True)
class InputItem:
    label: str
    origin: str  # archive / manual


@dataclass(frozen=True)
class Work:
    code: str
    title: str = ""
    category: str = ""
    url: str = ""
    status: str = "unavailable"  # verified / unavailable
    store: str = "dlsite"  # dlsite / steam


@dataclass(frozen=True)
class Result:
    query: str
    input_origin: str
    status: str  # confirmed / partial / excluded
    works: tuple[Work, ...] = ()
    warnings: tuple[str, ...] = ()
    selected_store: str = ""  # dlsite / steam / ""
    attempted_stores: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def file_name(value: str) -> str:
    """입력된 경로에서는 이름만 보존. 로컬 경로는 웹으로 보내지 않음."""
    return re.split(r"[/\\]", str(value or ""))[-1].strip()


def archive_name(value: str) -> str:
    name = file_name(value)
    return name if any(name.casefold().endswith(s) and len(name) > len(s)
                       for s in SUFFIXES) else ""


def selected_archives(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(name for path in paths if (name := archive_name(path)))


def folder_archives(directory: str) -> tuple[str, ...]:
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
    """DLsite 품번을 파일명에서 순서대로 추출하고 중복 제거."""
    return tuple(dict.fromkeys(m.group(1).upper()
                               for m in CODE_PATTERN.finditer(file_name(value))))


def steam_ids_in(value: str, *, manual: bool = False) -> tuple[str, ...]:
    """명시적인 Steam App ID만 추출. 직접 입력한 순수 숫자는 허용."""
    name = file_name(value)
    ids = [m.group(1) for m in STEAM_MARKED.finditer(name)
           if STEAM_ID.fullmatch(m.group(1))]
    if manual and STEAM_ID.fullmatch(name):
        ids.insert(0, name)
    return tuple(dict.fromkeys(ids))


def _verified_dlsite(code: str, product: Product | None) -> Work:
    if (product is not None and product.code.upper() == code and
            product.title.strip() and product_page_candidate(product.url) is not None and
            product_page_candidate(product.url)[0] == code):
        return Work(code, product.title, product.category, product.url, "verified", "dlsite")
    return Work(code, store="dlsite")


def _verified_steam(appid: str, product: SteamProduct | None) -> Work:
    if product is None or product.app_id != appid or not product.title.strip():
        return Work(appid, store="steam")
    parts = urlsplit(product.url)
    if not (parts.scheme == "https" and
            parts.hostname == "store.steampowered.com" and
            parts.username is None and parts.password is None and
            re.fullmatch(r"/app/" + re.escape(appid) + r"(?:/[^/]*)?/?", parts.path)):
        return Work(appid, store="steam")
    return Work(appid, product.title, product.item_type, product.url, "verified", "steam")


def fetch_steam_public(appid: str, *,
                       api_fetcher: Callable[[str], SteamProduct | None] = fetch_steam_product,
                       html_fetcher: Callable[[str], SteamProduct | None] = fetch_steam_html
                       ) -> SteamProduct | None:
    """API 키가 없는 Steam 공개 Store appdetails 우선, 공식 HTML로 대체.

    Steam 스토어의 일반 HTML은 GitHub Windows 환경에서 작품명을 제공하지 않을
    수 있으므로 공개 Store JSON을 먼저 시도한다. 계정/토큰/키는 사용하지 않는다.
    """
    try:
        product = api_fetcher(appid)
        if product is not None:
            return product
    except Exception:
        # Store 공개 endpoint 차단·HTTP 429 때 HTML 직접 조회로 폴백.
        pass
    return html_fetcher(appid)


def check(item: InputItem, *,
          fetcher: Callable[[str], Product | None] = fetch_dlsite_html,
          steam_fetcher: Callable[[str], SteamProduct | None] = fetch_steam_public,
          cache: dict[str, Work] | None = None) -> Result:
    """작품 식별번호만으로 공식 상품명을 조회. 실패 시 다른 사이트로 순차 폴백."""
    dl_codes = codes_in(item.label)
    steam_ids = steam_ids_in(item.label, manual=(item.origin == "manual"))
    attempted: list[str] = []
    warnings: list[str] = []
    checked: list[Work] = []
    selected = ""

    if len(dl_codes) > MAX_CODES_PER_ITEM:
        warnings.append(f"DLsite 품번 {len(dl_codes)}개 중 앞의 {MAX_CODES_PER_ITEM}개만 확인.")
    if len(steam_ids) > MAX_CODES_PER_ITEM:
        warnings.append(f"Steam App ID {len(steam_ids)}개 중 앞의 {MAX_CODES_PER_ITEM}개만 확인.")

    if dl_codes:
        attempted.append("dlsite")
        for code in dl_codes[:MAX_CODES_PER_ITEM]:
            if cache is not None and code in cache:
                row = cache[code]
            else:
                try:
                    row = _verified_dlsite(code, fetcher(code))
                except Exception as exc:
                    warnings.append(f"DLsite {code}: 공식 페이지 조회 실패 ({type(exc).__name__})")
                    row = Work(code, store="dlsite")
                if cache is not None:
                    cache[code] = row
            checked.append(row)
        if any(row.status == "verified" for row in checked):
            selected = "dlsite"
        else:
            if steam_ids:
                warnings.append("DLsite 공식 작품명 확인 실패 · Steam App ID로 이어서 조회합니다.")
            else:
                warnings.append("DLsite 공식 작품명 확인 실패 · Steam App ID가 없어 Steam 조회는 생략했습니다.")

    # DLsite 품번이 없어도 Steam 식별번호가 있으면 조회.
    # DLsite와 Steam 둘 다 있을 때 DLsite가 성공하면 Steam 접속은 하지 않는다.
    if not selected and steam_ids:
        attempted.append("steam")
        steam_rows: list[Work] = []
        for appid in steam_ids[:MAX_CODES_PER_ITEM]:
            cache_key = "STEAM:" + appid
            if cache is not None and cache_key in cache:
                row = cache[cache_key]
            else:
                try:
                    row = _verified_steam(appid, steam_fetcher(appid))
                except Exception as exc:
                    warnings.append(f"Steam {appid}: 공식 페이지 조회 실패 ({type(exc).__name__})")
                    row = Work(appid, store="steam")
                if cache is not None:
                    cache[cache_key] = row
            checked.append(row)
            steam_rows.append(row)
        if any(row.status == "verified" for row in steam_rows):
            selected = "steam"

    if not selected:
        if not dl_codes and not steam_ids:
            warnings.append("DLsite 품번과 명시적인 Steam App ID가 없어 제외했습니다.")
        elif attempted == ["dlsite"]:
            warnings.append("DLsite 공식 조회 실패로 제외했습니다. "
                            "Steam App ID는 없어서 조회하지 않았습니다. 미등록 판정은 아닙니다.")
        elif attempted == ["steam"]:
            warnings.append("Steam 공식 조회 실패로 제외했습니다. "
                            "DLsite 품번이 없어서 조회하지 않았습니다. 미등록 판정은 아닙니다.")
        else:
            warnings.append("DLsite와 Steam 공식 조회가 모두 실패해 제외했습니다. "
                            "접속 제한이나 조회 장애일 수 있으며 미등록 판정은 아닙니다.")
        return Result(item.label, item.origin, "excluded", tuple(checked),
                      tuple(warnings), "", tuple(attempted))

    active = [row for row in checked if row.store == selected]
    success = sum(row.status == "verified" for row in active)
    status = "confirmed" if success == len(active) else "partial"
    if status == "partial":
        warnings.append("선택된 사이트의 일부 식별번호는 공식 이름을 확인하지 못했습니다.")
    if selected == "steam" and dl_codes:
        warnings.append("DLsite 공식 확인 실패 후 Steam 확인 결과를 사용했습니다.")
    if selected == "dlsite" and steam_ids:
        warnings.append("DLsite 우선 확인에 성공하여 Steam 조회는 생략했습니다.")
    return Result(item.label, item.origin, status, tuple(checked),
                  tuple(warnings), selected, tuple(attempted))
