"""Motor 4 — conversa de duas pontas.

O grosso destes testes nao verifica o que o motor RESPONDE, e sim quando ele
se CALA. Um agente que insiste depois de "nao tenho interesse", ou que
argumenta contra "me tire da lista", queima a reputacao do remetente e expoe o
cliente juridicamente. Silencio na hora certa e a funcionalidade.
"""

from __future__ import annotations

import unicodedata

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
from app.services.conversa import (
    Intencao,
    ServicoDeConversa,
    classificar_por_sinal,
    decodificar_quoted_printable,
    html_para_texto,
    recompor_acentos,
    remover_historico_citado,
    remover_invisiveis,
)


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


# --- Separacao da resposta nova ----------------------------------------------
def test_remover_historico_citado_nao_mexe_em_mensagem_limpa() -> None:
    """Sem fronteira de citacao, o texto volta inteiro. O corte nunca inventa."""
    corpo = "Tenho interesse, qual o valor?"
    assert remover_historico_citado(corpo) == corpo


@pytest.mark.parametrize(
    "corpo",
    [
        # Gmail: atribuicao + linhas citadas com ">"
        "Vamos marcar!\n\nEm 9/9, Fulano escreveu:\n> mensagem antiga\n> nao tenho interesse",
        # Outlook: regua de sublinhados antes do cabecalho De:/Para:
        "Vamos marcar!\n\n________________________________\nDe: Fulano\nnao tenho interesse",
        # Cliente com "-----Mensagem original-----"
        "Vamos marcar!\n-----Mensagem original-----\nnao tenho interesse",
    ],
)
def test_remover_historico_citado_corta_o_que_veio_antes(corpo: str) -> None:
    novo = remover_historico_citado(corpo).lower()
    assert "vamos marcar" in novo
    assert "interesse" not in novo, "o historico citado nao pode sobrar na resposta nova"


# --- Bloco de cabecalho do Outlook (De:/Para:/Assunto:) ----------------------
def test_remover_historico_citado_corta_bloco_encaminhado_sem_regua() -> None:
    """Outlook intercala De:/Para:/Assunto: SEM a regua de sublinhados e sem ">".

    Sem reconhecer esse bloco, o historico embaixo dele volta como "resposta
    nova" e um "nao tenho interesse" antigo contamina a intencao de negocio.
    """
    corpo = (
        "Vamos marcar!\n\n"
        "De: Fulano <fulano@exemplo.com>\n"
        "Para: voce@exemplo.com\n"
        "Assunto: RE: proposta\n\n"
        "nao tenho interesse"
    )
    novo = remover_historico_citado(corpo).lower()
    assert "vamos marcar" in novo
    assert "interesse" not in novo, "o cabecalho encaminhado tem que cortar o historico"


def test_bloco_encaminhado_do_outlook_nao_descarta_lead_que_disse_sim() -> None:
    """Um "nao tenho interesse" citado sob o bloco De:/Para: nao pode virar recusa.

    E o cenario 1 do objetivo com o formato do Outlook: sem a regua e sem ">",
    a resposta nova ("tenho interesse") tem que ganhar do historico citado.
    """
    corpo = (
        "Perfeito, tenho interesse! Podemos conversar esta semana.\n\n"
        "De: Prospector AI <contato@exemplo.com>\n"
        "Enviada em: terca-feira, 9 de setembro de 2026 10:15\n"
        "Para: gerencia@brisamarhotel.com.br\n"
        "Assunto: RE: manutencao de ar-condicionado\n\n"
        "Ola, equipe. No mes passado voces responderam: nao tenho interesse, obrigado."
    )
    assert classificar_por_sinal(corpo) is Intencao.INTERESSE


def test_bloco_encaminhado_exige_duas_linhas_e_nao_corta_resposta_comum() -> None:
    """O corte e conservador: uma linha isolada nao abre bloco.

    "De acordo, ..." nem casa (nao ha ":" depois de "De"), e um unico
    "Assunto: ..." dentro de uma resposta de verdade nao pode engolir o texto.
    """
    corpo = "De acordo, podemos conversar.\nAssunto: o contrato que voce mandou."
    assert remover_historico_citado(corpo) == corpo


