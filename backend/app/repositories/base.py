"""Repository pattern sobre SQLAlchemy.

Regra: NENHUMA rota escreve SQL nem monta select. Toda leitura e escrita passa
por um repositorio, e toda listagem e PAGINADA (nunca SELECT sem limite).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from math import ceil
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.base import Base

T = TypeVar("T", bound=Base)

MAX_POR_PAGINA = 200


@dataclass(slots=True)
class Page(Generic[T]):
    itens: list[T]
    total: int
    pagina: int
    por_pagina: int

    @property
    def paginas(self) -> int:
        return max(1, ceil(self.total / self.por_pagina)) if self.por_pagina else 1

    @property
    def tem_proxima(self) -> bool:
        return self.pagina < self.paginas

    def to_dict(self, serializer) -> dict[str, Any]:  # noqa: ANN001
        return {
            "itens": [serializer(i) for i in self.itens],
            "total": self.total,
            "pagina": self.pagina,
            "por_pagina": self.por_pagina,
            "paginas": self.paginas,
        }


class Repository(Generic[T]):
    model: type[T]

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- escrita --------------------------------------------------------------
    def add(self, obj: T) -> T:
        self.session.add(obj)
        self.session.flush()
        return obj

    def add_all(self, objs: list[T]) -> list[T]:
        self.session.add_all(objs)
        self.session.flush()
        return objs

    # -- leitura --------------------------------------------------------------
    def get(self, id_: uuid.UUID, user_id: uuid.UUID | None = None) -> T | None:
        stmt = select(self.model).where(self.model.id == id_)
        if user_id is not None and hasattr(self.model, "user_id"):
            stmt = stmt.where(self.model.user_id == user_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def contar(self, stmt: Select) -> int:
        sub = stmt.order_by(None).subquery()
        return int(self.session.execute(select(func.count()).select_from(sub)).scalar_one())

    def paginar(self, stmt: Select, pagina: int = 1, por_pagina: int = 25) -> Page[T]:
        pagina = max(1, int(pagina))
        por_pagina = max(1, min(int(por_pagina), MAX_POR_PAGINA))
        total = self.contar(stmt)
        itens = (
            self.session.execute(stmt.limit(por_pagina).offset((pagina - 1) * por_pagina))
            .scalars()
            .all()
        )
        return Page(itens=list(itens), total=total, pagina=pagina, por_pagina=por_pagina)

    # -- soft delete ----------------------------------------------------------
    def vivos(self, stmt: Select) -> Select:
        if hasattr(self.model, "deleted_at"):
            return stmt.where(self.model.deleted_at.is_(None))
        return stmt
