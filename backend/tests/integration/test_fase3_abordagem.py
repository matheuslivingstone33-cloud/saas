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
    assert conteudo.gancho
    # Por padrao a mensagem sai sem declaracao de IA e sem linha de descadastro
    # no texto (decisao do dono, 22/09): ela le como e-mail escrito por gente.
    assert conteudo.declaracao_ia is None
    assert "/descadastro/" not in conteudo.corpo
    assert "inteligencia artificial" not in conteudo.corpo


def test_declaracao_de_ia_volta_quando_a_chave_e_ligada(
    session, usuario, portas_db, monkeypatch
) -> None:
    """A obrigacao pode voltar (PL 2338): ligar e trocar uma variavel."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "declarar_ia", True)
    monkeypatch.setattr(get_settings(), "link_descadastro_no_corpo", True)
    campanha = _campanha(session, usuario, nome="Com declaracao")
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    lead = next(x for x in leads if x.email)

    conteudo = PersonalizationService(session, portas_db).gerar(lead, campanha, expansao, usuario)
    assert conteudo.declaracao_ia and "inteligencia artificial" in conteudo.corpo
    linha = next(li for li in conteudo.corpo.splitlines() if "/descadastro/" in li)
    assert "descadastre-se" in linha, "rotulo e link na mesma linha (protecao do Motor 4)"


def test_link_no_corpo_sai_com_rotulo_na_mesma_linha(
    session, usuario, portas_db, settings, monkeypatch
) -> None:
    """Quando a linha visivel e ligada, ela tem que sair de um jeito so.

    Por padrao o link fica so no cabecalho `List-Unsubscribe` (decisao do dono,
    22/09): a linha no texto dava cara de disparo em massa. Quem precisar dela —
    um cliente mais conservador, ou o dia em que a regra mudar — liga
    LINK_DESCADASTRO_NO_CORPO, e entao vale a regra invisivel do radar 0.3:
    rotulo e link na MESMA linha. O Motor 4 remove a linha inteira que contem
    `/descadastro/` antes de varrer opt-out; se o rotulo caisse numa linha a
    parte, ele voltaria citado em toda resposta e todo "tenho interesse" viraria
    opt-out, que e terminal.
    """
    monkeypatch.setattr(settings, "link_descadastro_no_corpo", True)
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
    # A saida vive no CABECALHO, que e o que o Gmail e o Yahoo exigem e viram
    # botao no topo da mensagem. O texto sai limpo.
    assert "/descadastro/" in payload["headers"]["List-Unsubscribe"]
    assert "/descadastro/" not in payload["corpo_texto"]
    assert "inteligencia artificial" not in payload["corpo_texto"]


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


# --- Campanha parada nao despacha abordagem fria -----------------------------
def test_campanha_pausada_barra_aprovacao_de_abordagem_fria(
    session, usuario, portas_db, settings
) -> None:
    """A pausa por reputacao/conta so protege o dominio se PARAR de fato.

    Antes desta trava, a leva parava na falha mas um `aprovar` humano seguinte
    ainda despachava cold mail para a MESMA campanha que estourou o limite — a
    pausa virava enfeite. Agora aprovar uma abordagem fria de campanha parada e
    bloqueado, e nada sai.
    """
    campanha = _campanha(session, usuario, nome="Pausada", nivel=NivelAutonomia.ASSISTIDO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    envio = SendService(session, portas_db)
    lote = envio.preparar_lote(campanha, leads, expansao)
    mensagem = lote.mensagens[0]

    # A campanha e pausada DEPOIS de a mensagem ja estar aguardando aprovacao.
    campanha.status = StatusCampanha.PAUSADA
    session.flush()

    antes = len(list(settings.outbox_path.glob("*.json")))
    assert envio.aprovar(mensagem, usuario) is False
    depois = len(list(settings.outbox_path.glob("*.json")))
    assert depois == antes, "nada pode sair de campanha parada"

    # A mensagem ESPERA na fila, nao morre: antes de 21/09 virava BLOQUEADA e,
    # com a chave de idempotencia gravada, o lead nunca mais era abordado.
    assert mensagem.status is StatusMensagem.APROVADA
    assert "adiada: campanha_parada" in (mensagem.erro or "")

    campanha.status = StatusCampanha.EXECUTANDO
    session.flush()
    envio.processar_pendentes(usuario.id)
    assert mensagem.status is StatusMensagem.ENVIADA, "retomada, a fila anda"


def test_limite_do_dia_adia_e_a_mensagem_sai_no_dia_seguinte(
    session, usuario, portas_db, monkeypatch
) -> None:
    """Limite do dia e aquecimento do dominio passam; a mensagem nao pode morrer."""
    from datetime import timedelta

    from app.core.config import get_settings
    from app.core.ids import now

    campanha = _campanha(session, usuario, nome="Teto", nivel=NivelAutonomia.ASSISTIDO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario, meta=2)
    envio = SendService(session, portas_db)
    # Duas mensagens ja redigidas e aprovadas; o teto do dia so cabe uma.
    lote = envio.preparar_lote(campanha, leads[:2], expansao)
    assert len(lote.mensagens) == 2
    for m in lote.mensagens:
        m.status = StatusMensagem.APROVADA
    session.flush()
    monkeypatch.setattr(get_settings(), "max_envios_por_campanha_dia", 1)
    envio.processar_pendentes(usuario.id)

    enviadas = [m for m in lote.mensagens if m.status is StatusMensagem.ENVIADA]
    esperando = [m for m in lote.mensagens if m.status is StatusMensagem.APROVADA]
    assert len(enviadas) == 1 and len(esperando) == 1
    assert "adiada: limite_diario_campanha" in (esperando[0].erro or "")

    # "Amanha": o envio de ontem sai da janela de 24 h.
    enviadas[0].enviado_em = now() - timedelta(hours=25)
    session.flush()
    envio.processar_pendentes(usuario.id)
    assert esperando[0].status is StatusMensagem.ENVIADA


def test_campanha_pausada_nao_trava_a_fila_das_outras(session, usuario, portas_db) -> None:
    """A fila e do usuario inteiro: a pendencia adiada nao pode ocupar a vez."""
    pausada = _campanha(session, usuario, nome="Pausada fila", nivel=NivelAutonomia.AUTOMATICO)
    ativa = _campanha(session, usuario, nome="Ativa fila", nivel=NivelAutonomia.AUTOMATICO)
    exp_p, leads_p = _descobrir(session, portas_db, pausada, usuario, meta=2)
    exp_a, leads_a = _descobrir(session, portas_db, ativa, usuario, meta=1)
    envio = SendService(session, portas_db)

    retidas = envio.preparar_lote(pausada, leads_p, exp_p, nivel=NivelAutonomia.ASSISTIDO)
    for m in retidas.mensagens:
        m.status = StatusMensagem.APROVADA
    pausada.status = StatusCampanha.PAUSADA
    da_ativa = envio.preparar_lote(ativa, leads_a, exp_a, nivel=NivelAutonomia.ASSISTIDO)
    for m in da_ativa.mensagens:
        m.status = StatusMensagem.APROVADA
    session.flush()

    envio.processar_pendentes(usuario.id, limite=1)

    assert all(m.status is StatusMensagem.APROVADA for m in retidas.mensagens)
    assert all(m.status is StatusMensagem.ENVIADA for m in da_ativa.mensagens)


def test_mensagem_manual_a_quem_nunca_respondeu_e_abordagem_fria(
    session, usuario, portas_db
) -> None:
    """Ser escrita a mao nao faz uma mensagem virar resposta."""
    from app.core.ids import now
    from app.models.enums import Canal, Direcao
    from app.models.message import Message

    campanha = _campanha(session, usuario, nome="Manual fria")
    _, leads = _descobrir(session, portas_db, campanha, usuario, meta=1)
    lead = leads[0]
    envio = SendService(session, portas_db)

    def _saida() -> Message:
        return Message(
            user_id=usuario.id, campaign_id=campanha.id, lead_id=lead.id,
            canal=Canal.EMAIL, direcao=Direcao.SAIDA, status=StatusMensagem.APROVADA,
            destinatario=lead.email, corpo="oi", metadados={"gerado_por": "humano"},
        )

    assert envio._e_abordagem_fria(_saida()) is True

    session.add(
        Message(
            user_id=usuario.id, campaign_id=campanha.id, lead_id=lead.id,
            canal=Canal.EMAIL, direcao=Direcao.ENTRADA, status=StatusMensagem.RESPONDIDA,
            destinatario=lead.email, corpo="tenho interesse", created_at=now(),
        )
    )
    session.flush()
    assert envio._e_abordagem_fria(_saida()) is False


def test_campanha_pausada_nao_gera_lote_novo(session, usuario, portas_db) -> None:
    """Campanha parada nem redige (custo de IA) nem dispara uma leva nova."""
    campanha = _campanha(session, usuario, nome="Parada geracao", nivel=NivelAutonomia.AUTOMATICO)
    expansao, leads = _descobrir(session, portas_db, campanha, usuario)
    campanha.status = StatusCampanha.PAUSADA
    session.flush()

    lote = SendService(session, portas_db).preparar_lote(campanha, leads, expansao)
    assert lote.geradas == 0
    assert lote.enviadas == 0


def test_resposta_em_conversa_nao_e_barrada_por_campanha_pausada(
    session, usuario, portas_db
) -> None:
    """A trava vale so para ABORDAGEM FRIA: responder a quem ja escreveu segue.

    Uma resposta e solicitada e nao ameaca a reputacao — a camada de conversa a
    despacha sem a flag `abordagem_fria`, entao a pausa da campanha nao a barra.
    """
    campanha = _campanha(session, usuario, nome="Pausada resposta")
    lead = _lead_qualificado(session, usuario, campanha, "77")
    campanha.status = StatusCampanha.PAUSADA
    session.flush()
    envio = SendService(session, portas_db)
    destino = lead.email.strip().lower()

    # Sem a flag (resposta em conversa): a pausa da campanha NUNCA e o motivo.
    sem_flag = envio.checar_bloqueios(campanha, lead, destino)
    assert sem_flag is None or sem_flag.motivo != "campanha_parada"
    # Com a flag (abordagem fria): a pausa barra.
    com_flag = envio.checar_bloqueios(campanha, lead, destino, abordagem_fria=True)
    assert com_flag is not None and com_flag.motivo == "campanha_parada"


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


# --- Warmup (aquecimento) do dominio de envio --------------------------------
def _marcar_email_enviado(session, usuario, campanha, sufixo, *, enviado_em=None):  # noqa: ANN001
    """Insere um e-mail JA ENVIADO, para encher o contador global do warmup."""
    from app.core.ids import now
    from app.models.enums import Direcao
    from app.models.message import Message

    msg = Message(
        user_id=usuario.id,
        campaign_id=campanha.id,
        canal=Canal.EMAIL,
        direcao=Direcao.SAIDA,
        status=StatusMensagem.ENVIADA,
        destinatario=f"enviado{sufixo}@exemplo.com.br",
        corpo="x",
        enviado_em=enviado_em or now(),
    )
    session.add(msg)
    session.flush()
    return msg


def test_leva_automatica_respeita_o_warmup_do_dominio(
    session, usuario, portas_db, settings, monkeypatch
) -> None:
    """Dominio novo em modo real: a leva automatica para no teto do warmup.

    Sem a rampa, um dominio recem-criado dispararia o volume cheio no primeiro
    dia e iria direto para spam — e reputacao de dominio nao volta. Com o teto do
    dia 0 rebaixado para 2, so 2 abordagens frias saem e as demais sao barradas.
    """
    from app.services import envio as envio_mod

    monkeypatch.setattr(envio_mod, "_RAMPA_AQUECIMENTO", ((0, 2),))
    real = settings.model_copy(update={"email_mode": "real"})
    campanha = _campanha(session, usuario, nome="Warmup", nivel=NivelAutonomia.AUTOMATICO)
    leads = [_lead_qualificado(session, usuario, campanha, s) for s in ("01", "02", "03", "04")]

    antes = len(list(settings.outbox_path.glob("*.json")))
    lote = SendService(session, portas_db, settings=real).preparar_lote(campanha, leads, None)

    assert lote.enviadas == 2, "so o teto do warmup (2) pode sair no dia 0"
    assert lote.motivos_bloqueio.get("aquecimento_dominio", 0) >= 1
    depois = len(list(settings.outbox_path.glob("*.json")))
    assert depois - antes == 2, "nada acima do teto do warmup vai para o outbox"


def test_warmup_barra_abordagem_fria_mas_nao_resposta(
    session, usuario, portas_db, settings, monkeypatch
) -> None:
    """A rampa vale so para ABORDAGEM FRIA e so em modo real.

    Resposta a quem ja escreveu (`abordagem_fria=False`) nao ameaca a reputacao e
    perde o lead engajado se barrada — a mesma regra da pausa por campanha. E em
    mock nao ha dominio a proteger, entao nem a abordagem fria e barrada.
    """
    from app.services import envio as envio_mod

    monkeypatch.setattr(envio_mod, "_RAMPA_AQUECIMENTO", ((0, 1),))
    real = settings.model_copy(update={"email_mode": "real"})
    campanha = _campanha(session, usuario, nome="Warmup flag", nivel=NivelAutonomia.AUTOMATICO)
    lead = _lead_qualificado(session, usuario, campanha, "88")
    destino = lead.email.strip().lower()
    _marcar_email_enviado(session, usuario, campanha, "89")  # esgota o teto do dia (1)

    envio = SendService(session, portas_db, settings=real)
    com_flag = envio.checar_bloqueios(campanha, lead, destino, abordagem_fria=True)
    assert com_flag is not None and com_flag.motivo == "aquecimento_dominio"
    sem_flag = envio.checar_bloqueios(campanha, lead, destino)
    assert sem_flag is None or sem_flag.motivo != "aquecimento_dominio"

    mock = SendService(session, portas_db, settings=settings)
    mock_bloqueio = mock.checar_bloqueios(campanha, lead, destino, abordagem_fria=True)
    assert mock_bloqueio is None or mock_bloqueio.motivo != "aquecimento_dominio"


def test_teto_do_warmup_sobe_com_a_idade_do_dominio(
    session, usuario, portas_db, settings
) -> None:
    """A rampa padrao sobe com a idade do dominio e some depois de aquecido.

    Cobre tambem a normalizacao do timestamp que volta do banco (naive/str no
    SQLite): sem ela, `now() - primeiro_envio` estouraria.
    """
    from datetime import timedelta

    from app.core.ids import now

    real = settings.model_copy(update={"email_mode": "real"})
    envio = SendService(session, portas_db, settings=real)
    campanha = _campanha(session, usuario, nome="Idade dominio")

    assert envio._idade_do_dominio_em_dias() == 0
    assert envio._teto_de_aquecimento() == 50  # dia 0: base da rampa

    _marcar_email_enviado(session, usuario, campanha, "70", enviado_em=now() - timedelta(days=10))
    assert envio._idade_do_dominio_em_dias() == 10
    assert envio._teto_de_aquecimento() == 500  # >= 7 dias

    _marcar_email_enviado(session, usuario, campanha, "71", enviado_em=now() - timedelta(days=31))
    assert envio._idade_do_dominio_em_dias() == 31
    assert envio._teto_de_aquecimento() is None  # dominio aquecido: rampa nao limita
