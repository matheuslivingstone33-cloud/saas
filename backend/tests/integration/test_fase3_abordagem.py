"""FASE 3 — Motor 3: personalizacao, SendService, limites e autonomia."""

from __future__ import annotations

import json

import pytest

from app.models.campaign import Campaign
from app.models.enums import (
    Canal,
    NivelAutonomia,
    OrigemOptOut,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
    TipoContato,
)
from app.models.lead import Lead
from app.models.opt_out import OptOut
from app.ports.dto import SendResult
from app.repositories.misc import OptOutRepository, UserRepository
from app.services.cerebro import ExpansorDeServico
from app.services.compliance import OptOutService
from app.services.descoberta import DiscoveryService
from app.services.envio import SendService
from app.services.personalizacao import LIMIAR_INTENCAO, PersonalizationService
from app.services.pipeline import PipelineStub

SERVICO = "instalacao e manutencao de ar condicionado para empresas"


def _campanha(session, usuario, nome="Abordagem", nivel=None) -> Campaign:  # noqa: ANN001
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


def _descobrir(session, portas, campanha, usuario, meta=3):  # noqa: ANN001
    expansao = ExpansorDeServico(session, portas).expandir(
        SERVICO, "Fortaleza, CE", user_id=usuario.id
    )
    achado = DiscoveryService(session, portas).descobrir(campanha, expansao, meta_leads=meta)
    for lead in achado.leads:
        lead.score = 50
        lead.score_breakdown = {"componentes": {"contato": 1.0}}
        if lead.status is StatusLead.DESCOBERTO:
            lead.status = StatusLead.QUALIFICADO
    session.flush()
    return expansao, achado.leads


