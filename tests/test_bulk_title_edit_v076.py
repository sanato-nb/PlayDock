from refactor_test_support import launcher_source, editor_source
"""Safety and behavior of opt-in bulk rename preview/apply."""
from pathlib import Path
_ui_editor = editor_source()


from unittest.mock import patch
import zipfile
import pytest

from core import Game, Library, load_json
from simple_title_edit import title_history, undo_display_title, save_display_title
from bulk_title_edit import (
    BulkChange, replace_name, apply_bulk_changes,
    validate_changes, name_was_manually_changed,
)


def sample(tmp_path):
    root = tmp_path / 'installed'
    root.mkdir()
    a = tmp_path / 'RJ01159100 [v24.09.02].zip'
    b = tmp_path / 'PASEC [v2.2566].7z'
    a.write_bytes(b'original zip')
    b.write_bytes(b'original 7z')
    lib = Library(store=tmp_path / 'store')
    ga = Game('game-a', a.stem, root, archive=a)
    gb = Game('game-b', b.stem, root, archive=b)
    return lib, [ga, gb], a, b


def test_literal_replace_case_insensitive_and_optional_case_sensitive():
    assert replace_name('PASEC [KOR] kor', 'kor', '한국어') == 'PASEC [한국어] 한국어'
    assert replace_name('PASEC kor KOR', 'kor', '', case_sensitive=True) == 'PASEC  KOR'
    with pytest.raises(ValueError):
        replace_name('any', '', 'x')
    assert replace_name('a+b [v1]', 'a+b', 'X') == 'X [v1]'


def test_bulk_manual_save_backup_and_undo_one_by_one(tmp_path):
    lib, games, a, b = sample(tmp_path)
    lib.update_meta(games[0], launch_exe='test.exe', unrelated_setting=True)
    changes = [BulkChange(g.id, lib.title(g), f'게임 변경 {i}') for i, g in enumerate(games)]
    count, backup = apply_bulk_changes(lib, games, changes)
    assert count == 2 and backup.is_file()
    assert [lib.base_title(g) for g in games] == ['게임 변경 0', '게임 변경 1']
    assert all(len(title_history(lib, g)) == 1 for g in games)
    assert a.read_bytes() == b'original zip' and b.read_bytes() == b'original 7z'
    assert lib.meta(games[0])['launch_exe'] == 'test.exe'
    assert lib.meta(games[0])['unrelated_setting'] is True
    with zipfile.ZipFile(backup) as zf:
        assert len([n for n in zf.namelist() if n.startswith('meta/')]) == 2
        assert 'manifest.json' in zf.namelist()
    assert undo_display_title(lib, games[0])
    assert lib.title(games[0]) == games[0].name
    assert lib.title(games[1]) == '게임 변경 1'


def test_bulk_restore_original_and_undo(tmp_path):
    lib, games, *_ = sample(tmp_path)
    save_display_title(lib, games[0], '직접 바꾼 이름')
    orig = lib.title(games[0])
    changed, _ = apply_bulk_changes(lib, games,
        [BulkChange(games[0].id, orig, games[0].name, method='original')])
    assert changed == 1
    assert lib.title(games[0]) == games[0].name
    assert undo_display_title(lib, games[0])
    assert lib.title(games[0]) == orig


def test_stale_preview_does_not_write_or_create_backup(tmp_path):
    lib, games, *_ = sample(tmp_path)
    old = lib.title(games[0])
    save_display_title(lib, games[0], '사용자 다른 수정')
    with pytest.raises(ValueError, match='다시 미리보기'):
        apply_bulk_changes(lib, games, [BulkChange(games[0].id, old, '일괄 변경')])
    assert lib.title(games[0]) == '사용자 다른 수정 [RJ01159100]'
    assert not (lib.store / 'backups').exists()


def test_duplicate_and_invalid_name_prevent_all_write(tmp_path):
    lib, games, *_ = sample(tmp_path)
    old = lib.title(games[0])
    with pytest.raises(ValueError, match='중복'):
        apply_bulk_changes(lib, games, [BulkChange(games[0].id, old, 'A'), BulkChange(games[0].id, old, 'B')])
    with pytest.raises(ValueError, match='1~240'):
        apply_bulk_changes(lib, games, [BulkChange(games[0].id, old, 'bad\nname')])
    assert lib.title(games[0]) == old
    assert not (lib.store / 'backups').exists()


