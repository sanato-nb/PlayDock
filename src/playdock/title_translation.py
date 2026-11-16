"""Optional text-only translation; user must review before saving.

This is *not* a product-code identity verification and never generates artwork.
"""
from __future__ import annotations

from product_titles import clean_title
from localized_titles import LANGUAGES, language_is_plausible


def translate_work_title(source_title: str, target_language: str, provider: str,
                         model: str, api_key: str, *, responder=None) -> str:
    if target_language not in LANGUAGES:
        raise ValueError('지원하지 않는 제목 언어입니다.')
    title = clean_title(source_title)
    if not title:
        raise ValueError('번역할 실제 작품 제목을 먼저 조회하거나 입력하세요.')
    from ai_providers import _text_response, _extract_json
    language = LANGUAGES[target_language][0]
    prompt = (
        'Translate the following existing video game title into ' + language + '. '
        'This is title translation, NOT title identification. Preserve proper names and meaning. '
        'Never invent game titles, work codes, versions, characters, developers, or store pages. '
        'If the original is a proper noun best left untranslated, keep it unchanged. '
        'Return ONLY JSON {"title":"translated title"}.\\n'
        'Published title: ' + repr(title)
    )
    if responder is None:
        raw = _text_response(provider, model, prompt, api_key)
    else:
        raw = responder(provider, model, prompt, api_key)
    try:
        translated = clean_title(_extract_json(raw).get('title'))
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise LookupError('제목 번역 결과를 해석할 수 없습니다.') from exc
    if not translated or not language_is_plausible(translated, target_language):
        raise LookupError('번역이 확인되지 않았습니다. 기존 제목을 유지합니다.')
    return translated
