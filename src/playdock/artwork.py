"""Local image cache and optional provider-based AI helpers. No Steam API."""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import zipfile

from PIL import Image, ImageOps, UnidentifiedImageError

from core import Game, Library
from ai_providers import (get_secret, set_secret, provider_details, recommend_title,
                          _extract_json as _decode_json)

Image.MAX_IMAGE_PIXELS = 90_000_000
OPENAI_URL = "https://api.openai.com/v1/responses"
SERVICE = "PlayDock"


def request_json(url: str, api_key: str, payload: dict, max_bytes: int = 2 * 1024**2) -> dict:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=raw, headers={
        "User-Agent": "PlayDock/0.2",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            body = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        # Do not expose the submitted token or any raw headers.
        try:
            data = json.loads(exc.read(4096).decode("utf-8", "replace"))
            detail = str(data.get("error", {}).get("message", ""))[:450]
        except Exception:
            detail = ""
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail or '요청이 실패했습니다.'}") from exc
    if len(body) > max_bytes:
        raise ValueError("API 응답 크기가 허용 범위를 넘었습니다.")
    return json.loads(body.decode("utf-8"))


def _openai_text(data: dict) -> str:
    return "".join(item.get("text", "") for output in data.get("output", [])
                   for item in output.get("content", []) if item.get("type") == "output_text")


def ai_game_title(raw: str, api_key: str, provider: str = "openai", model: str | None = None) -> str:
    """Conservatively clean filename into a game title; do not invent identities."""
    if provider != "openai" or model is not None:
        return recommend_title(raw, provider, model or provider_details(provider)["text_model"], api_key)
    payload = {
        "model": "gpt-4.1-mini", "max_output_tokens": 140,
        "input": [{"role": "user", "content": (
            "Recognize a game title from a local archive or folder filename. "
            "If identity is unclear or only an RJ code, preserve the input exactly. "
            'Return only JSON: {"title":string,"confidence":number}. '
            f"Filename: {raw!r}")}],
    }
    try:
        result = _decode_json(_openai_text(request_json(OPENAI_URL, api_key, payload)))
        title = str(result.get("title", "")).strip()
        if title and float(result.get("confidence", 0)) >= 0.8:
            return title[:150]
    except (ValueError, KeyError, TypeError):
        pass
    return raw


def save_image(source: Path | BytesIO, target: Path, kind: str) -> None:
    with Image.open(source) as im:
        im.load()
        if kind == "hero":
            final = ImageOps.fit(im.convert("RGB"), (1600, 520), method=Image.Resampling.LANCZOS,
                                 centering=(0.5, 0.48))
        else:
            final = ImageOps.fit(im.convert("RGBA"), (256, 256), method=Image.Resampling.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".writing.png")
        final.save(tmp, format="PNG", optimize=True)
        tmp.replace(target)


