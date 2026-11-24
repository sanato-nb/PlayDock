"""Optional AI providers shared by PlayDock and Title Editor.

No API requests happen on import or while saving settings. Keys live in the OS
credential manager via keyring, not in settings.json or the portable data dir.
This module intentionally uses only the standard library + keyring (on demand).
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import quote
from urllib import request, error

SERVICE = "PlayDock"
LEGACY_SERVICE = "LocalGameShelf"
# image/image_model are legacy settings metadata only, not supported generation capabilities.
# Preserve stored model values and existing settings-service round trips.
PROVIDERS = {
    "openai": {
        "name": "OpenAI", "text_model": "gpt-4.1-mini", "image_model": "gpt-image-1-mini",
        "image": True, "hint": "OpenAI Platform에서 발급한 API 키가 필요합니다.",
    },
    "gemini": {
        "name": "Google Gemini", "text_model": "gemini-3.8-flash", "image_model": "",
        "image": True, "hint": "Google AI Studio API 키가 필요합니다. 게임 이름 추천에만 사용합니다.",
    },
    "anthropic": {
        "name": "Anthropic Claude", "text_model": "claude-haiku-4-5-20251001", "image_model": "",
        "image": False, "hint": "Anthropic Console API 키. 게임 이름 추천만 지원합니다.",
    },
    "openrouter": {
        "name": "OpenRouter", "text_model": "google/gemini-2.5-flash", "image_model": "bytedance-seed/seedream-4.5",
        "image": True, "hint": "OpenRouter API 키가 필요합니다. 게임 이름 추천에만 사용합니다.",
    },
    "ollama": {
        "name": "Ollama (내 PC)", "text_model": "gemma3:4b", "image_model": "",
        "image": False, "hint": "API 키 없이 로컬 Ollama(http://127.0.0.1:11434)에 연결합니다. 먼저 모델을 설치하세요.",
    },
}
ENV_KEYS = {
    "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY",
}


def provider_details(name: str) -> dict:
    if name not in PROVIDERS:
        raise ValueError("지원하지 않는 AI 서비스입니다.")
    return PROVIDERS[name]


def get_secret(name: str) -> str:
    provider_details(name)
    if name == "ollama":
        return ""
    env = os.getenv(ENV_KEYS[name], "").strip()
    if env:
        return env
    try:
        import keyring
        return (keyring.get_password(SERVICE, name) or keyring.get_password(LEGACY_SERVICE, name) or "").strip()
    except Exception:
        return ""


def set_secret(name: str, value: str) -> None:
    provider_details(name)
    if name == "ollama":
        raise ValueError("Ollama는 API 키가 필요하지 않습니다.")
    try:
        import keyring
        if value.strip():
            keyring.set_password(SERVICE, name, value.strip())
        # Never leave an obsolete legacy credential that would resurrect a
        # deleted PlayDock key. Credentials are never embedded in the release.
        for service in (LEGACY_SERVICE,) if value.strip() else (SERVICE, LEGACY_SERVICE):
            try:
                keyring.delete_password(service, name)
            except keyring.errors.PasswordDeleteError:
                pass
    except Exception as exc:
        raise RuntimeError("API 키 저장 실패: Windows 자격 증명 저장소(keyring)를 확인하세요.") from exc


def current_provider(library) -> str:
    value = library.settings.get("ai_provider", "openai")
    return value if value in PROVIDERS else "openai"


def current_models(library, provider: str | None = None) -> tuple[str, str]:
    provider = provider or current_provider(library)
    defaults = provider_details(provider)
    settings = library.settings.get("ai_models", {})
    selected = settings.get(provider, {}) if isinstance(settings, dict) else {}
    if not isinstance(selected, dict):
        selected = {}
    text_model = str(selected.get("text") or defaults["text_model"]).strip()
    # Google's 2.5 Flash access is restricted for new projects. Previously,
    # the app saved this model as its default; use the supported replacement
    # while leaving unrelated custom model choices untouched.
    if provider == 'gemini' and text_model == 'gemini-2.5-flash':
        text_model = 'gemini-3.8-flash'
    return text_model, str(selected.get("image") or defaults["image_model"]).strip()


def save_provider_settings(library, provider: str, text_model: str, image_model: str) -> None:
    details = provider_details(provider)
    text_model = text_model.strip()
    if provider == 'gemini' and text_model == 'gemini-2.5-flash':
        text_model = 'gemini-3.8-flash'
    image_model = image_model.strip()
    if not text_model or len(text_model) > 160 or len(image_model) > 160:
        raise ValueError("모델 이름을 확인하세요 (1~160자).")
    models = library.settings.get("ai_models", {})
    models = dict(models) if isinstance(models, dict) else {}
    models[provider] = {"text": text_model, "image": image_model if details["image"] else ""}
    library.settings["ai_provider"] = provider
    library.settings["ai_models"] = models
    library.save_settings()


def require_access(provider: str) -> str:
    provider_details(provider)
    if provider == "ollama":
        return ""
    key = get_secret(provider)
    if not key:
        raise RuntimeError(f"{PROVIDERS[provider]['name']} API 키를 환경 변수 또는 기존 Windows 자격 증명 저장소에서 확인해 주세요.")
    return key


def _safe_api_error(status: int, raw: bytes, url: str, retry_after: str = "") -> str:
    """Turn a bounded provider error into actionable text, without credentials.

    Gemini errors may contain quota details; read the complete small JSON body
    rather than truncating it mid-document and replacing it with a generic 429.
    """
    is_gemini = "generativelanguage.googleapis.com" in url
    message = ""
    quota_details = []
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
        error_obj = payload.get("error", payload) if isinstance(payload, dict) else {}
        if isinstance(error_obj, dict):
            message = str(error_obj.get("message") or "")
            for detail in error_obj.get("details", []) or []:
                if not isinstance(detail, dict):
                    continue
                for violation in detail.get("violations", []) or []:
                    if isinstance(violation, dict):
                        metric = str(violation.get("quotaMetric") or violation.get("quotaId") or "").split("/")[-1]
                        limit = violation.get("quotaValue")
                        if metric:
                            quota_details.append((metric[:90], str(limit)[:20] if limit is not None else ""))
        elif isinstance(error_obj, str):
            message = error_obj
    except (ValueError, UnicodeError, TypeError):
        pass

    # Never reflect tokens or credentials that providers might echo in messages.
    message = re.sub(r"AIza[0-9A-Za-z_-]{12,}", "[API 키 숨김]", message)
    message = re.sub(r"sk-[0-9A-Za-z_-]{12,}", "[API 키 숨김]", message)
    message = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)\S+", r"\1[숨김]", message)
    message = " ".join(message.split())[:650]
    if status == 429 and is_gemini:
        zero = any(limit == "0" for _, limit in quota_details)
        if not zero:
            zero = bool(re.search(r"(?:limit|quota(?:Value)?)\s*[:=]\s*0(?:\D|$)", message, re.I))
        if zero:
            guide = ("이 Gemini 모델의 할당량이 0으로 설정되어 있습니다. "
                     "특히 이미지 생성 모델은 무료 등급에서 지원되지 않을 수 있습니다. "
                     "다른 무료 지원 모델을 선택하거나 Google AI Studio에서 요금제·할당량을 확인하세요.")
        else:
            guide = ("Gemini 모델별 요청/토큰/일일 할당량 초과 또는 무료 등급 제한일 수 있습니다. "
                     "Google AI Studio에서 해당 모델의 할당량을 확인하세요.")
        parts = ["Gemini API HTTP 429 — 사용 한도 초과", guide]
        if message:
            parts.append("서버 응답: " + message)
        if quota_details:
            parts.append("제한 항목: " + "; ".join(f"{m} (한도 {lim or '미표시'})" for m, lim in quota_details[:3]))
        if retry_after and retry_after.isdigit() and int(retry_after) < 3600:
            parts.append("재시도 안내: 약 " + retry_after + "초 후")
        parts.append("할당량 확인: https://aistudio.google.com/rate-limit")
        return "\n".join(parts)
    if status == 429:
        return f"AI API HTTP 429 — 요청 제한 또는 사용량 한도 초과. {message or '모델별 할당량을 확인해 주세요.'}"
    return f"AI API HTTP {status}: {message or '요청에 실패했습니다.'}"


def http_json(url: str, body: dict, headers: dict[str, str], *, max_bytes=2 * 1024**2, timeout=120) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json", "Accept": "application/json",
                       "User-Agent": "PlayDock/0.6.2", **headers}
    req = request.Request(url, data=data, headers=request_headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
    except error.HTTPError as exc:
        # 16 KiB is enough for Gemini's quota details without printing headers.
        raw_error = exc.read(16 * 1024)
        retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
        detail = _safe_api_error(exc.code, raw_error, url, retry_after)
        # One more defense if a service ever echoes a secret verbatim.
        for name, value in headers.items():
            if name.lower() in ("authorization", "x-goog-api-key", "x-api-key"):
                for secret in (value, value.removeprefix("Bearer ")):
                    if secret and len(secret) > 12:
                        detail = detail.replace(secret, "[API 키 숨김]")
        raise RuntimeError(detail) from exc
    except error.URLError as exc:
        raise RuntimeError("AI 서비스에 연결하지 못했습니다. 인터넷 또는 Ollama 실행 상태를 확인하세요.") from exc
    if len(raw) > max_bytes:
        raise ValueError("AI 응답 크기 제한을 초과했습니다.")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("AI 서비스의 응답이 올바른 JSON이 아닙니다.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("AI 서비스의 응답 형식이 올바르지 않습니다.")
    return parsed


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    return json.loads(text)


def _text_response(provider: str, model: str, prompt: str, api_key: str) -> str:
    if provider == "openai":
        result = http_json("https://api.openai.com/v1/responses", {
            "model": model, "max_output_tokens": 220,
            "input": [{"role": "user", "content": prompt}],
        }, {"Authorization": f"Bearer {api_key}"})
        return "".join(chunk.get("text", "") for output in result.get("output", [])
                       for chunk in output.get("content", []) if chunk.get("type") == "output_text")
    if provider == "gemini":
        result = http_json("https://generativelanguage.googleapis.com/v1beta/models/"
                           + quote(model, safe="") + ":generateContent", {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 400},
        }, {"x-goog-api-key": api_key})
        return "".join(part.get("text", "") for can in result.get("candidates", [])
                       for part in can.get("content", {}).get("parts", []) if isinstance(part.get("text"), str))
    if provider == "anthropic":
        result = http_json("https://api.anthropic.com/v1/messages", {
            "model": model, "max_tokens": 220,
            "messages": [{"role": "user", "content": prompt}],
        }, {"x-api-key": api_key, "anthropic-version": "2026-10-21"})
        return "".join(p.get("text", "") for p in result.get("content", []) if p.get("type") == "text")
    if provider == "openrouter":
        result = http_json("https://openrouter.ai/api/v1/chat/completions", {
            "model": model, "max_tokens": 240,
            "messages": [{"role": "user", "content": prompt}],
        }, {"Authorization": f"Bearer {api_key}", "X-Title": "PlayDock"})
        content = (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if p.get("type") == "text")
        return str(content)
    if provider == "ollama":
        # Fixed loopback address: no API key is ever sent to this endpoint.
        result = http_json("http://127.0.0.1:11434/api/generate", {
            "model": model, "prompt": prompt, "stream": False, "format": "json",
        }, {}, timeout=180)
        return str(result.get("response", ""))
    raise ValueError("지원하지 않는 AI 서비스입니다.")


def recommend_title(raw: str, provider: str, model: str, api_key: str) -> str:
    """Return original title unless a model confidently identifies a better one."""
    provider_details(provider)
    prompt = ("Recognize a game title from this local archive/folder filename. "
              "Preserve version, language and patch notes if present. "
              "Never invent identity from an RJ code alone. If unsure, return the filename unchanged. "
              'Return ONLY JSON: {"title":string,"confidence":number}. '
              f"Filename: {raw!r}")
    text = _text_response(provider, model, prompt, api_key)
    try:
        result = _extract_json(text)
        title = str(result.get("title", "")).strip()
        if title and float(result.get("confidence", 0)) >= 0.8:
            return title[:150]
    except (ValueError, TypeError, KeyError):
        pass
    return raw

