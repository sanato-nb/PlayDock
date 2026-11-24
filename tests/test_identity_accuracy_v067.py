"""Offline tests for the identity-first v0.6.7 artwork workflow."""
from unittest.mock import patch
import sys
import types

import pytest

from ai_providers import current_models, PROVIDERS
from core import Library
from game_identity import (initial_identity, find_public_work_code,
                           discover_public_identity)
from online_artwork import Candidate, candidate_matches_game, search_images
from product_titles import lookup_title


def make_candidate(title, page):
    return Candidate(title, 'https://example.org/screenshot.png', '', page, 'search', 1400, 700)


def test_specific_korean_title_resolves_crosschecked_code():
    result = initial_identity('6월의 너와 나 [한국어]')
    assert result.title == '6월의 너와 나'
    assert result.code == 'RJ01081508'
    assert not result.verified


def test_crosschecked_original_title_offline(tmp_path):
    title, source = lookup_title('RJ01081508', tmp_path / 'product_titles.json')
    assert title == '6月の君と僕'
    assert '오프라인' in source


def test_discovery_requires_two_independent_matching_sites():
    rows = [
        {'title':'Another game', 'body':'RJ00001000', 'href':'https://example.org/fake'},
        {'title':'Test Work RJ12345678', 'body':'Test Work RJ12345678', 'href':'https://site-one.example/one'},
        {'title':'Test Work RJ12345678', 'body':'Test Work RJ12345678', 'href':'https://site-two.example/two'},
    ]
    assert find_public_work_code('Test Work', searcher=lambda q: rows) == 'RJ12345678'
    with pytest.raises(LookupError):
        find_public_work_code('Test Work', searcher=lambda q: rows[:2])


def test_title_overlap_not_sufficient_for_korean_work():
    assert not candidate_matches_game(make_candidate('작년 6월의 여름 너와 함께', 'https://example.org/test'),
                                      '6월의 너와 나')
    assert candidate_matches_game(make_candidate('6월의 너와 나 작품 이미지', 'https://example.org/test'),
                                  '6월의 너와 나')
    assert candidate_matches_game(make_candidate('6月の君と僕 サンプル画像',
                                                  'https://example.org/items/RJ01081508'),
                                  '6月の君と僕', 'RJ01081508')
    assert not candidate_matches_game(make_candidate('6月の君と僕 다른 상품',
                                                      'https://example.org/items/RJ00001234'),
                                      '6月の君と僕', 'RJ01081508')


def test_numbered_sequels_are_distinct():
    assert not candidate_matches_game(make_candidate('BUZAMA 2 title screen', 'https://example.org/p'),
                                      'BUZAMA 1')
    assert candidate_matches_game(make_candidate('BUZAMA 1 title screen', 'https://example.org/p'),
                                  'BUZAMA 1')


def test_code_search_ranks_only_exact_work(monkeypatch):
    class FakeDDGS:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def images(self, q, **kwargs):
            return [
                {'title':'6月の君と僕 alternate work', 'image':'https://example.org/other.png',
                 'url':'https://example.org/product/RJ00000011', 'width':1600,'height':520},
                {'title':'RJ01081508 original cover', 'image':'https://example.org/right.png',
                 'url':'https://www.dlsite.com/maniax/work/=/product_id/RJ01081508.html',
                 'width':700, 'height':950},
            ]
    monkeypatch.setitem(sys.modules, 'ddgs', types.SimpleNamespace(DDGS=FakeDDGS))
    results = search_images('6月の君と僕', 'hero', product_code='RJ01081508')
    assert len(results) == 1
    assert 'RJ01081508' in results[0].title


def test_saved_gemini_model_alias_avoids_new_user_404(tmp_path):
    lib = Library(store=tmp_path)
    lib.settings['ai_models'] = {'gemini': {'text':'gemini-2.5-flash', 'image':''}}
    assert current_models(lib,'gemini')[0] == 'gemini-3.8-flash'
    assert PROVIDERS['gemini']['text_model'] == 'gemini-3.8-flash'
    lib.settings['ai_models']['gemini']['text'] = 'custom-model'
    assert current_models(lib,'gemini')[0] == 'custom-model'


def test_ui_has_code_entry_and_manual_search_fallback():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'ui/artwork_dialog.py').read_text(encoding='utf-8')
    assert 'self.code_input' in source
    assert "self.resolve_identity('discover')" in source
    assert 'AI로 게임명 추천 (선택)' in source
    assert 'image_bytes(' not in source
