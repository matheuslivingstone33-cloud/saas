"""Porta de WhatsApp.

GUARDRAIL: nunca disparar WhatsApp frio para pessoa fisica. Uso preferencial e
INBOUND (resposta a quem escreveu). Template ativo so com
settings.whatsapp_template_enabled = True.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ports.dto import SendResult, WhatsAppMessage


@runtime_checkable
class WhatsAppPort(Protocol):
    provedor: str
    modo: str

    def enviar(self, mensagem: WhatsAppMessage) -> SendResult:
        ...
