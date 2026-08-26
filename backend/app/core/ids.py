"""Identificadores e utilitarios de tempo (UTC sempre)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def now() -> datetime:
    return datetime.now(UTC)


def request_id() -> str:
    return uuid.uuid4().hex[:16]
