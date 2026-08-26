"""GooglePlacesAdapter — Google Places API (New). FASE 7, implementado.

GUARDRAIL PERMANENTE: a unica fonte de descoberta e a Places API oficial.
Scraping de Google Maps/Earth e proibido e nao esta implementado aqui.

Toda chamada passa pelo HttpClient central (timeout, retry, rate limit,
circuit breaker e cost_event). O adaptador so traduz DTO <-> payload.

Custo: cada requisicao e um SKU. A field mask abaixo e deliberadamente enxuta —
pedir `places.reviews` ou `places.currentOpeningHours` sobe a faixa de preco.

Endpoints usados:
  POST /v1/places:searchText   (Text Search)
  GET  /v1/places/{place_id}   (Place Details)
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import ProviderNotConfigured
from app.core.http_client import HttpClient
from app.core.logging import get_logger
from app.ports.dto import PlaceResult, PlacesQuery, PlacesResponse
from app.services.cost import CostRecorder, CostSpec

log = get_logger("google_places")

BASE_URL = "https://places.googleapis.com/v1"

#: Campos do Text Search. Cada campo extra pode mudar o SKU cobrado.
FIELD_MASK_BUSCA = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.location",
        "places.types",
        "places.rating",
        "places.userRatingCount",
        "nextPageToken",
    ]
)
FIELD_MASK_DETALHES = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "internationalPhoneNumber",
        "websiteUri",
        "location",
        "types",
        "rating",
        "userRatingCount",
    ]
)


class GooglePlacesAdapter:
    provedor = "places"
    modo = "real"

    def __init__(
        self,
        http: HttpClient,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http
        self.cost = cost
        if not self.settings.google_maps_api_key:
            raise ProviderNotConfigured(
                "GOOGLE_MAPS_API_KEY vazia. Preencha o .env antes de PLACES_MODE=real."
            )

    # -- PlacesPort -----------------------------------------------------------
    def buscar(self, query: PlacesQuery) -> PlacesResponse:
        corpo: dict[str, Any] = {
            "textQuery": self._texto(query),
            "languageCode": query.idioma,
            "maxResultCount": min(20, max(1, query.max_resultados)),
            "regionCode": "BR",
        }
        if query.latitude is not None and query.longitude is not None:
            corpo["locationBias"] = {
                "circle": {
                    "center": {"latitude": query.latitude, "longitude": query.longitude},
                    "radius": float(query.raio_m or 20_000),
                }
            }
        if query.tipos_incluidos:
            corpo["includedType"] = query.tipos_incluidos[0]
        if query.page_token:
            corpo["pageToken"] = query.page_token

        resposta = self.http.request(
            "POST",
            f"{BASE_URL}/places:searchText",
            headers=self._headers(FIELD_MASK_BUSCA),
            json=corpo,
            operacao="text_search",
            custo=CostSpec(
                provedor=self.provedor,
                operacao="text_search",
                chave_preco="places.text_search",
                quantidade=1,
                metadados={"termo": query.termo, "regiao": query.regiao},
            ),
        )
        dados = resposta.json or {}
        itens = [self._para_dto(p) for p in dados.get("places", [])]
        itens = [i for i in itens if not self._excluido(i, query)]
        log.info(
            "places_busca_real",
            termo=query.termo,
            regiao=query.regiao,
            resultados=len(itens),
            request_id=resposta.request_id,
        )
        return PlacesResponse(
            itens=itens,
            proximo_token=dados.get("nextPageToken"),
            modo=self.modo,
            request_id=resposta.request_id,
        )

    def detalhes(self, place_id: str) -> PlaceResult | None:
        resposta = self.http.request(
            "GET",
            f"{BASE_URL}/places/{place_id}",
            headers=self._headers(FIELD_MASK_DETALHES),
            operacao="place_details",
            custo=CostSpec(
                provedor=self.provedor,
                operacao="place_details",
                chave_preco="places.place_details",
                quantidade=1,
                metadados={"place_id": place_id},
            ),
        )
        if not resposta.json:
            return None
        return self._para_dto(resposta.json)

    # -- internos -------------------------------------------------------------
    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            "X-Goog-Api-Key": self.settings.google_maps_api_key,
            "X-Goog-FieldMask": field_mask,
            "Content-Type": "application/json",
        }

    def _texto(self, query: PlacesQuery) -> str:
        """O Text Search recebe uma frase: `termo em regiao`."""
        termo = query.termo.strip()
        regiao = query.regiao.strip()
        return f"{termo} em {regiao}" if regiao else termo

    def _para_dto(self, bruto: dict[str, Any]) -> PlaceResult:
        local = bruto.get("location") or {}
        nome = (bruto.get("displayName") or {}).get("text") or bruto.get("id", "")
        return PlaceResult(
            place_id=bruto.get("id", ""),
            nome=nome,
            endereco_formatado=bruto.get("formattedAddress"),
            telefone=bruto.get("internationalPhoneNumber"),
            website=bruto.get("websiteUri"),
            latitude=local.get("latitude"),
            longitude=local.get("longitude"),
            tipos=list(bruto.get("types", [])),
            nota=bruto.get("rating"),
            total_avaliacoes=bruto.get("userRatingCount"),
            fonte="google_places",
        )

    def _excluido(self, item: PlaceResult, query: PlacesQuery) -> bool:
        """Aplica os termos negativos na resposta (a API nao tem 'NOT')."""
        if not query.excluir_termos:
            return False
        alvo = f"{item.nome} {item.endereco_formatado or ''}".lower()
        return any(termo.lower() in alvo for termo in query.excluir_termos if termo)