# --- Texto real: a citacao nao pode contaminar a intencao --------------------
def test_recusa_citada_nao_descarta_lead_que_disse_sim() -> None:
    """Um "nao tenho interesse" citado de uma troca antiga nao pode virar recusa.

    E-mail de verdade nao chega limpo: a resposta nova vem colada em cima do
    historico citado. Antes, o classificador varria o corpo INTEIRO e o
    "nao tenho interesse" que estava la embaixo, numa mensagem antiga, ganhava
    de um "tenho interesse" que a pessoa acabou de escrever no topo — e o lead
    quente era descartado. A intencao de negocio sai da RESPOSTA NOVA.
    """
    corpo = (
        "Perfeito, tenho interesse sim! Podemos conversar esta semana.\n\n"
        "Em ter., 9 de set. de 2026 as 10:15, Prospector AI escreveu:\n"
        "> Ola, equipe. Sobre manutencao de ar-condicionado...\n"
        "> No mes passado voces responderam: nao tenho interesse, obrigado.\n"
    )
    assert classificar_por_sinal(corpo) is Intencao.INTERESSE


def test_opt_out_apos_citacao_nao_se_perde() -> None:
    """Opt-out e a excecao: vale sobre o texto INTEIRO, venha onde vier.

    "Opt-out duvidoso e opt-out" — o direito do titular ganha do negocio.
    Reduzir o escopo do opt-out para so a resposta nova arriscaria perder um
    pedido de saida escrito abaixo da citacao, e esse risco nao se corre.
    """
    corpo = (
        "Obrigado pelo retorno.\n\n"
        "> Em 9/9, Prospector AI escreveu:\n"
        "> Podemos agendar uma conversa?\n\n"
        "Alias, nao quero receber mais e-mails de voces."
    )
    assert classificar_por_sinal(corpo) is Intencao.PEDIDO_OPT_OUT


def test_recusa_citada_nao_encerra_a_conversa_pelo_motor(
    session, usuario, portas_db, lead_abordado
) -> None:
    """O mesmo caso, ponta a ponta: a resposta com citacao NAO descarta o lead."""
    motor = ServicoDeConversa(session, portas_db)
    r = motor.receber(
        lead=lead_abordado,
        corpo=(
            "Otimo, tenho interesse! Vamos marcar.\n\n"
            "Em 9/9, Prospector AI escreveu:\n"
            "> Segue a proposta. Voce havia dito: nao tenho interesse.\n"
        ),
    )
    assert r.intencao is Intencao.INTERESSE
    assert not r.encerrou
    assert lead_abordado.status is StatusLead.RESPONDIDO


# --- Texto real: quoted-printable --------------------------------------------
# O provedor manda o corpo codificado: "nao" vira "n=C3=A3o", e palavra longa
# quebra com soft break ("desca=\ndastrar"). Sem decodificar, "descadastr" e
# "nao quero receber" nao casam com marca nenhuma — e o pior acontece: um
# opt-out que o classificador NAO ve.


def test_decodifica_bytes_qp() -> None:
    assert decodificar_quoted_printable("N=C3=A3o quero receber") == "Não quero receber"


def test_decodifica_soft_break_que_parte_palavra() -> None:
    assert decodificar_quoted_printable("Quero me desca=\ndastrar") == "Quero me descadastrar"


def test_texto_comum_com_igual_nao_e_tocado() -> None:
    """"= 4" (espaco depois) nao tem cara de QP: decodificar corromperia a resposta."""
    texto = "O custo hoje = 4 mil, da para melhorar?"
    assert decodificar_quoted_printable(texto) == texto


def test_opt_out_em_quoted_printable_e_reconhecido() -> None:
    assert (
        classificar_por_sinal("N=C3=A3o quero receber mais, obrigado.")
        is Intencao.PEDIDO_OPT_OUT
    )


def test_opt_out_partido_por_soft_break_e_reconhecido() -> None:
    assert (
        classificar_por_sinal("Por favor, quero me desca=\ndastrar da lista.")
        is Intencao.PEDIDO_OPT_OUT
    )


