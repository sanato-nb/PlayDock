from refactor_test_support import launcher_source, editor_source
"""Regression tests for searchable real artwork (no generative image UI)."""
from pathlib import Path
_ui_main = launcher_source()



ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8') + _ui_main


def test_official_image_and_catalog_actions_are_direct_and_not_generated():
    assert 'self.action_button("게임 정보 수집", self.collect_library_information)' in APP
    assert "공식 배너·아이콘 적용" in APP
    assert "self.identify_selected_game" in APP
    assert '인터넷 이미지 검색·편집' not in APP
    assert 'def open_online_artwork(self):' not in APP
    assert 'def fetch_art(self):' not in APP
    assert 'def start_ai_task(self, mode:' not in APP
    assert 'generate_ai_art(' not in APP
    assert 'AI로 새 배너·아이콘 생성' not in APP
    assert 'Gemini 무료 등급은 이미지 생성' not in APP

def test_retired_ai_settings_window_is_absent():
    assert 'class SettingsDialog(' not in APP
    assert 'def settings_dialog(' not in APP
    assert 'form.addRow("AI 서비스", self.provider)' not in APP
    assert 'form.addRow("이미지 모델",' not in APP


def test_official_image_checkboxes_retain_crop_and_safe_file_backup():
    dialog = (ROOT / 'src/playdock/ui/dialogs/identity_artwork.py').read_text(encoding='utf-8')
    official = (ROOT / 'src/playdock/services/official_artwork_service.py').read_text(encoding='utf-8')
    service = (ROOT / 'src/playdock/services/artwork_service.py').read_text(encoding='utf-8')
    assert 'QCheckBox(caption)' in dialog
    assert 'checkbox.setChecked(False)' in dialog
    assert 'prepare_official_images(' in official
    assert 'apply_checked_images(' in official
    assert 'save_selected_art(' in service
