"""Registry de provedores — o UNICO lugar que conhece adaptadores concretos.

O dominio pede uma porta; o registry decide mock ou real lendo o env.
Trocar mock <-> real nao altera uma linha de regra de negocio.

    portas = ProviderRegistry(cost=recorder)
    plano = portas.llm.orquestrar_descoberta(servico, regiao, {})
    achados = portas.places.buscar(query)
"""

from __future__ import annotations

from functools import cached_property

from app.adapters.mock.fake_billing import FakeBilling
from app.adapters.mock.fake_email import FakeEmail
from app.adapters.mock.fake_llm import FakeLLM
from app.adapters.mock.fake_places import FakePlaces
from app.adapters.mock.fake_search import FakeSearch
from app.adapters.mock.fake_whatsapp import FakeWhatsApp
from app.adapters.mock.receita_local import ReceitaLocal
from app.core.config import Provider, Settings, get_settings
from app.core.http_client import HttpClient
from app.core.logging import get_logger
from app.ports import (
    BillingPort,
    EmailPort,
    EnrichmentPort,
    LLMPort,
    PlacesPort,
    SearchPort,
    WhatsAppPort,
)
from app.services.cost import CostRecorder

log = get_logger("registry")


class ProviderRegistry:
    """Fabrica de portas. Instancia sob demanda e memoriza por instancia."""

    def __init__(
        self, cost: CostRecorder | None = None, settings: Settings | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.cost = cost or CostRecorder.em_memoria()
        self._clients: dict[str, HttpClient] = {}

    # -- infraestrutura -------------------------------------------------------
    def modo(self, provider: Provider) -> str:
        return self.settings.mode_for(provider)

    def http(self, provider: Provider) -> HttpClient:
        chave = provider.value
        if chave not in self._clients:
            self._clients[chave] = HttpClient(
                chave, modo=self.modo(provider), settings=self.settings, cost=self.cost
            )
        return self._clients[chave]

    def fechar(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    # -- portas ---------------------------------------------------------------
    @cached_property
    def places(self) -> PlacesPort:
        if self.modo(Provider.PLACES) == "real":
            from app.adapters.real.google_places import GooglePlacesAdapter

            log.info("provedor_real", provedor="places")
            return GooglePlacesAdapter(self.http(Provider.PLACES), self.cost, self.settings)
        return FakePlaces(self.cost, self.settings)

    @cached_property
    def llm(self) -> LLMPort:
        if self.modo(Provider.LLM) == "real":
            from app.adapters.real.anthropic_llm import AnthropicAdapter

            log.info("provedor_real", provedor="llm", modelo=self.settings.llm_model)
            # `places=self.places` fecha o loop de tool use: a ferramenta
            # `buscar_empresas` delega ao PlacesPort, nunca a Google direto.
            return AnthropicAdapter(
                self.http(Provider.LLM), self.cost, self.settings, places=self.places
            )
        return FakeLLM(self.cost, self.settings)

    @cached_property
    def search(self) -> SearchPort:
        if self.modo(Provider.SEARCH) == "real":
            from app.adapters.real.anthropic_search import AnthropicWebSearchAdapter

            log.info("provedor_real", provedor="search")
            return AnthropicWebSearchAdapter(self.http(Provider.SEARCH), self.cost, self.settings)
        return FakeSearch(self.cost, self.settings)

    @cached_property
    def email(self) -> EmailPort:
        if self.modo(Provider.EMAIL) == "real":
            from app.adapters.real.ses_email import SESAdapter

            log.info("provedor_real", provedor="email")
            return SESAdapter(self.http(Provider.EMAIL), self.cost, self.settings)
        return FakeEmail(self.cost, self.settings)

    @cached_property
    def whatsapp(self) -> WhatsAppPort:
        if self.modo(Provider.WHATSAPP) == "real":
            from app.adapters.real.bsp_whatsapp import BSPAdapter

            log.info("provedor_real", provedor="whatsapp")
            return BSPAdapter(self.http(Provider.WHATSAPP), self.cost, self.settings)
        return FakeWhatsApp(self.cost, self.settings)

    @cached_property
    def enrichment(self) -> EnrichmentPort:
        # Receita Federal e dado aberto: mesmo adaptador em dev e producao.
        return ReceitaLocal(self.cost, self.settings)

    @cached_property
    def billing(self) -> BillingPort:
        if self.modo(Provider.BILLING) == "real":
            from app.adapters.real.stripe_billing import StripeAdapter

            log.info("provedor_real", provedor="billing")
            return StripeAdapter(self.http(Provider.BILLING), self.cost, self.settings)
        return FakeBilling(self.settings)

    # -- diagnostico ----------------------------------------------------------
    def diagnostico(self) -> dict[str, dict[str, object]]:
        """Usado por GET /v1/providers e pelos smoke tests da Fase 7."""
        chaves = {
            Provider.PLACES: bool(self.settings.google_maps_api_key),
            Provider.LLM: bool(self.settings.anthropic_api_key),
            Provider.SEARCH: bool(self.settings.anthropic_api_key),
            Provider.EMAIL: bool(self.settings.ses_from_email),
            Provider.WHATSAPP: bool(self.settings.whatsapp_bsp_token),
            Provider.ENRICHMENT: True,  # dado aberto
            Provider.BILLING: bool(self.settings.stripe_secret_key),
        }
        return {
            p.value: {
                "modo": self.modo(p),
                "chave_presente": chaves[p],
                "rede_habilitada": self.modo(p) == "real",
            }
            for p in Provider
        }
