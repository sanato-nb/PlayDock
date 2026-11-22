"""Verify an AI-filled rename_games.ps1 against the frozen PlayDock code.

This checks exact fixed-code integrity and the editable JSON name mapping.
It does NOT claim the AI's researched IDs are correct: user approval remains needed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .rename_template import PS1_TEMPLATE

_HEADER = "$renameJson = @'\n"
_FOOTER = "\n'@\n# ===== END AI RULES ====="
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
_RESERVED = re.compile(r"(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)")


@dataclass(frozen=True)
class RenameValidation:
    number_of_rules: int
    rules: tuple[tuple[str, str], ...]


def _no_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"AI 목록에 중복 JSON 속성이 있습니다: {key}")
        obj[key] = value
    return obj


def _valid_filename(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise ValueError(f"{label}: 파일명이 문자열이 아니거나 너무 깁니다.")
    if _INVALID.search(value) or value[-1] in ". " or _RESERVED.match(value):
        raise ValueError(f"{label}: 금지된 Windows 파일명이 있습니다.")
    suffix = Path(value).suffix
    if suffix.casefold() not in (".zip", ".7z", ".rar"):
        raise ValueError(f"{label}: ZIP/7z/RAR 압축파일 이름만 허용합니다.")
    return value


def verify_rename_script(source: str | Path, *, from_text: bool = False) -> RenameValidation:
    """Verifies the immutable PowerShell body byte-for-byte after CRLF normalization.

    Only contents of $renameJson here-string may differ. This is independent
    of the script's own checksum and survives changing an embedded expected hash.
    """
    if from_text:
        content = str(source)
    else:
        content = Path(source).read_text(encoding="utf-8-sig")
    content = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")

    if PS1_TEMPLATE.count(_HEADER) != 1 or PS1_TEMPLATE.count(_FOOTER) != 1:
        raise RuntimeError("배포용 PowerShell 템플릿이 손상됐습니다.")
    begin = PS1_TEMPLATE.index(_HEADER) + len(_HEADER)
    stop = PS1_TEMPLATE.index(_FOOTER, begin)
    expected_head = PS1_TEMPLATE[:begin]
    expected_tail = PS1_TEMPLATE[stop:]

    if not (content.startswith(expected_head) and content.endswith(expected_tail)):
        raise ValueError(
            "기본 PS1 코드가 수정됐습니다. AI가 JSON 변경 목록 이외의 코드를 수정했거나 "
            "코드 전체를 제공하지 않았습니다."
        )
    payload = content[len(expected_head):len(content) - len(expected_tail)]
    if _FOOTER in payload or "$renameJson = @'" in payload or "\n'@" in payload:
        raise ValueError("AI의 변경 데이터 영역 경계가 손상됐습니다.")
    try:
        rules = json.loads(payload, object_pairs_hook=_no_duplicate_json_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"AI의 이름 변경 JSON 형식이 잘못됐습니다: {exc}") from exc
    if not isinstance(rules, list):
        raise ValueError("AI의 이름 변경 데이터는 JSON 배열이어야 합니다.")
    if len(rules) > 1000:
        raise ValueError("변경 규칙은 한 번에 1000개까지 허용합니다.")
    parsed = []
    seen_old: set[str] = set()
    seen_new: set[str] = set()
    for n, rule in enumerate(rules, 1):
        if not isinstance(rule, dict) or set(rule) != {"OldName", "NewName"}:
            raise ValueError(f"{n}번 규칙에는 OldName과 NewName 두 속성만 허용합니다.")
        old = _valid_filename(rule["OldName"], f"{n}번 원래 이름")
        new = _valid_filename(rule["NewName"], f"{n}번 변경 이름")
        if Path(old).suffix.casefold() != Path(new).suffix.casefold():
            raise ValueError(f"{n}번 규칙이 압축파일의 확장자를 변경하려고 합니다.")
        if old.casefold() == new.casefold():
            raise ValueError(f"{n}번 규칙은 이름이 실제로 바뀌지 않습니다.")
        if old.casefold() in seen_old or new.casefold() in seen_new:
            raise ValueError(f"{n}번 규칙에 중복 파일명이 있습니다.")
        seen_old.add(old.casefold())
        seen_new.add(new.casefold())
        parsed.append((old, new))
    return RenameValidation(len(parsed), tuple(parsed))