def test_nosso_link_partido_por_soft_break_nao_vira_opt_out() -> None:
    """A protecao da linha do nosso link precisa ver a linha JA remontada.

    Em QP a linha longa do link chega partida em duas. Sem decodificar antes,
    so a metade com `/descadastro/` sairia, e a outra metade ("descadastre-se")
    ficaria na varredura — um "tenho interesse" viraria opt-out.
    """
    corpo = (
        "Tenho interesse, podem me ligar amanha.\n\n"
        "Em 10/09/2026, Prospector escreveu:\n"
        "> Para sair da lista, descadastre-se: https://app.exemplo.com.br/desca=\n"
        "dastro/abc123"
    )
    assert classificar_por_sinal(corpo) is Intencao.INTERESSE


def test_receber_opt_out_em_qp_registra_supressao(
    session, usuario, portas_db, lead_abordado
) -> None:
    """Ponta a ponta: opt-out codificado suprime e para, igual ao texto limpo."""
    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="N=C3=A3o me envie mais e-mails, por favor."
    )
    assert r.intencao is Intencao.PEDIDO_OPT_OUT
    assert r.encerrou and not r.respondeu
    assert lead_abordado.status is StatusLead.OPT_OUT
    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead_abordado.email)
    ).scalar_one_or_none()
    assert supressao is not None


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


def test_resposta_da_ia_leva_link_de_descadastro_que_funciona(
    session, usuario, portas_db, lead_abordado, settings
) -> None:
    """O link saia com endereco de teste e o id cru do lead: a pagina recusava.

    E o corpo nao trazia link nenhum. Guardrail: toda mensagem leva descadastro.
    """
    from app.services.compliance import OptOutService

    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Tenho interesse sim, me manda mais detalhes."
    )
    resposta = session.get(Message, r.resposta_id)

    assert resposta.link_descadastro.startswith(settings.url_publica.rstrip("/"))
    linha = next(li for li in resposta.corpo.splitlines() if "/descadastro/" in li)
    assert "descadastre-se" in linha, "rotulo e link na mesma linha (protecao do Motor 4)"
    assert resposta.link_descadastro in linha

    token = resposta.link_descadastro.rsplit("/", 1)[1]
    assert OptOutService(session).por_token(token).registrado


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


def test_webhook_aceita_sem_vazar_se_o_lead_existe(webhook, usuario) -> None:
    """Endereco desconhecido tambem devolve 202: 404 diria ao remetente quais
    e-mails estao na base."""
    r = webhook("/v1/inbound/email", {"remetente": "ninguem@exemplo.com", "corpo": "oi"})
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


# --- A nossa propria mensagem citada na resposta ------------------------------
def test_nossa_declaracao_citada_nao_vira_pedido_de_humano() -> None:
    """A declaracao termina com "Responda a este e-mail para falar com uma pessoa".

    Toda resposta real traz a nossa mensagem citada embaixo. Lida inteira, ela fazia
    todo cliente parecer pedir atendimento humano, e a IA nunca respondia ninguem.
    """
    resposta = (
        "Tenho interesse, qual o valor?\n\n"
        "Em 10/09/2026, Prospector escreveu:\n"
        "> Ola, equipe.\n"
        "> ---\n"
        "> Esta mensagem foi redigida por um agente de inteligencia artificial a servico\n"
        "> de Refrigeracao Ceara. Responda a este e-mail para falar com uma pessoa."
    )
    assert classificar_por_sinal(resposta) is Intencao.INTERESSE


def test_nosso_link_de_descadastro_citado_nao_vira_opt_out() -> None:
    """Opt-out e procurado no texto inteiro; a linha do NOSSO link nao conta."""
    resposta = (
        "Tenho interesse, qual o valor?\n\n"
        "Em 10/09/2026, Prospector escreveu:\n"
        "> Esta mensagem foi redigida por um agente de inteligencia artificial.\n"
        "> Para sair da lista, descadastre-se: https://app.exemplo.com.br/descadastro/abc123"
    )
    assert classificar_por_sinal(resposta) is Intencao.INTERESSE


