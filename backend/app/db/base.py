"""Base declarativa e mixins compartilhados."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import new_id


class Base(DeclarativeBase):
    """Base de todos os modelos."""


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDelete:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
