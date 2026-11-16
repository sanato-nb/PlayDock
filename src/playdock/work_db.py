"""Backward-compatible work catalogue API; implementation is split by responsibility.

No network call happens when creating, reading, or updating the SQLite DB.
"""
from integrations.dlsite_client import (
    CATEGORIES, LOCALES, MAX_RESPONSE, MAX_TAGS, MAX_IMAGES,
    _timestamp, _safe_text, _safe_dlsite_url, _image_urls, _extract_payload,
    _parse_tags, fetch_dlsite_work,
)
from database.work_repository import WorkDatabase, SCHEMA_VERSION
