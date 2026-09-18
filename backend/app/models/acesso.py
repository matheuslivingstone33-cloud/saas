from __future__ import annotations

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk


class TentativaDeAcesso(Base, UUIDPk, Timestamps):
    """Cada login e cada cadastro, com o IP de onde veio.

    Serve a duas coisas: travar quem testa senha em serie (e quem cria conta
    em serie para ganhar credito), e ser o registro de acesso que o Marco Civil
    (art. 15) manda guardar por 6 meses. Depois disso, a retencao apaga.
    """

    __tablename__ = "tentativas_acesso"
    __table_args__ = (
        Index("ix_tentativas_acesso_email", "email_normalizado", "created_at"),
        Index("ix_tentativas_acesso_ip", "ip", "created_at"),
    )

    #: "login" ou "cadastro". Texto e nao enum: valor novo de enum exige
    #: migration nos dois dialetos, e aqui nao ha regra que dependa do tipo.
    acao: Mapped[str] = mapped_column(String(20), nullable=False)
    email_normalizado: Mapped[str | None] = mapped_column(String(320))
    ip: Mapped[str | None] = mapped_column(String(64))
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TentativaDeAcesso {self.acao} {self.sucesso}>"
