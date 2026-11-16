"""Identity-first search without live APIs or local game data mutation."""
from pathlib import Path
from unittest.mock import patch
import pytest
from online_artwork import Candidate, candidate_matches_game, search_images
from game_identity import initial_identity, lookup_code_identity, suggest_ai_identity


def sample(title, width=1600, height=520):
    return Candidate(title, 'https://public.example/' + str(abs(hash(title))) + '.png', '',
                     'https://public.example/' + title.replace(' ', '-') + '.html', 'web', width, height)


def test_plain_game_title_is_not_claimed_official():
    identity = initial_identity('BUZAMA 1 [한국어]')
    assert identity.title == 'BUZAMA 1'
    assert identity.verified is False
    assert identity.code is None


def test_work_code_and_release_info_are_separate():
    identity = initial_identity('ㄹㄹㅌ의 메시아 [v25.08.01] [RJ01373814]')
    assert identity.code == 'RJ01373814'
    assert identity.verified is False


def test_code_lookup_requires_matching_public_record(tmp_path):
    with patch('game_identity.lookup_title', return_value=('게임 정식 명칭', 'published metadata')) as lookup:
        result = lookup_code_identity('RJ12345678', tmp_path / 'products.json')
    assert result.verified and result.title == '게임 정식 명칭'
    lookup.assert_called_once()


def test_ai_identity_is_unverified_even_with_confidence():
    with patch('game_identity._text_response', return_value='{"title":"BUZAMA 1","confidence":0.94}'):
        result = suggest_ai_identity('BUZAMA [v1]', None, 'ollama', 'gemma3:4b', '')
    assert result.title == 'BUZAMA 1'
    assert result.verified is False


def test_ai_identity_hallucination_not_used():
    with patch('game_identity._text_response', return_value='{"title":"random","confidence":0.2}'):
        with pytest.raises(LookupError):
            suggest_ai_identity('RJ12345678', 'RJ12345678', 'ollama', 'gemma3:4b', '')


def test_candidate_filter_excludes_generic_image_even_if_perfect_aspect():
    unrelated = sample('Gaming Banner Template Free', 1600, 520)
    related = sample('BUZAMA 1 original game screenshot', 640, 360)
    assert not candidate_matches_game(unrelated, 'BUZAMA 1')
    assert candidate_matches_game(related, 'BUZAMA 1')
    assert candidate_matches_game(sample('Night of Revenge key visual'), 'Night of Revenge')
    assert not candidate_matches_game(sample('Night in Space game'), 'Night of Revenge')


def test_search_takes_only_related_candidates(monkeypatch):
    import sys, types
    generic = {'title':'Generic banner template', 'image':'https://public.example/generic.png',
               'thumbnail':'https://public.example/generic-t.png', 'width':1600, 'height':520}
    related = {'title':'BUZAMA 1 game promotional artwork', 'image':'https://public.example/buzama.png',
               'thumbnail':'https://public.example/buzama-t.png', 'width':900, 'height':600}
    class FakeDDGS:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def images(self, query, **kw): return [generic, related]
    monkeypatch.setitem(sys.modules, 'ddgs', types.SimpleNamespace(DDGS=FakeDDGS))
    result = search_images('BUZAMA 1')
    assert [x.title for x in result] == [related['title']]


def test_dialog_gives_name_review_and_manual_web_search():
    src = (Path(__file__).resolve().parents[1] / 'ui/artwork_dialog.py').read_text(encoding='utf-8')
    assert 'IdentityJob' in src
    assert 'AI로 게임명 추천 (선택)' in src
    assert 'RJ 품번으로 작품명 확인' in src
    assert 'open_web_search' in src
    assert 'CropEditor(' in src
    assert 'image_bytes(' not in src
