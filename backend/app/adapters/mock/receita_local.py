"""ReceitaLocal — EnrichmentPort sobre a base de CNPJ da Receita Federal.

A base da Receita e DADO ABERTO: nao existe chave de API. Este e o mesmo
adaptador de dev e de producao — muda so o tamanho do arquivo importado
(amostra em data/receita/cnpj_sample.csv; em producao, o dump completo).

Por isso EnrichmentPort nao tem "modo real": ja e real desde a Fase 0.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.adapters.mock._text import normalizar, tokenizar
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ports.dto import CompanyRecord
from app.services.cost import CostRecorder, CostSpec

log = get_logger("receita_local")


def _so_digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


class ReceitaLocal:
    provedor = "enrichment"
    modo = "mock"  # o dado e real e aberto; o rotulo mantem o registry uniforme

    def __init__(
        self,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
        caminho: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.cost = cost
        self.caminho = caminho or self.settings.resolve_path(self.settings.receita_dataset_path)
        self._por_cnpj: dict[str, CompanyRecord] = {}
        self._indice_nome: list[tuple[set[str], CompanyRecord]] = []
        self._carregar()

    def _carregar(self) -> None:
        if not self.caminho.exists():
            log.warning("dataset_receita_ausente", caminho=str(self.caminho))
            return
        with self.caminho.open(encoding="utf-8", newline="") as fh:
            for linha in csv.DictReader(fh, delimiter=";"):
                registro = CompanyRecord(
                    cnpj=_so_digitos(linha["cnpj"]),
                    razao_social=linha["razao_social"].strip(),
                    nome_fantasia=(linha.get("nome_fantasia") or "").strip() or None,
                    cnae_principal=(linha.get("cnae_principal") or "").strip() or None,
                    cnaes_secundarios=[
                        c for c in (linha.get("cnaes_secundarios") or "").split("|") if c
                    ],
                    porte=(linha.get("porte") or "desconhecido").strip().lower(),
                    situacao_cadastral=(linha.get("situacao_cadastral") or "").strip() or None,
                    data_abertura=(linha.get("data_abertura") or "").strip() or None,
                    logradouro=(linha.get("logradouro") or "").strip() or None,
                    bairro=(linha.get("bairro") or "").strip() or None,
                    municipio=(linha.get("municipio") or "").strip() or None,
                    uf=(linha.get("uf") or "").strip().upper() or None,
                    cep=_so_digitos(linha.get("cep")) or None,
                    telefone=(linha.get("telefone") or "").strip() or None,
                    email=(linha.get("email") or "").strip() or None,
                )
                self._por_cnpj[registro.cnpj] = registro
                chaves = set(tokenizar(registro.razao_social)) | set(
                    tokenizar(registro.nome_fantasia or "")
                )
                self._indice_nome.append((chaves, registro))
        log.info("dataset_receita_carregado", registros=len(self._por_cnpj))

    # -- EnrichmentPort -------------------------------------------------------
    def por_cnpj(self, cnpj: str) -> CompanyRecord | None:
        self._custo("por_cnpj")
        return self._por_cnpj.get(_so_digitos(cnpj))

    def buscar(
        self, nome: str, uf: str | None = None, municipio: str | None = None
    ) -> list[CompanyRecord]:
        self._custo("buscar")
        alvo = set(tokenizar(nome))
        if not alvo:
            return []
        uf_norm = (uf or "").strip().upper() or None
        mun_norm = normalizar(municipio or "") or None

        pontuados: list[tuple[float, CompanyRecord]] = []
        for chaves, registro in self._indice_nome:
            if uf_norm and registro.uf != uf_norm:
                continue
            if mun_norm and normalizar(registro.municipio or "") != mun_norm:
                continue
            if not chaves:
                continue
            score = len(alvo & chaves) / len(alvo | chaves)
            if score > 0:
                pontuados.append((score, registro))
        pontuados.sort(key=lambda item: (-item[0], item[1].cnpj))
        return [registro for _, registro in pontuados[:5]]

    def _custo(self, operacao: str) -> None:
        if self.cost is None:
            return
        self.cost.registrar(
            CostSpec(
                provedor=self.provedor,
                operacao=operacao,
                chave_preco="enrichment.receita_cnpj",
                quantidade=1,
                metadados={"fonte": "dados_abertos"},
            ),
            modo=self.modo,
        )
