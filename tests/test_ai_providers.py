from refactor_test_support import launcher_source, editor_source
"""Offline integration tests; no external AI service calls or real keys required."""
from pathlib import Path
_ui_main = launcher_source()
_ui_editor = editor_source()


import base64
import json
from io import BytesIO

import pytest
from PIL import Image

import ai_providers as ai
import artwork
from core import Library, Game


def test_provider_catalog_and_image_capabilities():
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


def image_png_b64():
    img = Image.new('RGB', (80, 45), (40, 150, 210))
    memory = BytesIO()
    img.save(memory, format='PNG')
    return base64.b64encode(memory.getvalue()).decode('ascii')


def test_gemini_image_response_is_cached(monkeypatch, tmp_path):
    b64 = image_png_b64()
    seen = []
    def mocked(url, body, headers, **kwargs):
        seen.append((url, body, headers))
        return {'candidates': [{'content': {'parts': [{'inlineData': {'mimeType': 'image/png', 'data': b64}}]}}]}
    monkeypatch.setattr(ai, 'http_json', mocked)
    lib = Library(store=tmp_path / 'store')
    game = Game('game', 'Game', tmp_path / 'games')
    message = artwork.generate_ai_art(lib, game, 'fake-key', provider='gemini', model='gemini-2.5-flash-image')
    assert len(seen) == 2
    assert all(':generateContent' in url for url, _, _ in seen)
    assert (lib.art_dir(game) / 'hero.png').is_file()
    assert (lib.art_dir(game) / 'icon.png').is_file()
    assert 'Gemini' in lib.meta(game)['artwork_source']
    assert 'AI' in message


def test_openai_new_image_path(monkeypatch):
    monkeypatch.setattr(ai, 'http_json', lambda *args, **kwargs: {'data': [{'b64_json': image_png_b64()}]})
    image = ai.image_bytes('openai', 'gpt-image-1-mini', 'test', 'fake', 'icon')
    assert image.startswith(b'\x89PNG')


def test_text_only_services_reject_image_generation():
    for p in ('anthropic', 'ollama'):
        with pytest.raises(ValueError, match='이미지 생성'):
            ai.image_bytes(p, 'model', 'prompt', '', 'icon')


def test_http_errors_do_not_include_credentials(monkeypatch):
    # This is a source-level guard: keys only flow in the Authorization headers.
    source = (ai.__file__)
    from pathlib import Path
    text = Path(source).read_text(encoding='utf-8')
    assert 'Authorization' in text
    assert 'api_key' not in text.split('def http_json(', 1)[1].split('def _extract_json(', 1)[0]


def test_main_and_editor_share_provider_settings():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    app = (root / 'app.py').read_text(encoding='utf-8') + _ui_main
    title_editor = (root / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert 'save_provider_settings' in app
    assert 'current_provider(self.library)' in title_editor
    assert 'ai_game_title(' in title_editor
    assert 'get_secret("openai")' not in app


def test_openrouter_image_endpoint(monkeypatch):
    calls = []
    def mock_http(url, body, headers, **kwargs):
        calls.append((url, body, headers))
        return {'data': [{'b64_json': image_png_b64()}]}
    monkeypatch.setattr(ai, 'http_json', mock_http)
    png = ai.image_bytes('openrouter', 'bytedance-seed/seedream-4.5', 'Banner prompt', 'fake-key', 'hero')
    assert png.startswith(b'\x89PNG')
    assert calls[0][0] == 'https://openrouter.ai/api/v1/images'
    assert calls[0][1]['model'] == 'bytedance-seed/seedream-4.5'
    assert calls[0][2]['Authorization'] == 'Bearer fake-key'
