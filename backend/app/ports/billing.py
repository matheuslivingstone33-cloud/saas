"""Porta de pagamento (Fase 5 usa; adaptador real fica para depois)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ports.dto import CheckoutSession


@runtime_checkable
class BillingPort(Protocol):
    provedor: str
    modo: str

    def criar_checkout(self, user_id: str, pacote: str, valor_centavos: int) -> CheckoutSession:
        ...

    def confirmar(self, checkout_id: str) -> bool:
        ...
