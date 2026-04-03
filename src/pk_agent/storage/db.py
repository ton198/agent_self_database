from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def _as_utc_aware(dt: datetime | None) -> datetime | None:
    """SQLite often returns naive datetimes; normalize for Python comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ScreenChunk(Base):
    __tablename__ = "screen_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    app_name: Mapped[str] = mapped_column(String(512), default="")
    window_title: Mapped[str] = mapped_column(String(1024), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)


class NotifyLog(Base):
    __tablename__ = "notify_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    body: Mapped[str] = mapped_column(Text, default="")


def make_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{db_path.as_posix()}",
        future=True,
        connect_args={"check_same_thread": False},
    )


def init_db(engine) -> sessionmaker[Session]:
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False, class_=Session)


def insert_chunk(
    session: Session,
    *,
    app_name: str,
    window_title: str,
    text: str,
    content_hash: str,
) -> str:
    chunk_id = str(uuid.uuid4())
    row = ScreenChunk(
        id=chunk_id,
        created_at=datetime.now(timezone.utc),
        app_name=app_name[:512],
        window_title=window_title[:1024],
        text=text,
        content_hash=content_hash,
    )
    session.add(row)
    session.commit()
    return chunk_id


def recent_chunks_text(session: Session, minutes: int, limit: int = 80) -> str:
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    stmt = (
        select(ScreenChunk)
        .where(ScreenChunk.created_at >= since)
        .order_by(ScreenChunk.created_at.desc())
        .limit(limit)
    )
    rows = list(session.scalars(stmt))
    rows.reverse()
    parts: list[str] = []
    for r in rows:
        head = f"[{r.app_name}] {r.window_title}".strip()
        parts.append(f"{head}\n{r.text}")
    return "\n---\n".join(parts)


def insert_notify_log(session: Session, *, title: str, body: str) -> None:
    row = NotifyLog(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        title=title[:512],
        body=body,
    )
    session.add(row)
    session.commit()


def count_notifies_since(session: Session, since: datetime) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(NotifyLog).where(NotifyLog.created_at >= since)
    return int(session.scalar(stmt) or 0)


def last_notify_time(session: Session) -> datetime | None:
    stmt = select(NotifyLog.created_at).order_by(NotifyLog.created_at.desc()).limit(1)
    return _as_utc_aware(session.scalar(stmt))
