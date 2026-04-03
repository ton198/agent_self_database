from __future__ import annotations

import logging
import os
import queue
import threading
import time

import typer
from dotenv import load_dotenv

from pk_agent.capture.screenshot import (
    frame_fingerprint,
    grab_active_window,
    grab_primary_monitor,
    mean_abs_diff,
)
from pk_agent.capture.visual_context import (
    build_visual_context_png,
    cursor_relative_to_capture,
)
from pk_agent.capture.win_focus import (
    get_cursor_screen_pos,
    get_foreground_info,
    prepare_windows_capture,
)
from pk_agent.config import load_settings
from pk_agent.latest_frame import LatestFrame, LatestFrameSnapshot, format_rag_fallback
from pk_agent.pipeline.ingest import ScreenMergeBuffer
from pk_agent.proactive import proactive_tick
from pk_agent.storage.db import init_db, make_engine
from pk_agent.storage.vector import VectorStore
from pk_agent.notify.popup import start_ui_loop

load_dotenv()

app = typer.Typer(no_args_is_help=True)
log = logging.getLogger(__name__)


def _configure_logging(*, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Third-party noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    if verbose:
        logging.getLogger("pk_agent").setLevel(logging.DEBUG)


def _capture_loop(
    stop: threading.Event,
    settings,
    session,
    buffer: ScreenMergeBuffer,
    latest_frame: LatestFrame,
) -> None:
    last_fp = None
    while not stop.is_set():
        try:
            if settings.capture_active_window_only:
                got = grab_active_window()
                if got is None:
                    if os.name == "nt":
                        log.debug(
                            "capture: skip tick (no foreground rect, e.g. minimized)"
                        )
                        stop.wait(settings.capture_interval_seconds)
                        continue
                    img, ox, oy = grab_primary_monitor()
                    log.debug(
                        "capture: active window only supported on Windows; using full screen"
                    )
                else:
                    img, ox, oy = got
            else:
                img, ox, oy = grab_primary_monitor()

            fp = frame_fingerprint(img)
            if last_fp is not None:
                if mean_abs_diff(fp, last_fp) < settings.frame_diff_threshold:
                    app_name, title = get_foreground_info()
                    snap = latest_frame.snapshot()
                    if snap.image_png:
                        if (app_name, title) != (
                            snap.app_name,
                            snap.window_title,
                        ):
                            latest_frame.update_focus_meta(
                                app_name=app_name, window_title=title
                            )
                        else:
                            latest_frame.add_static_time(
                                settings.capture_interval_seconds
                            )
                    stop.wait(settings.capture_interval_seconds)
                    continue
            last_fp = fp

            app_name, title = get_foreground_info()
            cur = get_cursor_screen_pos()
            crel = cursor_relative_to_capture(
                cur, ox, oy, img.width, img.height
            )
            png = build_visual_context_png(
                img,
                crel,
                max_side=settings.vision_max_image_side,
            )
            snap_for_rag = format_rag_fallback(
                LatestFrameSnapshot(
                    app_name=app_name,
                    window_title=title,
                    image_png=png,
                    cursor_rel=crel,
                )
            )
            mode = "active_window" if settings.capture_active_window_only else "full_screen"
            log.info(
                "capture: %s app=%r title=%r png_bytes=%d size=%dx%d cursor=%s",
                mode,
                app_name,
                (title[:80] + "…") if len(title) > 80 else title,
                len(png),
                img.width,
                img.height,
                crel,
            )
            latest_frame.update(
                image_png=png,
                app_name=app_name,
                window_title=title,
                cursor_rel=crel,
            )
            buffer.push(session, app_name=app_name, window_title=title, text=snap_for_rag)
        except Exception as e:
            log.exception("capture tick failed: %s", e)
        stop.wait(settings.capture_interval_seconds)
    try:
        buffer.flush(session)
        session.commit()
    except Exception:
        log.exception("flush on stop")


@app.command()
def run(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="DEBUG logs for pk_agent (e.g. each capture tick).",
    ),
) -> None:
    """Start screen capture ingest + proactive agent + popup UI."""
    _configure_logging(verbose=verbose)
    settings = load_settings()
    if os.name == "nt":
        prepare_windows_capture()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.db_path)
    SessionLocal = init_db(engine)
    vector = VectorStore(settings.chroma_path)
    buffer = ScreenMergeBuffer(settings=settings, vector=vector)
    latest_frame = LatestFrame()

    stop = threading.Event()
    notify_q: queue.Queue[tuple[str, str]] = queue.Queue()

    cap_session = SessionLocal()

    def capture_worker() -> None:
        try:
            _capture_loop(stop, settings, cap_session, buffer, latest_frame)
        finally:
            cap_session.close()

    def proactive_worker() -> None:
        sess = SessionLocal()
        try:
            while not stop.wait(settings.proactive_interval_seconds):
                try:
                    proactive_tick(settings, sess, vector, notify_q, latest_frame)
                except Exception:
                    log.exception("proactive tick failed")
        finally:
            sess.close()

    threading.Thread(target=capture_worker, name="capture", daemon=True).start()
    threading.Thread(target=proactive_worker, name="proactive", daemon=True).start()
    log.info(
        "run: started capture + proactive (interval=%ss, gate=%s, hint=%s, region=%s)",
        settings.proactive_interval_seconds,
        settings.claude_gate_model,
        settings.claude_model,
        "active_window" if settings.capture_active_window_only else "full_screen",
    )

    try:
        start_ui_loop(notify_q, stop)
    finally:
        stop.set()
        time.sleep(0.3)


@app.command()
def doctor() -> None:
    """Quick checks: data dir, sqlite, chroma, env keys."""
    _configure_logging(verbose=False)
    settings = load_settings()
    typer.echo(f"data_dir: {settings.data_dir.resolve()}")
    typer.echo(f"Claude gate model (cloud): {settings.claude_gate_model}")
    typer.echo(f"Claude gen model: {settings.claude_model}")
    typer.echo(
        f"Capture region: {'active window only' if settings.capture_active_window_only else 'full screen'}"
    )
    typer.echo(f"Vision max image side: {settings.vision_max_image_side}")
    if settings.anthropic_base_url.strip():
        typer.echo(f"Anthropic base URL: {settings.anthropic_base_url.rstrip('/')}")
    typer.echo(f"ANTHROPIC_API_KEY set: {bool(settings.anthropic_api_key.strip())}")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.db_path)
    init_db(engine)
    VectorStore(settings.chroma_path)
    typer.echo("sqlite + chroma paths OK")


if __name__ == "__main__":
    app()
