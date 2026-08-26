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


def test_auditoria_continua_integra_depois_de_tudo(session, usuario, portas_db) -> None:
    from app.services.audit import AuditService

    _rodar(session, usuario, portas_db, nome="Integridade final")
    LIAService(session).gerar(usuario)
    integra, erro = AuditService(session).verificar_cadeia()
    assert integra and erro is None
