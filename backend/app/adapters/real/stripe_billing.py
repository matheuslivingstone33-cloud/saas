"""StripeAdapter — BillingPort real. FASE 7, implementado.

Usa o SDK oficial do Stripe dentro do `guard()` do HttpClient.

Em producao, o credito NAO deve ser lancado por esta chamada e sim pelo webhook
`checkout.session.completed` com assinatura verificada — senao um cliente pode
creditar-se chamando /confirmar. `confirmar()` aqui existe para reconciliacao e
para o smoke test.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import ProviderNotConfigured
from app.core.http_client import HttpClient
from app.core.logging import get_logger
from app.ports.dto import CheckoutSession, ConsultaCheckout
from app.services.cost import CostRecorder

log = get_logger("stripe")


class StripeAdapter:
    provedor = "billing"
    modo = "real"

    def __init__(
        self,
        http: HttpClient | None = None,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
        cliente: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http
        self.cost = cost
        if not self.settings.stripe_secret_key:
            raise ProviderNotConfigured(
                "STRIPE_SECRET_KEY vazia. Preencha o .env antes de BILLING_MODE=real."
            )
        self._cliente = cliente

    @property
    def cliente(self):  # noqa: ANN201
        if self._cliente is None:
            import stripe

            self._cliente = stripe.StripeClient(self.settings.stripe_secret_key)
        return self._cliente

    def criar_checkout(self, user_id: str, pacote: str, valor_centavos: int) -> CheckoutSession:
        base = self.settings.url_publica.rstrip("/")
        with self.http.guard("checkout.create"):
            sessao = self.cliente.checkout.sessions.create(
                params={
                    "mode": "payment",
                    "success_url": f"{base}/creditos?compra=ok&sessao={{CHECKOUT_SESSION_ID}}",
                    "cancel_url": f"{base}/creditos?compra=cancelada",
                    "client_reference_id": user_id,
                    "metadata": {"pacote": pacote, "user_id": user_id},
                    "line_items": [
                        {
                            "quantity": 1,
                            "price_data": {
                                "currency": "brl",
                                "unit_amount": valor_centavos,
                                "product_data": {"name": f"Prospector AI — {pacote}"},
                            },
                        }
                    ],
                }
            )
        log.info("checkout_criado", sessao=sessao.id, pacote=pacote)
        return CheckoutSession(
            id=sessao.id,
            url=sessao.url or "",
            valor_centavos=valor_centavos,
            moeda="BRL",
            modo=self.modo,
        )

    def confirmar(self, checkout_id: str) -> bool:
        """Reconciliacao. O caminho normal em producao e o webhook assinado."""
        with self.http.guard("checkout.retrieve"):
            sessao = self.cliente.checkout.sessions.retrieve(checkout_id)
        pago = getattr(sessao, "payment_status", None) == "paid"
        log.info("checkout_consultado", sessao=checkout_id, pago=pago)
        return pago

    def consultar(self, checkout_id: str) -> ConsultaCheckout:
        """O que o Stripe diz que foi pago, lido do metadata gravado no checkout."""
        with self.http.guard("checkout.retrieve"):
            sessao = self.cliente.checkout.sessions.retrieve(checkout_id)
        metadata = getattr(sessao, "metadata", None) or {}
        return ConsultaCheckout(
            pago=getattr(sessao, "payment_status", None) == "paid",
            user_id=metadata.get("user_id") or getattr(sessao, "client_reference_id", None),
            pacote=metadata.get("pacote"),
            valor_centavos=getattr(sessao, "amount_total", None),
        )
