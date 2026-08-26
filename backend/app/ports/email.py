"""Porta de e-mail — canal PADRAO da abordagem (e-mail-first)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ports.dto import EmailMessage, SendResult


@runtime_checkable
class EmailPort(Protocol):
    provedor: str
    modo: str

    def enviar(self, mensagem: EmailMessage) -> SendResult:
        ...
