"""FakePlaces — implementacao mock do PlacesPort.

Le fixtures de data/fixtures/places.json e devolve resultados DETERMINISTICOS,
ordenados por aderencia ao termo buscado. Se a fixture nao cobrir o termo,
sintetiza empresas plausiveis de forma deterministica (mesma entrada, mesma
saida), para que qualquer campanha rode ponta a ponta sem chave.

Registra cost_event exatamente como o adaptador real fara (balde 1 = dados).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.adapters.mock._text import normalizar, slug, tokenizar
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ports.dto import PlaceResult, PlacesQuery, PlacesResponse
from app.services.cost import CostRecorder, CostSpec

log = get_logger("fake_places")

_SUFIXOS = ["LTDA", "ME", "EIRELI", "SA", "Comercio", "Servicos"]


def _carregar_fixtures(caminho: Path) -> list[dict[str, Any]]:
    if not caminho.exists():
        log.warning("fixtures_places_ausentes", caminho=str(caminho))
        return []
    with caminho.open(encoding="utf-8") as fh:
        dados = json.load(fh)
    return dados.get("lugares", [])


class FakePlaces:
    """Mock do PlacesPort. NUNCA toca a rede."""

    provedor = "places"
    modo = "mock"

    def __init__(
        self,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
        fixtures: list[dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.cost = cost
        caminho = self.settings.resolve_path(self.settings.fixtures_path) / "places.json"
        self._lugares = fixtures if fixtures is not None else _carregar_fixtures(caminho)

    # -- PlacesPort -----------------------------------------------------------
    def buscar(self, query: PlacesQuery) -> PlacesResponse:
        termos = set(tokenizar(query.termo))
        regiao = normalizar(query.regiao)
        excluir = {normalizar(e) for e in query.excluir_termos}

        candidatos: list[tuple[float, PlaceResult]] = []
        for bruto in self._lugares:
            endereco = normalizar(bruto.get("endereco_formatado") or "")
            if regiao and not any(parte and parte in endereco for parte in regiao.split(",")):
                continue
            texto = " ".join(
                [
                    bruto.get("nome", ""),
                    " ".join(bruto.get("tags", [])),
                    " ".join(bruto.get("tipos", [])),
                ]
            )
            if excluir and any(e in normalizar(texto) for e in excluir if e):
                continue
            tokens = set(tokenizar(texto))
            aderencia = len(termos & tokens) / len(termos) if termos else 0.0
            if aderencia == 0 and termos:
                continue
            candidatos.append((aderencia, self._para_dto(bruto)))

        candidatos.sort(key=lambda item: (-item[0], item[1].place_id))
        itens = [dto for _, dto in candidatos][: query.max_resultados]

        # So sintetiza quando a fixture nao cobre o termo. Antes preenchiamos
        # ate 3 sempre, o que criava leads-fantasma (sem CNPJ e sem contato) ao
        # lado de empresas reais — ruido que atrapalha o score e o dedup.
        if not itens:
            itens = self._sintetizar(query, faltando=min(3, query.max_resultados))

        self._registrar_custo("places.text_search", len(itens), query)
        log.info(
            "places_busca_mock",
            termo=query.termo,
            regiao=query.regiao,
            resultados=len(itens),
        )
        return PlacesResponse(itens=itens, proximo_token=None, modo=self.modo)

    def detalhes(self, place_id: str) -> PlaceResult | None:
        for bruto in self._lugares:
            if bruto.get("place_id") == place_id:
                self._registrar_custo("places.place_details", 1, None)
                return self._para_dto(bruto)
        return None

    # -- internos -------------------------------------------------------------
    def _para_dto(self, bruto: dict[str, Any]) -> PlaceResult:
        return PlaceResult(
            place_id=bruto["place_id"],
            nome=bruto["nome"],
            endereco_formatado=bruto.get("endereco_formatado"),
            telefone=bruto.get("telefone"),
            website=bruto.get("website"),
            latitude=bruto.get("latitude"),
            longitude=bruto.get("longitude"),
            tipos=list(bruto.get("tipos", [])),
            nota=bruto.get("nota"),
            total_avaliacoes=bruto.get("total_avaliacoes"),
        )

    def _sintetizar(self, query: PlacesQuery, faltando: int) -> list[PlaceResult]:
        """Gera resultados deterministicos quando a fixture nao cobre o termo."""
        base = slug(f"{query.termo}-{query.regiao}")
        cidade = query.regiao.split(",")[0].strip() or "Fortaleza"
        saida: list[PlaceResult] = []
        for i in range(faltando):
            sufixo = _SUFIXOS[i % len(_SUFIXOS)]
            nome = f"{query.termo.title()} {sufixo} {i + 1}"
            saida.append(
                PlaceResult(
                    place_id=f"mock_gen_{base}_{i + 1}",
                    nome=nome,
                    endereco_formatado=f"Rua Exemplo, {100 + i * 10} - Centro, {cidade}",
                    telefone=f"+55 85 3{i}00-{1000 + i}",
                    website=f"https://{slug(nome)}.com.br",
                    latitude=-3.73 - i * 0.01,
                    longitude=-38.52 - i * 0.01,
                    tipos=["establishment"],
                    nota=4.0 + (i % 5) / 10,
                    total_avaliacoes=50 + i * 17,
                )
            )
        return saida

    def _registrar_custo(self, chave: str, itens: int, query: PlacesQuery | None) -> None:
        if self.cost is None:
            return
        self.cost.registrar(
            CostSpec(
                provedor=self.provedor,
                operacao=chave.split(".", 1)[1],
                chave_preco=chave,
                quantidade=1,
                metadados={
                    "itens": itens,
                    "termo": query.termo if query else None,
                    "regiao": query.regiao if query else None,
                },
            ),
            modo=self.modo,
        )
