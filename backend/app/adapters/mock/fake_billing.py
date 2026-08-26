"""FakeBilling — mock do BillingPort (Fase 5 usa; real fica para depois)."""

from __future__ import annotations

import hashlib

from app.core.config import Settings, get_settings
from app.ports.dto import CheckoutSession


class FakeBilling:
    provedor = "billing"
    modo = "mock"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.confirmados: set[str] = set()

    def criar_checkout(self, user_id: str, pacote: str, valor_centavos: int) -> CheckoutSession:
        semente = f"{user_id}:{pacote}:{valor_centavos}".encode()
        cid = "cs_mock_" + hashlib.blake2b(semente, digest_size=8).hexdigest()
        return CheckoutSession(
            id=cid,
            url=f"https://checkout.mock.local/{cid}",
            valor_centavos=valor_centavos,
            moeda="BRL",
            modo=self.modo,
        )

    def confirmar(self, checkout_id: str) -> bool:
        self.confirmados.add(checkout_id)
        return True
