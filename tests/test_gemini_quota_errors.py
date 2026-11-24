from refactor_test_support import launcher_source, editor_source
"""Offline Gemini error handling tests: API keys never leave error dialogs."""
from pathlib import Path
_ui_main = launcher_source()


import io
import json
from urllib import error

import pytest

import ai_providers as ai


def _as_http_error(status, body, url='https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent'):
    return error.HTTPError(url, status, 'Too Many Requests', {'Retry-After': '12'}, io.BytesIO(json.dumps(body).encode('utf-8')))


def test_gemini_quota_zero_has_human_explanation(monkeypatch):
    problem = {'error': {'code': 429, 'status': 'RESOURCE_EXHAUSTED',
                         'message': 'Quota exceeded for metric generate_content_free_tier_requests limit: 0',
                         'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure',
                                      'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaValue': '0'}]}]}}
    def fake_urlopen(*args, **kwargs):
        raise _as_http_error(429, problem)
    monkeypatch.setattr(ai.request, 'urlopen', fake_urlopen)
    with pytest.raises(RuntimeError) as exc:
        ai.http_json('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent', {}, {'x-goog-api-key': 'TEST_SUPER_SECRET_123456789'})
    message = str(exc.value)
    assert 'Gemini API HTTP 429' in message
    assert '0' in message and '무료 등급' in message
    assert 'generate_content_free_tier_requests' in message
    assert 'https://aistudio.google.com/rate-limit' in message
    assert 'TEST_SUPER_SECRET' not in message


def test_gemini_recoverable_quota_retains_message(monkeypatch):
    problem = {'error': {'message': 'Rate limit of 2 RPM exceeded'}}
    def fake_urlopen(*args, **kwargs):
        raise _as_http_error(429, problem)
    monkeypatch.setattr(ai.request, 'urlopen', fake_urlopen)
    with pytest.raises(RuntimeError) as exc:
        ai.http_json('https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent', {}, {})
    message = str(exc.value)
    assert '2 RPM exceeded' in message
    assert '12초' in message
    assert '할당량' in message


def test_long_api_error_json_is_not_truncated_to_generic(monkeypatch):
    problem = {'error': {'message': 'quota exceeded, ' + 'a' * 2500,
                         'details': [{'violations': [{'quotaMetric': 'requests_per_day', 'quotaValue': '0'}]}]}}
    def fake_urlopen(*args, **kwargs):
        raise _as_http_error(429, problem)
    monkeypatch.setattr(ai.request, 'urlopen', fake_urlopen)
    with pytest.raises(RuntimeError) as exc:
        ai.http_json('https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent', {}, {})
    assert 'requests_per_day' in str(exc.value)
    assert '요청에 실패했습니다' not in str(exc.value)


def test_image_error_includes_model_name(monkeypatch):
    monkeypatch.setattr(ai, 'http_json', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('429 사용량 초과')))
    with pytest.raises(RuntimeError) as exc:
        ai.image_bytes('gemini', 'gemini-2.5-flash-image', 'hello', 'FAKEKEY', 'hero')
    assert 'gemini-2.5-flash-image' in str(exc.value)
    assert '429' in str(exc.value)
    assert 'FAKEKEY' not in str(exc.value)


def test_error_message_redacts_google_style_api_key():
    key='AIza' + 'L' * 26
    detail = ai._safe_api_error(403, json.dumps({'error': {'message': f'Problem with {key}'}}).encode('utf-8'), 'https://generativelanguage.googleapis.com')
    assert key not in detail
    assert 'API 키 숨김' in detail


def test_gemini_image_generation_not_exposed_in_main_program():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8') + _ui_main
    assert '게임 정보 수집' in source
    assert '인터넷 이미지 검색·편집' not in source
    assert 'gemini_limits_button' not in source
    assert 'fetch_art(' not in source