def _local_images(folder: Path) -> list[Path]:
    candidates = []
    keywords = ("hero", "header", "banner", "background", "cover", "capsule", "splash", "icon", "logo", "title")
    for base, dirs, files in os.walk(folder):
        depth = len(Path(base).relative_to(folder).parts)
        if depth >= 2:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d.casefold() not in {"data", "resources", "streamingassets", "assets", "_data", "cache", "www"}]
        for name in files:
            if Path(name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                continue
            if not any(word in name.casefold() for word in keywords):
                continue
            candidates.append(Path(base) / name)
            if len(candidates) >= 80:
                return candidates
    return candidates


def _find_artwork_library(library: Library, game: Game) -> list[Path]:
    """Look for explicitly supplied artwork in data/artwork_library/<game title>/.

    Avoid arbitrary Internet scraping and do not invent game identities.
    """
    from core import safe_folder_name
    root = library.store / 'artwork_library'
    if not root.is_dir():
        return []
    names = (safe_folder_name(library.title(game)), safe_folder_name(game.name))
    found = []
    for name in names:
        folder = root / name
        if folder.is_dir() and not folder.is_symlink():
            for filename in ('hero.png', 'hero.jpg', 'banner.jpg', 'header.jpg',
                             'icon.png', 'icon.jpg', 'cover.jpg', 'cover.png'):
                target = folder / filename
                if target.is_file() and not target.is_symlink():
                    found.append(target)
    return list(dict.fromkeys(found))


def _archive_artwork_candidates(game: Game) -> list[tuple[str, bytes]]:
    """Read only small, clearly named artwork from an unencrypted ZIP.

    No bulk archive extraction and no automatic fetch from the Internet.
    """
    if game.archive is None or game.archive.suffix.lower() != '.zip':
        return []
    results = []
    try:
        with zipfile.ZipFile(game.archive) as zf:
            for item in zf.infolist()[:2500]:
                name = Path(item.filename).name.casefold()
                if (item.is_dir() or item.file_size > 8 * 1024**2 or item.flag_bits & 1
                        or item.compress_type == 99 or len(results) >= 12):
                    continue
                stem = Path(name).stem
                if (Path(name).suffix not in ('.png', '.jpg', '.jpeg', '.webp')
                        or not any(word in stem for word in ('banner', 'header', 'cover', 'icon', 'hero'))):
                    continue
                blob = zf.read(item)
                if len(blob) <= 8 * 1024**2:
                    results.append((name, blob))
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError):
        pass
    return results


def discover_local(library: Library, game: Game) -> list[str]:
    """Choose recognizable local art from a game folder, library or ZIP.

    Cached user art always wins. No Steam, scraping, GPT or paid API calls.
    """
    dest = library.art_dir(game)
    if (dest / 'hero.png').exists() and (dest / 'icon.png').exists():
        return []
    candidates = _find_artwork_library(library, game)
    if game.folder and game.folder.is_dir():
        candidates.extend(_local_images(game.folder))
    embedded = _archive_artwork_candidates(game)
    found: list[str] = []
    for kind in ('hero', 'icon'):
        target = dest / f'{kind}.png'
        if target.exists():
            continue
        scored = []
        for file in candidates:
            try:
                if file.is_symlink() or file.stat().st_size > 14 * 1024**2:
                    continue
                with Image.open(file) as im:
                    width, height = im.size
                aspect = width / max(1, height)
                name = file.stem.casefold()
                if kind == 'hero' and (aspect < 1.45 or width < 600):
                    continue
                if kind == 'icon' and (aspect < 0.7 or aspect > 1.5 or width < 64):
                    continue
                score = width * height / 1_000_000
                if kind == 'hero' and any(w in name for w in ('hero','header','banner')):
                    score += 25
                if kind == 'icon' and any(w in name for w in ('icon','cover')):
                    score += 25
                if 'artwork_library' in file.parts:
                    score += 50  # Explicitly supplied images outrank arbitrary game assets.
                scored.append((score, file, None))
            except (OSError, UnidentifiedImageError, ValueError):
                continue
        for name, blob in embedded:
            try:
                with Image.open(BytesIO(blob)) as im:
                    width, height = im.size
                aspect = width / max(1, height)
                if kind == 'hero' and (aspect < 1.45 or width < 600):
                    continue
                if kind == 'icon' and (aspect < 0.7 or aspect > 1.5 or width < 64):
                    continue
                score = width * height / 1_000_000 + 5
                if kind == 'hero' and any(w in name for w in ('banner','header','hero')):
                    score += 20
                if kind == 'icon' and any(w in name for w in ('cover','icon')):
                    score += 20
                scored.append((score, None, blob))
            except (OSError, UnidentifiedImageError, ValueError):
                continue
        if scored:
            try:
                _, file, blob = max(scored, key=lambda row: row[0])
                save_image(file if file is not None else BytesIO(blob), target, kind)
                found.append(kind)
            except (OSError, UnidentifiedImageError, ValueError):
                pass
    return found

