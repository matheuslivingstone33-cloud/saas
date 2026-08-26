"""FASE 1 — Motor 2 (Cerebro): expansao, score explicavel e loop de aprendizado."""

from __future__ import annotations

import pytest

from app.models.enums import Porte, StatusLead
from app.models.lead import Lead
from app.services.aprendizado import MINIMO_AMOSTRAS, LoopAprendizado
from app.services.cerebro import ExpansorDeServico, eh_concorrente
from app.services.scoring import COMPONENTES, Pesos, ScoringService

SERVICOS = [
    "instalacao e manutencao de ar condicionado para empresas",
    "servico de limpeza e conservacao predial",
    "contabilidade e assessoria fiscal para empresas",
]


@pytest.fixture
def cerebro(session, portas_db, usuario):  # noqa: ANN001
    return ExpansorDeServico(session, portas_db)


# --- Expansao ----------------------------------------------------------------
def test_expansao_encontra_ramos_e_termos(cerebro, usuario) -> None:
    exp = cerebro.expandir(SERVICOS[0], "Fortaleza, CE", user_id=usuario.id, max_ramos=6)
    assert exp.ramos, "deveria achar ramos compradores"
    assert exp.termos, "deveria propor termos de busca"
    assert exp.justificativa
    assert all(0 <= r.peso <= 1 for r in exp.ramos)
    assert exp.ramos == sorted(exp.ramos, key=lambda r: (-r.peso, r.codigo))


def test_expansao_e_deterministica(cerebro, usuario) -> None:
    a = cerebro.expandir(SERVICOS[0], "Fortaleza, CE", user_id=usuario.id)
    b = cerebro.expandir(SERVICOS[0], "Fortaleza, CE", user_id=usuario.id)
    assert a.cnaes_alvo == b.cnaes_alvo
    assert a.termos == b.termos


@pytest.mark.parametrize("servico", SERVICOS)
def test_expansao_coerente_em_tres_servicos(cerebro, usuario, servico) -> None:
    exp = cerebro.expandir(servico, "Fortaleza, CE", user_id=usuario.id, max_ramos=8)
    assert 1 <= len(exp.ramos) <= 8
    # Nenhum ramo escolhido pode ser concorrente do proprio servico.
    for ramo in exp.ramos:
        assert not eh_concorrente(servico, ramo.descricao, ramo.termos), ramo.codigo


def test_cerebro_exclui_concorrentes(cerebro, usuario) -> None:
    """Quem instala ar condicionado nao quer prospectar outra instaladora."""
    exp = cerebro.expandir(SERVICOS[0], "Fortaleza, CE", user_id=usuario.id, max_ramos=10)
    # 4322302 = instalacao/manutencao de ar condicionado (o proprio ramo).
    assert "4322302" in exp.excluidos_como_concorrente
    assert "4322302" not in exp.cnaes_alvo


def test_cnae_fixado_no_filtro_entra_mesmo_distante(cerebro, usuario) -> None:
    exp = cerebro.expandir(
        SERVICOS[0], "Fortaleza, CE", filtros={"cnaes": ["6911701"]}, user_id=usuario.id
    )
    assert "6911701" in exp.cnaes_alvo
    assert exp.peso_do_cnae("6911701") == 1.0


def test_expansao_gera_audit_de_decisao_ia(cerebro, usuario, session) -> None:
    from sqlalchemy import select

    from app.models.audit_log import AuditLog
    from app.models.enums import TipoEvento

    cerebro.expandir(SERVICOS[0], "Fortaleza, CE", user_id=usuario.id)
    decisoes = session.execute(
        select(AuditLog).where(AuditLog.evento == TipoEvento.DECISAO_IA)
    ).scalars().all()
    assert decisoes
    dados = decisoes[-1].dados
    assert dados["decisao"] == "expansao_de_servico"
    assert dados["ramos"] and dados["justificativa"]


# --- Scoring -----------------------------------------------------------------
def _lead(**kwargs) -> Lead:  # noqa: ANN003
    base = {
        "razao_social": "EMPRESA TESTE LTDA",
        "cnae_principal": None,
        "porte": Porte.EPP,
        "email": None,
        "telefone_normalizado": None,
        "website": None,
        "contexto": {},
        "cnaes_secundarios": None,
        "embedding": None,
        "status": StatusLead.DESCOBERTO,
    }
    base.update(kwargs)
    return Lead(**base)


def test_score_e_explicavel(cerebro, usuario) -> None:
    exp = cerebro.expandir(SERVICOS[0], "Fortaleza, CE", user_id=usuario.id)
    alvo = exp.cnaes_alvo[0]
    resultado = ScoringService().pontuar(
        _lead(cnae_principal=alvo, email="contato@x.com.br", telefone_normalizado="5585999"),
        exp,
    )
    assert 0 <= resultado.score <= 100
    assert set(resultado.componentes) == set(COMPONENTES)
    assert set(resultado.pesos) == set(COMPONENTES)
    assert abs(sum(resultado.pesos.values()) - 1.0) < 1e-6
    assert resultado.explicacao


def test_lead_do_ramo_alvo_pontua_mais_que_lead_fora(cerebro, usuario) -> None:
    exp = cerebro.expandir(SERVICOS[0], "Fortaleza, CE", user_id=usuario.id)
    scoring = ScoringService()
    dentro = scoring.pontuar(_lead(cnae_principal=exp.cnaes_alvo[0], email="a@b.com.br"), exp)
    fora = scoring.pontuar(_lead(cnae_principal="9999999", email="a@b.com.br"), exp)
    assert dentro.score > fora.score


