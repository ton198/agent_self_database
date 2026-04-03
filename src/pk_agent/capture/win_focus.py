"""Foreground window title, process name, and window rect (Windows ctypes)."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shcore = None
try:
    shcore = ctypes.windll.shcore
except OSError:
    pass

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

HWND = wintypes.HWND
BOOL = wintypes.BOOL

_win_capture_inited = False


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _ensure_win32_capture_ready() -> None:
    """
    Once per process: DPI awareness so GetWindowRect matches physical pixels (mss),
    and correct HWND ctypes so 64-bit handles are not truncated.
    """
    global _win_capture_inited
    if _win_capture_inited or os.name != "nt":
        return
    _win_capture_inited = True

    # Per-monitor DPI → logical coords from WinAPI match what GDI/mss use
    if shcore is not None:
        try:
            # 2 = PROCESS_PER_MONITOR_DPI_AWARE
            shcore.SetProcessDpiAwareness(2)
        except OSError:
            try:
                user32.SetProcessDPIAware()
            except OSError:
                pass
    else:
        try:
            user32.SetProcessDPIAware()
        except OSError:
            pass

    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = HWND

    user32.IsIconic.argtypes = [HWND]
    user32.IsIconic.restype = BOOL

    user32.GetWindowRect.argtypes = [HWND, ctypes.POINTER(_RECT)]
    user32.GetWindowRect.restype = BOOL

    user32.GetWindowTextLengthW.argtypes = [HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int

    user32.GetWindowTextW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
    user32.GetCursorPos.restype = BOOL


def prepare_windows_capture() -> None:
    """Call once at app startup before Tk or capture threads (DPI + HWND ctypes)."""
    if os.name == "nt":
        _ensure_win32_capture_ready()


def get_foreground_window_rect() -> tuple[int, int, int, int] | None:
    """
    Screen pixel rect of the foreground window: (left, top, width, height).
    None if unavailable, minimized, or degenerate. Windows only.
    """
    if os.name != "nt":
        return None

    _ensure_win32_capture_ready()

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    if user32.IsIconic(hwnd):
        return None

    rect = _RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None

    left = int(rect.left)
    top = int(rect.top)
    w = int(rect.right - rect.left)
    h = int(rect.bottom - rect.top)
    if w < 8 or h < 8:
        return None
    return left, top, w, h


def get_cursor_screen_pos() -> tuple[int, int] | None:
    """Physical screen coordinates of the cursor. Windows only."""
    if os.name != "nt":
        return None
    _ensure_win32_capture_ready()
    pt = _POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return None
    return int(pt.x), int(pt.y)


def get_foreground_info() -> tuple[str, str]:
    """Return (app_name_or_empty, window_title). Non-Windows: ('', '')."""
    if os.name != "nt":
        return "", ""

    _ensure_win32_capture_ready()

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""

    length = user32.GetWindowTextLengthW(hwnd) + 1
    title_buf = ctypes.create_unicode_buffer(length)
    user32.GetWindowTextW(hwnd, title_buf, length)
    title = title_buf.value or ""

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return "", title

    access = PROCESS_QUERY_LIMITED_INFORMATION
    proc = kernel32.OpenProcess(access, False, pid.value)
    if not proc:
        return "", title

    try:
        size = wintypes.DWORD(1024)
        path_buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(proc, 0, path_buf, ctypes.byref(size)):
            full = path_buf.value
            app = os.path.basename(full) if full else ""
            return app, title
    finally:
        kernel32.CloseHandle(proc)

    return "", title
