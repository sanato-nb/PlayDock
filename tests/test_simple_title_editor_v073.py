from refactor_test_support import launcher_source, editor_source
"""The quick title editor preserves metadata and has durable, safe undo."""
from pathlib import Path
_ui_editor = editor_source()



import pytest

from core import Game, Library, load_json
from simple_title_edit import (
    MAX_TITLE_HISTORY, save_display_title, undo_display_title,
    restore_filename_title, title_history,
)


def sample(tmp_path, name='PASEC [v2.2566]'):
    root = tmp_path / 'installed'; root.mkdir()
    archive = tmp_path / (name + '.zip')
    archive.write_bytes(b'game archive should not change')
    lib = Library(store=tmp_path / 'store')
    game = Game('pasec', name, root, archive=archive)
    return lib, game, archive


def test_simple_edit_save_undo_restore_persists_after_reopen(tmp_path):
    lib, game, archive = sample(tmp_path)
    before = archive.read_bytes()
    lib.update_meta(game, launch_exe='Some.exe', custom_flag=True)
    assert lib.title(game) == game.name
    assert save_display_title(lib, game, '내가 바꾼 게임')
    assert lib.title(game) == '내가 바꾼 게임'
    assert save_display_title(lib, game, '두 번째 게임명')
    lib2 = Library(store=lib.store)
    assert lib2.title(game) == '두 번째 게임명'
    assert len(title_history(lib2, game)) == 2
    assert undo_display_title(lib2, game)
    assert lib2.title(game) == '내가 바꾼 게임'
    assert undo_display_title(lib2, game)
    assert lib2.title(game) == game.name
    assert not undo_display_title(lib2, game)
    assert archive.read_bytes() == before
    assert lib2.meta(game)['launch_exe'] == 'Some.exe'
    assert lib2.meta(game)['custom_flag'] is True


def test_original_filename_restore_is_reversible(tmp_path):
    lib, game, _ = sample(tmp_path)
    save_display_title(lib, game, '다른 이름')
    assert restore_filename_title(lib, game)
    assert lib.title(game) == game.name
    assert undo_display_title(lib, game)
    assert lib.title(game) == '다른 이름'


def test_manual_title_overrides_but_does_not_erase_localized_titles(tmp_path):
    lib, game, _ = sample(tmp_path, 'RJ01159100 [v24.09.02]')
    lib.update_meta(game, localized_titles={'ko': '한국어 작품명', 'en': 'English Name'},
                    title_source='AI verified')
    assert lib.title(game) == '한국어 작품명 [v24.09.02] [RJ01159100]'
    assert save_display_title(lib, game, '내가 정한 이름')
    assert lib.title(game) == '내가 정한 이름 [RJ01159100]'
    assert lib.meta(game)['localized_titles'] == {'ko':'한국어 작품명','en':'English Name'}
    lib.settings['title_language'] = 'en'
    assert lib.title(game) == '내가 정한 이름 [RJ01159100]'
    assert undo_display_title(lib, game)
    assert lib.title(game) == 'English Name [v24.09.02] [RJ01159100]'


def test_original_from_localized_and_undo(tmp_path):
    lib, game, archive = sample(tmp_path, 'RJ01159100 [v24.09.02]')
    lib.update_meta(game, localized_titles={'ko':'한국어 작품명'})
    assert restore_filename_title(lib, game)
    assert lib.title(game) == 'RJ01159100 [v24.09.02]'
    assert undo_display_title(lib, game)
    assert lib.title(game) == '한국어 작품명 [v24.09.02] [RJ01159100]'


def test_history_bound_and_bad_titles(tmp_path):
    lib, game, _ = sample(tmp_path)
    for i in range(MAX_TITLE_HISTORY + 7):
        assert save_display_title(lib, game, f'사용자 제목 {i}')
    assert len(title_history(lib, game)) == MAX_TITLE_HISTORY
    for bad in ('', '   ', 'a'*241, 'invalid\nname'):
        with pytest.raises(ValueError):
            save_display_title(lib, game, bad)
    assert lib.title(game) == '사용자 제목 26'


def test_games_are_independent_and_no_archive_changes(tmp_path):
    lib, game_a, archive = sample(tmp_path)
    game_b = Game('other', '다른 게임', game_a.root)
    save_display_title(lib, game_a, '변경')
    assert lib.title(game_b) == '다른 게임'
    assert not title_history(lib, game_b)
    assert archive.read_bytes() == b'game archive should not change'


def test_easy_mode_default_and_detailed_tools_preserved():
    project = Path(__file__).resolve().parents[1]
    source = (project / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert "self.panel_stack.setCurrentIndex(0)" in source
    assert "self.mode_btn = QPushButton('상세 기능 보기')" in source
    assert 'self.panel_stack.addWidget(detailed_page)' in source
    assert 'self.save_simple_title' in source
    assert 'self.undo_simple_title' in source
    assert 'self.restore_simple_original' in source
    assert "self.lookup_btn.clicked.connect(lambda: self.start_lookup('rj'))" in source
    assert "self.localized_save_btn.clicked.connect(self.save_localized_title)" in source
    assert 'QStackedWidget' in source
