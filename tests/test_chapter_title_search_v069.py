"""Regression: chapter tag must be parsed without truncation or wrong images."""
from pathlib import Path
import sys
import types

import pytest

from online_artwork import suggest_query, Candidate, candidate_matches_game, search_images
from game_identity import initial_identity


def test_complete_chapter_tag_is_not_broken():
    assert suggest_query('HeNTeRia Chronicles [Chap.1]') == 'HeNTeRia Chronicles Chapter 1'
    assert suggest_query('HeNTeRia Chronicles [Chap.1') == 'HeNTeRia Chronicles Chapter 1'
    assert suggest_query('HeNTeRia Chronicles [Chapter 2]') == 'HeNTeRia Chronicles Chapter 2'


def test_chapter_number_preserved_but_release_tag_removed():
    assert suggest_query('HeNTeRia Chronicles [Chap.1] [한국어] [v1.02]') == 'HeNTeRia Chronicles Chapter 1'
    assert suggest_query('HeNTeRia Chronicles [Chap.2] [RJ12345678]') == 'HeNTeRia Chronicles Chapter 2'
    assert suggest_query('PASEC_v2.2566.zip') == 'PASEC'
    assert suggest_query('BUZAMA 1 [한국어]') == 'BUZAMA 1'


def test_unknown_bracket_is_not_silently_corrupted():
    # If it isn't known to be release metadata, preserve the original tag.
    assert suggest_query('MyGame [Reborn]') == 'MyGame [Reborn]'


def candidate(title, page='https://example.org/game'):
    return Candidate(title, 'https://example.org/image.jpg', '', page, 'test', 1600, 520)


def test_chapter_punctuation_variants_match():
    query = 'HeNTeRia Chronicles Chapter 1'
    assert candidate_matches_game(candidate('Henteria Chronicles: Chapter 1 [Complete]'), query)
    assert candidate_matches_game(candidate('HeNTeRia Chronicles Chap.1 key art'), query)
    assert candidate_matches_game(candidate('HeNTeRia Chronicles Ch 1 cover'), query)


@pytest.mark.parametrize('different', ['Chapter 2', 'Chapter 10', 'Chap.11', 'Ch 3'])
def test_wrong_chapter_does_not_match(different):
    assert not candidate_matches_game(candidate(f'Henteria Chronicles {different} cover'),
                                      'HeNTeRia Chronicles Chapter 1')


def test_without_code_initial_identity_preserves_chapter():
    ident = initial_identity('HeNTeRia Chronicles [Chap.1]')
    assert ident.title == 'HeNTeRia Chronicles Chapter 1'
    assert ident.code is None
    assert ident.verified is False


def test_search_also_tries_publisher_chap_spelling(monkeypatch):
    seen = []
    class FakeDDGS:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def images(self, query, **kwargs):
            seen.append(query)
            if 'Chap.1' not in query:
                return []
            return [{'title':'Henteria Chronicles: Chapter 1 [Complete]',
                     'image':'https://example.org/chap1.jpg',
                     'url':'https://n-taii.itch.io/henteria-chronicles-chapter-1-complete',
                     'width':1200, 'height':550}]
    monkeypatch.setitem(sys.modules, 'ddgs', types.SimpleNamespace(DDGS=FakeDDGS))
    result = search_images('HeNTeRia Chronicles Chapter 1', kind='hero')
    assert len(result) == 1
    assert any('Chap.1' in phrase for phrase in seen)


def test_original_title_unchanged_by_search_ui():
    src = (Path(__file__).resolve().parents[1] / 'src/playdock/ui/artwork_dialog.py').read_text(encoding='utf-8')
    assert 'self.original_title_note' in src
    assert 'self.query = QLineEdit(self.identity.title)' in src