def test_titular_que_pede_para_sair_continua_sendo_opt_out() -> None:
    """O filtro tira a linha do nosso link, nunca as palavras de quem escreveu."""
    assert classificar_por_sinal("Quero me descadastrar, por favor.") is Intencao.PEDIDO_OPT_OUT
    embaixo_da_citacao = "> Podemos agendar uma visita?\nMe tire da lista."
    assert classificar_por_sinal(embaixo_da_citacao) is Intencao.PEDIDO_OPT_OUT


# --- Texto real: corpo em HTML -----------------------------------------------
# Muito e-mail real chega em HTML: tags de bloco (`<div>`, `<br>`), inline
# (`<span>`, `<a>`) e entidades (`&nbsp;`, `n&atilde;o`). Sem converter para
# texto, o casamento lexical trabalha sobre "<p>N&atilde;o tenho interesse</p>"
# e nao acha marca nenhuma — inclusive um opt-out entidade-codificado, que e o
# pior caso: um pedido de saida que o classificador NAO ve.


def test_html_vira_texto_e_decodifica_entidades() -> None:
    limpo = html_para_texto("<p>N&atilde;o quero receber mais.</p>")
    assert limpo.strip() == "Não quero receber mais."


def test_texto_comum_com_menor_que_nao_e_tocado() -> None:
    """"< 4 mil" (espaco depois do "<") nao tem cara de HTML: converter engoliria
    o texto ate o proximo ">" e poderia apagar ate um opt-out."""
    texto = "Nosso consumo hoje e < 4 mil kWh > o do ano passado, da para melhorar?"
    assert html_para_texto(texto) == texto


def test_tags_de_bloco_viram_quebra_de_linha() -> None:
    """O corte por linha depende disso: `<div>`/`<br>` precisam separar linhas."""
    linhas = html_para_texto("<div>linha um</div><div>linha dois<br>linha tres</div>").split("\n")
    assert [linha for linha in linhas if linha.strip()] == ["linha um", "linha dois", "linha tres"]


def test_opt_out_em_html_e_reconhecido() -> None:
    assert (
        classificar_por_sinal("<div>N&atilde;o quero receber mais, obrigado.</div>")
        is Intencao.PEDIDO_OPT_OUT
    )


def test_conteudo_de_style_e_script_nao_vota_na_intencao() -> None:
    """CSS/JS nao e texto de leitura: um "nao tenho interesse" perdido num seletor
    nao pode descartar um lead que, no corpo, disse que tem interesse."""
    corpo = (
        "<style>.rodape::after{content:'nao tenho interesse'}</style>"
        "<script>var t='ja temos fornecedor';</script>"
        "<p>Tenho interesse, podemos conversar!</p>"
    )
    assert classificar_por_sinal(corpo) is Intencao.INTERESSE


def test_recusa_citada_em_html_nao_descarta_lead_que_disse_sim() -> None:
    """A conversao para texto e o que faz o corte de historico funcionar em HTML.

    Sem as quebras de linha das tags de bloco, tudo vira uma linha so, nenhuma
    fronteira e reconhecida, e o "Nao tenho interesse" citado (RECUSA vem antes
    de INTERESSE na ordem das regras) descartaria o lead que acabou de dizer sim.
    """
    corpo = (
        "<div>Perfeito, tenho interesse! Podemos conversar esta semana.</div>"
        "<div>Em 10/09/2026, Prospector escreveu:</div>"
        "<blockquote>Não tenho interesse, obrigado.</blockquote>"
    )
    assert classificar_por_sinal(corpo) is Intencao.INTERESSE


def test_opt_out_em_html_encerra_e_suprime_ponta_a_ponta(
    session, usuario, portas_db, lead_abordado
) -> None:
    """Ponta a ponta: opt-out em HTML com entidade suprime e para, como o texto limpo."""
    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="<p>Por favor, n&atilde;o me envie mais e-mails.</p>"
    )
    assert r.intencao is Intencao.PEDIDO_OPT_OUT
    assert r.encerrou and not r.respondeu
    assert lead_abordado.status is StatusLead.OPT_OUT
    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead_abordado.email)
    ).scalar_one_or_none()
    assert supressao is not None


