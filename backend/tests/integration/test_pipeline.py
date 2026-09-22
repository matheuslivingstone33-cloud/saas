"""Fluxo stub ponta a ponta: campanha -> leads -> mensagens, tudo em mock."""

from __future__ import annotations

from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.enums import (
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
from app.repositories.leads import LeadRepository
from app.repositories.misc import CostEventRepository, UserRepository
from app.services.audit import AuditService
from app.services.pipeline import PipelineStub


def _campanha(session, usuario, nome="Teste", servico=None, regiao="Fortaleza, CE") -> Campaign:
    campanha = Campaign(
        user_id=usuario.id,
        nome=nome,
        servico=servico or "instalacao e manutencao de ar condicionado para empresas",
        regiao=regiao,
        filtros={},
        status=StatusCampanha.RASCUNHO,
    )
    session.add(campanha)
    session.flush()
    return campanha


def test_pipeline_assistido_nao_envia_nada(session, usuario, portas_db, settings) -> None:
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.autonomy_level = NivelAutonomia.ASSISTIDO
    campanha = _campanha(session, usuario)

    resultado = PipelineStub(session, portas_db).executar(campanha, limite_leads=3)

    assert resultado.descobertos == 3
    assert resultado.qualificados == 3
    assert resultado.mensagens_enviadas == 0
    assert resultado.mensagens_aguardando_aprovacao == resultado.mensagens_geradas > 0
    assert campanha.status is StatusCampanha.CONCLUIDA

    pendentes = session.execute(
        select(Message).where(Message.status == StatusMensagem.AGUARDANDO_APROVACAO)
    ).scalars().all()
    assert len(pendentes) == resultado.mensagens_geradas
    for mensagem in pendentes:
        assert mensagem.link_descadastro, "toda mensagem precisa de saida no cabecalho"
        assert (mensagem.metadados or {}).get("gerado_por") == "ia"


def test_pipeline_automatico_dispara_para_outbox(session, usuario, portas_db, settings) -> None:
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.autonomy_level = NivelAutonomia.AUTOMATICO
    campanha = _campanha(session, usuario, nome="Auto")

    antes = len(list(settings.outbox_path.glob("*.json")))
    resultado = PipelineStub(session, portas_db).executar(campanha, limite_leads=3)
    depois = len(list(settings.outbox_path.glob("*.json")))

    assert resultado.mensagens_enviadas > 0
    assert resultado.mensagens_aguardando_aprovacao == 0
    assert depois - antes == resultado.mensagens_enviadas

    abordados = session.execute(
        select(Lead).where(Lead.campaign_id == campanha.id, Lead.status == StatusLead.ABORDADO)
    ).scalars().all()
    assert len(abordados) == resultado.mensagens_enviadas


def test_leads_nascem_com_proveniencia_e_auditoria(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Proveniencia")
    PipelineStub(session, portas_db).executar(campanha, limite_leads=2)

    leads = LeadRepository(session).listar(usuario.id, campaign_id=campanha.id).itens
    assert leads
    for lead in leads:
        assert lead.provenance["fonte_primaria"] == "google_places"
        assert lead.provenance["base_legal"] == "legitimo_interesse"
        assert lead.provenance["finalidade"] == "prospeccao_b2b"
        assert "coletado_em" in lead.provenance

    eventos = session.execute(
        select(Lead.id).where(Lead.campaign_id == campanha.id)
    ).scalars().all()
    from app.models.audit_log import AuditLog

    coletas = session.execute(
        select(AuditLog).where(AuditLog.evento == TipoEvento.DADO_COLETADO)
    ).scalars().all()
    assert len(coletas) >= len(eventos)


def test_dedup_impede_lead_repetido(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Dedup 1")
    PipelineStub(session, portas_db).executar(campanha, limite_leads=3)
    total_1 = len(LeadRepository(session).listar(usuario.id).itens)

    campanha2 = _campanha(session, usuario, nome="Dedup 2")
    resultado = PipelineStub(session, portas_db).executar(campanha2, limite_leads=3)
    total_2 = len(LeadRepository(session).listar(usuario.id, por_pagina=200).itens)

    assert resultado.duplicados >= 1
    assert total_2 > total_1  # criou novos, mas nao repetiu os antigos
    cnpjs = [
        lead.cnpj
        for lead in LeadRepository(session).listar(usuario.id, por_pagina=200).itens
        if lead.cnpj
    ]
    assert len(cnpjs) == len(set(cnpjs)), "nenhum CNPJ pode aparecer duas vezes no tenant"


def test_opt_out_bloqueia_envio(session, usuario, portas_db) -> None:
    """Nenhum contato suprimido pode receber mensagem — independente do lead."""
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.autonomy_level = NivelAutonomia.AUTOMATICO

    # Suprime TODO e-mail da base publica: qualquer lead descoberto sera barrado.
    suprimidos = {
        empresa.email.strip().lower()
        for empresa in portas_db.enrichment._por_cnpj.values()
        if empresa.email
    }
    for email in suprimidos:
        session.add(
            OptOut(
                user_id=usuario.id,
                tipo_contato=TipoContato.EMAIL,
                contato=email,
                contato_normalizado=email,
                origem=OrigemOptOut.SOLICITACAO_TITULAR,
            )
        )
    session.flush()

    campanha = _campanha(session, usuario, nome="Com opt-out")
    resultado = PipelineStub(session, portas_db).executar(campanha, limite_leads=3)

    assert resultado.bloqueados_opt_out >= 1
    bloqueados = session.execute(
        select(Lead).where(
            Lead.campaign_id == campanha.id, Lead.status == StatusLead.OPT_OUT
        )
    ).scalars().all()
    assert bloqueados
    enviadas = [
        m
        for m in session.execute(select(Message)).scalars().all()
        if (m.destinatario or "").lower() in suprimidos
    ]
    assert enviadas == []


def test_custo_e_registrado_nos_dois_baldes(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Custo")
    PipelineStub(session, portas_db).executar(campanha, limite_leads=3)

    resumo = CostEventRepository(session).resumo_por_balde(
        user_id=usuario.id, campaign_id=campanha.id
    )
    assert resumo["balde_1_dados"]["eventos"] > 0
    assert resumo["balde_2_ia"]["eventos"] > 0
    assert resumo["balde_1_dados"]["micros"] > 0


def test_cadeia_de_auditoria_integra_e_detecta_adulteracao(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Auditoria")
    PipelineStub(session, portas_db).executar(campanha, limite_leads=2)

    audit = AuditService(session)
    integra, erro = audit.verificar_cadeia()
    assert integra and erro is None

    from app.models.audit_log import AuditLog

    alvo = session.execute(select(AuditLog).order_by(AuditLog.seq).limit(1)).scalar_one()
    alvo.dados = {**(alvo.dados or {}), "adulterado": True}
    session.flush()

    integra, erro = audit.verificar_cadeia()
    assert not integra
    assert erro == alvo.seq
