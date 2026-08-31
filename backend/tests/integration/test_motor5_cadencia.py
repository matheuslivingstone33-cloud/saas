"""Motor 5 — cadencia, e a supressao por retorno do provedor.

Como no Motor 4, o grosso destes testes nao verifica o toque que SAI, e sim os
casos em que ele NAO sai. Um segundo toque para quem ja respondeu, para quem
pediu para sair ou para um endereco que voltou como inexistente e pior do que
nao ter cadencia nenhuma: queima o dominio do cliente, e dominio queimado leva
junto o e-mail com que ele fatura.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.ids import now
from app.models.campaign import Campaign
from app.models.enums import (
    Canal,
    Direcao,
    NivelAutonomia,
    OrigemOptOut,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
    TipoContato,
)
from app.models.lead import Lead
from app.models.message import Message
from app.models.opt_out import OptOut
from app.services.cadencia import ServicoDeCadencia
from app.services.entregabilidade import ServicoDeEntregabilidade, TipoRetorno


def _campanha(session, usuario, nivel: NivelAutonomia) -> Campaign:
    campanha = Campaign(
        user_id=usuario.id,
        nome="Cadencia",
        servico="manutencao de ar-condicionado para empresas",
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.EXECUTANDO,
        autonomy_override=nivel,
        expansao={
            "servico": "manutencao de ar-condicionado",
            "regiao": "Fortaleza, CE",
            "termos": ["hotel"],
            "ramos": [
                {
                    "codigo": "5510801",
                    "descricao": "Hoteis",
                    "distancia": 0.2,
                    "peso": 0.9,
                    "termos": ["hospedagem", "climatizacao de quartos"],
                }
            ],
        },
    )
    session.add(campanha)
    session.flush()
    return campanha


def _lead(session, usuario, campanha, **extra) -> Lead:
    campos = {
        "cnpj": "44555666000154",
        "razao_social": "HOTEL BRISA MAR LTDA",
        "nome_fantasia": "Brisa Mar",
        "email": "gerencia@brisamarhotel.com.br",
        "municipio": "Fortaleza",
        "uf": "CE",
        "cnae_principal": "5510801",
        "status": StatusLead.ABORDADO,
        "provenance": {"fonte_primaria": "teste"},
        "score": 45,
    }
    campos.update(extra)
    lead = Lead(user_id=usuario.id, campaign_id=campanha.id, **campos)
    session.add(lead)
    session.flush()
    return lead


def _primeiro_toque(session, usuario, campanha, lead, **extra) -> Message:
    """A abordagem que ja saiu. Sem ela nao existe cadencia: o toque 2 e o
    segundo de alguma coisa."""
    padrao = {
        "status": StatusMensagem.ENVIADA,
        "enviado_em": now(),
        "ordem": 1,
        "idempotency_key": f"{campanha.id}:{lead.id}:email",
    }
    padrao.update(extra)
    mensagem = Message(
        user_id=usuario.id,
        campaign_id=campanha.id,
        lead_id=lead.id,
        canal=Canal.EMAIL,
        direcao=Direcao.SAIDA,
        destinatario=lead.email,
        assunto="manutencao de ar-condicionado para Brisa Mar",
        corpo="Ola, equipe da Brisa Mar.",
        metadados={"toque": 1, "angulo": "insight"},
        **padrao,
    )
    session.add(mensagem)
    session.flush()
    return mensagem


@pytest.fixture
def automatico(session, usuario, portas_db):  # noqa: ANN201
    campanha = _campanha(session, usuario, NivelAutonomia.AUTOMATICO)
    lead = _lead(session, usuario, campanha)
    _primeiro_toque(session, usuario, campanha, lead)
    return campanha, lead, ServicoDeCadencia(session, portas_db)


@pytest.fixture
def assistido(session, usuario, portas_db):  # noqa: ANN201
    campanha = _campanha(session, usuario, NivelAutonomia.ASSISTIDO)
    lead = _lead(session, usuario, campanha)
    _primeiro_toque(session, usuario, campanha, lead)
    return campanha, lead, ServicoDeCadencia(session, portas_db)


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


# --- Quando o toque sai ------------------------------------------------------
def test_toque_2_so_depois_da_espera(automatico) -> None:
    _, lead, servico = automatico

    hoje = servico.estado(lead)
    assert hoje.devido is False, "o toque 2 nao sai no mesmo dia do primeiro"
    assert hoje.proximo_toque == 2

    daqui_4_dias = servico.estado(lead, now() + timedelta(days=4))
    assert daqui_4_dias.devido is True
    assert daqui_4_dias.encerrada is False


def test_toque_2_sai_com_angulo_e_assunto_proprios(session, automatico) -> None:
    """Um toque que repete o anterior e spam com outro nome."""
    _, lead, servico = automatico
    resultado = servico.executar(lead.user_id, agora=now() + timedelta(days=4))

    assert resultado.gerados == 1
    assert resultado.enviados == 1
    primeiro, segundo = _saidas(session, lead)
    assert segundo.assunto != primeiro.assunto
    assert segundo.corpo != primeiro.corpo
    assert segundo.metadados["toque"] == 2
    assert segundo.metadados["angulo"] == "prova"
    assert segundo.ordem > primeiro.ordem, "o toque entra DEPOIS na thread"


def test_todo_toque_declara_ia_e_leva_descadastro(session, automatico) -> None:
    """O guardrail nao vale so para a primeira mensagem."""
    _, lead, servico = automatico
    servico.executar(lead.user_id, agora=now() + timedelta(days=4))

    segundo = _saidas(session, lead)[1]
    assert segundo.declaracao_ia
    assert "inteligencia artificial" in segundo.corpo
    assert segundo.link_descadastro


def test_toque_3_e_a_pergunta_de_encerramento(session, automatico) -> None:
    _, lead, servico = automatico
    servico.executar(lead.user_id, agora=now() + timedelta(days=4))
    servico.executar(lead.user_id, agora=now() + timedelta(days=9))

    terceiro = _saidas(session, lead)[2]
    assert terceiro.metadados["toque"] == 3
    assert terceiro.metadados["angulo"] == "saida"
    assert "Encerro por aqui" in terceiro.assunto


def test_cadencia_para_no_teto_de_toques(session, automatico) -> None:
    """Tres toques e o lead descansa. Lista eterna e o comeco do spam."""
    _, lead, servico = automatico
    servico.executar(lead.user_id, agora=now() + timedelta(days=4))
    servico.executar(lead.user_id, agora=now() + timedelta(days=9))
    ultimo = servico.executar(lead.user_id, agora=now() + timedelta(days=30))

    assert ultimo.gerados == 0
    assert len(_saidas(session, lead)) == 3
    assert servico.estado(lead).encerrada is True
    assert "completa" in servico.estado(lead).motivo


def test_cada_toque_tem_chave_de_idempotencia_propria(session, automatico) -> None:
    _, lead, servico = automatico
    servico.executar(lead.user_id, agora=now() + timedelta(days=4))
    servico.executar(lead.user_id, agora=now() + timedelta(days=9))

    chaves = [m.idempotency_key for m in _saidas(session, lead)]
    assert len(set(chaves)) == 3
    assert chaves[1].endswith(":t2")
    assert chaves[2].endswith(":t3")


def test_toque_nao_paga_sinal_de_intencao_de_novo(session, automatico) -> None:
    """Web search e balde 2. O que ela acha nao muda em tres dias."""
    _, lead, servico = automatico
    servico.executar(lead.user_id, agora=now() + timedelta(days=4))

    segundo = _saidas(session, lead)[1]
    assert segundo.metadados["usou_web_search"] is False


# --- Quando o toque NAO sai --------------------------------------------------
def test_nao_toca_quem_ja_respondeu(session, automatico) -> None:
    _, lead, servico = automatico
    lead.status = StatusLead.RESPONDIDO
    session.flush()

    estado = servico.estado(lead, now() + timedelta(days=10))
    assert estado.encerrada is True
    assert "Motor 4" in estado.motivo
    assert servico.executar(lead.user_id, agora=now() + timedelta(days=10)).gerados == 0


def test_nao_toca_quem_tem_resposta_na_thread(session, usuario, automatico) -> None:
    """Defesa dupla: mesmo com o status desatualizado, a resposta manda parar."""
    campanha, lead, servico = automatico
    session.add(
        Message(
            user_id=usuario.id,
            campaign_id=campanha.id,
            lead_id=lead.id,
            canal=Canal.EMAIL,
            direcao=Direcao.ENTRADA,
            status=StatusMensagem.RESPONDIDA,
            remetente=lead.email,
            corpo="Pode me mandar mais detalhes?",
            ordem=2,
        )
    )
    session.flush()

    assert servico.estado(lead, now() + timedelta(days=10)).encerrada is True


def test_nao_toca_quem_pediu_para_sair(session, automatico) -> None:
    _, lead, servico = automatico
    lead.status = StatusLead.OPT_OUT
    session.flush()

    estado = servico.estado(lead, now() + timedelta(days=10))
    assert estado.encerrada is True
    assert "nao ser contatado" in estado.motivo


def test_nao_toca_lead_descartado(session, automatico) -> None:
    _, lead, servico = automatico
    lead.status = StatusLead.DESCARTADO
    session.flush()

    assert servico.estado(lead, now() + timedelta(days=10)).encerrada is True


def test_supressao_bloqueia_o_toque_mesmo_com_lead_abordado(session, automatico) -> None:
    """O opt-out e revalidado no momento do toque, nao na geracao anterior."""
    _, lead, servico = automatico
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

    resultado = servico.executar(lead.user_id, agora=now() + timedelta(days=4))
    assert resultado.gerados == 0
    assert resultado.motivos.get("opt_out") == 1
    assert len(_saidas(session, lead)) == 1


def test_campanha_pausada_nao_recebe_toque(session, automatico) -> None:
    campanha, lead, servico = automatico
    campanha.status = StatusCampanha.PAUSADA
    session.flush()

    estado = servico.estado(lead, now() + timedelta(days=10))
    assert estado.encerrada is True
    assert "pausada" in estado.motivo


def test_campanha_concluida_continua_com_a_cadencia(session, automatico) -> None:
    """A rodada acaba em segundos; o toque 2 sai tres dias depois.

    Toda campanha termina em `concluida` assim que o pipeline roda. Se isso
    parasse a cadencia, o Motor 5 nunca rodaria para ninguem — foi exatamente
    o que apareceu ao abrir a tela pela primeira vez, com a lista vazia.
    """
    campanha, lead, servico = automatico
    campanha.status = StatusCampanha.CONCLUIDA
    session.flush()

    estado = servico.estado(lead, now() + timedelta(days=4))
    assert estado.encerrada is False
    assert estado.devido is True
    assert servico.executar(lead.user_id, agora=now() + timedelta(days=4)).enviados == 1


def test_nao_empilha_toque_sobre_mensagem_pendente(session, assistido) -> None:
    """No assistido, o toque fica esperando aprovacao — e nenhum outro nasce
    em cima dele. Tres mensagens para aprovar de uma vez seria a interface
    empurrando o usuario a aprovar sem ler."""
    _, lead, servico = assistido
    primeira = servico.executar(lead.user_id, agora=now() + timedelta(days=4))
    assert primeira.aguardando_aprovacao == 1
    assert primeira.enviados == 0

    segunda = servico.executar(lead.user_id, agora=now() + timedelta(days=20))
    assert segunda.gerados == 0
    assert len(_saidas(session, lead)) == 2


def test_cadencia_desligada_nao_gera_nada(session, portas_db, automatico) -> None:
    _, lead, _ = automatico
    desligada = get_settings().model_copy(update={"cadencia_ativa": False})
    servico = ServicoDeCadencia(session, portas_db, settings=desligada)

    resultado = servico.executar(lead.user_id, agora=now() + timedelta(days=30), forcar=True)
    assert resultado.gerados == 0
    assert resultado.motivos == {"cadencia_desligada": 1}


def test_lead_ainda_nao_abordado_nao_entra_na_cadencia(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, NivelAutonomia.AUTOMATICO)
    lead = _lead(session, usuario, campanha, status=StatusLead.QUALIFICADO)
    servico = ServicoDeCadencia(session, portas_db)

    assert servico.estado(lead).encerrada is True
    assert servico.executar(usuario.id, agora=now() + timedelta(days=30)).gerados == 0


# --- Entregabilidade ---------------------------------------------------------
def test_bounce_permanente_suprime_e_descarta(session, automatico) -> None:
    _, lead, _ = automatico
    resultado = ServicoDeEntregabilidade(session).registrar(
        contato=lead.email, tipo=TipoRetorno.PERMANENTE, diagnostico="550 no such user"
    )

    assert resultado.suprimido is True
    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead.email)
    ).scalar_one()
    assert supressao.origem is OrigemOptOut.BOUNCE_PERMANENTE
    assert lead.status is StatusLead.DESCARTADO, "endereco morto nao e opt-out do titular"

    mensagem = _saidas(session, lead)[0]
    assert mensagem.retorno == "permanente"
    assert mensagem.status is StatusMensagem.FALHOU


def test_reclamacao_de_spam_tem_origem_propria(session, automatico) -> None:
    """Somar reclamacao com bounce esconderia o sinal que manda parar."""
    _, lead, _ = automatico
    ServicoDeEntregabilidade(session).registrar(
        contato=lead.email, tipo=TipoRetorno.RECLAMACAO
    )

    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead.email)
    ).scalar_one()
    assert supressao.origem is OrigemOptOut.RECLAMACAO_SPAM
    assert lead.status is StatusLead.OPT_OUT, "quem reclamou manifestou vontade"
    assert _saidas(session, lead)[0].status is StatusMensagem.ENVIADA, (
        "a mensagem foi entregue e lida — marcar como falha apagaria isso"
    )


def test_retorno_temporario_nao_suprime_ninguem(session, automatico) -> None:
    """Caixa cheia hoje nao e cliente ruim para sempre."""
    _, lead, _ = automatico
    resultado = ServicoDeEntregabilidade(session).registrar(
        contato=lead.email, tipo=TipoRetorno.TRANSITORIO, diagnostico="452 mailbox full"
    )

    assert resultado.suprimido is False
    assert lead.status is StatusLead.ABORDADO
    assert (
        session.execute(
            select(OptOut).where(OptOut.contato_normalizado == lead.email)
        ).first()
        is None
    )
    assert _saidas(session, lead)[0].status is StatusMensagem.ENVIADA


def test_bounce_encerra_a_cadencia_daquele_lead(session, automatico) -> None:
    """O teste que amarra os dois motores."""
    _, lead, servico = automatico
    ServicoDeEntregabilidade(session).registrar(
        contato=lead.email, tipo=TipoRetorno.PERMANENTE
    )

    resultado = servico.executar(lead.user_id, agora=now() + timedelta(days=4))
    assert resultado.gerados == 0
    assert len(_saidas(session, lead)) == 1


def test_taxa_de_retorno_alta_pausa_a_campanha(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, NivelAutonomia.AUTOMATICO)
    for i in range(30):
        alvo = _lead(
            session, usuario, campanha,
            email=f"contato{i}@exemplo.com.br",
            place_id=f"p{i}",
        )
        _primeiro_toque(
            session, usuario, campanha, alvo, idempotency_key=f"{campanha.id}:{alvo.id}:email"
        )
    session.flush()

    servico = ServicoDeEntregabilidade(session)
    pausada = False
    for i in range(3):
        resultado = servico.registrar(
            contato=f"contato{i}@exemplo.com.br", tipo=TipoRetorno.PERMANENTE
        )
        pausada = pausada or resultado.campanha_pausada

    assert pausada is True, "3 retornos em 30 envios = 10%, muito acima do teto de 2%"
    assert campanha.status is StatusCampanha.PAUSADA


def test_amostra_pequena_nao_pausa_campanha(session, automatico) -> None:
    """1 bounce em 1 envio e 100% e nao diz nada sobre reputacao."""
    campanha, lead, _ = automatico
    resultado = ServicoDeEntregabilidade(session).registrar(
        contato=lead.email, tipo=TipoRetorno.PERMANENTE
    )

    assert resultado.campanha_pausada is False
    assert resultado.reputacao.amostra_suficiente is False
    assert campanha.status is StatusCampanha.EXECUTANDO


# --- Rotas -------------------------------------------------------------------
def test_api_lista_a_cadencia_pendente(client, automatico) -> None:
    _, lead, _ = automatico
    r = client.get("/v1/cadencia")

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ativa"] is True
    assert corpo["max_toques"] == 3
    pendente = next(p for p in corpo["pendentes"] if p["lead_id"] == str(lead.id))
    assert pendente["proximo_toque"] == 2
    assert pendente["angulo"] == "prova"
    assert pendente["devido"] is False


def test_api_executa_com_forcar_em_modo_mock(session, client, automatico) -> None:
    """`forcar` pula a espera — e so ela. Sem isso a cadencia so seria
    demonstravel esperando tres dias de relogio."""
    _, lead, _ = automatico
    r = client.post("/v1/cadencia/executar", json={"forcar": True})

    assert r.status_code == 200, r.text
    assert r.json()["gerados"] == 1
    assert len(_saidas(session, lead)) == 2


def test_webhook_de_retorno_aceita_endereco_desconhecido(client, usuario) -> None:
    """202 mesmo sem casar: 404 diria quais enderecos estao na base."""
    r = client.post(
        "/v1/inbound/retorno",
        json={"contato": "ninguem@exemplo.com", "tipo": "permanente"},
    )

    assert r.status_code == 202
    assert r.json()["casou_com_lead"] is False


def test_api_de_reputacao_mostra_teto_e_amostra(client, automatico) -> None:
    campanha, _, _ = automatico
    r = client.get(f"/v1/campanhas/{campanha.id}/reputacao")

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["enviadas"] == 1
    assert corpo["retornos"] == 0
    assert corpo["amostra_suficiente"] is False
