"""Optional game product IDs, independent of archive filenames and title edits.

An explicit empty product_code means this game has *no* registered work number.
Display overlays are derived: they are never written to the archive filename.
"""
from __future__ import annotations
import re

PRODUCT_ID = re.compile(r'(?<![A-Z0-9])((?:RJ|VJ|BJ|EJ)\d{6,8})(?![A-Z0-9])', re.I)


def normalize_code(value: str | None) -> str:
    """Return a clean RJ/VJ/BJ/EJ code or raise for invalid nonblank input."""
    code = (value or '').strip().upper()
    if code and not PRODUCT_ID.fullmatch(code):
        raise ValueError('작품 코드는 RJ/VJ/BJ/EJ + 숫자 6~8자리로 입력하세요.')
    return code


def find_code(*parts: str | None) -> str:
    for part in parts:
        match = PRODUCT_ID.search(part or '')
        if match:
            return match.group(1).upper()
    return ''


def effective_product_code(metadata: dict, *original_titles: str | None) -> str:
    """User choice wins, including explicit empty (no product code)."""
    if 'product_code' in metadata:
        try:
            return normalize_code(metadata.get('product_code'))
        except (ValueError, TypeError, AttributeError):
            return ''
    return find_code(metadata.get('title_product_code'), metadata.get('artwork_identity_code'),
                     metadata.get('title'), *original_titles)


def title_with_code(title: str, code: str | None) -> str:
    """Append when useful, without duplicating or mixing work numbers."""
    cleaned = (title or '').strip()
    code = normalize_code(code)
    if not code or not cleaned or find_code(cleaned):
        return cleaned
    return f'{cleaned} [{code}]'
