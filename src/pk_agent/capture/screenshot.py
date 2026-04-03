from __future__ import annotations

import logging

import numpy as np
from PIL import Image

import mss

from pk_agent.capture.win_focus import get_foreground_window_rect

log = logging.getLogger(__name__)


def grab_primary_monitor() -> tuple[Image.Image, int, int]:
    """Return (image, origin_left, origin_top) in screen pixels."""
    with mss.mss() as sct:
        mon = sct.monitors[1]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img, int(mon["left"]), int(mon["top"])


def grab_active_window() -> tuple[Image.Image, int, int] | None:
    """
    Capture only the foreground window region (Windows).
    Returns None if not Windows or rect unavailable.
    Image (0,0) matches screen pixel (il, it).
    """
    bounds = get_foreground_window_rect()
    if bounds is None:
        return None
    left, top, w, h = bounds
    with mss.mss() as sct:
        # Clip to virtual desktop (monitor 0) so mss always gets a valid box
        va = sct.monitors[0]
        vx1, vy1 = va["left"], va["top"]
        vx2, vy2 = vx1 + va["width"], vy1 + va["height"]
        il = max(left, vx1)
        it = max(top, vy1)
        ir = min(left + w, vx2)
        ib = min(top + h, vy2)
        cw, ch = ir - il, ib - it
        if cw < 8 or ch < 8:
            return None
        region = {"left": il, "top": it, "width": cw, "height": ch}
        log.debug("grab_active_window region=%s", region)
        raw = sct.grab(region)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img, il, it


def frame_fingerprint(img: Image.Image, size: int = 48) -> np.ndarray:
    """Small grayscale array for cheap change detection."""
    g = img.convert("L").resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(g, dtype=np.float32)


def mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))