def test_contato_e_porte_movem_o_score(cerebro, usuario) -> None:
    exp = cerebro.expandir(SERVICOS[0], "Fortaleza, CE", user_id=usuario.id)
    scoring = ScoringService()
    com_contato = scoring.pontuar(_lead(email="a@b.com.br", website="https://b.com.br"), exp)
    sem_contato = scoring.pontuar(_lead(), exp)
    assert com_contato.score > sem_contato.score

    grande = scoring.pontuar(_lead(porte=Porte.DEMAIS), exp)
    mei = scoring.pontuar(_lead(porte=Porte.MEI), exp)
    assert grande.score > mei.score


def test_pesos_sempre_normalizam() -> None:
    p = Pesos(aderencia_cnae=10, aderencia_texto=0, contato=0, porte=0, intencao=0, reputacao=0)
    assert abs(sum(p.normalizados().to_dict().values()) - 1.0) < 1e-9
    assert Pesos.from_dict({"contato": 1}).contato > 0


# --- Loop de aprendizado -----------------------------------------------------
def test_loop_nao_ajusta_sem_amostra(session, usuario) -> None:
    loop = LoopAprendizado(session)
    ajuste = loop.recalcular(usuario.id)
    assert not ajuste.aplicado
    assert "amostras insuficientes" in ajuste.motivo


def test_loop_desloca_peso_do_componente_que_prediz(session, usuario) -> None:
    """Se todo lead convertido tinha contato e nenhum descartado tinha, contato sobe."""
    loop = LoopAprendizado(session)
    antes = loop.pesos_de(usuario.id).contato

    for _ in range(MINIMO_AMOSTRAS // 2 + 1):
        loop.observar(
            user_id=usuario.id,
            resultado=StatusLead.CONVERTIDO,
            componentes={"contato": 1.0, "porte": 0.5, "aderencia_cnae": 0.5,
                         "aderencia_texto": 0.5, "intencao": 0.0, "reputacao": 0.5},
        )
        loop.observar(
            user_id=usuario.id,
            resultado=StatusLead.DESCARTADO,
            componentes={"contato": 0.0, "porte": 0.5, "aderencia_cnae": 0.5,
                         "aderencia_texto": 0.5, "intencao": 0.0, "reputacao": 0.5},
        )

    ajuste = loop.recalcular(usuario.id)
    assert ajuste.aplicado, ajuste.motivo
    depois = loop.pesos_de(usuario.id).contato
    assert depois > antes
    assert abs(sum(loop.pesos_de(usuario.id).to_dict().values()) - 1.0) < 1e-6


def test_loop_ignora_transicoes_neutras(session, usuario) -> None:
    loop = LoopAprendizado(session)
    contou = loop.observar(
        user_id=usuario.id, resultado=StatusLead.QUALIFICADO, componentes={"contato": 1.0}
    )
    assert contou is False


def test_restaurar_padrao_zera_o_aprendizado(session, usuario) -> None:
    loop = LoopAprendizado(session)
    loop.observar(
        user_id=usuario.id, resultado=StatusLead.CONVERTIDO, componentes={"contato": 1.0}
    )
    ajuste = loop.restaurar_padrao(usuario.id)
    assert ajuste.aplicado
    assert loop.estado(usuario.id)["amostras"] == 0


def test_transicao_de_lead_alimenta_o_loop(session, usuario, portas_db) -> None:
    """O gancho tem que estar no LeadService, nao no pipeline."""
    from app.models.campaign import Campaign
    from app.services.pipeline import PipelineStub

    campanha = Campaign(
        user_id=usuario.id, nome="Aprendizado", servico=SERVICOS[0], regiao="Fortaleza, CE",
        filtros={},
    )
    session.add(campanha)
    session.flush()
    PipelineStub(session, portas_db).executar(campanha, limite_leads=3)

    from app.domain.lead_state import proximos
    from app.models.enums import Ator
    from app.services.aprendizado import FRACASSO, SUCESSO
    from app.services.audit import AuditService
    from app.services.leads import LeadService

    loop = LoopAprendizado(session)
    antes = loop.estado(usuario.id)["amostras"]
    servico = LeadService(session, AuditService(session))

    # Pega qualquer lead cuja proxima transicao valida seja um desfecho.
    desfechos = SUCESSO | FRACASSO
    for lead in session.query(Lead).filter(Lead.campaign_id == campanha.id).all():
        alvos = [s for s in proximos(lead.status) if s in desfechos]
        if alvos and lead.score_breakdown:
            servico.transicionar(lead, alvos[0], motivo="teste", ator=Ator.USUARIO)
            break
    else:  # pragma: no cover - so acontece se o pipeline mudar de forma
        pytest.fail("nenhum lead com desfecho disponivel")

    assert loop.estado(usuario.id)["amostras"] > antes


# --- API ---------------------------------------------------------------------
def test_api_expandir_mostra_o_porque(client, usuario) -> None:
    r = client.post(
        "/v1/cerebro/expandir",
        json={"servico": SERVICOS[0], "regiao": "Fortaleza, CE", "max_ramos": 5},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ramos"] and corpo["termos"]
    assert corpo["justificativa"]
    assert "excluidos_como_concorrente" in corpo


def test_api_pesos_e_recalculo(client, usuario) -> None:
    estado = client.get("/v1/cerebro/pesos").json()
    assert abs(sum(estado["pesos"].values()) - 1.0) < 1e-6

    ajuste = client.post("/v1/cerebro/pesos/recalcular").json()
    assert ajuste["aplicado"] is False  # sem amostras ainda

    restaurado = client.post("/v1/cerebro/pesos/restaurar").json()
    assert restaurado["aplicado"] is True
