"""Localized metadata must never overwrite downloaded game binaries or guess titles."""
from pathlib import Path
from unittest.mock import patch

import pytest

from core import Library, Game, load_json
from services.localized_titles import (
    is_code_only_title, lookup_localized_title, language_is_plausible,
    localized_title_for, display_language_for,
)
from title_translation import translate_work_title


@pytest.mark.parametrize('raw,expected', [
    ('RJ01159100 [v24.09.02]', True),
    ('RJ01155094', True),
    ('VJ123456 [한국어]', True),
    ('RJ123456 [수정2] [v1.1]', True),
    ('Night of Revenge [RJ405582]', False),
    ('PASEC [v2.2566]', False),
    ('RJ01159100 more', False),
    ('RJ12345', False),
])
def test_code_only_title(raw, expected):
    assert is_code_only_title(raw) == expected


def test_prefer_real_korean_title_not_japanese_when_available(tmp_path):
    calls = []
    def fetcher(code, locale):
        calls.append((code, locale))
        return ('검증된 한국어 제목', 'https://example.org/verified') if locale == 'ko_KR' else None
    cache = tmp_path / 'titles.json'
    result = lookup_localized_title('RJ01159100', 'ko', cache, fetcher=fetcher)
    assert result.title == '검증된 한국어 제목'
    assert result.language == 'ko' and result.is_fallback is False
    assert calls == [('RJ01159100', 'ko_KR')]
    cached = lookup_localized_title('RJ01159100', 'ko', cache, fetcher=lambda *_: 1/0)
    assert cached.title == result.title


def test_japanese_fallback_does_not_become_fake_korean(tmp_path):
    calls = []
    def fetcher(code, locale):
        calls.append(locale)
        return ('すてきなゲーム', 'https://example.org/jp')
    result = lookup_localized_title('RJ01159100', 'ko', tmp_path / 'cache.json', fetcher=fetcher)
    assert result.language == 'ja' and result.is_fallback
    assert calls == ['ko_KR', 'ja_JP']
    cache = load_json(tmp_path / 'cache.json')
    assert 'ko' not in cache['RJ01159100']
    assert cache['RJ01159100']['ja']['title'] == 'すてきなゲーム'


def test_english_language_fetch(tmp_path):
    result = lookup_localized_title('RJ01159100', 'en', tmp_path / 'cache.json',
                                    fetcher=lambda code, locale: ('Some Game', 'official')
                                    if locale == 'en_US' else None)
    assert result.language == 'en' and result.title == 'Some Game'


def test_reject_wrong_work_identifier_and_no_guess(tmp_path):
    with pytest.raises(ValueError):
        lookup_localized_title('RJ11', 'ko', tmp_path / 'cache.json')
    with pytest.raises(LookupError):
        lookup_localized_title('RJ01159100', 'ko', tmp_path / 'cache.json',
                               fetcher=lambda *_: None)


def test_alias_is_not_conflated_with_another_language(tmp_path):
    ko = lookup_localized_title('RJ01373814', 'ko', tmp_path / 'cache.json',
                                fetcher=lambda *_: None)
    assert ko.title == '메시아 오브 로리타' and ko.language == 'ko'


def test_library_switches_language_preserving_version_archive_and_code(tmp_path):
    store = tmp_path / 'data'
    root = tmp_path / 'installed'
    root.mkdir()
    archive = tmp_path / 'RJ01159100 [v24.09.02].zip'
    archive.write_bytes(b'original-archive')
    lib = Library(store=store)
    game = Game('rj01159100 [v24.09.02]', archive.stem, root, archive=archive)
    lib.update_meta(game, localized_titles={
        'ko': '한국어 제목', 'en': 'English Name', 'ja': '日本語の作品',
    })
    assert lib.title(game) == '한국어 제목 [v24.09.02] [RJ01159100]'
    lib.settings['title_language'] = 'en'
    lib.save_settings()
    assert lib.title(game) == 'English Name [v24.09.02] [RJ01159100]'
    lib.settings['title_language'] = 'ja'
    assert lib.title(game) == '日本語の作品 [v24.09.02] [RJ01159100]'
    assert archive.read_bytes() == b'original-archive'
    assert not (root / 'RJ01159100 [v24.09.02]').exists()


def test_code_only_can_fallback_japanese_without_inventing_korean(tmp_path):
    library = Library(store=tmp_path / 'store')
    root = tmp_path / 'root'; root.mkdir()
    game = Game('rj01159100', 'RJ01159100 [v24.09.02]', root)
    library.update_meta(game, localized_titles={'ja': '日本語の題名'})
    assert library.title(game) == '日本語の題名 [v24.09.02] [RJ01159100]'
    library.settings['title_language'] = 'en'
    assert library.title(game).startswith('日本語の題名')
    assert not (library.meta(game).get('localized_titles') or {}).get('ko')


def test_non_code_game_keeps_user_name_when_no_translation(tmp_path):
    library = Library(store=tmp_path / 'store')
    root = tmp_path / 'root'; root.mkdir()
    game = Game('pasec', 'PASEC [v2.2566]', root)
    library.update_meta(game, title='PASEC - 내 게임')
    assert library.title(game) == 'PASEC - 내 게임'
    library.settings['title_language'] = 'ja'
    assert library.title(game) == 'PASEC - 내 게임'


def test_text_translation_requires_review_and_no_image_generation():
    translated = translate_work_title('日本語の題名', 'ko', 'ollama', 'my-model', '',
        responder=lambda *_: '{"title": "한국어 번역 제목"}')
    assert translated == '한국어 번역 제목'
    with pytest.raises(LookupError):
        translate_work_title('日本語の題名', 'ko', 'ollama', 'my-model', '',
            responder=lambda *_: '{"title": "日本語の題名"}')


def test_per_game_language_override_takes_priority(tmp_path):
    lib = Library(store=tmp_path / 'store')
    root = tmp_path / 'root'; root.mkdir()
    game = Game('rj01159100', 'RJ01159100 [v24.09.02]', root)
    lib.settings['title_language'] = 'ko'
    lib.update_meta(game, localized_titles={'ko': '한국어 게임', 'en': 'English Game'},
                    title_language='en')
    assert lib.title(game) == 'English Game [v24.09.02] [RJ01159100]'
    lib.update_meta(game, title_language='')
    assert lib.title(game) == '한국어 게임 [v24.09.02] [RJ01159100]'
