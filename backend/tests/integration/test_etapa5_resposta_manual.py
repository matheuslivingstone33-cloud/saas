"""Etapa 5 — a resposta manual acontece DENTRO do produto.

Antes disto, "assumir a conversa" abria um `mailto:`. Parece equivalente e nao
e: a resposta do lead voltaria para a caixa pessoal do usuario, fora do alcance
do Motor 4, e a thread ficaria com um buraco exatamente no trecho que decide o
negocio.

O que estes testes protegem, em ordem de importancia:

  1. mensagem escrita por gente NAO se declara escrita por IA;
  2. os guardrails valem igual — opt-out nao cede para humano nenhum;
  3. quando a pessoa assume, o agente CALA (cadencia e Motor 4);
  4. e assumir tem volta.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.errors import BloqueadoPorCompliance
from app.core.ids import now
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    Canal,
    Direcao,
    NivelAutonomia,
    OrigemOptOut,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
    TipoContato,
    TipoEvento,
)
from app.models.lead import Lead
from app.models.message import Message
from app.models.opt_out import OptOut
from app.services.cadencia import ServicoDeCadencia
from app.services.conversa import ServicoDeConversa

TEXTO = "Bom dia, Joao. Consigo passar ai quinta as 9h para ver os equipamentos?"


@pytest.fixture
def conversa(session, usuario, portas_db):  # noqa: ANN201
    """Um lead ja abordado, com a primeira mensagem enviada."""
    campanha = Campaign(
        user_id=usuario.id,
        nome="Manual",
        servico="manutencao de ar-condicionado para empresas",
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.CONCLUIDA,
        autonomy_override=NivelAutonomia.AUTOMATICO,
    )
    session.add(campanha)
    session.flush()

    lead = Lead(
        user_id=usuario.id,
        campaign_id=campanha.id,
        cnpj="44555666000154",
        razao_social="HOTEL BRISA MAR LTDA",
        nome_fantasia="Brisa Mar",
        email="gerencia@brisamarhotel.com.br",
        municipio="Fortaleza",
        uf="CE",
        status=StatusLead.ABORDADO,
        provenance={"fonte_primaria": "teste"},
        score=55,
    )
    session.add(lead)
    session.flush()

    session.add(
        Message(
            user_id=usuario.id,
            campaign_id=campanha.id,
            lead_id=lead.id,
            canal=Canal.EMAIL,
            direcao=Direcao.SAIDA,
            status=StatusMensagem.ENVIADA,
            destinatario=lead.email,
            assunto="manutencao de ar-condicionado para Brisa Mar",
            corpo="Ola, equipe da Brisa Mar.",
            enviado_em=now(),
            ordem=1,
            idempotency_key=f"{campanha.id}:{lead.id}:email",
        )
    )
    session.flush()
    return campanha, lead, ServicoDeConversa(session, portas_db)


def _saidas(session, lead) -> list[Message]:
    return list(
        session.execute(
            select(Message)
            .where(Message.lead_id == lead.id, Message.direcao == Direcao.SAIDA)
            .order_by(Message.ordem)
        )
        .scalars()
        .all()
    )


# --- A mensagem que a pessoa escreveu ----------------------------------------
def test_mensagem_humana_nao_se_declara_escrita_por_ia(session, usuario, conversa) -> None:
    """O Marco da IA manda declarar quando E IA. Nao manda mentir que e."""
    _, lead, servico = conversa
    resultado = servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)

    assert resultado.enviada is True
    manual = _saidas(session, lead)[1]
    assert manual.declaracao_ia is None
    assert "inteligencia artificial" not in manual.corpo


def test_mensagem_humana_leva_link_de_descadastro(session, usuario, conversa) -> None:
    """LGPD nao muda porque quem digitou foi gente: continua sendo contato
    comercial nao solicitado."""
    _, lead, servico = conversa
    servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)

    assert _saidas(session, lead)[1].link_descadastro


def test_texto_sai_exatamente_como_foi_escrito(session, usuario, portas_db, conversa) -> None:
    """Nenhum LLM entre a pessoa e o lead. Reescrever o que alguem digitou e
    colocar palavra na boca dela."""
    _, lead, servico = conversa
    chamadas_antes = len(portas_db.llm.chamadas)

    servico.responder_manualmente(lead=lead, corpo=f"  {TEXTO}  ", autor=usuario)

    assert _saidas(session, lead)[1].corpo == TEXTO
    assert len(portas_db.llm.chamadas) == chamadas_antes, "nao pode ter passado por LLM"


def test_mensagem_entra_depois_na_thread(session, usuario, conversa) -> None:
    _, lead, servico = conversa
    servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)

    primeira, manual = _saidas(session, lead)
    assert manual.ordem > primeira.ordem


def test_corpo_vazio_e_recusado(usuario, conversa) -> None:
    _, lead, servico = conversa
    with pytest.raises(BloqueadoPorCompliance):
        servico.responder_manualmente(lead=lead, corpo="   ", autor=usuario)


def test_auditoria_registra_que_foi_pessoa(session, usuario, conversa) -> None:
    _, lead, servico = conversa
    servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)

    registro = session.execute(
        select(AuditLog)
        .where(AuditLog.evento == TipoEvento.MENSAGEM_GERADA)
        .order_by(AuditLog.seq.desc())
        .limit(1)
    ).scalar_one()
    assert registro.ator is Ator.USUARIO
    assert registro.dados["gerado_por"] == "humano"
    assert registro.dados["declara_ia"] is False


# --- Os guardrails valem igual -----------------------------------------------
def test_opt_out_bloqueia_ate_a_mensagem_manual(session, usuario, conversa) -> None:
    """Nenhum humano passa por cima de "nao me contate": o direito e do
    titular, nao do remetente."""
    _, lead, servico = conversa
    session.add(
        OptOut(
            user_id=lead.user_id,
            tipo_contato=TipoContato.EMAIL,
            contato=lead.email,
            contato_normalizado=lead.email,
            origem=OrigemOptOut.LINK_DESCADASTRO,
        )
    )
    session.flush()

    with pytest.raises(BloqueadoPorCompliance, match="opt_out"):
        servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)
    assert len(_saidas(session, lead)) == 1


def test_lead_sem_email_nao_recebe_mensagem_manual(session, usuario, conversa) -> None:
    _, lead, servico = conversa
    lead.email = None
    session.flush()

    with pytest.raises(BloqueadoPorCompliance):
        servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)


# --- Quando a pessoa assume, o agente cala -----------------------------------
def test_responder_marca_a_conversa_como_assumida(usuario, conversa) -> None:
    _, lead, servico = conversa
    assert lead.assumido_em is None

    resultado = servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)

    assert resultado.assumida is True
    assert lead.assumido_em is not None


def test_cadencia_para_na_conversa_assumida(session, usuario, portas_db, conversa) -> None:
    """O toque 2 sairia por cima do que a pessoa acabou de escrever."""
    _, lead, servico = conversa
    servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)

    cadencia = ServicoDeCadencia(session, portas_db)
    estado = cadencia.estado(lead, now() + timedelta(days=30))
    assert estado.encerrada is True
    assert "assumiu" in estado.motivo
    assert cadencia.executar(lead.user_id, agora=now() + timedelta(days=30)).gerados == 0


def test_motor4_nao_responde_em_conversa_assumida(session, usuario, conversa) -> None:
    """Duas vozes escrevendo para o mesmo lead, sem uma saber da outra, e pior
    do que nenhuma."""
    _, lead, servico = conversa
    servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)
    saidas_antes = len(_saidas(session, lead))

    resultado = servico.receber(lead=lead, corpo="Quanto ficaria esse servico?")

    assert resultado.respondeu is False
    assert "assumida" in resultado.motivo
    assert len(_saidas(session, lead)) == saidas_antes, "o agente nao escreveu nada"
    entradas = session.execute(
        select(Message).where(
            Message.lead_id == lead.id, Message.direcao == Direcao.ENTRADA
        )
    ).scalars().all()
    assert len(entradas) == 1, "a resposta do lead continua sendo registrada"


def test_opt_out_continua_valendo_em_conversa_assumida(session, usuario, conversa) -> None:
    """A checagem de conversa assumida vem DEPOIS do opt-out de proposito: o
    direito do titular nao depende de quem conduz a conversa."""
    _, lead, servico = conversa
    servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)

    servico.receber(lead=lead, corpo="Por favor me tire da lista.")

    assert lead.status is StatusLead.OPT_OUT
    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead.email)
    ).scalar_one()
    assert supressao.origem is OrigemOptOut.RESPOSTA_MANUAL


# --- Assumir tem volta -------------------------------------------------------
def test_devolver_para_ia_religa_a_cadencia(session, usuario, portas_db, conversa) -> None:
    """Assumir nao pode ser porta sem volta: um clique errado calaria aquele
    lead para sempre, e a ausencia de mensagem nao aparece em lugar nenhum."""
    _, lead, servico = conversa
    servico.responder_manualmente(lead=lead, corpo=TEXTO, autor=usuario)

    assert servico.devolver_para_ia(lead, usuario) is True
    assert lead.assumido_em is None

    estado = ServicoDeCadencia(session, portas_db).estado(lead, now() + timedelta(days=30))
    assert estado.encerrada is False
    assert estado.devido is True


def test_devolver_conversa_que_ninguem_assumiu_nao_faz_nada(usuario, conversa) -> None:
    _, lead, servico = conversa
    assert servico.devolver_para_ia(lead, usuario) is False


# --- Rotas -------------------------------------------------------------------
def test_api_responde_e_assume(client, session, conversa) -> None:
    _, lead, _ = conversa
    r = client.post(f"/v1/leads/{lead.id}/responder", json={"corpo": TEXTO})

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["enviada"] is True
    assert corpo["assumida"] is True
    assert len(_saidas(session, lead)) == 2


def test_api_recusa_envio_para_contato_suprimido(client, session, conversa) -> None:
    _, lead, _ = conversa
    session.add(
        OptOut(
            user_id=lead.user_id,
            tipo_contato=TipoContato.EMAIL,
            contato=lead.email,
            contato_normalizado=lead.email,
            origem=OrigemOptOut.RESPOSTA_MANUAL,
        )
    )
    session.flush()

    r = client.post(f"/v1/leads/{lead.id}/responder", json={"corpo": TEXTO})

    assert r.status_code == 451, r.text
    assert r.json()["tipo"] == "compliance"


def test_api_devolve_para_ia(client, conversa) -> None:
    _, lead, _ = conversa
    client.post(f"/v1/leads/{lead.id}/responder", json={"corpo": TEXTO})

    r = client.post(f"/v1/leads/{lead.id}/devolver-para-ia")

    assert r.status_code == 200, r.text
    assert r.json()["devolvida"] is True
    assert r.json()["assumida"] is False


def test_api_404_em_lead_inexistente(client, usuario) -> None:
    import uuid as _uuid

    r = client.post(f"/v1/leads/{_uuid.uuid4()}/responder", json={"corpo": TEXTO})
    assert r.status_code == 404


def test_api_recusa_corpo_vazio(client, conversa) -> None:
    _, lead, _ = conversa
    r = client.post(f"/v1/leads/{lead.id}/responder", json={"corpo": ""})
    assert r.status_code == 422, "validacao do schema, antes de chegar ao servico"


def test_lead_expoe_quem_conduz_a_conversa(client, session, conversa) -> None:
    """A interface precisa saber, senao promete resposta do agente numa
    conversa em que ele foi calado."""
    _, lead, _ = conversa
    antes = client.get("/v1/leads?por_pagina=100").json()["itens"]
    assert next(i for i in antes if i["id"] == str(lead.id))["assumido_em"] is None

    client.post(f"/v1/leads/{lead.id}/responder", json={"corpo": TEXTO})

    depois = client.get("/v1/leads?por_pagina=100").json()["itens"]
    assert next(i for i in depois if i["id"] == str(lead.id))["assumido_em"] is not None