# --- Texto real: caractere invisivel partindo a palavra ----------------------
# Depois do quoted-printable e do HTML, ainda sobra um jeito de esconder um
# opt-out do casamento lexical: um caractere de LARGURA ZERO ou um HIFEN SUAVE
# no meio da palavra. `desca<U+200B>dastrar`, `desca<U+00AD>dastrar` ou a versao
# HTML `desca&#8203;dastrar` (o html.unescape deixa o U+200B literal no lugar) —
# "descadastr" nao casa, e a pessoa que pediu para sair continua recebendo. E o
# analogo do soft break do QP, e o mesmo pior caso: um opt-out que o
# classificador NAO ve. "Opt-out duvidoso e opt-out" — na duvida, revela.


def test_remover_invisiveis_junta_palavra_partida_por_largura_zero() -> None:
    assert remover_invisiveis("desca​dastrar") == "descadastrar"


def test_remover_invisiveis_tira_hifen_suave_e_bom() -> None:
    assert remover_invisiveis("desca­dastrar﻿") == "descadastrar"


def test_remover_invisiveis_nao_mexe_em_texto_comum() -> None:
    """Espaco normal, acento e quebra de linha ficam intactos: so o invisivel sai."""
    texto = "Não tenho interesse,\nobrigado."
    assert remover_invisiveis(texto) == texto


def test_opt_out_partido_por_largura_zero_e_reconhecido() -> None:
    assert (
        classificar_por_sinal("Por favor, quero me desca​dastrar da lista.")
        is Intencao.PEDIDO_OPT_OUT
    )


def test_opt_out_partido_por_hifen_suave_e_reconhecido() -> None:
    assert (
        classificar_por_sinal("Quero me desca­dastrar, obrigado.")
        is Intencao.PEDIDO_OPT_OUT
    )


def test_opt_out_em_html_com_entidade_de_largura_zero_e_reconhecido() -> None:
    """`&#8203;` vira U+200B no html.unescape; sem tirar o invisivel, "descadastr"
    ainda nao casa e o pedido de saida se perde."""
    assert (
        classificar_por_sinal("<p>Quero me desca&#8203;dastrar da lista.</p>")
        is Intencao.PEDIDO_OPT_OUT
    )


def test_opt_out_com_largura_zero_encerra_e_suprime_ponta_a_ponta(
    session, usuario, portas_db, lead_abordado
) -> None:
    """Ponta a ponta: opt-out partido por largura-zero suprime e para, como o limpo."""
    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Por favor, não me envie​ mais e-mails."
    )
    assert r.intencao is Intencao.PEDIDO_OPT_OUT
    assert r.encerrou and not r.respondeu
    assert lead_abordado.status is StatusLead.OPT_OUT
    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead_abordado.email)
    ).scalar_one_or_none()
    assert supressao is not None


# --- Texto real: acento decomposto (NFD) -------------------------------------
# Depois do quoted-printable, do HTML e dos invisiveis, ainda sobra um jeito de
# o MESMO texto esconder uma marca do casamento lexical: o acento pode chegar
# DECOMPOSTO (NFD) — a vogal seguida do til/agudo/circunflexo como um caractere
# combinante SEPARADO ("na" + U+0303 + "o") no lugar do "ã" pronto. macOS e
# alguns provedores serializam assim. Nessa forma, "não me envie" nao casa nem
# com "não me envie" nem com "nao me envie" — e a pessoa que pediu para sair
# continua recebendo. E o mesmo pior caso do soft break e do largura-zero: um
# opt-out que o classificador NAO ve. Recompor para NFC (a forma canonica dos
# nossos sinais) fecha o buraco sem tocar em texto ja composto.


def test_recompor_acentos_compoe_forma_decomposta() -> None:
    decomposto = unicodedata.normalize("NFD", "Não")  # n + a + U+0303 + o
    assert decomposto != "Não", "o teste so vale se a entrada estiver mesmo decomposta"
    assert recompor_acentos(decomposto) == "Não"


