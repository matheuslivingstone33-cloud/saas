"""FASE 4 — Compliance: opt-out 1 clique, LIA, direitos do titular e retencao."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.ids import now
from app.models.campaign import Campaign
from app.models.enums import (
    NivelAutonomia,
    OrigemOptOut,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
    TipoEvento,
    TipoSolicitacao,
)
from app.models.lead import Lead
from app.models.message import Message
from app.services.compliance import (
    LIAService,
    OptOutService,
    PrivacyService,
    RetencaoService,
    gerar_token,
    validar_token,
)
from app.services.pipeline import PipelineStub

SERVICO = "instalacao e manutencao de ar condicionado para empresas"


def _rodar(session, usuario, portas_db, nome="Compliance", nivel=NivelAutonomia.AUTOMATICO):  # noqa: ANN001
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
    PipelineStub(session, portas_db).executar(campanha, limite_leads=3)
    return campanha


# --- Token de descadastro -----------------------------------------------------
def test_token_e_assinado_e_nao_pode_ser_forjado(usuario) -> None:
    import uuid as _uuid

    alvo = _uuid.uuid4()
    token = gerar_token(alvo, "segredo-a")
    assert validar_token(token, "segredo-a") == alvo
    assert validar_token(token, "outro-segredo") is None
    assert validar_token(f"{alvo.hex}.0000000000000000", "segredo-a") is None
    assert validar_token("lixo", "segredo-a") is None


def test_link_de_descadastro_vai_em_toda_mensagem(session, usuario, portas_db) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Link")
    mensagens = session.execute(
        select(Message).where(Message.campaign_id == campanha.id)
    ).scalars().all()
    assert mensagens
    for mensagem in mensagens:
        assert mensagem.link_descadastro
        assert "/descadastro/" in mensagem.link_descadastro
        token = mensagem.link_descadastro.rsplit("/", 1)[-1]
        assert "." in token, "o link precisa carregar token assinado, nao o id cru"
        assert str(mensagem.lead_id) not in mensagem.link_descadastro


# --- Opt-out de 1 clique -----------------------------------------------------
def test_opt_out_de_um_clique_ponta_a_ponta(session, usuario, portas_db, settings) -> None:
    """O clique no link basta: suprime, tira o lead do funil e audita."""
    campanha = _rodar(session, usuario, portas_db, nome="1 clique")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()
    assert lead is not None
    email = lead.email

    servico = OptOutService(session, settings=settings)
    token = servico.link_para(lead).rsplit("/", 1)[-1]
    resultado = servico.por_token(token)

    assert resultado.registrado is True
    assert resultado.contato == email
    session.refresh(lead)
    assert lead.status is StatusLead.OPT_OUT

    # o contato agora esta suprimido para novos envios
    from app.repositories.misc import OptOutRepository

    assert OptOutRepository(session).existe(email.lower(), user_id=usuario.id)

    from app.models.audit_log import AuditLog

    eventos = session.execute(
        select(AuditLog).where(AuditLog.evento == TipoEvento.OPT_OUT_REGISTRADO)
    ).scalars().all()
    assert eventos


def test_opt_out_e_idempotente(session, usuario, portas_db, settings) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Idem opt-out")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()
    servico = OptOutService(session, settings=settings)
    token = servico.link_para(lead).rsplit("/", 1)[-1]

    primeiro = servico.por_token(token)
    segundo = servico.por_token(token)
    assert primeiro.registrado and segundo.registrado
    assert segundo.ja_existia is True


def test_opt_out_impede_nova_abordagem_em_outra_campanha(
    session, usuario, portas_db, settings
) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Antes")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()
    email = lead.email
    OptOutService(session, settings=settings).registrar(
        contato=email, user_id=usuario.id, origem=OrigemOptOut.LINK_DESCADASTRO
    )

    outra = _rodar(session, usuario, portas_db, nome="Depois")
    enviadas = session.execute(
        select(Message).where(
            Message.campaign_id == outra.id, Message.status == StatusMensagem.ENVIADA
        )
    ).scalars().all()
    assert all((m.destinatario or "").lower() != email.lower() for m in enviadas)


def test_endpoint_publico_de_descadastro(client, session, usuario, portas_db, settings) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Endpoint")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()
    token = OptOutService(session, settings=settings).link_para(lead).rsplit("/", 1)[-1]

    r = client.get(f"/descadastro/{token}")
    assert r.status_code == 200
    assert "descadastrado" in r.text.lower()

    ruim = client.get("/descadastro/token-invalido")
    assert ruim.status_code == 400


# --- LIA ----------------------------------------------------------------------
def test_lia_e_gerada_com_dados_reais(session, usuario, portas_db) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="LIA")
    lia = LIAService(session).gerar(usuario, campanha)

    assert lia.hash
    assert lia.controlador["empresa"]
    assert any("Places" in f for f in lia.fontes)
    assert any("Receita" in f for f in lia.fontes)
    assert lia.balanceamento["interesse"] and lia.balanceamento["impacto"]
    assert len(lia.salvaguardas) >= 5
    assert "art. 18" in " ".join(lia.direitos)

    md = lia.markdown()
    assert md.startswith("# Avaliacao de Legitimo Interesse")
    for secao in ("Teste de necessidade", "Teste de balanceamento", "Salvaguardas"):
        assert secao in md


def test_lia_gera_evento_de_auditoria(session, usuario, portas_db) -> None:
    from app.models.audit_log import AuditLog

    LIAService(session).gerar(usuario)
    eventos = session.execute(
        select(AuditLog).where(AuditLog.evento == TipoEvento.LIA_GERADO)
    ).scalars().all()
    assert eventos
    assert eventos[-1].dados["hash"]
    assert eventos[-1].base_legal == "legitimo_interesse"


def test_lia_pela_api_em_json_e_markdown(client, usuario) -> None:
    r = client.get("/v1/compliance/lia")
    assert r.status_code == 200
    assert r.json()["conclusao"]

    md = client.get("/v1/compliance/lia", params={"formato": "markdown"})
    assert md.status_code == 200
    assert "# Avaliacao de Legitimo Interesse" in md.text


# --- Direitos do titular ------------------------------------------------------
def test_acesso_devolve_o_que_temos(session, usuario, portas_db) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Acesso")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()

    servico = PrivacyService(session)
    pedido = servico.abrir(contato=lead.email, tipo=TipoSolicitacao.ACESSO, user_id=usuario.id)
    resultado = servico.atender(pedido)

    assert pedido.prazo_resposta is not None
    assert resultado["leads"], "o titular tem direito de saber que existe registro"
    assert resultado["leads"][0]["proveniencia"], "e de saber de onde veio o dado"


def test_acesso_inclui_a_resposta_enviada_pelo_titular(session, usuario) -> None:
    """O relatorio de acesso (art. 18, II) tem que trazer TODO dado do titular —
    inclusive as respostas que ele mesmo enviou.

    Numa mensagem de ENTRADA o titular esta no `remetente`, nao no
    `destinatario` (ver models/message.py). Buscar so por `destinatario` trazia
    a mensagem que enviamos AO titular, mas deixava de fora a resposta que o
    titular enviou A NOS — que e dado pessoal dele (o texto que escreveu e o
    endereco de onde respondeu). E a mesma assimetria que a retencao ja
    reconheceu ao mascarar o `remetente`; aqui e o direito de acesso que
    precisa enxergar os dois lados.
    """
    from app.models.enums import Canal, Direcao, StatusMensagem

    contato = "titular-respondeu@empresa.com.br"
    saida = Message(
        user_id=usuario.id,
        canal=Canal.EMAIL,
        direcao=Direcao.SAIDA,
        status=StatusMensagem.ENVIADA,
        destinatario=contato,
        remetente="prospector@nosso-dominio.com.br",
        corpo="Ola, temos uma oferta para a sua empresa...",
    )
    entrada = Message(
        user_id=usuario.id,
        canal=Canal.EMAIL,
        direcao=Direcao.ENTRADA,
        status=StatusMensagem.RESPONDIDA,
        remetente=contato,
        destinatario="prospector@nosso-dominio.com.br",
        corpo="Tenho interesse, pode me ligar.",
    )
    session.add_all([saida, entrada])
    session.flush()

    relatorio = PrivacyService(session).relatorio(contato)
    por_id = {m["id"]: m for m in relatorio["mensagens"]}
    assert str(saida.id) in por_id, "a mensagem enviada ao titular deve constar"
    assert str(entrada.id) in por_id, "a resposta enviada PELO titular tambem deve constar"
    assert por_id[str(entrada.id)]["direcao"] == Direcao.ENTRADA.value


def test_eliminacao_anonimiza_mas_mantem_supressao(session, usuario, portas_db) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Eliminacao")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()
    email = lead.email

    servico = PrivacyService(session)
    pedido = servico.abrir(contato=email, tipo=TipoSolicitacao.ELIMINACAO, user_id=usuario.id)
    resultado = servico.atender(pedido)

    assert resultado["leads_anonimizados"] >= 1
    session.refresh(lead)
    assert lead.email is None
    assert lead.razao_social == "[anonimizado]"
    assert lead.deleted_at is not None

    # A supressao SOBREVIVE a eliminacao — senao a proxima campanha recoleta.
    from app.repositories.misc import OptOutRepository

    assert OptOutRepository(session).existe(email.lower())


def test_solicitacao_publica_pela_api(client, session, usuario, portas_db) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Publico")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()

    r = client.post(
        "/privacidade/solicitacao",
        json={"contato": lead.email, "tipo": "acesso"},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["protocolo"]
    assert corpo["status"] == "atendida"
    assert corpo["prazo_resposta"]


# --- Retencao -----------------------------------------------------------------
def test_retencao_anonimiza_leads_vencidos(session, usuario, portas_db, settings) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Retencao", nivel=NivelAutonomia.ASSISTIDO)
    leads = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id)
    ).scalars().all()
    antigo = leads[0]
    antigo.created_at = now() - timedelta(days=settings.retencao_leads_dias + 10)
    antigo.status = StatusLead.QUALIFICADO
    antigo.email = antigo.email or "alvo@exemplo.com.br"
    session.flush()

    seco = RetencaoService(session).executar(dry_run=True)
    assert seco.leads_anonimizados >= 1
    session.refresh(antigo)
    assert antigo.email is not None, "dry_run nao pode apagar nada"

    real = RetencaoService(session).executar(dry_run=False)
    assert real.leads_anonimizados >= 1
    session.refresh(antigo)
    assert antigo.email is None
    assert antigo.provenance.get("anonimizado_em")


def test_anonimizar_apaga_os_reidentificadores_da_empresa(
    session, usuario, portas_db, settings
) -> None:
    """Anonimizar tem que impedir a REIDENTIFICACAO (LGPD art. 5, XI), nao so
    apagar o texto do endereco.

    O `place_id` e a chave estavel do Google Places: um `GET /places/{id}`
    recompoe nome, endereco e telefone do estabelecimento — o dado
    "anonimizado" volta inteiro. Ele sobrevivia em DOIS lugares (a coluna e a
    `provenance`), junto do CNPJ, da lat/long exata, do CEP e do bairro:
    qualquer um deles devolve a identidade da empresa que o expurgo diz remover,
    enquanto so o `endereco` em texto era zerado. As dimensoes agregadas
    (municipio/UF, ramo, porte, score) ficam — sustentam o aprendizado sem
    apontar para uma empresa especifica.
    """
    campanha = _rodar(
        session, usuario, portas_db, nome="Reident", nivel=NivelAutonomia.ASSISTIDO
    )
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id)
    ).scalars().first()
    assert lead is not None
    lead.created_at = now() - timedelta(days=settings.retencao_leads_dias + 10)
    lead.status = StatusLead.QUALIFICADO
    lead.email = lead.email or "alvo@exemplo.com.br"
    lead.cnpj = "12345678000199"
    lead.place_id = "ChIJ_reidentifica_a_empresa"
    lead.cep = "60000000"
    lead.bairro = "Centro"
    lead.latitude = -3.731861
    lead.longitude = -38.526670
    lead.municipio = "Fortaleza"
    lead.uf = "CE"
    lead.provenance = {**(lead.provenance or {}), "place_id": "ChIJ_reidentifica_a_empresa"}
    session.flush()

    RetencaoService(session, settings=settings).executar(dry_run=False)
    session.refresh(lead)

    # o dado de contato ja saia antes; o registro estatistico continua.
    assert lead.email is None
    assert lead.razao_social == "[anonimizado]"
    assert lead.provenance.get("anonimizado_em")

    # os reidentificadores diretos e a localizacao de precisao TEM que sumir.
    assert lead.cnpj is None
    assert lead.place_id is None
    assert lead.cep is None
    assert lead.bairro is None
    assert lead.latitude is None
    assert lead.longitude is None
    # o place_id tambem morava na proveniencia — a copia sai junto, senao
    # zerar so a coluna deixava a chave de reidentificacao de pe.
    assert "place_id" not in lead.provenance

    # dimensoes agregadas ficam: nao apontam para uma empresa, alimentam a mira.
    assert lead.municipio == "Fortaleza"
    assert lead.uf == "CE"


def test_retencao_preserva_lead_convertido(session, usuario, portas_db, settings) -> None:
    campanha = _rodar(session, usuario, portas_db, nome="Preserva")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()
    lead.created_at = now() - timedelta(days=settings.retencao_leads_dias + 30)
    lead.status = StatusLead.CONVERTIDO
    session.flush()

    RetencaoService(session).executar(dry_run=False)
    session.refresh(lead)
    assert lead.email is not None, "cliente convertido nao entra no expurgo automatico"


def test_retencao_mascara_o_remetente_da_resposta_do_lead(session, usuario, settings) -> None:
    """Em mensagem de ENTRADA o titular esta no `remetente`, nao no `destinatario`.

    O expurgo mascarava so o `destinatario` — que na entrada somos nos — e o
    e-mail real de quem respondeu sobrevivia ao prazo de retencao. Regressao:
    o `remetente` tambem precisa sumir.
    """
    from app.models.enums import Canal, Direcao, StatusMensagem

    resposta = Message(
        user_id=usuario.id,
        canal=Canal.EMAIL,
        direcao=Direcao.ENTRADA,
        status=StatusMensagem.RESPONDIDA,
        remetente="contato-real@empresa.com.br",
        destinatario="prospector@nosso-dominio.com.br",
        corpo="Tenho interesse, pode me ligar.",
    )
    session.add(resposta)
    session.flush()
    resposta.created_at = now() - timedelta(days=settings.retencao_mensagens_dias + 5)
    session.flush()

    seco = RetencaoService(session, settings=settings).executar(dry_run=True)
    assert seco.mensagens_expurgadas >= 1
    session.refresh(resposta)
    assert resposta.remetente == "contato-real@empresa.com.br", "dry_run nao pode apagar nada"

    RetencaoService(session, settings=settings).executar(dry_run=False)
    session.refresh(resposta)
    assert "contato-real@empresa.com.br" not in (resposta.remetente or "")
    assert resposta.remetente == "co***@empresa.com.br"
    assert resposta.corpo == "[expurgado por politica de retencao]"


def test_retencao_expurga_solicitacao_concluida_vencida(
    session, usuario, portas_db, settings
) -> None:
    """Solicitacao de direito concluida ha muito tempo perde o dado pessoal e
    mantem so os metadados do atendimento, para prestacao de contas."""
    from app.models.audit_log import AuditLog
    from app.services.compliance import SOLICITACAO_EXPURGADA

    campanha = _rodar(session, usuario, portas_db, nome="Expurgo solicitacao")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()

    servico = PrivacyService(session, settings=settings)
    pedido = servico.abrir(
        contato=lead.email,
        tipo=TipoSolicitacao.ACESSO,
        user_id=usuario.id,
        observacao="quero ver meus dados",
    )
    servico.atender(pedido)
    assert pedido.resultado.get("leads"), "acesso guarda o relatorio com dado pessoal"
    contato_original = pedido.contato_normalizado

    # concluida ha mais tempo que o prazo de retencao do payload
    pedido.concluida_em = now() - timedelta(days=settings.retencao_mensagens_dias + 5)
    session.flush()

    seco = RetencaoService(session, settings=settings).executar(dry_run=True)
    assert seco.solicitacoes_expurgadas >= 1
    session.refresh(pedido)
    assert pedido.resultado.get("leads"), "dry_run nao pode apagar nada"

    real = RetencaoService(session, settings=settings).executar(dry_run=False)
    assert real.solicitacoes_expurgadas >= 1
    session.refresh(pedido)
    assert pedido.resultado == SOLICITACAO_EXPURGADA
    assert pedido.observacao is None
    assert contato_original not in pedido.contato_normalizado
    # metadados do atendimento sobrevivem ao expurgo
    assert pedido.tipo is TipoSolicitacao.ACESSO
    assert pedido.prazo_resposta is not None and pedido.concluida_em is not None

    eventos = session.execute(
        select(AuditLog).where(
            AuditLog.evento == TipoEvento.RETENCAO_EXPURGO,
            AuditLog.entidade_tipo == "privacy_request",
        )
    ).scalars().all()
    assert eventos

    # idempotente: rodar de novo nao reexpurga a mesma solicitacao
    de_novo = RetencaoService(session, settings=settings).executar(dry_run=False)
    assert de_novo.solicitacoes_expurgadas == 0


def test_retencao_preserva_solicitacao_em_aberto(session, usuario, portas_db, settings) -> None:
    """Solicitacao ainda nao concluida nunca e expurgada, por mais antiga que seja."""
    servico = PrivacyService(session, settings=settings)
    pedido = servico.abrir(
        contato="titular@exemplo.com.br",
        tipo=TipoSolicitacao.CORRECAO,  # correcao fica EM_ANALISE, sem concluir
        user_id=usuario.id,
    )
    servico.atender(pedido)
    pedido.created_at = now() - timedelta(days=settings.retencao_mensagens_dias + 30)
    session.flush()

    resultado = RetencaoService(session, settings=settings).executar(dry_run=False)
    assert resultado.solicitacoes_expurgadas == 0
    session.refresh(pedido)
    assert pedido.contato_normalizado == "titular@exemplo.com.br"


def test_retencao_gera_auditoria(session, usuario, portas_db, settings) -> None:
    from app.models.audit_log import AuditLog

    campanha = _rodar(session, usuario, portas_db, nome="Retencao audit")
    lead = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.email.is_not(None))
    ).scalars().first()
    lead.created_at = now() - timedelta(days=settings.retencao_leads_dias + 1)
    lead.status = StatusLead.QUALIFICADO
    session.flush()

    RetencaoService(session).executar(dry_run=False)
    eventos = session.execute(
        select(AuditLog).where(AuditLog.evento == TipoEvento.RETENCAO_EXPURGO)
    ).scalars().all()
    assert eventos


def test_retencao_de_mensagem_audita_e_nao_reconta(session, usuario, portas_db, settings) -> None:
    """O expurgo do corpo entra na trilha e nao reprocessa o que ja saiu.

    A Politica de Privacidade promete que "cada remocao e registrada na
    auditoria"; ate aqui so o expurgo de lead gerava evento. E, sem pular a
    mensagem ja expurgada, cada nova rodada recontava a mesma linha.
    """
    from app.models.audit_log import AuditLog
    from app.services.compliance import CORPO_EXPURGADO

    campanha = _rodar(session, usuario, portas_db, nome="Expurgo msg")
    mensagem = session.execute(
        select(Message).where(Message.campaign_id == campanha.id)
    ).scalars().first()
    assert mensagem is not None
    mensagem.corpo = "corpo original com dado pessoal"
    mensagem.destinatario = "contato@exemplo.com.br"
    mensagem.created_at = now() - timedelta(days=settings.retencao_mensagens_dias + 5)
    session.flush()

    def eventos_de_mensagem():
        return (
            session.execute(
                select(AuditLog).where(
                    AuditLog.evento == TipoEvento.RETENCAO_EXPURGO,
                    AuditLog.entidade_tipo == "mensagens",
                )
            )
            .scalars()
            .all()
        )

    # dry_run conta, mas nao apaga nem audita.
    seco = RetencaoService(session).executar(dry_run=True)
    assert seco.mensagens_expurgadas >= 1
    session.refresh(mensagem)
    assert mensagem.corpo == "corpo original com dado pessoal"
    assert eventos_de_mensagem() == []

    # Rodada real: expurga o corpo, mascara o destinatario e registra na trilha.
    real = RetencaoService(session).executar(dry_run=False)
    assert real.mensagens_expurgadas >= 1
    session.refresh(mensagem)
    assert mensagem.corpo == CORPO_EXPURGADO
    assert mensagem.destinatario == "co***@exemplo.com.br"
    eventos = eventos_de_mensagem()
    assert len(eventos) == 1
    assert eventos[-1].dados["quantidade"] == real.mensagens_expurgadas

    # Segunda rodada NAO reprocessa a mensagem ja expurgada, nem audita de novo.
    de_novo = RetencaoService(session).executar(dry_run=False)
    assert de_novo.mensagens_expurgadas == 0
    assert len(eventos_de_mensagem()) == 1


def test_retencao_expurga_o_assunto_junto_do_corpo(session, usuario, settings) -> None:
    """O assunto tambem e conteudo: na abordagem de saida ele traz o nome da
    empresa-alvo (`_assunto` monta "<servico> para <empresa>"). Expurgar o corpo
    e deixar o assunto de pe fazia essa identidade sobreviver ao prazo."""
    from app.models.enums import Canal, Direcao

    abordagem = Message(
        user_id=usuario.id,
        canal=Canal.EMAIL,
        direcao=Direcao.SAIDA,
        status=StatusMensagem.ENVIADA,
        destinatario="contato@hotel-exemplo.com.br",
        assunto="manutencao de ar condicionado para Hotel Exemplo Ltda",
        corpo="Ola, notamos que o hotel tem camara fria de grande porte...",
    )
    session.add(abordagem)
    session.flush()
    abordagem.created_at = now() - timedelta(days=settings.retencao_mensagens_dias + 5)
    session.flush()

    # dry_run nao pode apagar o assunto.
    RetencaoService(session, settings=settings).executar(dry_run=True)
    session.refresh(abordagem)
    assert abordagem.assunto == "manutencao de ar condicionado para Hotel Exemplo Ltda"

    # Rodada real: assunto some junto do corpo.
    RetencaoService(session, settings=settings).executar(dry_run=False)
    session.refresh(abordagem)
    assert abordagem.assunto is None
    assert abordagem.corpo == "[expurgado por politica de retencao]"


def test_retencao_preserva_registro_de_destinatario_sem_arroba(
    session, usuario, settings
) -> None:
    """Expurgar um destinatario que nao e e-mail nao pode ANULAR o registro.

    `_mascarar` devolvia `None` para qualquer contato sem `@` — um destinatario
    de telefone/WhatsApp virava NULL no expurgo, e a auditoria perdia ate a
    evidencia de que houve destinatario (uma linha sem destinatario e
    indistinguivel de uma que nunca teve um). O dado pessoal (o numero) tem que
    sair, mas o registro de que existiu um destinatario fica, com a mesma marca
    `[expurgado]` ja usada no expurgo de solicitacao. O formato de mascara
    PARCIAL de telefone e outra decisao, ainda em aberto — aqui so garantimos
    que o registro nao some em silencio.
    """
    from app.models.enums import Canal, Direcao

    zap = Message(
        user_id=usuario.id,
        canal=Canal.WHATSAPP,
        direcao=Direcao.SAIDA,
        status=StatusMensagem.ENVIADA,
        destinatario="+5585999990000",
        corpo="Ola, temos uma oferta para a sua empresa...",
    )
    session.add(zap)
    session.flush()
    zap.created_at = now() - timedelta(days=settings.retencao_mensagens_dias + 5)
    session.flush()

    # dry_run nao pode apagar nada.
    RetencaoService(session, settings=settings).executar(dry_run=True)
    session.refresh(zap)
    assert zap.destinatario == "+5585999990000"

    RetencaoService(session, settings=settings).executar(dry_run=False)
    session.refresh(zap)
    assert "999990000" not in (zap.destinatario or ""), "o numero real tem que sumir"
    assert zap.destinatario == "[expurgado]", "mas fica o registro de que houve destinatario"
    assert zap.corpo == "[expurgado por politica de retencao]"


# --- Documentos publicos ------------------------------------------------------
@pytest.mark.parametrize(
    ("rota", "trecho"),
    [
        ("/legal/privacidade", "Política de Privacidade"),
        ("/legal/ia", "Inteligência Artificial"),
    ],
)
def test_documentos_legais_publicados(client, rota: str, trecho: str) -> None:
    r = client.get(rota)
    assert r.status_code == 200
    assert trecho in r.text


def test_nota_interna_de_revisao_nao_vai_para_o_texto_publico() -> None:
    """Rascunho juridico carrega notas que descrevem falhas abertas."""
    from app.api.routes.compliance import sem_notas_internas

    rascunho = (
        "# Politica\n<!-- REVISAR: hoje um impostor\npode pedir dados -->\n"
        "Texto publico.\n<!-- outra nota -->"
    )
    publicado = sem_notas_internas(rascunho)
    assert "REVISAR" not in publicado and "impostor" not in publicado
    assert "outra nota" not in publicado
    assert "Texto publico." in publicado


def test_auditoria_continua_integra_depois_de_tudo(session, usuario, portas_db) -> None:
    from app.services.audit import AuditService

    _rodar(session, usuario, portas_db, nome="Integridade final")
    LIAService(session).gerar(usuario)
    integra, erro = AuditService(session).verificar_cadeia()
    assert integra and erro is None
