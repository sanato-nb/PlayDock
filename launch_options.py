"""Persist non-shell per-game launch arguments. Never pass commands through shell."""
from __future__ import annotations

import shlex


def parse_game_arguments(raw: str) -> list[str]:
    if not isinstance(raw, str) or len(raw) > 2048 or any(c in raw for c in '\r\n\x00'):
        raise ValueError('실행 인수는 2,048자 이하 한 줄만 입력할 수 있습니다.')
    if not raw.strip():
        return []
    # posix=False preserves Windows backslashes; remove surrounding paired quotes
    # on individual tokens, which QProcess will then re-escape for Windows.
    try:
        tokens = shlex.split(raw, posix=False)
    except ValueError as exc:
        raise ValueError('실행 인수의 따옴표 구성이 올바르지 않습니다.') from exc
    normalized = []
    for t in tokens:
        if t.startswith('"') != t.endswith('"'):
            raise ValueError('실행 인수의 따옴표가 맞지 않습니다.')
        if t.startswith('"') and t.endswith('"') and len(t) >= 2:
            t = t[1:-1]
        normalized.append(t)
    return normalized