def test_recompor_acentos_nao_mexe_em_texto_ja_composto() -> None:
    """Em texto ja em NFC (o caso comum) recompor e no-op: nao muda nada."""
    texto = "Não tenho interesse, obrigado. Orçamento, climatização e manutenção."
    assert recompor_acentos(texto) == texto


def test_opt_out_com_acento_decomposto_e_reconhecido() -> None:
    """"Não me envie" com o til combinante separado nao pode escapar do opt-out."""
    corpo = unicodedata.normalize("NFD", "Não me envie mais e-mails, por favor.")
    assert classificar_por_sinal(corpo) is Intencao.PEDIDO_OPT_OUT


def test_recusa_com_acento_decomposto_nao_vira_outra_intencao() -> None:
    """Decomposta, "Não tenho interesse" perdia o "não" e a marca de recusa nao
    casava — o lexical caia para o LLM ou classificava errado."""
    corpo = unicodedata.normalize("NFD", "Não tenho interesse, obrigado.")
    assert classificar_por_sinal(corpo) is Intencao.RECUSA


def test_opt_out_com_acento_decomposto_encerra_e_suprime_ponta_a_ponta(
    session, usuario, portas_db, lead_abordado
) -> None:
    """Ponta a ponta: opt-out em NFD suprime e para, como o texto ja composto."""
    corpo = unicodedata.normalize("NFD", "Não me envie mais e-mails, por favor.")
    r = ServicoDeConversa(session, portas_db).receber(lead=lead_abordado, corpo=corpo)
    assert r.intencao is Intencao.PEDIDO_OPT_OUT
    assert r.encerrou and not r.respondeu
    assert lead_abordado.status is StatusLead.OPT_OUT
    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead_abordado.email)
    ).scalar_one_or_none()
    assert supressao is not None


# --- Texto real: frases inequivocas de opt-out -------------------------------
# Depois de decodificar QP/HTML, tirar invisiveis e recompor acento, o texto ja
# chega legivel. Sobra a cobertura das FRASES: varias formas comuns de pedir
# saida nao casavam com sinal nenhum e caiam para o LLM — "pare de me enviar",
# "remova-me da lista", "remova meu e-mail", "nao desejo receber", "solicito
# remocao", "opt out" (so havia "unsubscribe"). E direito do titular: cada frase
# que escapa e alguem que pediu para sair e continua recebendo. Fechamos as
# INEQUIVOCAS (pedido claro de parar de receber / de ser removido). As ambiguas
# ("cancelar" sozinho, que tambem e "cancelar a reuniao") ficam com o LLM: nao e
# transform seguro como o NFC, tem risco dos dois lados.


@pytest.mark.parametrize(
    "texto",
    [
        "Por favor, pare de me enviar e-mails.",
        "Parem de me enviar mensagens.",
        "Pare de me mandar propostas.",
        "Parem de me mandar isso.",
        "Não desejo receber mais contato de voces.",
        "Nao desejo receber mais e-mails.",
        "Remova-me da lista, obrigado.",
        "Me remova da base de contatos.",
        "Favor remover meu e-mail do cadastro.",
        "Remova meu contato, por gentileza.",
        "Peço para remover o meu e-mail.",
        "Favor remover-me da base.",
        "Solicito a remoção do meu contato da base.",
        "Solicito remocao da base de dados.",
        "Quero opt out desta lista.",
        "Please opt-out me from this list.",
    ],
)
def test_frases_de_opt_out_inequivocas_sao_reconhecidas(texto: str) -> None:
    """Cada frase clara de saida vira PEDIDO_OPT_OUT no lexical, sem depender do LLM.

    Antes desta leva todas caiam para None (nenhuma marca casava) e o pedido de
    saida ficava nas maos do modelo — direito do titular dependendo de acerto de
    interpretacao.
    """
    assert classificar_por_sinal(texto) is Intencao.PEDIDO_OPT_OUT


