from refactor_test_support import launcher_source, editor_source
"""Regression tests for searchable real artwork (no generative image UI)."""
from pathlib import Path
_ui_main = launcher_source()



ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8') + _ui_main
DIALOG = (ROOT / 'src/playdock/ui/artwork_dialog.py').read_text(encoding='utf-8')


def test_official_image_and_catalog_actions_are_direct_and_not_generated():
    assert 'self.action_button("게임 정보 수집", self.collect_library_information)' in APP
    assert 'self.action_button("게임 정체 판독", self.identify_selected_game)' in APP
    assert '인터넷 이미지 검색·편집' not in APP
    assert 'def open_online_artwork(self):' not in APP
    assert 'def fetch_art(self):' not in APP
    assert 'def start_ai_task(self, mode:' not in APP
    assert 'generate_ai_art(' not in APP
    assert 'AI로 새 배너·아이콘 생성' not in APP
    assert 'Gemini 무료 등급은 이미지 생성' not in APP

def test_settings_name_only_and_no_image_generation_model_field():
    settings = APP.split('class SettingsDialog(', 1)[1].split('class FirstRunDialog(', 1)[0]
    assert 'form.addRow("게임 이름 모델", self.text_model)' in settings
    assert 'form.addRow("이미지 모델",' not in settings
    assert 'AI 키 없이 무료로' in settings or 'API 키 없이 무료로' in settings

def test_official_image_checkboxes_retain_crop_and_safe_file_backup():
    dialog = (ROOT / 'src/playdock/ui/dialogs/identity_artwork.py').read_text(encoding='utf-8')
    official = (ROOT / 'src/playdock/services/official_artwork_service.py').read_text(encoding='utf-8')
    service = (ROOT / 'src/playdock/services/artwork_service.py').read_text(encoding='utf-8')
    assert 'QCheckBox(caption)' in dialog
    assert 'checkbox.setChecked(False)' in dialog
    assert 'prepare_official_images(' in official
    assert 'apply_checked_images(' in official
    assert 'save_selected_art(' in service
