"""Steam Store 공개 상품 JSON 직접 조회 (독립 검색기 전용).

Steam 비공식 Store endpoint 사용. 계정/키 필요 없음, 단일 appid만 조회.
파싱 결과에서 요청 ID와 응답 ID가 다르면 즉시 거부한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import re


STEAM_ID = re.compile(r"[1-9]\d{2,9}$")
MAX_RESPONSE = 1_500_000


@dataclass(frozen=True)
class SteamProduct:
    app_id: str
    title: str
    item_type: str
    url: str
    developer: str = ""
    publisher: str = ""
    release_date: str = ""


class SteamLookupUnavailable(RuntimeError):
    pass


def parse_steam_appdetails(data, app_id: str) -> SteamProduct | None:
    if not STEAM_ID.fullmatch(str(app_id)):
        raise ValueError("Steam App ID는 숫자 3~10자리여야 합니다.")
    if not isinstance(data, dict):
        return None
    row = data.get(str(app_id))
    if not isinstance(row, dict) or row.get("success") is not True:
        return None
    body = row.get("data")
    if not isinstance(body, dict):
        return None
    actual_id = body.get("steam_appid")
    if actual_id is not None and str(actual_id) != str(app_id):
        return None
    title = body.get("name")
    kind = body.get("type")
    if not isinstance(title, str) or len(title.strip()) < 2 or len(title) > 240:
        return None
    if "<" in title or ">" in title or not isinstance(kind, str):
        return None
    developers = body.get("developers")
    publishers = body.get("publishers")
    release = body.get("release_date")
    def first_string(items):
        return items[0][:120] if isinstance(items, list) and items and isinstance(items[0], str) else ""
    date = release.get("date", "") if isinstance(release, dict) else ""
    return SteamProduct(
        str(app_id), title.strip(), kind.lower().strip()[:32],
        f"https://store.steampowered.com/app/{app_id}/",
        first_string(developers), first_string(publishers),
        str(date)[:80] if isinstance(date, str) else "",
    )


def fetch_steam_product(app_id: str, *, opener=urlopen, timeout: float = 8.0) -> SteamProduct | None:
    if not STEAM_ID.fullmatch(str(app_id)):
        raise ValueError("Steam App ID 형식이 잘못됐습니다.")
    url = "https://store.steampowered.com/api/appdetails?" + urlencode({
        "appids": app_id, "cc": "US", "l": "english",
    })
    req = Request(url, headers={
        "User-Agent": "PlayDock-Identity-Experiment/0.2",
        "Accept": "application/json",
    })
    try:
        with opener(req, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise SteamLookupUnavailable(f"Steam HTTP {response.status}")
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise SteamLookupUnavailable("Steam 응답 크기 제한 초과")
        payload = json.loads(raw.decode("utf-8-sig"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError,
            UnicodeError, TypeError) as exc:
        raise SteamLookupUnavailable(f"Steam 조회 실패: {type(exc).__name__}") from exc
    return parse_steam_appdetails(payload, app_id)
