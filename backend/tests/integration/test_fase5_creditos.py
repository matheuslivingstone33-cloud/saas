"""FASE 5 — Creditos, planos, bloqueio sem saldo e vitrine de tokens."""

from __future__ import annotations

import pytest

from app.core.errors import SaldoInsuficiente
from app.models.campaign import Campaign
from app.models.enums import NivelAutonomia, Plano, StatusCampanha, TipoCredito
from app.repositories.misc import UserRepository
from app.services.creditos import (
    CATALOGO,
    CUSTO_CREDITOS,
    PACOTES,
    TOKENS_ESTIMADOS_POR_LEAD,
    CreditService,
)
from app.services.pipeline import PipelineStub

SERVICO = "instalacao e manutencao de ar condicionado para empresas"


def _campanha(session, usuario, nome="Creditos", nivel=NivelAutonomia.AUTOMATICO):  # noqa: ANN001
    campanha = Campaign(
        user_id=usuario.id,
        nome=nome,
        servico=SERVICO,
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.RASCUNHO,
        autonomy_override=nivel,
    )
    session.add(campanha)
    session.flush()
    return campanha


def _zerar_saldo(session, usuario) -> None:
    servico = CreditService(session)
    saldo = servico.ledger.saldo(usuario.id)
    if saldo:
        servico.ledger.lancar(
            user_id=usuario.id,
            tipo=TipoCredito.AJUSTE_MANUAL,
            quantidade=-saldo,
            descricao="zerado no teste",
        )
    session.flush()


# --- Ledger -------------------------------------------------------------------
def test_seed_credita_o_trial(session, usuario) -> None:
    estado = CreditService(session).saldo(usuario.id)
    assert estado.creditos == 500
    assert estado.plano == Plano.TRIAL.value
    assert estado.bloqueado is False


def test_ledger_e_append_only_e_o_saldo_e_derivado(session, usuario) -> None:
    servico = CreditService(session)
    inicial = servico.ledger.saldo(usuario.id)

    servico.debitar(usuario.id, "lead_qualificado")
    servico.debitar(usuario.id, "mensagem_enviada")
    depois = servico.ledger.saldo(usuario.id)

    esperado = inicial - CUSTO_CREDITOS["lead_qualificado"] - CUSTO_CREDITOS["mensagem_enviada"]
    assert depois == esperado

    extrato = servico.ledger.extrato(usuario.id, por_pagina=50)
    assert extrato.total >= 3  # credito inicial + 2 consumos
    assert extrato.itens[0].saldo_apos == depois


def test_estorno_devolve_credito(session, usuario) -> None:
    servico = CreditService(session)
    antes = servico.ledger.saldo(usuario.id)
    servico.debitar(usuario.id, "lead_qualificado")
    servico.estornar(usuario.id, 1, "entrega falhou")
    assert servico.ledger.saldo(usuario.id) == antes


def test_compra_de_pacote_credita(session, usuario) -> None:
    servico = CreditService(session)
    antes = servico.ledger.saldo(usuario.id)
    pacote = PACOTES["recarga_500"]
    saldo = servico.creditar(usuario.id, pacote.creditos, descricao="compra")
    assert saldo == antes + pacote.creditos


# --- Bloqueio -----------------------------------------------------------------
def test_sem_saldo_o_consumo_e_bloqueado(session, usuario) -> None:
    _zerar_saldo(session, usuario)
    servico = CreditService(session)

    estado = servico.pode_consumir(usuario.id, "lead_qualificado")
    assert estado.bloqueado is True
    assert "zerado" in estado.motivo_bloqueio

    with pytest.raises(SaldoInsuficiente):
        servico.debitar(usuario.id, "lead_qualificado")


def test_campanha_nao_roda_sem_saldo(session, usuario, portas_db) -> None:
    """O bloqueio vem ANTES de qualquer chamada externa."""
    _zerar_saldo(session, usuario)
    campanha = _campanha(session, usuario, nome="Sem saldo")

    with pytest.raises(SaldoInsuficiente):
        PipelineStub(session, portas_db).executar(campanha, limite_leads=3)

    assert campanha.status is StatusCampanha.PAUSADA
    from app.repositories.leads import LeadRepository

    assert LeadRepository(session).listar(usuario.id, campaign_id=campanha.id).total == 0


def test_teto_do_plano_bloqueia_mesmo_com_credito(session, usuario) -> None:
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.leads_consumidos_mes = assinatura.teto_leads_mes
    session.flush()

    estado = CreditService(session).saldo(usuario.id)
    assert estado.bloqueado is True
    assert "teto" in estado.motivo_bloqueio


def test_overage_libera_consumo_acima_do_teto(session, usuario) -> None:
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.leads_consumidos_mes = assinatura.teto_leads_mes
    assinatura.overage_habilitado = True
    session.flush()

    servico = CreditService(session)
    estado = servico.saldo(usuario.id)
    assert estado.bloqueado is False
    assert any("overage" in a for a in estado.alertas)

    _zerar_saldo(session, usuario)
    servico.debitar(usuario.id, "lead_qualificado")
    lancamento = servico.ledger.extrato(usuario.id, por_pagina=1).itens[0]
    assert lancamento.tipo is TipoCredito.OVERAGE
    assert lancamento.saldo_apos < 0


def test_alerta_de_saldo_baixo(session, usuario) -> None:
    servico = CreditService(session)
    _zerar_saldo(session, usuario)
    servico.creditar(usuario.id, 3, descricao="quase acabando")
    estado = servico.saldo(usuario.id)
    assert any("saldo baixo" in a for a in estado.alertas)


