from refactor_test_support import launcher_source, editor_source
"""Offline regression tests for FREE search/crop pipeline (no real network)."""
from pathlib import Path
_ui_main = launcher_source()


from io import BytesIO
import json
import sys
import types

import pytest
from PIL import Image

from online_artwork import (Candidate, _https_public_url, _normalize_ddgs,
                            _rank_unique, crop_png, read_image, save_selected_art,
                            search_images, suggest_query, download_image)


def fake_image(w=700, h=500, color=(220, 50, 40)):
    im = Image.new('RGB', (w, h), color)
    buf = BytesIO()
    im.save(buf, format='PNG')
    return buf.getvalue()


def test_search_title_cleanup_and_code_fallback():
    assert suggest_query('Night of Revenge [v1.07] [RJ405582]') == 'Night of Revenge'
    assert suggest_query('RJ01373814 [수정2]') == 'RJ01373814'
    assert '한글' not in suggest_query('PASEC [한글패치] [v2.2566]')
    assert suggest_query('Monster Hunter Wilds [PC]') == 'Monster Hunter Wilds'
    assert suggest_query('BUZAMA 1 [한국어]') == 'BUZAMA 1'


@pytest.mark.parametrize('url', [
    'file:///etc/passwd', 'http://example.org/x.png',
    'https://127.0.0.1/a.png', 'https://192.168.1.1/i.jpg',
    'https://localhost/x', 'https://server.internal/x.png',
    'https://user:pass@example.org/x.png',
])
def test_private_or_non_https_url_blocked(url):
    with pytest.raises(ValueError):
        _https_public_url(url)


def test_valid_url_and_ddgs_candidate_normalization():
    url = 'https://images.example.org/example.png'
    assert _https_public_url(url) == url
    rows = [{'image': url, 'thumbnail': 'http://example.org/a',
             'url': 'https://www.example.org/attribution', 'width': 800, 'height': 300,
             'title': 'Game Banner'}]
    entries = _normalize_ddgs(rows)
    assert entries[0].image_url == url
    assert entries[0].thumbnail_url == url
    assert entries[0].source_url.startswith('https://')
    assert entries[0].license_label == '사용 권한 미확인'


def test_rank_favors_banner_shape_and_deduplicates():
    a = Candidate('wide', 'https://x.example/wide.png', '', '', 'DDGS', 1600, 520)
    b = Candidate('square', 'https://x.example/square.png', '', '', 'DDGS', 512, 512)
    assert _rank_unique([b, a, a], 'hero') == [a, b]


def test_crop_outputs_correct_size_and_expected_centering():
    im = Image.new('RGB', (900, 450), (210, 20, 20))
    for x in range(450, 900):
        for y in range(450):
            im.putpixel((x, y), (20, 20, 210))
    data = BytesIO()
    im.save(data, format='PNG')
    left = Image.open(BytesIO(crop_png(data.getvalue(), 'icon', 0, 50)))
    right = Image.open(BytesIO(crop_png(data.getvalue(), 'icon', 100, 50)))
    hero = Image.open(BytesIO(crop_png(data.getvalue(), 'hero')))
    preview = Image.open(BytesIO(crop_png(data.getvalue(), 'hero', preview=True)))
    assert left.size == (256, 256)
    assert right.size == (256, 256)
    assert hero.size == (1600, 520)
    assert preview.size == (640, 208)
    assert left.getpixel((128, 128))[0] > left.getpixel((128, 128))[2]
    assert right.getpixel((128, 128))[2] > right.getpixel((128, 128))[0]


def test_image_bad_payload_and_crop_ranges_blocked():
    for blob in [b'', b'<html>test</html>', b'z' * (12 * 1024 * 1024 + 1)]:
        with pytest.raises(ValueError):
            read_image(blob)
    with pytest.raises(ValueError):
        crop_png(fake_image(), 'hero', zoom=999)
    with pytest.raises(ValueError):
        crop_png(fake_image(), 'random')


def test_save_art_no_mutation_of_other_files(tmp_path):
    target = tmp_path / 'cache' / 'some-id' / 'hero.png'
    meta = target.parent / 'meta.json'
    meta.parent.mkdir(parents=True)
    meta.write_text('{"title":"Test"}', encoding='utf-8')
    save_selected_art(fake_image(), target, 'hero')
    assert meta.read_text(encoding='utf-8') == '{"title":"Test"}'
    assert Image.open(target).size == (1600, 520)
    assert not (target.parent / 'hero.png.writing').exists()
    save_selected_art(fake_image(color=(30, 30, 220)), target, 'hero')
    assert Image.open(target).getpixel((100, 100))[2] > 200


def test_search_uses_ddgs_and_no_image_generation(monkeypatch):
    calls = []
    class FakeDDGS:
        def __init__(self, timeout):
            assert timeout == 12
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def images(self, query, **kwargs):
            calls.append((query, kwargs))
            return [{'title': 'Warframe official game key art banner', 'image': 'https://example.org/game.png',
                     'thumbnail': 'https://example.org/thumb.png', 'url':'https://example.org/game',
                     'width':1600, 'height':520}]
    monkeypatch.setitem(sys.modules, 'ddgs', types.SimpleNamespace(DDGS=FakeDDGS))
    results = search_images('Warframe', 'hero')
    assert len(results) == 1
    assert 'game banner key art' in calls[0][0]
    assert results[0].provider == '웹 이미지 검색'


def test_search_fallback_to_commons(monkeypatch):
    class FakeDDGS:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def images(self, *args, **kwargs): return []
    monkeypatch.setitem(sys.modules, 'ddgs', types.SimpleNamespace(DDGS=FakeDDGS))
    blob = {'query': {'pages': [{
        'title':'File:Nice artwork.png',
        'imageinfo':[{'mime':'image/png', 'url':'https://upload.wikimedia.org/a.png',
                      'thumburl':'https://upload.wikimedia.org/thumb.png',
                      'descriptionurl':'https://commons.wikimedia.org/wiki/File:Nice_artwork.png',
                      'width':1024, 'height':768,
                      'extmetadata':{'LicenseShortName':{'value':'CC BY 4.0'}}}]
    }]}}
    import online_artwork
    monkeypatch.setattr(online_artwork, '_get', lambda url, *args: json.dumps(blob).encode())
    result = search_images('Nice', 'icon')
    assert len(result) == 1
    assert result[0].provider == 'Wikimedia Commons'
    assert result[0].license_label == 'CC BY 4.0'


def test_download_invalid_response_fails(monkeypatch):
    import online_artwork
    monkeypatch.setattr(online_artwork, '_get', lambda url, *args: b'<html>no</html>')
    with pytest.raises(ValueError):
        download_image('https://example.org/image.png')


def test_integration_menu_has_explicit_free_search():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'app.py').read_text(encoding='utf-8') + _ui_main
    assert '인터넷 이미지 검색·편집' in app
    assert 'OnlineArtworkDialog' in app
    assert 'PlayDock_Setup' in (root/'scripts/Build-Windows-Release.ps1').read_text(encoding='utf-8-sig')
    assert 'ddgs' in (root/'requirements.txt').read_text(encoding='utf-8')
