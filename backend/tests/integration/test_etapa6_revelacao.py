"""Etapa 6 — o paywall passa a ser do servidor, e cobra pelo que tem valor.

O corte das "3 melhores" era um `slice(0, 3)` na TELA: a API devolvia as 42
empresas com CNPJ, e-mail e telefone. Qualquer pessoa com o devtools aberto via
tudo que o plano PRO cobrava — cortina, nao porta.

E o eixo do que se cobra mudou junto: descoberta deixou de custar credito
(cobrar por lead descoberto punia o cliente quando o Cerebro errava a mira) e
CONTATO REVELADO passou a custar.

O que estes testes protegem:

  1. lead nao revelado nao vaza contato, nem na listagem nem no detalhe;
  2. o que tem valor SEM o contato continua visivel — e o que faz querer pagar;
  3. revelar cobra uma vez so;
  4. abordar tambem revela, senao o paywall cairia com um clique.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import SaldoInsuficiente
from app.models.campaign import Campaign
from app.models.credit_ledger import CreditLedger
from app.models.enums import (
    NivelAutonomia,
    Plano,
    Porte,
    StatusCampanha,
    StatusLead,
)
from app.models.lead import Lead
from app.repositories.misc import UserRepository
from app.services.creditos import REVELACOES_GRATIS_POR_CAMPANHA, CreditService
from app.services.envio import SendService
from app.services.revelacao import ServicoDeRevelacao, mascarar


@pytest.fixture
def campanha(session, usuario) -> Campaign:
    c = Campaign(
        user_id=usuario.id,
        nome="Revelacao",
        servico="manutencao de ar-condicionado para empresas",
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.PRONTA,
        autonomy_override=NivelAutonomia.AUTOMATICO,
    )
    session.add(c)
    session.flush()
    return c


def _lead(session, usuario, campanha, i: int = 0, **extra) -> Lead:
    campos = {
        "cnpj": f"4455566600015{i}",
        "razao_social": f"HOTEL BRISA MAR {i} LTDA",
        "nome_fantasia": f"Brisa Mar {i}",
        "email": f"gerencia{i}@brisamarhotel.com.br",
        "telefone": "8533334444",
        "website": "https://brisamarhotel.com.br",
        "bairro": "Meireles",
        "municipio": "Fortaleza",
        "uf": "CE",
        "cnae_principal": "5510801",
        "porte": Porte.EPP,
        "status": StatusLead.QUALIFICADO,
        "provenance": {"fonte_primaria": "teste"},
        "score": 70 - i,
        "score_breakdown": {"componentes": {"aderencia_cnae": 0.9}},
        "place_id": f"place-{i}",
    }
    campos.update(extra)
    lead = Lead(user_id=usuario.id, campaign_id=campanha.id, **campos)
    session.add(lead)
    session.flush()
    return lead


# --- A mascara ---------------------------------------------------------------
def test_lead_nao_revelado_nao_entrega_contato(session, usuario, campanha) -> None:
    lead = _lead(session, usuario, campanha)
    saida = mascarar(lead)

    assert saida["revelado"] is False
    for campo in ("razao_social", "nome_fantasia", "cnpj", "email", "telefone", "website"):
        assert saida[campo] is None, f"{campo} vazou sem revelacao"


def test_o_que_faz_querer_pagar_continua_visivel(session, usuario, campanha) -> None:
    """Ver que existem 39 hoteis e nao poder falar com eles e o que vende."""
    lead = _lead(session, usuario, campanha)
    saida = mascarar(lead)

    assert saida["cnae_principal"] == "5510801"
    assert saida["bairro"] == "Meireles"
    assert saida["municipio"] == "Fortaleza"
    assert saida["porte"] is Porte.EPP
    assert saida["score"] == 70
    # O insight do cartao sai daqui: sem o breakdown, o cartao nao teria o
    # "por que esta empresa" — que e justamente a parte que convence.
    assert saida["score_breakdown"]["componentes"]["aderencia_cnae"] == 0.9


def test_lead_revelado_sai_completo(session, usuario, campanha) -> None:
    lead = _lead(session, usuario, campanha)
    ServicoDeRevelacao(session).revelar(lead)

    saida = mascarar(lead)
    assert saida["revelado"] is True
    assert saida["email"] == "gerencia0@brisamarhotel.com.br"
    assert saida["cnpj"] == "44555666000150"


def test_api_nao_vaza_contato_na_listagem(client, session, usuario, campanha) -> None:
    """O corte e do servidor: abrir o devtools nao mostra mais nada."""
    _lead(session, usuario, campanha, i=1)
    _lead(session, usuario, campanha, i=2)

    itens = client.get("/v1/leads?por_pagina=100").json()["itens"]

    assert itens, "a listagem continua devolvendo os leads"
    for item in itens:
        assert item["revelado"] is False
        assert item["email"] is None
        assert item["cnpj"] is None
        assert item["razao_social"] is None
        assert item["score"] is not None, "o valor continua visivel"


# --- Revelar cobra, e cobra uma vez -----------------------------------------
def test_revelar_debita_um_credito(session, usuario, campanha) -> None:
    lead = _lead(session, usuario, campanha)
    antes = CreditService(session).ledger.saldo(usuario.id)

    ServicoDeRevelacao(session).revelar(lead)

    assert lead.revelado_em is not None
    assert CreditService(session).ledger.saldo(usuario.id) == antes - 1


def test_revelar_duas_vezes_nao_cobra_duas_vezes(session, usuario, campanha) -> None:
    """Um duplo clique nao pode custar dois creditos."""
    lead = _lead(session, usuario, campanha)
    servico = ServicoDeRevelacao(session)

    assert servico.revelar(lead) is True
    antes = CreditService(session).ledger.saldo(usuario.id)
    assert servico.revelar(lead) is False

    assert CreditService(session).ledger.saldo(usuario.id) == antes


def test_revelar_conta_no_teto_do_mes(session, usuario, campanha) -> None:
    """O teto do plano passou a contar contato revelado, nao lead descoberto."""
    lead = _lead(session, usuario, campanha)
    assinatura = UserRepository(session).assinatura(usuario.id)
    antes = assinatura.leads_consumidos_mes

    ServicoDeRevelacao(session).revelar(lead)

    assert assinatura.leads_consumidos_mes == antes + 1


def test_revelacao_deixa_lancamento_no_extrato(session, usuario, campanha) -> None:
    lead = _lead(session, usuario, campanha)
    ServicoDeRevelacao(session).revelar(lead, motivo="revelado na Descoberta")

    lancamento = session.execute(
        select(CreditLedger)
        .where(CreditLedger.user_id == usuario.id)
        .order_by(CreditLedger.created_at.desc())
        .limit(1)
    ).scalar_one()
    assert lancamento.quantidade == -1
    assert lancamento.metadados["operacao"] == "contato_revelado"


# --- As duas travas ----------------------------------------------------------
def test_plano_gratuito_libera_tres_por_busca(session, usuario, campanha) -> None:
    """A trava por campanha mantem "as 3 melhores" valendo em toda busca nova."""
    servico = ServicoDeRevelacao(session)
    for i in range(REVELACOES_GRATIS_POR_CAMPANHA):
        servico.revelar(_lead(session, usuario, campanha, i=i))

    quarto = _lead(session, usuario, campanha, i=9)
    with pytest.raises(SaldoInsuficiente, match="por busca"):
        servico.revelar(quarto)


def test_a_trava_e_por_busca_nao_por_conta(session, usuario, campanha) -> None:
    """Busca nova, tres contatos novos — senao o gratuito so serve uma vez."""
    servico = ServicoDeRevelacao(session)
    for i in range(REVELACOES_GRATIS_POR_CAMPANHA):
        servico.revelar(_lead(session, usuario, campanha, i=i))

    outra = Campaign(
        user_id=usuario.id,
        nome="Outra busca",
        servico="limpeza para empresas",
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.PRONTA,
    )
    session.add(outra)
    session.flush()

    assert servico.revelar(_lead(session, usuario, outra, i=5)) is True


def test_teto_do_mes_bloqueia_mesmo_com_busca_nova(session, usuario, campanha) -> None:
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.leads_consumidos_mes = assinatura.teto_leads_mes
    session.flush()

    lead = _lead(session, usuario, campanha)
    with pytest.raises(SaldoInsuficiente):
        ServicoDeRevelacao(session).revelar(lead)


def test_plano_pago_nao_tem_trava_por_busca(session, usuario, campanha) -> None:
    """Quem paga ja esta limitado pelo teto do mes; duas regras so confundem."""
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.plano = Plano.PRO
    session.flush()

    servico = ServicoDeRevelacao(session)
    for i in range(REVELACOES_GRATIS_POR_CAMPANHA + 2):
        assert servico.revelar(_lead(session, usuario, campanha, i=i)) is True

    assert servico.cota(usuario.id, campanha.id).por_campanha is None


def test_a_mensagem_do_bloqueio_diz_a_regra_certa(session, usuario, campanha) -> None:
    """Quem esbarrou na trava da busca nao pode ler "compre creditos": comprar
    nao resolveria o bloqueio dele."""
    servico = ServicoDeRevelacao(session)
    for i in range(REVELACOES_GRATIS_POR_CAMPANHA):
        servico.revelar(_lead(session, usuario, campanha, i=i))

    cota = servico.cota(usuario.id, campanha.id)
    assert "por busca" in cota.motivo_de_bloqueio()
    assert cota.creditos > 0, "ainda ha credito: a trava e de plano, nao de saldo"


# --- Abordar revela ----------------------------------------------------------
def test_abordar_revela_o_contato(session, usuario, portas_db, campanha) -> None:
    """A mensagem cita o nome da empresa e o e-mail. Sem cobrar aqui, o paywall
    cairia com um clique em "iniciar abordagem"."""
    lead = _lead(session, usuario, campanha)
    envio = SendService(session, portas_db)

    lote = envio.preparar_lote(campanha, [lead], None)

    assert lote.enviadas == 1
    assert lead.revelado_em is not None


def test_sem_cota_a_abordagem_e_bloqueada(session, usuario, portas_db, campanha) -> None:
    servico = ServicoDeRevelacao(session)
    for i in range(REVELACOES_GRATIS_POR_CAMPANHA):
        servico.revelar(_lead(session, usuario, campanha, i=i))

    alvo = _lead(session, usuario, campanha, i=9)
    lote = SendService(session, portas_db).preparar_lote(campanha, [alvo], None)

    assert lote.enviadas == 0
    assert lote.motivos_bloqueio.get("cota_de_contatos") == 1
    assert alvo.revelado_em is None


# --- Rotas -------------------------------------------------------------------
def test_api_revela_e_devolve_o_contato(client, session, usuario, campanha) -> None:
    lead = _lead(session, usuario, campanha)

    r = client.post(f"/v1/leads/{lead.id}/revelar")

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["revelado"] is True
    assert corpo["email"] == "gerencia0@brisamarhotel.com.br"


def test_api_recusa_revelar_sem_cota(client, session, usuario, campanha) -> None:
    servico = ServicoDeRevelacao(session)
    for i in range(REVELACOES_GRATIS_POR_CAMPANHA):
        servico.revelar(_lead(session, usuario, campanha, i=i))
    alvo = _lead(session, usuario, campanha, i=9)

    r = client.post(f"/v1/leads/{alvo.id}/revelar")

    assert r.status_code == 402, r.text
    assert r.json()["tipo"] == "saldo"


def test_api_mostra_a_cota_da_busca(client, session, usuario, campanha) -> None:
    lead = _lead(session, usuario, campanha)

    corpo = client.get(f"/v1/leads/{lead.id}/cota").json()

    assert corpo["por_campanha"] == REVELACOES_GRATIS_POR_CAMPANHA
    assert corpo["restantes_na_campanha"] == REVELACOES_GRATIS_POR_CAMPANHA
    assert corpo["bloqueio"] is None
