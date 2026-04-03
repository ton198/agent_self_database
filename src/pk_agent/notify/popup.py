from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext

from pk_agent.logutil import one_line

log = logging.getLogger(__name__)


def start_ui_loop(
    message_queue: queue.Queue[tuple[str, str]],
    stop_event: threading.Event,
) -> None:
    """Run Tk mainloop on calling thread; poll queue for (title, body) popups."""

    root = tk.Tk()
    root.withdraw()

    def poll() -> None:
        if stop_event.is_set():
            root.quit()
            return
        try:
            while True:
                title, body = message_queue.get_nowait()
                _show_popup(root, title, body)
        except queue.Empty:
            pass
        root.after(400, poll)

    root.after(400, poll)
    root.mainloop()


def _show_popup(root: tk.Tk, title: str, body: str) -> None:
    log.info(
        "ui: popup title=%s body=%s",
        one_line(title, 100),
        one_line(body, 240),
    )
    win = tk.Toplevel(root)
    win.title(title[:120] or "Hint")
    win.attributes("-topmost", True)
    win.geometry("420x220")
    frm = tk.Frame(win, padx=10, pady=10)
    frm.pack(fill=tk.BOTH, expand=True)
    txt = scrolledtext.ScrolledText(frm, height=8, wrap=tk.WORD, font=("Segoe UI", 10))
    txt.insert(tk.END, body)
    txt.configure(state=tk.DISABLED)
    txt.pack(fill=tk.BOTH, expand=True)

    def close() -> None:
        win.destroy()

    btn = tk.Button(frm, text="OK", command=close)
    btn.pack(pady=(8, 0))
    win.protocol("WM_DELETE_WINDOW", close)