# --- Personalizacao ----------------------------------------------------------
def test_mensagem_e_personalizada_com_contexto_do_lead(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    lead = next(x for x in leads if x.email)

    conteudo = PersonalizationService(session, portas_db).gerar(lead, campanha, expansao, usuario)

    nome = lead.nome_fantasia or lead.razao_social
    assert nome.split()[0] in conteudo.corpo
    assert conteudo.assunto and nome.split()[0] in conteudo.assunto
    assert conteudo.declaracao_ia, "toda mensagem de IA precisa se declarar"
    assert conteudo.gancho


def test_corpo_traz_link_de_descadastro_com_rotulo_na_mesma_linha(
    session, usuario, portas_db, settings
) -> None:
    """O link de descadastro precisa aparecer VISIVEL no corpo, nao so no header.

    Com SES real, quem nao acha como sair marca como spam — e reclamacao de spam
    e o que suspende a conta e queima a reputacao do dominio. Dar o link na cara
    reduz o risco que mais importa.

    Regra invisivel (radar 0.3): rotulo e link ficam na MESMA linha. O Motor 4
    remove a linha inteira que contem `/descadastro/` antes de varrer opt-out; se
    o rotulo caisse numa linha a parte, ele voltaria citado em toda resposta e
    todo "tenho interesse" viraria opt-out, que e terminal.
    """
    campanha = _campanha(session, usuario)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    lead = next(x for x in leads if x.email)

    conteudo = PersonalizationService(session, portas_db, settings).gerar(
        lead, campanha, expansao, usuario
    )

    # O link do corpo e IDENTICO ao que vai no header List-Unsubscribe (mesmo
    # gerador deterministico), senao o destinatario teria dois enderecos de saida.
    link = OptOutService(session, settings=settings).link_para(lead, settings.url_publica)
    assert "/descadastro/" in link
    assert link in conteudo.corpo, "o link de descadastro tem que estar no corpo, nao so no header"

    linhas_com_link = [ln for ln in conteudo.corpo.splitlines() if "/descadastro/" in ln]
    assert len(linhas_com_link) == 1, "o link do descadastro tem que ficar numa unica linha"
    linha = linhas_com_link[0]
    assert linha.strip() != link, "a linha do link precisa trazer o rotulo junto, nao a URL nua"

    # A prova do que importa para o Motor 4: removida a linha do `/descadastro/`,
    # o corpo nao guarda NENHUMA marca de opt-out. Se o rotulo estivesse solto,
    # "descadastr" sobraria aqui e o rodape citado viraria falso opt-out.
    resto = "\n".join(ln for ln in conteudo.corpo.splitlines() if "/descadastro/" not in ln)
    assert "descadastr" not in resto.lower()


def test_web_search_so_roda_em_lead_de_alto_valor(session, usuario, portas_db) -> None:
    """Sinal de intencao custa (balde 2): so vale nos leads de maior score."""
    campanha = _campanha(session, usuario, nome="Intencao")
    _, leads = _descobrir(session, portas_db, campanha, usuario)
    lead = next(x for x in leads if x.email)
    servico = PersonalizationService(session, portas_db)

    lead.score = LIMIAR_INTENCAO - 10
    barato = servico.gerar(lead, campanha, None, usuario)
    assert barato.usou_web_search is False
    assert barato.sinais == []

    lead.score = LIMIAR_INTENCAO + 10
    servico.reiniciar_orcamento()
    caro = servico.gerar(lead, campanha, None, usuario)
    assert caro.usou_web_search is True
    assert caro.sinais


def test_orcamento_de_intencao_limita_o_lote(session, usuario, portas_db) -> None:
    from app.services.personalizacao import MAX_BUSCAS_INTENCAO

    campanha = _campanha(session, usuario, nome="Orcamento")
    _, leads = _descobrir(session, portas_db, campanha, usuario)
    lead = next(x for x in leads if x.email)
    lead.score = 95
    servico = PersonalizationService(session, portas_db)
    servico.reiniciar_orcamento()

    usos = sum(
        1 for _ in range(MAX_BUSCAS_INTENCAO + 3)
        if servico.gerar(lead, campanha, None, usuario).usou_web_search
    )
    assert usos == MAX_BUSCAS_INTENCAO


# --- Nivel de autonomia ------------------------------------------------------
def test_modo_assistido_nao_envia_sem_aprovacao(session, usuario, portas_db, settings) -> None:
    campanha = _campanha(session, usuario, nome="Assistido", nivel=NivelAutonomia.ASSISTIDO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)

    antes = len(list(settings.outbox_path.glob("*.json")))
    lote = SendService(session, portas_db).preparar_lote(campanha, leads, expansao)

    assert lote.geradas > 0
    assert lote.enviadas == 0
    assert lote.aguardando_aprovacao == lote.geradas
    assert len(list(settings.outbox_path.glob("*.json"))) == antes
    assert all(m.status is StatusMensagem.AGUARDANDO_APROVACAO for m in lote.mensagens)


def test_modo_automatico_dispara_sozinho(session, usuario, portas_db, settings) -> None:
    campanha = _campanha(session, usuario, nome="Automatico", nivel=NivelAutonomia.AUTOMATICO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)

    antes = len(list(settings.outbox_path.glob("*.json")))
    lote = SendService(session, portas_db).preparar_lote(campanha, leads, expansao)

    assert lote.enviadas > 0
    assert lote.aguardando_aprovacao == 0
    assert len(list(settings.outbox_path.glob("*.json"))) == antes + lote.enviadas
    for mensagem in lote.mensagens:
        if mensagem.status is StatusMensagem.ENVIADA:
            lead = session.get(Lead, mensagem.lead_id)
            assert lead.status is StatusLead.ABORDADO


def test_aprovacao_manual_envia_e_audita(session, usuario, portas_db, settings) -> None:
    campanha = _campanha(session, usuario, nome="Aprovar", nivel=NivelAutonomia.ASSISTIDO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    envio = SendService(session, portas_db)
    lote = envio.preparar_lote(campanha, leads, expansao)
    mensagem = lote.mensagens[0]

    antes = len(list(settings.outbox_path.glob("*.json")))
    assert envio.aprovar(mensagem, usuario) is True
    assert mensagem.status is StatusMensagem.ENVIADA
    assert mensagem.aprovado_em is not None
    assert len(list(settings.outbox_path.glob("*.json"))) == antes + 1

    # aprovar de novo tem que falhar: ja saiu do estado de aprovacao
    from app.core.errors import BloqueadoPorCompliance

    with pytest.raises(BloqueadoPorCompliance):
        envio.aprovar(mensagem, usuario)


# --- Guardrails do envio -----------------------------------------------------
def test_opt_out_bloqueia_no_momento_do_envio(session, usuario, portas_db) -> None:
    """Opt-out registrado DEPOIS da geracao ainda barra o disparo."""
    campanha = _campanha(session, usuario, nome="OptOut tardio", nivel=NivelAutonomia.ASSISTIDO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    envio = SendService(session, portas_db)
    lote = envio.preparar_lote(campanha, leads, expansao)
    mensagem = lote.mensagens[0]

    session.add(
        OptOut(
            user_id=usuario.id,
            tipo_contato=TipoContato.EMAIL,
            contato=mensagem.destinatario,
            contato_normalizado=mensagem.destinatario.lower(),
            origem=OrigemOptOut.LINK_DESCADASTRO,
        )
    )
    session.flush()

    assert envio.aprovar(mensagem, usuario) is False
    assert mensagem.status is StatusMensagem.BLOQUEADA
    assert "opt_out" in (mensagem.erro or "")


def test_limite_diario_por_usuario_barra_envio(session, usuario, portas_db, settings) -> None:
    campanha = _campanha(session, usuario, nome="Limite", nivel=NivelAutonomia.AUTOMATICO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)

    original = settings.max_envios_por_usuario_dia
    settings.max_envios_por_usuario_dia = 1
    try:
        lote = SendService(session, portas_db, settings=settings).preparar_lote(
            campanha, leads, expansao
        )
        assert lote.enviadas <= 1
        assert lote.motivos_bloqueio.get("limite_diario_usuario", 0) >= 1
    finally:
        settings.max_envios_por_usuario_dia = original


def test_whatsapp_frio_e_bloqueado_por_padrao(session, usuario, portas_db, settings) -> None:
    assert settings.whatsapp_template_enabled is False
    campanha = _campanha(session, usuario, nome="WhatsApp", nivel=NivelAutonomia.AUTOMATICO)
    campanha.canal_padrao = Canal.WHATSAPP
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)

    lote = SendService(session, portas_db).preparar_lote(campanha, leads, expansao)
    assert lote.enviadas == 0
    assert lote.motivos_bloqueio.get("canal_bloqueado", 0) >= 1


def test_idempotencia_impede_segunda_abordagem(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Idempotente", nivel=NivelAutonomia.ASSISTIDO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    envio = SendService(session, portas_db)

    primeiro = envio.preparar_lote(campanha, leads, expansao)
    segundo = envio.preparar_lote(campanha, leads, expansao)

    assert primeiro.geradas > 0
    assert segundo.geradas == 0
    assert segundo.motivos_bloqueio.get("ja_abordado", 0) >= primeiro.geradas


def test_lead_sem_email_e_descartado_e_nao_gera_mensagem(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Sem contato")
    _, leads = _descobrir(session, portas_db, campanha, usuario)
    for lead in leads:
        lead.email = None
    session.flush()

    lote = SendService(session, portas_db).preparar_lote(campanha, leads, None)
    assert lote.geradas == 0
    assert lote.sem_contato == len(leads)
    assert all(lead.status is StatusLead.DESCARTADO for lead in leads)


def test_conteudo_gravado_no_outbox_tem_descadastro(session, usuario, portas_db, settings) -> None:
    campanha = _campanha(session, usuario, nome="Outbox", nivel=NivelAutonomia.AUTOMATICO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    SendService(session, portas_db).preparar_lote(campanha, leads, expansao)

    arquivos = sorted(settings.outbox_path.glob("*.json"))
    assert arquivos
    payload = json.loads(arquivos[-1].read_text(encoding="utf-8"))
    assert "List-Unsubscribe" in payload["headers"]
    assert "inteligencia artificial" in payload["corpo_texto"]


# --- Falha SINCRONA de envio (o provedor recusa antes de aceitar) ------------
class _EmailQueFalha:
    """EmailPort que sempre recusa, com o escopo de falha que o teste escolher.

    Substitui o mock (que so tem sucesso) pelo caso que so acontece com SES real.
    """

    provedor = "email"
    modo = "real"

    def __init__(self, escopo: str) -> None:
        self.escopo = escopo
        self.tentativas = 0

    def enviar(self, mensagem) -> SendResult:  # noqa: ANN001
        self.tentativas += 1
        return SendResult(
            sucesso=False,
            erro=f"falha simulada ({self.escopo})",
            modo="real",
            detalhes={"escopo_falha": self.escopo, "codigo": "Simulado"},
        )


def test_falha_de_destinatario_suprime_e_descarta_o_lead(session, usuario, portas_db) -> None:
    """Endereco morto na entrega: a cadencia nao pode reinsistir nele."""
    campanha = _campanha(session, usuario, nome="Destino morto", nivel=NivelAutonomia.AUTOMATICO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    lead = next(x for x in leads if x.email)
    portas_db.email = _EmailQueFalha("destinatario")

    lote = SendService(session, portas_db).preparar_lote(campanha, [lead], expansao)

    session.refresh(lead)
    assert lote.mensagens[0].status is StatusMensagem.FALHOU
    assert lead.status is StatusLead.DESCARTADO
    suprimido = OptOutRepository(session).existe(lead.email.strip().lower(), user_id=usuario.id)
    assert suprimido, "endereco morto tem que entrar na supressao, senao a cadencia reinsiste"


def _lead_qualificado(session, usuario, campanha, sufixo: str) -> Lead:  # noqa: ANN001
    lead = Lead(
        user_id=usuario.id,
        campaign_id=campanha.id,
        cnpj=f"445556660001{sufixo}",
        razao_social=f"EMPRESA {sufixo} LTDA",
        nome_fantasia=f"Empresa {sufixo}",
        email=f"contato{sufixo}@exemplo.com.br",
        municipio="Fortaleza",
        uf="CE",
        status=StatusLead.QUALIFICADO,
        provenance={"fonte_primaria": "teste"},
        score=40,
    )
    session.add(lead)
    session.flush()
    return lead


def test_falha_de_conta_pausa_a_campanha_e_nao_toca_nos_leads(session, usuario, portas_db) -> None:
    """Conta/remetente quebrada atinge todo mundo: PAUSA, nunca suprime a base."""
    campanha = _campanha(session, usuario, nome="Conta quebrada", nivel=NivelAutonomia.AUTOMATICO)
    leads = [_lead_qualificado(session, usuario, campanha, s) for s in ("11", "22", "33")]
    fake = _EmailQueFalha("conta")
    portas_db.email = fake

    lote = SendService(session, portas_db).preparar_lote(campanha, leads, None)

    assert campanha.status is StatusCampanha.PAUSADA
    assert lote.interrompido_por_conta is True
    # A leva parou na primeira falha: os demais nem foram redigidos (custo de IA).
    assert fake.tentativas == 1
    assert lote.geradas == 1
    for lead in leads:
        session.refresh(lead)
        assert lead.status is not StatusLead.DESCARTADO, "conta quebrada nao descarta lead"
    op = OptOutRepository(session)
    assert not any(op.existe(x.email.strip().lower(), user_id=usuario.id) for x in leads)


def test_falha_transitoria_so_marca_falhou(session, usuario, portas_db) -> None:
    """Recusa passageira/ambigua (throttle, conteudo) nao suprime nem pausa.

    E o guarda contra supressao em massa: um `MessageRejected` por conteudo
    atinge todos os destinatarios; trata-lo como endereco morto apagaria a base.
    """
    campanha = _campanha(session, usuario, nome="Transitorio", nivel=NivelAutonomia.AUTOMATICO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    lead = next(x for x in leads if x.email)
    portas_db.email = _EmailQueFalha("transitoria")

    lote = SendService(session, portas_db).preparar_lote(campanha, [lead], expansao)

    session.refresh(lead)
    assert lote.mensagens[0].status is StatusMensagem.FALHOU
    assert lote.interrompido_por_conta is False
    assert campanha.status is StatusCampanha.RASCUNHO, "transitorio nao pausa"
    assert lead.status is not StatusLead.DESCARTADO
    assert not OptOutRepository(session).existe(lead.email.strip().lower(), user_id=usuario.id)


# --- Limites e API -----------------------------------------------------------
def test_limites_expostos_na_api(client, usuario, session, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="API limites")
    r = client.get(f"/v1/campaigns/{campanha.id}/limites")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["restante_usuario"] > 0
    assert corpo["limite_campanha"] > 0


def test_api_aprova_e_despacha(client, usuario, session) -> None:
    UserRepository(session).assinatura(usuario.id).autonomy_level = NivelAutonomia.ASSISTIDO
    session.flush()
    campanha = client.post(
        "/v1/campaigns",
        json={"nome": "API fase 3", "servico": SERVICO, "regiao": "Fortaleza, CE"},
    ).json()
    client.post(f"/v1/campaigns/{campanha['id']}/run", json={"limite_leads": 3})

    pendentes = client.get(
        "/v1/messages",
        params={"campaign_id": campanha["id"], "status": "aguardando_aprovacao"},
    ).json()
    assert pendentes["total"] > 0

    alvo = pendentes["itens"][0]
    r = client.post(f"/v1/messages/{alvo['id']}/aprovar")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "enviada"


def test_pipeline_reporta_metricas_do_motor_3(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Pipeline M3", nivel=NivelAutonomia.AUTOMATICO)
    resultado = PipelineStub(session, portas_db).executar(campanha, limite_leads=3)
    dados = resultado.to_dict()
    assert "motivos_bloqueio" in dados
    assert "sem_contato" in dados
    assert dados["mensagens_geradas"] >= dados["mensagens_enviadas"]
