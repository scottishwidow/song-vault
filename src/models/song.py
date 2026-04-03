from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SongStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    artist_or_source: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    tempo_bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[SongStatus] = mapped_column(
        Enum(
            SongStatus,
            name="song_status",
            values_callable=lambda members: [member.value for member in members],
        ),
        default=SongStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
