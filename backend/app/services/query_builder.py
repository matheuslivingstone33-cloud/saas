"""QueryBuilder — traduz a expansao do Cerebro em consultas ao PlacesPort.

Isolado e sem I/O de proposito: e a peca mais facil de errar (e a mais cara,
porque cada consulta e um SKU do Google). Aqui ela e testavel sozinha.

Decisoes que ficam neste arquivo:
  * **round-robin entre termos** — a cota se distribui entre os termos em vez
    de esgotar no primeiro. Um termo ruim nao consome a campanha inteira.
  * **regiao explodida** — "Fortaleza, CE" pode virar varias consultas quando o
    filtro pede bairros.
  * **exclusoes** — termos negativos vao junto e sao aplicados na origem.
  * **teto de consultas** — nunca dispara mais que o necessario para a meta.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.adapters.mock._text import normalizar
from app.ports.dto import PlacesQuery
from app.services.cerebro import Expansao

#: Quantos resultados pedimos por consulta. O Places cobra por requisicao, nao
#: por item, entao vale pedir a pagina cheia.
POR_CONSULTA = 20
#: Teto de seguranca: nunca mais que isto de consultas por execucao.
MAX_CONSULTAS = 40


@dataclass(slots=True)
class PlanoDeBusca:
    consultas: list[PlacesQuery] = field(default_factory=list)
    meta_leads: int = 0
    custo_estimado_micros: int = 0

    def __len__(self) -> int:
        return len(self.consultas)

    def to_dict(self) -> dict:
        return {
            "consultas": [
                {"termo": c.termo, "regiao": c.regiao, "max_resultados": c.max_resultados}
                for c in self.consultas
            ],
            "total_consultas": len(self.consultas),
            "meta_leads": self.meta_leads,
            "custo_estimado_micros": self.custo_estimado_micros,
        }


class QueryBuilder:
    def __init__(
        self, por_consulta: int = POR_CONSULTA, max_consultas: int = MAX_CONSULTAS
    ) -> None:
        self.por_consulta = por_consulta
        self.max_consultas = max_consultas

    def construir(
        self,
        expansao: Expansao,
        *,
        meta_leads: int = 25,
        filtros: dict | None = None,
    ) -> PlanoDeBusca:
        from app.core.pricing import estimar_micros

        filtros = filtros or {}
        termos = self._termos(expansao, filtros)
        regioes = self._regioes(expansao, filtros)
        if not termos or not regioes:
            return PlanoDeBusca(consultas=[], meta_leads=meta_leads)

        excluir = sorted({*expansao.excluir_termos, *filtros.get("excluir_termos", [])})
        raio = filtros.get("raio_km")
        tipos = list(filtros.get("tipos_incluidos", []))

        # Quantas consultas bastam para a meta? Uma consulta traz ate
        # `por_consulta` candidatos, dos quais boa parte cai no dedup/filtro.
        necessarias = max(len(termos), min(self.max_consultas, -(-meta_leads // 3)))
        combinacoes = [(t, r) for r in regioes for t in termos]

        consultas: list[PlacesQuery] = []
        indice = 0
        # Round-robin: percorre as combinacoes em ordem, repetindo o ciclo se
        # precisar de mais consultas do que combinacoes existentes.
        while len(consultas) < min(necessarias, self.max_consultas) and combinacoes:
            termo, regiao = combinacoes[indice % len(combinacoes)]
            if indice >= len(combinacoes):
                break  # ja cobrimos todas as combinacoes uma vez
            consultas.append(
                PlacesQuery(
                    termo=termo,
                    regiao=regiao,
                    max_resultados=self.por_consulta,
                    raio_m=int(raio * 1000) if raio else None,
                    tipos_incluidos=tipos,
                    excluir_termos=excluir,
                )
            )
            indice += 1

        return PlanoDeBusca(
            consultas=consultas,
            meta_leads=meta_leads,
            custo_estimado_micros=estimar_micros("places.text_search", len(consultas)),
        )

    # -- internos -------------------------------------------------------------
    def _termos(self, expansao: Expansao, filtros: dict) -> list[str]:
        fixos = [str(t).strip() for t in filtros.get("termos", []) if str(t).strip()]
        vindos = fixos or list(expansao.termos)
        vistos: set[str] = set()
        saida: list[str] = []
        for termo in vindos:
            chave = normalizar(termo)
            if chave and chave not in vistos:
                vistos.add(chave)
                saida.append(termo)
        return saida

    def _regioes(self, expansao: Expansao, filtros: dict) -> list[str]:
        bairros = [str(b).strip() for b in filtros.get("bairros", []) if str(b).strip()]
        if bairros:
            return [f"{bairro}, {expansao.regiao}" for bairro in bairros]
        extras = [str(r).strip() for r in filtros.get("regioes", []) if str(r).strip()]
        return [expansao.regiao, *extras] if extras else [expansao.regiao]
