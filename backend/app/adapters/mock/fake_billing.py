"""FakeBilling — mock do BillingPort (Fase 5 usa; real fica para depois).

O id do checkout carrega o que foi comprado (usuario, pacote e valor) e uma
assinatura com o `APP_SECRET`. E o equivalente do metadata do Stripe: na hora
de creditar, o sistema pergunta ao "provedor" o que foi pago em vez de
acreditar no pacote que o navegador manda. Um id forjado ou alterado nao
confere a assinatura e volta como nao pago.
"""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import Settings, get_settings
from app.ports.dto import CheckoutSession, ConsultaCheckout

PREFIXO = "cs_mock"


class FakeBilling:
    provedor = "billing"
    modo = "mock"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.confirmados: set[str] = set()

    def _assinatura(self, user_id: str, pacote: str, valor_centavos: int) -> str:
        mensagem = f"{user_id}:{pacote}:{valor_centavos}".encode()
        chave = self.settings.app_secret.encode()
        return hmac.new(chave, mensagem, hashlib.sha256).hexdigest()[:24]

    def criar_checkout(self, user_id: str, pacote: str, valor_centavos: int) -> CheckoutSession:
        assinatura = self._assinatura(user_id, pacote, valor_centavos)
        cid = f"{PREFIXO}.{user_id}.{pacote}.{valor_centavos}.{assinatura}"
        return CheckoutSession(
            id=cid,
            url=f"https://checkout.mock.local/{cid}",
            valor_centavos=valor_centavos,
            moeda="BRL",
            modo=self.modo,
        )

    def consultar(self, checkout_id: str) -> ConsultaCheckout:
        partes = checkout_id.split(".")
        if len(partes) != 5 or partes[0] != PREFIXO or not partes[3].isdigit():
            return ConsultaCheckout(pago=False)
        _, user_id, pacote, valor, assinatura = partes
        esperada = self._assinatura(user_id, pacote, int(valor))
        if not hmac.compare_digest(esperada, assinatura):
            return ConsultaCheckout(pago=False)
        return ConsultaCheckout(
            pago=True, user_id=user_id, pacote=pacote, valor_centavos=int(valor)
        )

    def confirmar(self, checkout_id: str) -> bool:
        pago = self.consultar(checkout_id).pago
        if pago:
            self.confirmados.add(checkout_id)
        return pago