# --- Consumo real pelo pipeline ----------------------------------------------
def test_pipeline_debita_por_lead_e_por_envio(session, usuario, portas_db) -> None:
    servico = CreditService(session)
    antes = servico.ledger.saldo(usuario.id)
    campanha = _campanha(session, usuario, nome="Debito real")

    resultado = PipelineStub(session, portas_db).executar(campanha, limite_leads=3)
    depois = servico.ledger.saldo(usuario.id)

    esperado = (
        antes
        - resultado.qualificados * CUSTO_CREDITOS["lead_qualificado"]
        - resultado.mensagens_enviadas * CUSTO_CREDITOS["mensagem_enviada"]
    )
    assert depois <= esperado  # pode ter sinal de intencao somando
    assert resultado.saldo_inicial == antes
    assert resultado.interrompido_por_saldo is False


def test_saldo_acaba_no_meio_e_a_leva_para(session, usuario, portas_db) -> None:
    _zerar_saldo(session, usuario)
    CreditService(session).creditar(usuario.id, 2, descricao="so dois creditos")
    campanha = _campanha(session, usuario, nome="Acaba no meio")

    resultado = PipelineStub(session, portas_db).executar(campanha, limite_leads=5)
    assert resultado.interrompido_por_saldo is True
    assert resultado.qualificados <= 3


# --- Vitrine de tokens --------------------------------------------------------
def test_equivalencia_comeca_estimada(session, usuario) -> None:
    servico = CreditService(session)
    eq = servico.equivalencia(usuario.id, Plano.PRO)
    assert eq.base == "estimado"
    assert eq.tokens_por_lead == TOKENS_ESTIMADOS_POR_LEAD
    # A conta da vitrine: tokens/mes = leads x tokens por lead
    assert eq.tokens_mes == eq.creditos_mes * eq.tokens_por_lead


def test_equivalencia_vira_medida_com_historico(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Medicao")
    PipelineStub(session, portas_db).executar(campanha, limite_leads=3)

    eq = CreditService(session).equivalencia(usuario.id, Plano.PRO)
    assert eq.base == "medido", "com historico, a vitrine usa o consumo REAL"
    assert eq.amostra_leads > 0
    assert eq.tokens_por_lead > 0
    assert eq.tokens_mes == eq.creditos_mes * eq.tokens_por_lead
    assert eq.custo_medio_lead_micros > 0


def test_vitrine_traz_todos_os_planos_e_pacotes(session, usuario) -> None:
    vitrine = CreditService(session).vitrine(usuario.id)
    assert len(vitrine["planos"]) == len(CATALOGO)
    assert len(vitrine["pacotes_avulsos"]) == len(PACOTES)
    for plano in vitrine["planos"]:
        assert plano["equivalencia"]["tokens_mes"] > 0
        assert plano["equivalencia"]["aviso"]


# --- API ----------------------------------------------------------------------
def test_api_saldo_e_vitrine(client, usuario) -> None:
    saldo = client.get("/v1/billing/saldo").json()
    assert saldo["creditos"] > 0
    assert saldo["bloqueado"] is False

    vitrine = client.get("/v1/billing/vitrine").json()
    assert vitrine["planos"]
    assert vitrine["custo_em_creditos"]["lead_qualificado"] == 1


def test_api_compra_e_confirmacao_creditam(client, usuario, session) -> None:
    antes = client.get("/v1/billing/saldo").json()["creditos"]

    compra = client.post("/v1/billing/comprar", json={"pacote": "recarga_100"})
    assert compra.status_code == 200, compra.text
    checkout = compra.json()["checkout"]
    assert checkout["modo"] == "mock"

    confirmacao = client.post(
        "/v1/billing/confirmar",
        json={"checkout_id": checkout["id"], "pacote": "recarga_100"},
    )
    assert confirmacao.status_code == 200
    assert confirmacao.json()["saldo"] == antes + 100


def test_api_troca_de_plano_aplica_teto_e_recarrega(client, usuario, session) -> None:
    r = client.post("/v1/billing/plano", json={"plano": "pro"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["para"] == "pro"
    assert corpo["creditos_creditados"] == CATALOGO[Plano.PRO].creditos_mes

    saldo = client.get("/v1/billing/saldo").json()
    assert saldo["plano"] == "pro"
    assert saldo["teto_leads_mes"] == CATALOGO[Plano.PRO].teto_leads_mes
    assert saldo["leads_consumidos_mes"] == 0


def test_api_extrato_pagina(client, usuario, session, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Extrato")
    PipelineStub(session, portas_db).executar(campanha, limite_leads=2)

    extrato = client.get("/v1/billing/extrato", params={"por_pagina": 5}).json()
    assert extrato["total"] > 0
    assert len(extrato["itens"]) <= 5
    assert extrato["itens"][0]["saldo_apos"] is not None


def test_api_bloqueia_campanha_sem_saldo_com_402(client, usuario, session) -> None:
    _zerar_saldo(session, usuario)
    campanha = client.post(
        "/v1/campaigns",
        json={"nome": "402", "servico": SERVICO, "regiao": "Fortaleza, CE"},
    ).json()
    r = client.post(f"/v1/campaigns/{campanha['id']}/run", json={"limite_leads": 2})
    assert r.status_code == 402
    assert r.json()["tipo"] == "saldo"
