from refactor_test_support import launcher_source, editor_source
"""Regression tests for searchable real artwork (no generative image UI)."""
from pathlib import Path
_ui_main = launcher_source()



ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8') + _ui_main
DIALOG = (ROOT / 'src/playdock/ui/artwork_dialog.py').read_text(encoding='utf-8')


def test_search_is_direct_action_and_not_generated():
    assert 'image_search_button = self.action_button("인터넷 이미지 검색·편집", self.open_online_artwork)' in APP
    assert 'def open_online_artwork(self):' in APP
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

def test_dialog_is_candidate_crop_workflow_and_auto_searches():
    assert 'QTimer.singleShot(0, self._initial_search)' in DIALOG
    assert '이미지 검색' in DIALOG
    assert '선택 · 편집' in DIALOG
    assert 'CropEditor(' in DIALOG
    assert 'self.artwork_actions.apply_selection(' in DIALOG
    service = (ROOT / 'src/playdock/services/artwork_service.py').read_text(encoding='utf-8')
    assert 'save_selected_art(' in service