def test_localized_bulk_preserves_language_and_undo_restores_prior_variants(tmp_path):
    lib, games, *_ = sample(tmp_path)
    game = games[0]
    lib.update_meta(game, localized_titles={'en': 'English before'},
                    localized_sources={'en': 'old source'})
    old = lib.title(game)
    count, backup = apply_bulk_changes(lib, games, [BulkChange(game.id, old,
        '정확한 한국어 제목', method='localized', language='ko',
        source='공개 자료 사용자 확인', product_code='RJ01159100')])
    assert count == 1 and backup.is_file()
    meta = lib.meta(game)
    assert meta['localized_titles'] == {'en': 'English before', 'ko': '정확한 한국어 제목'}
    assert lib.title(game) == '정확한 한국어 제목 [v24.09.02] [RJ01159100]'
    assert undo_display_title(lib, game)
    assert lib.meta(game)['localized_titles'] == {'en': 'English before'}
    assert lib.meta(game)['localized_sources'] == {'en': 'old source'}
    assert lib.title(game) == old


def test_not_mislabel_japanese_as_korean_and_code_must_match(tmp_path):
    lib, games, *_ = sample(tmp_path)
    game = games[0]
    with pytest.raises(ValueError, match='언어'):
        apply_bulk_changes(lib, games, [BulkChange(game.id, lib.title(game),
            '日本語タイトル', method='localized', language='ko', product_code='RJ01159100')])
    with pytest.raises(ValueError, match='코드'):
        apply_bulk_changes(lib, games, [BulkChange(game.id, lib.title(game),
            '한국어 제목', method='localized', language='ko', product_code='RJ999999')])


def test_bulk_transaction_rolls_back_when_second_write_fails(tmp_path):
    import bulk_title_edit
    lib, games, a, b = sample(tmp_path)
    lib.update_meta(games[0], custom='keep')
    before = lib.meta(games[0])
    actual = bulk_title_edit.save_display_title
    called = []
    def intermittent(library, game, title, **kwargs):
        called.append(game.id)
        if game.id == games[1].id:
            raise OSError('disk full')
        return actual(library, game, title, **kwargs)
    with patch.object(bulk_title_edit, 'save_display_title', intermittent):
        with pytest.raises(OSError, match='disk full'):
            apply_bulk_changes(lib, games,
                [BulkChange(g.id, lib.title(g), f'new {i}') for i,g in enumerate(games)])
    assert len(called) == 2
    assert lib.meta(games[0]) == before
    assert lib.title(games[0]) == games[0].name
    assert a.read_bytes() == b'original zip' and b.read_bytes() == b'original 7z'
    assert len(list((lib.store / 'backups').glob('title_bulk_*.zip'))) == 1


def test_manual_override_is_detected_for_default_safe_skip(tmp_path):
    lib, games, *_ = sample(tmp_path)
    assert not name_was_manually_changed(lib, games[0])
    save_display_title(lib, games[0], '내가 원하는 게임')
    assert name_was_manually_changed(lib, games[0])


def test_bulk_editor_has_detailed_controls_and_old_screen(tmp_path):
    src = (Path(__file__).resolve().parents[1] / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert "self.bulk_settings_btn = QPushButton('일괄 이름 변경 · 상세 설정')" in src
    assert 'class BulkTitleSettingsDialog(QDialog)' in src
    assert 'self.keep_custom.setChecked(True)' in src
    assert 'self.preview_table.itemChanged.connect(self.preview_edited)' in src
    assert 'apply_bulk_changes(self.library, self.games, changes)' in src
    assert 'self.mode_btn = QPushButton(\'상세 기능 보기\')' in src
    assert 'self.bulk_btn = QPushButton(\'품번만 있는 게임 일괄 조회\')' in src


def test_bulk_undo_mode_and_preview_name(tmp_path):
    from bulk_title_edit import preview_undo_name
    lib, games, *_ = sample(tmp_path)
    assert preview_undo_name(lib, games[0]) is None
    save_display_title(lib, games[0], '게임을 수정')
    before = lib.title(games[0])
    target = preview_undo_name(lib, games[0])
    assert target == games[0].name
    count, backup = apply_bulk_changes(lib, games,
        [BulkChange(games[0].id, before, target, method='undo')])
    assert count == 1 and backup.is_file()
    assert lib.title(games[0]) == games[0].name
    assert not title_history(lib, games[0])


def test_preview_undo_localized_title_state(tmp_path):
    from bulk_title_edit import preview_undo_name
    lib, games, *_ = sample(tmp_path)
    game = games[0]
    lib.update_meta(game, localized_titles={'ko': '이전 한국어 이름'})
    save_display_title(lib, game, '다른 이름')
    assert preview_undo_name(lib, game) == '이전 한국어 이름 [v24.09.02] [RJ01159100]'


def test_ui_has_manual_replace_lookup_restore_undo_bulk_modes():
    src = (Path(__file__).resolve().parents[1] / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    for mode in ['manual', 'lookup', 'replace', 'original', 'undo']:
        assert "'" + mode + "'" in src
    assert "self.preview_table" in src
    assert "self.targets.itemChanged.connect" in src
