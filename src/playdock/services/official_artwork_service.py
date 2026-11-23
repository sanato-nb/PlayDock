"""Official artwork for a VERIFIED DLsite/Steam work, not image-search results.

Read public store metadata only for an already verified (store, code, page_url).
Never use image generation or a guessed local filename for artwork.
All image requests are bounded, HTTPS and validated by online_artwork.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import json

from database.official_catalog import _valid_identity
from integrations.dlsite_client import fetch_dlsite_work, _safe_dlsite_url
from online_artwork import download_image, crop_png

MAX_STEAM_JSON = 1_500_000
_STEAM_CDN = {
    "cdn.akamai.steamstatic.com", "shared.akamai.steamstatic.com",
    "shared.fastly.steamstatic.com", "cdn.cloudflare.steamstatic.com",
    "cdn.steamstatic.com", "shared.steamstatic.com",
    "steamcdn-a.akamaihd.net",
}


@dataclass(frozen=True)
class OfficialImage:
    kind: str                 # hero / icon
    url: str
    data: bytes               # actual original image, fetched before checkbox enabled
    preview: bytes            # prepared PNG preview
    page_url: str


def trusted_image_url(store: str, code: str, url: str) -> bool:
    """Reject arbitrary/redirect-injected URLs and cross-work Steam artwork."""
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.username or parts.password or (
                parts.port not in (None, 443)) or not parts.hostname:
            return False
        host = parts.hostname.lower().rstrip(".")
        if store == "dlsite":
            return bool(_safe_dlsite_url(url))
        if store == "steam":
            if host not in _STEAM_CDN:
                return False
            components = parts.path.split("/")
            return "apps" in components and components[components.index("apps") + 1:
                                                      components.index("apps") + 2] == [code]
        return False
    except (ValueError, IndexError):
        return False


def _steam_api_art(app_id: str, *, opener=urlopen):
    """Get image URLs only from the public Steam Store appdetails for the same app."""
    url = "https://store.steampowered.com/api/appdetails?" + urlencode({
        "appids": app_id, "cc": "US", "l": "english",
    })
    req = Request(url, headers={
        "User-Agent": "PlayDock/0.8 (official artwork for one confirmed App ID)",
        "Accept": "application/json",
    })
    with opener(req, timeout=8) as response:
        raw = response.read(MAX_STEAM_JSON + 1)
    if len(raw) > MAX_STEAM_JSON:
        raise ValueError("Steam 이미지 메타데이터 크기 제한 초과")
    result = json.loads(raw.decode("utf-8-sig"))
    row = result.get(app_id) if isinstance(result, dict) else None
    if not isinstance(row, dict) or row.get("success") is not True:
        return {}
    body = row.get("data")
    if not isinstance(body, dict) or (body.get("steam_appid") is not None
                                       and str(body["steam_appid"]) != app_id):
        return {}
    header = body.get("header_image")
    icon = next((candidate for candidate in
                 (body.get("capsule_imagev5"), body.get("capsule_image"), header)
                 if isinstance(candidate, str)
                 and trusted_image_url("steam", app_id, candidate)), None)
    choices = {"hero": header, "icon": icon}
    return {kind: url for kind, url in choices.items()
            if isinstance(url, str) and trusted_image_url("steam", app_id, url)}


def official_image_urls(work, *, dlsite_fetch=fetch_dlsite_work,
                        steam_fetch=_steam_api_art) -> dict[str, str]:
    """Only the verified work may supply the official image-source candidates."""
    store, code, page = str(work.store), str(work.code), str(work.url)
    if work.status != "verified" or not _valid_identity(store, code, page):
        return {}
    if store == "steam":
        try:
            found = steam_fetch(code)
        except (OSError, ValueError, TimeoutError, TypeError):
            found = {}
        return {kind: url for kind, url in found.items()
                if kind in ("hero", "icon") and trusted_image_url(store, code, url)}
    if store == "dlsite":
        try:
            data = dlsite_fetch(code)
        except (OSError, ValueError, LookupError, TimeoutError, TypeError):
            return {}
        if str(data.get("code", "")).upper() != code.upper():
            return {}
        urls = {}
        images = data.get("images", [])
        if not isinstance(images, list):
            return {}
        # Banner: prefer an official sample; portrait cover is the fallback.
        for kind, source_types in (("hero", ("sample", "cover", "thumbnail")),
                                   ("icon", ("cover", "thumbnail", "sample"))):
            for typ in source_types:
                choice = next((row.get("url") for row in images
                               if isinstance(row, dict) and row.get("kind") == typ
                               and trusted_image_url(store, code, row.get("url", ""))), None)
                if choice:
                    urls[kind] = choice
                    break
        return urls
    return {}


def prepare_official_images(work, *, candidates=None, downloader=download_image,
                            preview_builder=crop_png) -> dict[str, OfficialImage]:
    """Download/validate both *before* showing checkboxes, off the GUI thread.

    A missing/broken image disables only that checkbox. No cache or disk writes.
    """
    urls = official_image_urls(work) if candidates is None else candidates
    offerings = {}
    downloaded = {}
    for kind in ("hero", "icon"):
        url = urls.get(kind)
        if not isinstance(url, str) or not trusted_image_url(work.store, work.code, url):
            continue
        try:
            if url not in downloaded:
                downloaded[url] = downloader(url)
            payload = downloaded[url]
            thumb = preview_builder(payload, kind, preview=True)
            offerings[kind] = OfficialImage(kind, url, payload, thumb, work.url)
        except (OSError, ValueError, TimeoutError, RuntimeError):
            continue
    return offerings


def apply_checked_images(library, game, work, offerings: dict,
                         selected: set[str]) -> list[str]:
    """Apply precisely the checked kinds and back up any existing destination.

    This must be invoked only AFTER the UI has obtained overwrite confirmation.
    Every unchecked destination, including a manual image, is untouched.
    """
    from online_artwork import Candidate
    from services.artwork_service import ArtworkActions
    if not selected.issubset({"hero", "icon"}):
        raise ValueError("지원하지 않는 이미지 종류입니다.")
    actions = ArtworkActions(library, game)
    applied = []
    for kind in ("hero", "icon"):
        if kind not in selected:
            continue
        offer = offerings.get(kind)
        if offer is None or not trusted_image_url(work.store, work.code, offer.url):
            raise ValueError("선택한 공식 이미지가 준비되어 있지 않습니다.")
        candidate = Candidate(
            f"{work.title} · {'배너' if kind == 'hero' else '아이콘'}",
            offer.url, offer.url, work.url, f"{work.store.upper()} 공식 페이지",
        )
        actions.apply_selection(offer.data, candidate, kind, 50, 50, 100)
        applied.append(kind)
    if applied:
        library.update_meta(game, artwork_source="공식 사이트 · 정체 판독 (사용자 선택)")
    return applied
