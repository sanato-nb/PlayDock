"""Resolve the independently packaged game title editor next to the launcher.

No shell invocation: game IDs are passed as argv strings, never interpolated
into a command line. The game files and AppData are not accessed here.
"""
from __future__ import annotations

import sys
from pathlib import Path


EDITOR_EXE = 'PlayDock_TitleEditor.exe'


def title_editor_command(*, executable: Path | None = None,
                         frozen: bool | None = None,
                         source_dir: Path | None = None,
                         game_id: str | None = None) -> tuple[str, list[str], str]:
    """Return (program, arguments, cwd) for installed EXE or source checkout.

    Missing installed editor is an error, rather than silently launching a
    Python source file inside the onefile extraction directory.
    """
    app_exe = Path(executable) if executable is not None else Path(sys.executable)
    packaged = bool(getattr(sys, 'frozen', False)) if frozen is None else frozen
    if packaged:
        target = app_exe.absolute().parent / EDITOR_EXE
        if not target.is_file():
            raise FileNotFoundError(f'게임 이름 관리자를 찾을 수 없습니다: {target}\n'
                                    '설치 프로그램으로 두 EXE를 함께 설치해 주세요.')
        program, arguments, working = str(target), [], str(target.parent)
    else:
        root = Path(source_dir) if source_dir is not None else Path(__file__).resolve().parent
        script = root / 'title_editor.py'
        if not script.is_file():
            raise FileNotFoundError(f'게임 이름 관리자 소스를 찾을 수 없습니다: {script}')
        program, arguments, working = str(app_exe), [str(script)], str(root)
    if game_id:
        arguments.extend(['--game-id', game_id])
    return program, arguments, working
