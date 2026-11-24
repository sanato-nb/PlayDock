from refactor_test_support import launcher_source, editor_source
"""Regression checks for the standalone title editor packaging and shared cache."""
from pathlib import Path
_ui_main = launcher_source()
_ui_editor = editor_source()



from core import Game, Library

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8') + _ui_main
EDITOR = (ROOT / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
SETUP = (ROOT / 'setup_wizard.py').read_text(encoding='utf-8')
BUILD = (ROOT / 'scripts/build_setup_windows.bat').read_text(encoding='utf-8')


def test_title_editing_lives_in_separate_entrypoint():
    assert 'class TitleEditor(TitleEditorActionsMixin, QMainWindow)' in EDITOR
    assert "from core import Library" in EDITOR
    assert 'lookup_title(' in EDITOR
    assert 'display_title(' in EDITOR
    assert 'ai_game_title(' in EDITOR
    assert 'save_display_title(self.library, game, candidate, source=self.suggestion_source)' in EDITOR
    assert 'lookup_product_title' not in APP
    assert 'def rename_game(' not in APP
    assert 'def ai_title(' not in APP
    assert '작품 코드(RJ)로 게임 제목 확인' not in APP
    assert 'def show_game_menu(' not in APP


def test_installer_bundles_two_independent_binaries_and_shortcuts():
    assert 'PlayDock.exe' in BUILD
    assert 'PlayDock_TitleEditor.exe' in BUILD
    assert '--add-binary "dist\\PlayDock_TitleEditor.exe;payload"' in BUILD
    assert 'def installed_title_editor(program: Path | None = None)' in SETUP
    assert 'def payload_title_editor()' in SETUP
    assert 'shutil.copy2(payload_title_editor(), tmp)' in SETUP
    assert 'create_shortcut(editor, start_menu.with_name(' in SETUP
    assert 'editor = payload_title_editor()' in SETUP  # --self-test validates both


def test_both_apps_share_existing_metadata_not_archives(tmp_path):
    install = tmp_path / 'installs'; install.mkdir()
    archive_dir = tmp_path / 'archives'; archive_dir.mkdir()
    file = archive_dir / 'RJ01373814 [old].zip'
    file.write_bytes(b'original game bytes')
    # Both executables independently construct Library() on the SAME store.
    primary = Library(store=tmp_path / 'shared')
    editor = Library(store=tmp_path / 'shared')
    game = Game(key='test-key', name=file.stem, root=install, archive=file)
    editor.update_meta(game, title='메시아 오브 로리타 [RJ01373814]')
    assert primary.title(game) == '메시아 오브 로리타 [RJ01373814]'
    assert file.read_bytes() == b'original game bytes'


def test_title_editor_styles_popups_like_main_window():
    assert 'class DarkDialogCaptionFilter(QObject)' in EDITOR
    assert 'app.installEventFilter(captions)' in EDITOR
    assert 'windows_dark_caption' in EDITOR


def test_title_editor_has_confirmation_step_not_autosave():
    assert 'self.edit.setText(candidate)' in EDITOR
    assert "self.save_btn.clicked.connect(self.save_title)" in EDITOR
    assert 'save_display_title(self.library, game, candidate' in EDITOR
    assert 'def lookup_found(' in EDITOR
    assert 'self.library.update_meta(' not in EDITOR.split('def lookup_found(', 1)[1].split('def lookup_failed(', 1)[0]
