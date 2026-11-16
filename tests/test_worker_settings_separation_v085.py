"""v0.8.4 이후 UI 작업자와 설정 저장 분리 회귀 검사."""
import ast
from pathlib import Path

import pytest

from services import settings_service as settings


ROOT = Path(__file__).resolve().parents[1] / "src" / "playdock"


def _classes(relative):
    src = (ROOT / relative).read_text(encoding="utf-8")
    return {node.name for node in ast.parse(src).body if isinstance(node, ast.ClassDef)}


def test_network_workers_live_in_services_without_ui_widget_logic():
    assert {"SearchJob", "DownloadJob", "IdentityJob"} <= _classes("services/artwork_workers.py")
    assert not {"SearchJob", "DownloadJob", "IdentityJob"} & _classes("ui/artwork_dialog.py")
    assert "WorkLookupThread" in _classes("services/work_lookup_worker.py")
    assert "WorkLookupThread" not in _classes("ui/work_info_dialog.py")
    assert "from services.artwork_workers import SearchJob, DownloadJob, IdentityJob" in (
        ROOT / "ui/artwork_dialog.py").read_text(encoding="utf-8")
    assert "from services.work_lookup_worker import WorkLookupThread" in (
        ROOT / "ui/work_info_dialog.py").read_text(encoding="utf-8")


class FakeLibrary:
    def __init__(self):
        self.settings = {
            "ai_provider": "openai",
            "ai_models": {"openai": {"text": "old-model", "image": "old-image"}},
        }
        self.saves = 0

    def save_settings(self):
        self.saves += 1


def test_settings_service_keeps_unused_image_field_and_secret_out_of_json(monkeypatch):
    library = FakeLibrary()
    writes = []
    monkeypatch.setattr(settings, "set_secret", lambda provider, key: writes.append((provider, key)))
    monkeypatch.setattr(settings, "get_secret", lambda provider: "saved")
    snapshot = settings.load_provider_preferences(library, "openai")
    assert snapshot.text_model == "old-model"
    assert snapshot.has_key and snapshot.key_required
    settings.save_provider_preferences(library, "openai", "new-model", api_key="new-secret")
    assert writes == [("openai", "new-secret")]
    assert library.settings["ai_models"]["openai"] == {"text": "new-model", "image": "old-image"}
    assert "new-secret" not in repr(library.settings)
    assert library.saves == 1


def test_invalid_settings_do_not_delete_key_or_modify_configuration(monkeypatch):
    library = FakeLibrary()
    writes = []
    monkeypatch.setattr(settings, "set_secret", lambda provider, key: writes.append((provider, key)))
    with pytest.raises(ValueError):
        settings.save_provider_preferences(library, "openai", " ", delete_key=True)
    assert not writes
    assert library.settings["ai_models"]["openai"]["text"] == "old-model"
    assert library.saves == 0


def test_ollama_settings_never_write_credentials(monkeypatch):
    library = FakeLibrary()
    monkeypatch.setattr(settings, "set_secret", lambda *_: pytest.fail("Ollama should not touch keyring"))
    snapshot = settings.load_provider_preferences(library, "ollama")
    assert not snapshot.key_required and not snapshot.has_key
    settings.save_provider_preferences(library, "ollama", "gemma3:4b", api_key="ignored", delete_key=True)
    assert library.settings["ai_provider"] == "ollama"
    assert library.saves == 1
