from refactor_test_support import launcher_source, editor_source
"""Web search Korean published-title candidates, not AI translations."""
from pathlib import Path
_ui_editor = editor_source()



import pytest

from korean_title_search import (
    KoreanTitleHit, suggest_korean_heading, find_korean_titles,
)
from services.localized_titles import lookup_localized_title


def test_korean_web_candidates_require_exact_work_code_and_hangul():
    calls = []
    def searcher(query):
        calls.append(query)
        return [
            {'title': '시골 라이프 - 게임 작품 정보', 'body': 'RJ390522 공식 작품 코드',
             'href': 'https://example.org/games/rj390522'},
            {'title': '엉뚱한 게임', 'body': 'RJ390523',
             'href': 'https://example.org/games/rj390523'},
            {'title': '田舎ライフ 2026', 'body': 'RJ390522',
             'href': 'https://example.org/japanese'},
            {'title': '시골 라이프', 'body': 'RJ390522',
             'href': 'http://example.org/insecure'},
        ]
    results = find_korean_titles('RJ390522', searcher=searcher)
    assert results
    assert all(r.matched_code for r in results)
    assert all('RJ390522' in r.excerpt for r in results)
    assert all(r.url.startswith('https://') for r in results)
    assert '시골 라이프' in [r.title for r in results]
    assert all('RJ390522' in q for q in calls)
    assert len({r.url for r in results}) == len(results)


def test_search_by_original_name_without_code_needs_actual_match():
    results = find_korean_titles(None, 'PASEC', searcher=lambda q: [
        {'title': 'PASEC 게임 한국어 소개', 'body': 'PASEC 제작자 정보',
         'href': 'https://example.com/pasec'},
        {'title': '다른 게임 한국어 제목', 'body': '완전히 다른 작품',
         'href': 'https://example.com/other'},
    ])
    assert len(results) == 1 and results[0].title.startswith('PASEC')
    with pytest.raises(ValueError):
        find_korean_titles(None, 'RJ390522', searcher=lambda q: [])


def test_search_never_translates_japanese_or_guesses_titles():
    results = find_korean_titles('RJ390522', searcher=lambda q: [
        {'title': '田舎ライフ | DLsite', 'body': 'RJ390522',
         'href': 'https://example.com/jp'},
    ])
    assert results == []
    assert suggest_korean_heading('田舎ライフ | DLsite', 'RJ390522') is None


def test_code_only_page_and_bad_urls_not_used():
    rows = [{'title': 'RJ390522', 'body': 'RJ390522 한국어', 'href': 'https://example.org/id'},
            {'title': '한국어 검색 결과', 'body': 'RJ390522', 'href': 'https://example.org/empty'},
            {'title': '시골 라이프', 'body': 'RJ390522', 'href': 'https://localhost/private'}]
    assert find_korean_titles('RJ390522', searcher=lambda q: rows) == []


def test_search_error_is_visible_and_does_not_save_any_data(tmp_path):
    def failing(_query):
        raise RuntimeError('blocked')
    with pytest.raises(LookupError, match='검색 서비스'):
        find_korean_titles('RJ390522', searcher=failing)
    assert list(tmp_path.iterdir()) == []


def test_ui_has_separate_web_lookup_from_ai_translation_and_preserves_save(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = (root / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert "self.korean_web_btn = QPushButton('한국어 제목 웹 검색 (무료 · 번역 아님)')" in source
    assert "self.korean_web_btn.clicked.connect(lambda: self.start_lookup('korean_web'))" in source
    assert "elif self.mode == 'korean_web':" in source
    assert 'self.korean_web_found.emit(self.game_id, suggestions)' in source
    assert "self.localized_candidate_language = 'ko'" in source
    assert "self.localized_source = '사용자가 선택한 웹 검색 후보" in source
    assert 'self.localized_save_btn.clicked.connect(self.save_localized_title)' in source
    assert 'self.translate_btn.clicked.connect(lambda: self.start_lookup(\'translate\'))' in source
    assert 'self.panel_stack.setCurrentIndex(0)' in source


def test_search_limits_and_validation():
    with pytest.raises(ValueError):
        find_korean_titles('RJ13', searcher=lambda q: [])
    with pytest.raises(ValueError):
        find_korean_titles('RJ390522', searcher=lambda q: [], limit=100)
    assert find_korean_titles('RJ390522', searcher=lambda q: [], limit=3) == []


def test_simple_mode_can_open_web_korean_search():
    source = (Path(__file__).resolve().parents[1] / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert 'self.simple_korean_btn.clicked.connect(self.open_korean_lookup_from_simple)' in source
    assert "self.start_lookup('korean_web')" in source
    assert 'self.simple_korean_btn.setEnabled(enabled and not busy)' in source


def test_manual_browser_lookup_is_available_when_api_search_is_blocked():
    source = (Path(__file__).resolve().parents[1] / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert "self.korean_browser_btn = QPushButton('브라우저에서 한국어 제목 검색')" in source
    assert 'QDesktopServices.openUrl(QUrl(url))' in source