@pytest.mark.parametrize(
    "texto",
    [
        "Podemos cancelar a reunião de amanhã?",
        "Precisei cancelar o horário, remarcamos?",
    ],
)
def test_cancelar_sozinho_nao_e_opt_out_no_lexical(texto: str) -> None:
    """"Cancelar" sozinho e ambiguo (a reuniao, o horario) — fica com o LLM.

    Adicionar "cancelar" como marca de opt-out geraria falso opt-out: suprimir um
    lead que so quis remarcar. O lado seguro de errar aqui NAO e suprimir; por isso
    a frase ambigua nao casa com sinal e desce para o modelo decidir."""
    assert classificar_por_sinal(texto) is not Intencao.PEDIDO_OPT_OUT


@pytest.mark.parametrize(
    "texto",
    [
        # remover / remova + objeto que NAO e o contato
        "Tenho interesse. Preciso remover meu ar-condicionado antigo e instalar um novo, "
        "qual o valor?",
        "Por favor remova o meu colega do cc e me envie a proposta.",
        "Pode remover meu sócio da cópia e mandar a proposta só pra mim?",
        # remocao como servico pedido
        "Solicito a remoção do entulho da obra. Podem enviar orçamento?",
        "Solicito remoção de 3 árvores no terreno da fábrica, qual o custo?",
        # preferencia de canal, nao saida
        "Não desejo receber ligações; prefiro por e-mail. Qual o valor?",
        "Não desejo receber visita comercial, mas pode enviar a proposta por e-mail.",
        # opt-out como assunto ou no rodape da assinatura do lead
        "Vocês têm opt-out para os destinatários? Tenho interesse na plataforma.",
        "Tenho interesse, me liga amanhã.\n\n--\nJoão | ACME\n"
        "If you no longer wish to receive emails from ACME, you can opt out here.",
        # negacao — resposta provavel ao 3o toque, que pergunta se encerramos
        "Não me remova da lista, tenho interesse sim!",
        # e o dano pelo historico citado
        "Pode ser terça às 10h.\n\nEm 10/09/2026, Fulano escreveu:\n"
        "> Preciso remover meu forro de gesso antigo, qual o valor?",
    ],
)
def test_frase_de_servico_ou_de_interesse_nao_vira_opt_out(texto: str) -> None:
    """Opt-out e terminal: o lead que queria comprar se perderia para sempre.

    Em 20/09 as frases novas de saida entraram como pedaco solto de texto, e cada
    caso abaixo virava PEDIDO_OPT_OUT. Agora a frase so vale com o proprio
    contato como objeto, e o "nao" logo antes anula.
    """
    assert classificar_por_sinal(texto) is not Intencao.PEDIDO_OPT_OUT


def test_html_com_espacos_longos_nao_trava_a_leitura() -> None:
    """O corpo vem do lead. A regex antiga voltava atras a cada espaco."""
    import time

    from app.services.conversa import html_para_texto

    corpo = "<p>oi</p>" + " " * 200_000 + "<p>tenho interesse</p>"
    inicio = time.perf_counter()
    texto = html_para_texto(corpo)
    assert time.perf_counter() - inicio < 1.0
    assert "oi" in texto and "tenho interesse" in texto


def test_frase_de_opt_out_apos_citacao_nao_se_perde() -> None:
    """Escrita embaixo do historico citado, a frase nova de saida ainda e pega —
    opt-out varre o texto inteiro, nao so a resposta nova."""
    corpo = "> Podemos agendar uma visita?\nRemova meu e-mail, por favor."
    assert classificar_por_sinal(corpo) is Intencao.PEDIDO_OPT_OUT


def test_nova_frase_de_opt_out_encerra_e_suprime_ponta_a_ponta(
    session, usuario, portas_db, lead_abordado
) -> None:
    """Ponta a ponta: "remova meu e-mail" suprime e para, como "descadastrar"."""
    r = ServicoDeConversa(session, portas_db).receber(
        lead=lead_abordado, corpo="Por favor, remova meu e-mail da lista."
    )
    assert r.intencao is Intencao.PEDIDO_OPT_OUT
    assert r.encerrou and not r.respondeu
    assert lead_abordado.status is StatusLead.OPT_OUT
    supressao = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == lead_abordado.email)
    ).scalar_one_or_none()
    assert supressao is not None
