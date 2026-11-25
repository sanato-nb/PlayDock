"""Best-effort dark native window captions for Windows 10/11.

This module is deliberately independent of PySide6 and Tkinter so both the
installed app and the one-file setup wizard can share the same behavior.
"""
from __future__ import annotations

import sys


CAPTION_BG = (18, 20, 22)   # #121416: app top navigation background
CAPTION_FG = (237, 239, 242)  # #edeff2: app title foreground


def windows_dark_caption(hwnd: int) -> bool:
    """Request a dark, native Windows caption without removing window controls.

    Returns False on non-Windows systems and unsupported Windows versions.
    Modern Windows 11 supports DWM caption/background color (35/36); Windows
    10 generally supports immersive dark mode (20, or older 19). These calls
    are safe to ignore if an OS/version does not implement them.
    """
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        dwmapi = ctypes.WinDLL("dwmapi.dll", use_last_error=True)
        setter = dwmapi.DwmSetWindowAttribute
        setter.argtypes = (ctypes.c_void_p, ctypes.c_uint,
                           ctypes.c_void_p, ctypes.c_uint)
        setter.restype = ctypes.c_long  # HRESULT
        handle = ctypes.c_void_p(int(hwnd))

        enabled = ctypes.c_int(1)
        result = setter(handle, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        if result != 0:  # some older Windows 10 builds use 19
            result = setter(handle, 19, ctypes.byref(enabled), ctypes.sizeof(enabled))
        success = result == 0

        for attr, (r, g, b) in ((35, CAPTION_BG), (36, CAPTION_FG)):
            # Windows COLORREF uses BGR, not HTML RGB.
            color = ctypes.c_uint32(r | (g << 8) | (b << 16))
            if setter(handle, attr, ctypes.byref(color), ctypes.sizeof(color)) == 0:
                success = True
        return success
    except (OSError, AttributeError, TypeError, ValueError, OverflowError):
        return False


def darken_tk_root(root) -> bool:
    """Tk child HWND often needs conversion to its real decorated root HWND."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        # GetAncestor(GA_ROOT=2) moves from Tk's content window to the actual
        # decorated top-level HWND, on which DWM attributes take effect.
        user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        user32.GetAncestor.restype = ctypes.c_void_p
        child_hwnd = int(root.winfo_id())
        decorated_hwnd = user32.GetAncestor(ctypes.c_void_p(child_hwnd), 2)
        return windows_dark_caption(decorated_hwnd or child_hwnd)
    except (OSError, AttributeError, TypeError, ValueError, OverflowError):
        return False
