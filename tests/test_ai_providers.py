from refactor_test_support import launcher_source, editor_source
"""Offline integration tests; no external AI service calls or real keys required."""
from pathlib import Path
_ui_main = launcher_source()
_ui_editor = editor_source()


import pytest

import ai_providers as ai
import artwork
from core import Library


def test_provider_catalog_and_legacy_image_settings_metadata():
    assert set(ai.PROVIDERS) == {'openai', 'gemini', 'anthropic', 'openrouter', 'ollama'}
    assert ai.PROVIDERS['openai']['image'] and ai.PROVIDERS['gemini']['image']
    assert ai.PROVIDERS['openrouter']['image']
    assert not ai.PROVIDERS['anthropic']['image']
    assert not ai.PROVIDERS['ollama']['image']


def test_previous_installation_stays_openai_and_switch_survives_reload(tmp_path):
    lib = Library(store=tmp_path / 'store')
    assert ai.current_provider(lib) == 'openai'
    assert ai.current_models(lib) == ('gpt-4.1-mini', 'gpt-image-1-mini')
    ai.save_provider_settings(lib, 'gemini', 'gemini-2.5-flash', 'gemini-2.5-flash-image')
    newer = Library(store=tmp_path / 'store')
    assert ai.current_provider(newer) == 'gemini'
    assert ai.current_models(newer) == ('gemini-3.8-flash', 'gemini-2.5-flash-image')
    ai.save_provider_settings(newer, 'ollama', 'qwen2.5:7b', '')
    another = Library(store=tmp_path / 'store')
    assert ai.current_provider(another) == 'ollama'
    assert ai.current_models(another)[0] == 'qwen2.5:7b'
    ai.save_provider_settings(another, 'gemini', 'gemini-2.5-flash', 'gemini-2.5-flash-image')
    assert ai.current_models(another)[1] == 'gemini-2.5-flash-image'


def test_api_key_never_saved_to_settings(monkeypatch, tmp_path):
    lib = Library(store=tmp_path / 'store')
    fake = {}
    monkeypatch.setattr(ai, 'get_secret', lambda provider: fake.get(provider, ''))
    monkeypatch.setattr(ai, 'set_secret', lambda provider, value: fake.__setitem__(provider, value))
    ai.set_secret('gemini', 'SECRET_NOT_FOR_DISK')
    ai.save_provider_settings(lib, 'gemini', 'gemini-2.5-flash', 'gemini-2.5-flash-image')
    assert 'SECRET_NOT_FOR_DISK' not in lib.config_path.read_text(encoding='utf-8')
    assert ai.get_secret('gemini') == 'SECRET_NOT_FOR_DISK'


def test_unknown_service_fails_closed():
    with pytest.raises(ValueError):
        ai.get_secret('steamgrid')
    with pytest.raises(ValueError):
        ai.save_provider_settings(object(), 'bad-service', 'model', '')


@pytest.mark.parametrize('provider,response,url_piece,auth_header', [
    ('openai', {'output': [{'content': [{'type': 'output_text', 'text': '{"title":"New Game","confidence":0.95}'}]}]}, '/v1/responses', 'Authorization'),
    ('gemini', {'candidates': [{'content': {'parts': [{'text': '{"title":"New Game","confidence":0.95}'}]}}]}, ':generateContent', 'x-goog-api-key'),
    ('anthropic', {'content': [{'type': 'text', 'text': '{"title":"New Game","confidence":0.95}'}]}, '/v1/messages', 'x-api-key'),
    ('openrouter', {'choices': [{'message': {'content': '{"title":"New Game","confidence":0.95}'}}]}, '/chat/completions', 'Authorization'),
    ('ollama', {'response': '{"title":"New Game","confidence":0.95}'}, '/api/generate', None),
])
def test_title_requests_all_providers(monkeypatch, provider, response, url_piece, auth_header):
    seen = []
    def fake_http(url, body, headers, **kwargs):
        seen.append((url, body, headers))
        return response
    monkeypatch.setattr(ai, 'http_json', fake_http)
    got = ai.recommend_title('Old Game', provider, ai.PROVIDERS[provider]['text_model'], 'fake-key')
    assert got == 'New Game'
    url, body, headers = seen[0]
    assert url_piece in url
    if auth_header:
        assert auth_header in headers
    else:
        assert url.startswith('http://127.0.0.1:11434/')
        assert 'Authorization' not in headers
        assert body['stream'] is False


def test_unconfident_title_kept(monkeypatch):
    monkeypatch.setattr(ai, '_text_response', lambda *args: '{"title":"Random","confidence":0.2}')
    assert ai.recommend_title('RJ123456', 'gemini', 'model', 'key') == 'RJ123456'


def test_http_errors_do_not_include_credentials(monkeypatch):
    # This is a source-level guard: keys only flow in the Authorization headers.
    source = (ai.__file__)
    from pathlib import Path
    text = Path(source).read_text(encoding='utf-8')
    assert 'Authorization' in text
    assert 'api_key' not in text.split('def http_json(', 1)[1].split('def _extract_json(', 1)[0]


def test_editor_retains_existing_provider_settings_without_main_settings_window():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'app.py').read_text(encoding='utf-8') + _ui_main
    title_editor = (root / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert 'class SettingsDialog(' not in app
    assert 'current_provider(self.library)' in title_editor
    assert 'ai_game_title(' in title_editor
    assert 'get_secret("openai")' not in app


def test_image_generation_entrypoints_and_endpoints_are_removed():
    assert not hasattr(ai, 'image_bytes')
    assert not hasattr(artwork, 'generate_ai_art')
    assert not hasattr(artwork, 'IMAGE_URL')
    for module in (ai, artwork):
        source = Path(module.__file__).read_text(encoding='utf-8')
        assert '/v1/images/generations' not in source
        assert 'openrouter.ai/api/v1/images' not in source
        assert 'responseModalities' not in source
