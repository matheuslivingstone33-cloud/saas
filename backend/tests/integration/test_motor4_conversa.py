"""Motor 4 — conversa de duas pontas.

O grosso destes testes nao verifica o que o motor RESPONDE, e sim quando ele
se CALA. Um agente que insiste depois de "nao tenho interesse", ou que
argumenta contra "me tire da lista", queima a reputacao do remetente e expoe o
cliente juridicamente. Silencio na hora certa e a funcionalidade.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.enums import (
    Canal,
    Direcao,
    NivelAutonomia,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
    TipoEvento,
)
from app.models.lead import Lead
from app.models.message import Message
from app.models.opt_out import OptOut
from app.repositories.misc import UserRepository
from app.services.conversa import Intencao, ServicoDeConversa, classificar_por_sinal


@pytest.fixture
def lead_abordado(session, usuario, portas_db) -> Lead:
    """Um lead que ja recebeu a primeira abordagem."""
    campanha = Campaign(
        user_id=usuario.id,
        nome="Conversa",
        servico="manutencao de ar-condicionado para empresas",
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.EXECUTANDO,
    )
    session.add(campanha)
    session.flush()

    lead = Lead(
        user_id=usuario.id,
        campaign_id=campanha.id,
        cnpj="44555666000154",
        razao_social="HOTEL BRISA MAR LTDA",
        email="gerencia@brisamarhotel.com.br",
        municipio="Fortaleza",
        uf="CE",
        status=StatusLead.ABORDADO,
        provenance={"fonte_primaria": "teste"},
        score=45,
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
            assunto="Manutencao preventiva",
            corpo="Ola, equipe do Hotel Brisa Mar.",
        )
    )
    session.flush()
    return lead


# --- Classificacao lexical ---------------------------------------------------
@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Por favor me tire da lista", Intencao.PEDIDO_OPT_OUT),
        ("nao quero receber mais e-mails", Intencao.PEDIDO_OPT_OUT),
        ("Quero falar com uma pessoa, isso é um robô?", Intencao.PEDIDO_HUMANO),
        ("Não tenho interesse, obrigado", Intencao.RECUSA),
        ("Já temos fornecedor", Intencao.RECUSA),
        ("Estou de férias, retorno no dia 10", Intencao.AUSENCIA),
        ("Tenho interesse sim, qual o valor?", Intencao.INTERESSE),
        ("Me manda mais detalhes", Intencao.INTERESSE),
        ("Está caro para o nosso momento", Intencao.OBJECAO),
    ],
)
def test_sinal_lexical_reconhece_o_essencial(texto: str, esperado: Intencao) -> None:
    assert classificar_por_sinal(texto) is esperado


def test_opt_out_ganha_de_interesse_na_mesma_frase() -> None:
    """"Nao quero receber, mas quanto custa?" e opt-out.

    Em caso de duvida o direito do titular ganha do negocio — e a ordem das
    regras no Motor 4 e o que garante isso.
    """
    texto = "nao quero receber mais nada de voces, mas qual o valor?"
    assert classificar_por_sinal(texto) is Intencao.PEDIDO_OPT_OUT


def test_texto_ambiguo_nao_e_classificado_por_sinal() -> None:
    """Quando nao ha sinal claro, o lexical devolve None e o LLM decide."""
    assert classificar_por_sinal("bom dia, tudo bem?") is None


# --- Guardrails: quando o motor se cala --------------------------------------
def test_pedido_de_opt_out_registra_supressao_e_nao_responde(
    session, usuario, portas_db, lead_abordado
) -> None:
    motor = ServicoDeConversa(session, portas_db)
    r = motor.receber(lead=lead_abordado, corpo="Por favor me tire da lista.")

    assert r.intencao is Intencao.PEDIDO_OPT_OUT
    assert r.encerrou and not r.respondeu
    assert r.resposta_id is None

    assert lead_abordado.status is StatusLead.OPT_OUT

    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead_abordado.email)
    ).scalar_one_or_none()
    assert supressao is not None, "o opt-out precisa ficar registrado, nao so no lead"

    saidas = session.execute(
        select(Message).where(
            Message.lead_id == lead_abordado.id, Message.direcao == Direcao.SAIDA
        )
    ).scalars().all()
    assert len(saidas) == 1, "nenhuma mensagem nova pode sair depois do opt-out"


def test_recusa_encerra_sem_insistir(session, usuario, portas_db, lead_abordado) -> None:
    motor = ServicoDeConversa(session, portas_db)
    r = motor.receber(lead=lead_abordado, corpo="Não tenho interesse, obrigado.")

    assert r.intencao is Intencao.RECUSA
    assert r.encerrou and r.resposta_id is None
    assert lead_abordado.status is StatusLead.DESCARTADO


def test_pedido_de_humano_nao_recebe_resposta_de_ia_nem_no_automatico(
    session, usuario, portas_db, lead_abordado
) -> None:
    """O piloto automatico NAO pode atropelar quem pediu uma pessoa."""
    UserRepository(session).assinatura(usuario.id).autonomy_level = NivelAutonomia.AUTOMATICO
    session.flush()

    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Quero falar com uma pessoa, por favor."
    )
    assert r.intencao is Intencao.PEDIDO_HUMANO
    assert r.encerrou and r.resposta_id is None
    assert "humano" in r.motivo


def test_resposta_automatica_de_ausencia_nao_gera_resposta(
    session, usuario, portas_db, lead_abordado
) -> None:
    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Estou de férias, retorno no dia 10."
    )
    assert r.intencao is Intencao.AUSENCIA
    assert r.resposta_id is None
    # O lead respondeu formalmente, mas nao leu nada — segue como respondido
    # sem virar descarte nem opt-out.
    assert lead_abordado.status is StatusLead.RESPONDIDO


# --- Quando o motor responde -------------------------------------------------
def test_interesse_gera_resposta_aguardando_aprovacao_no_assistido(
    session, usuario, portas_db, lead_abordado
) -> None:
    UserRepository(session).assinatura(usuario.id).autonomy_level = NivelAutonomia.ASSISTIDO
    session.flush()

    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Tenho interesse sim, me manda mais detalhes."
    )

    assert r.intencao is Intencao.INTERESSE
    assert r.aguardando_aprovacao and not r.respondeu
    assert r.resposta_id is not None

    resposta = session.get(Message, r.resposta_id)
    assert resposta.status is StatusMensagem.AGUARDANDO_APROVACAO
    assert resposta.declaracao_ia, "toda resposta da IA declara que e IA"
    assert resposta.link_descadastro


def test_interesse_dispara_sozinho_no_automatico(
    session, usuario, portas_db, lead_abordado, settings
) -> None:
    UserRepository(session).assinatura(usuario.id).autonomy_level = NivelAutonomia.AUTOMATICO
    session.flush()

    antes = len(list(settings.outbox_path.glob("*.json")))
    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Tenho interesse sim, podemos conversar."
    )
    depois = len(list(settings.outbox_path.glob("*.json")))

    assert r.respondeu and not r.aguardando_aprovacao
    assert depois == antes + 1, "no automatico a resposta sai para a caixa de saida"


def test_lead_quente_e_sinalizado(session, usuario, portas_db, lead_abordado) -> None:
    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Quanto custa? Temos interesse."
    )
    assert r.to_dict()["lead_quente"] is True


def test_objecao_recebe_resposta_sem_inventar_preco(
    session, usuario, portas_db, lead_abordado
) -> None:
    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Está caro para o nosso momento."
    )
    assert r.intencao is Intencao.OBJECAO
    assert r.resposta_id is not None

    corpo = session.get(Message, r.resposta_id).corpo
    assert "R$" not in corpo, "preco depende de escopo; a IA nao pode inventar numero"


# --- Estado e trilha ---------------------------------------------------------
def test_resposta_move_o_lead_para_respondido(
    session, usuario, portas_db, lead_abordado
) -> None:
    """O estado `respondido` existia e nunca acontecia. Agora acontece."""
    assert lead_abordado.status is StatusLead.ABORDADO
    ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Me manda mais detalhes."
    )
    assert lead_abordado.status is StatusLead.RESPONDIDO


def test_entrada_vira_mensagem_na_thread(session, usuario, portas_db, lead_abordado) -> None:
    ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado,
        corpo="Bom dia! Me manda mais detalhes.",
        remetente="OUTRO@Brisamar.com.BR",
    )
    entradas = session.execute(
        select(Message).where(
            Message.lead_id == lead_abordado.id, Message.direcao == Direcao.ENTRADA
        )
    ).scalars().all()
    assert len(entradas) == 1
    assert entradas[0].remetente == "OUTRO@Brisamar.com.BR"
    assert entradas[0].destinatario is None


def test_conversa_deixa_trilha_de_auditoria(session, usuario, portas_db, lead_abordado) -> None:
    from app.models.audit_log import AuditLog

    ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Tenho interesse, qual o valor?"
    )
    eventos = {
        e.evento
        for e in session.execute(select(AuditLog)).scalars().all()
    }
    assert TipoEvento.RESPOSTA_RECEBIDA in eventos
    assert TipoEvento.CONVERSA_RESPONDIDA in eventos


def test_nao_responde_duas_vezes_o_mesmo_turno(
    session, usuario, portas_db, lead_abordado
) -> None:
    """Webhook duplicado e comum. A idempotencia evita responder em dobro."""
    motor = ServicoDeConversa(session, portas_db)
    primeira = motor.receber(lead=lead_abordado, corpo="Me manda mais detalhes.")
    assert primeira.resposta_id is not None

    saidas_antes = len(
        session.execute(
            select(Message).where(
                Message.lead_id == lead_abordado.id, Message.direcao == Direcao.SAIDA
            )
        ).scalars().all()
    )
    # Mesma pergunta chegando de novo, mesmo turno.
    motor.receber(lead=lead_abordado, corpo="Me manda mais detalhes.")
    saidas_depois = len(
        session.execute(
            select(Message).where(
                Message.lead_id == lead_abordado.id, Message.direcao == Direcao.SAIDA
            )
        ).scalars().all()
    )
    assert saidas_depois == saidas_antes + 1, (
        "o segundo turno gera UMA resposta nova, nao duas"
    )


# --- Rotas -------------------------------------------------------------------
def test_simulacao_pela_api(client, usuario, session, portas_db, lead_abordado) -> None:
    r = client.post(
        f"/v1/leads/{lead_abordado.id}/simular-resposta",
        json={"corpo": "Tenho interesse, podemos conversar?"},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["intencao"] == "interesse"
    assert corpo["lead_quente"] is True


def test_webhook_aceita_sem_vazar_se_o_lead_existe(client, usuario) -> None:
    """Endereco desconhecido tambem devolve 202: 404 diria ao remetente quais
    e-mails estao na base."""
    r = client.post(
        "/v1/inbound/email",
        json={"remetente": "ninguem@exemplo.com", "corpo": "oi"},
    )
    assert r.status_code == 202
    assert r.json()["casou_com_lead"] is False


def test_intencoes_expostas_com_o_que_disparam(client, usuario) -> None:
    r = client.get("/v1/conversas/intencoes")
    assert r.status_code == 200
    por_valor = {i["valor"]: i for i in r.json()["intencoes"]}
    assert por_valor["pedido_opt_out"]["gera_resposta"] is False
    assert por_valor["recusa"]["gera_resposta"] is False
    assert por_valor["pedido_humano"]["gera_resposta"] is False
    assert por_valor["interesse"]["gera_resposta"] is True
    assert por_valor["interesse"]["lead_quente"] is True


def test_thread_fica_na_ordem_certa(session, usuario, portas_db, lead_abordado) -> None:
    """A pergunta do lead vem ANTES da resposta da IA.

    Regressao real: a ordem saia do `created_at`, e relogio nao serve como
    chave aqui — `datetime.now()` no Windows tem granularidade de ~15ms, entao
    a pergunta e a replica do mesmo turno saiam com carimbo IDENTICO e a thread
    aparecia invertida. A ordem agora e um numero explicito por conversa.
    """
    ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Tenho interesse, me manda mais detalhes."
    )

    thread = list(
        session.execute(
            select(Message)
            .where(Message.lead_id == lead_abordado.id)
            .order_by(Message.ordem, Message.created_at)
        ).scalars().all()
    )
    direcoes = [m.direcao for m in thread]

    assert direcoes == [Direcao.SAIDA, Direcao.ENTRADA, Direcao.SAIDA], (
        "esperado: abordagem, resposta do lead, replica da IA — nesta ordem"
    )
    ordens = [m.ordem for m in thread]
    assert ordens == sorted(ordens) and len(set(ordens)) == len(ordens), (
        "cada mensagem precisa de um numero proprio e crescente na conversa"
    )
