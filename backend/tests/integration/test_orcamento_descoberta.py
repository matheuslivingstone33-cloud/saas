"""A descoberta nao pode queimar orcamento numa regiao ja esgotada.

Bug real, encontrado assistindo a execucao ao vivo: rodar de novo uma campanha
cuja regiao ja foi varrida gastava 80 consultas ao Places (~US$2,56 em
producao) para descobrir ZERO empresas novas. A meta de leads nao protegia,
porque ela conta o que foi criado — e nada era criado.

O guardrail: apos N consultas seguidas sem nenhum lead novo, a rodada para.
"""

from __future__ import annotations

from app.models.campaign import Campaign
from app.models.enums import StatusCampanha
from app.repositories.misc import CostEventRepository
from app.services.cerebro import ExpansorDeServico
from app.services.descoberta import CONSULTAS_IMPRODUTIVAS_MAX, DiscoveryService
from app.services.leads import LeadService
from app.services.observador import ColetorDeEventos
from app.services.pipeline import PipelineStub
from app.services.query_builder import QueryBuilder


def _campanha(session, usuario, nome: str) -> Campaign:
    campanha = Campaign(
        user_id=usuario.id,
        nome=nome,
        servico="instalacao e manutencao de ar condicionado para empresas",
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.RASCUNHO,
    )
    session.add(campanha)
    session.flush()
    return campanha


def test_para_quando_a_regiao_esgota(session, usuario, portas_db) -> None:
    # 1a rodada: descobre tudo o que a regiao tem.
    primeira = _campanha(session, usuario, "Esgotamento 1")
    PipelineStub(session, portas_db).executar(primeira, limite_leads=50)

    # 2a rodada na MESMA regiao: tudo ja e duplicata.
    segunda = _campanha(session, usuario, "Esgotamento 2")
    coletor = ColetorDeEventos()
    resultado = PipelineStub(session, portas_db, observador=coletor).executar(
        segunda, limite_leads=50
    )

    assert resultado.descobertos == 0, "a regiao ja estava esgotada"

    consultas_2 = CostEventRepository(session).listar(
        usuario.id, campaign_id=segunda.id, por_pagina=500
    ).itens
    places_2 = len([c for c in consultas_2 if c.provedor == "places"])

    # O corte tem que agir: no maximo o limite + a consulta que o disparou.
    assert places_2 <= CONSULTAS_IMPRODUTIVAS_MAX + 1, (
        f"gastou {places_2} consultas sem achar nada (limite {CONSULTAS_IMPRODUTIVAS_MAX})"
    )
    assert "esgotado" in coletor.etapas

    # A comparacao que importa nao e com a 1a rodada (que para ao bater a meta),
    # e com o que a 2a TERIA gasto sem o corte: o plano inteiro.
    cerebro = ExpansorDeServico(session, portas_db)
    expansao = cerebro.expandir(segunda.servico, segunda.regiao)
    plano = QueryBuilder().construir(expansao, meta_leads=50, filtros={})
    assert places_2 < len(plano.consultas), (
        f"o corte precisa economizar: {places_2} de {len(plano.consultas)} consultas do plano"
    )


def test_regiao_produtiva_nao_e_cortada(session, usuario, portas_db) -> None:
    """O corte so vale para consulta improdutiva: quem esta achando continua."""
    campanha = _campanha(session, usuario, "Produtiva")
    coletor = ColetorDeEventos()
    resultado = PipelineStub(session, portas_db, observador=coletor).executar(
        campanha, limite_leads=5
    )

    assert resultado.descobertos == 5
    assert "esgotado" not in coletor.etapas


def test_descoberta_narra_o_que_faz(session, usuario, portas_db) -> None:
    """O observador precisa contar as etapas que a interface mostra ao vivo."""
    campanha = _campanha(session, usuario, "Narrada")
    coletor = ColetorDeEventos()
    PipelineStub(session, portas_db, observador=coletor).executar(campanha, limite_leads=3)

    etapas = set(coletor.etapas)
    assert {"inicio", "cerebro", "busca", "encontrado", "qualificado", "fim"} <= etapas

    cerebro = coletor.primeiro("cerebro")
    assert cerebro is not None
    assert cerebro.dados["ramos"], "o Cerebro precisa dizer que ramos escolheu"
    assert "justificativa" in cerebro.dados

    qualificado = coletor.primeiro("qualificado")
    assert qualificado is not None
    assert qualificado.dados["score"] > 0
    assert qualificado.dados["explicacao"]


def test_observador_quebrado_nao_derruba_a_campanha(session, usuario, portas_db) -> None:
    """Quem assiste nao pode quebrar quem trabalha."""

    def explode(etapa: str, dados: dict) -> None:
        raise RuntimeError("observador com defeito")

    campanha = _campanha(session, usuario, "Observador ruim")
    resultado = PipelineStub(session, portas_db, observador=explode).executar(
        campanha, limite_leads=2
    )
    assert resultado.descobertos == 2


def test_discovery_service_aceita_observador_opcional(session, usuario, portas_db) -> None:
    """Sem observador, nada muda — o custo de instrumentar e zero."""
    campanha = _campanha(session, usuario, "Sem observador")
    cerebro = ExpansorDeServico(session, portas_db)
    expansao = cerebro.expandir(campanha.servico, campanha.regiao)
    servico = DiscoveryService(
        session, portas_db, cerebro.audit, LeadService(session, cerebro.audit)
    )
    resultado = servico.descobrir(campanha, expansao, meta_leads=2)
    assert resultado.criados <= 2
