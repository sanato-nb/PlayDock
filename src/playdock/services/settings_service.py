"""AI 자격 증명과 모델·폴더 설정의 저장 작업.

화면 객체를 참조하지 않고, 기존 settings.json 및 Windows keyring 동작을 유지한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from ai_providers import (
    PROVIDERS, current_provider, current_models, get_secret, set_secret,
    provider_details, save_provider_settings,
)
from setup_paths import proposed_paths, save_folder_settings


@dataclass(frozen=True)
class ProviderPreferences:
    text_model: str
    hint: str
    has_key: bool
    key_required: bool


def load_provider_preferences(library, provider: str) -> ProviderPreferences:
    details = provider_details(provider)
    text_model, _unused_image_model = current_models(library, provider)
    key_required = provider != "ollama"
    return ProviderPreferences(
        text_model=text_model,
        hint=details["hint"],
        has_key=bool(get_secret(provider)) if key_required else False,
        key_required=key_required,
    )


def save_provider_preferences(
    library, provider: str, text_model: str, *, api_key: str = "", delete_key: bool = False
) -> None:
    """기존 비밀키 처리 순서와 저장되지 않는 이미지 모델 설정을 유지한다."""
    provider_details(provider)
    if not text_model.strip() or len(text_model.strip()) > 160:
        raise ValueError("게임 이름 모델을 입력해 주세요.")
    if provider != "ollama":
        if delete_key:
            set_secret(provider, "")
        elif api_key.strip():
            set_secret(provider, api_key)
    saved_image_model = current_models(library, provider)[1]
    save_provider_settings(library, provider, text_model, saved_image_model)
