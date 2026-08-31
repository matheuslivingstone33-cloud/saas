"""ETAPA 7 — aprendizado por intencao: a mira que cada cliente afina sozinho.

Dois eixos, e eles aprendem coisas diferentes: o peso dos COMPONENTES do score
(que ja existia) e o fator por RAMO (que e a novidade e o fosso do produto).

O grosso destes testes nao verifica o que o loop aprende, e sim o que ele se
RECUSA a aprender. Aprendizado que se move rapido demais vira supersticao — e
supersticao aqui e invisivel: um loop guloso apagaria hoteis da mira do cliente
por causa de tres respostas ruins, e ausencia de lead nao aparece em tela
nenhuma.
"""

from __future__ import annotations

import pytest

from app.models.campaign import Campaign
from app.models.enums import (
    Canal,
    Direcao,
    Porte,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
)
from app.models.lead import Lead
from app.models.message import Message
from app.services.aprendizado import (
    FATOR_MAXIMO,
    FATOR_MINIMO,
    MINIMO_AMOSTRAS_RAMO,
    VALOR_POR_INTENCAO,
    LoopAprendizado,
)
from app.services.conversa import Intencao, ServicoDeConversa

CNAE_HOTEL = "5510801"
CNAE_MERCADO = "4711302"

COMPONENTES = {
    "aderencia_cnae": 0.8,
    "aderencia_texto": 0.5,
    "contato": 1.0,
    "porte": 0.6,
    "intencao": 0.0,
    "reputacao": 0.4,
}


@pytest.fixture
def campanha(session, usuario) -> Campaign:
    c = Campaign(
        user_id=usuario.id,
        nome="Etapa 7",
        servico="manutencao de ar-condicionado para empresas",
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.EXECUTANDO,
    )
    session.add(c)
    session.flush()
    return c


def _lead_abordado(session, usuario, campanha, *, cnae: str, sufixo: str) -> Lead:
    lead = Lead(
        user_id=usuario.id,
        campaign_id=campanha.id,
        cnpj=f"445556660001{sufixo}",
        razao_social=f"EMPRESA {sufixo} LTDA",
        email=f"contato{sufixo}@exemplo.com.br",
        municipio="Fortaleza",
        uf="CE",
        cnae_principal=cnae,
        status=StatusLead.ABORDADO,
        provenance={"fonte_primaria": "teste"},
        score=45,
        score_breakdown={"componentes": dict(COMPONENTES)},
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
            corpo="Ola.",
        )
    )
    session.flush()
    return lead


def _responder(session, portas_db, lead: Lead, corpo: str) -> None:
    ServicoDeConversa(session, portas_db).receber(lead=lead, corpo=corpo)


# --- O defeito de sinal que existia antes desta etapa ------------------------
def test_opt_out_ensina_uma_vez_so_e_no_sentido_certo(
    session, usuario, portas_db, campanha
) -> None:
    """Antes da Etapa 7 um "me tire da lista" ensinava duas coisas opostas.

    O lead passa por `respondido` a caminho de `opt_out`. Como `respondido`
    contava como SUCESSO, a mesma mensagem primeiro ensinava que a mira estava
    certa e logo depois que estava errada — duas amostras contraditorias por um
    unico fato, e a primeira francamente errada: quem irrita a ponto de a
    pessoa pedir para sair da lista nao acertou o alvo.
    """
    loop = LoopAprendizado(session)
    lead = _lead_abordado(session, usuario, campanha, cnae=CNAE_HOTEL, sufixo="01")

    _responder(session, portas_db, lead, "por favor me tire da lista")

    estado = loop.estado(usuario.id)
    assert estado["amostras"] == 1, "um fato, uma amostra"

    sucesso = estado["estatisticas"]["aderencia_cnae"]["sucesso"]["n"]
    fracasso = estado["estatisticas"]["aderencia_cnae"]["fracasso"]["n"]
    assert (sucesso, fracasso) == (0, 1), "opt-out e fracasso, e so isso"

    ramo = next(r for r in estado["mira"] if r["cnae"] == CNAE_HOTEL)
    assert ramo["amostras"] == 1
    assert ramo["media_sinal"] == -1.0
    assert lead.status is StatusLead.OPT_OUT


def test_interesse_ensina_uma_vez_so(session, usuario, portas_db, campanha) -> None:
    loop = LoopAprendizado(session)
    lead = _lead_abordado(session, usuario, campanha, cnae=CNAE_HOTEL, sufixo="02")

    _responder(session, portas_db, lead, "tenho interesse sim, qual o valor?")

    estado = loop.estado(usuario.id)
    assert estado["amostras"] == 1
    assert estado["estatisticas"]["aderencia_cnae"]["sucesso"]["n"] == 1
    assert next(r for r in estado["mira"] if r["cnae"] == CNAE_HOTEL)["media_sinal"] == 1.0


# --- Distinguir as intencoes entre si ----------------------------------------
def test_objecao_de_preco_nao_ensina_a_fugir_do_ramo() -> None:
    """Esta caro diz que o ramo compra e o momento estava errado.

    Para a maquina de estados, objecao e recusa acabam parecidas. Nao sao a
    mesma coisa: tratar "sem orcamento este ano" como erro de mira ensinaria o
    Cerebro a abandonar justamente o ramo que reconheceu a necessidade.
    """
    assert VALOR_POR_INTENCAO["objecao"] > 0
    assert VALOR_POR_INTENCAO["objecao"] < VALOR_POR_INTENCAO["interesse"]


def test_recusa_e_opt_out_nao_pesam_igual() -> None:
    """Ja temos fornecedor e me tire da lista ensinam coisas diferentes.

    A primeira e a frase de quem CONSOME o servico. So a segunda diz que o
    alvo estava errado — e por isso e a unica que vale -1.
    """
    assert VALOR_POR_INTENCAO["pedido_opt_out"] == -1.0
    assert VALOR_POR_INTENCAO["recusa"] > VALOR_POR_INTENCAO["pedido_opt_out"]


def test_ausencia_nao_e_resposta_e_nao_move_a_mira(
    session, usuario, portas_db, campanha
) -> None:
    """Resposta de ferias nao diz nada sobre o ramo — nem a favor, nem contra."""
    loop = LoopAprendizado(session)
    lead = _lead_abordado(session, usuario, campanha, cnae=CNAE_HOTEL, sufixo="03")

    _responder(session, portas_db, lead, "estou de ferias, retorno no dia 10")

    estado = loop.estado(usuario.id)
    stats = estado["estatisticas"]["aderencia_cnae"]
    assert stats["sucesso"]["n"] == 0 and stats["fracasso"]["n"] == 0
    ramo = next(r for r in estado["mira"] if r["cnae"] == CNAE_HOTEL)
    assert ramo["media_sinal"] == 0.0


# --- O eixo novo: fator por ramo ---------------------------------------------
def _acumular(loop: LoopAprendizado, user_id, cnae: str, intencao: str, vezes: int) -> None:
    for _ in range(vezes):
        loop.observar_intencao(
            user_id=user_id, intencao=intencao, cnae=cnae, componentes=dict(COMPONENTES)
        )


def test_ramo_nao_se_move_sem_amostra(session, usuario) -> None:
    """Tres respostas ruins de hotel nao podem tirar hotel da mira."""
    loop = LoopAprendizado(session)
    _acumular(loop, usuario.id, CNAE_HOTEL, Intencao.PEDIDO_OPT_OUT.value, 3)

    ajuste = loop.recalcular_ramos(usuario.id)
    assert not ajuste.aplicado
    assert str(MINIMO_AMOSTRAS_RAMO) in ajuste.motivo
    assert loop.fatores_de_ramo(usuario.id)[CNAE_HOTEL] == 1.0


def test_ramo_que_responde_sobe_e_ramo_que_recusa_desce(session, usuario) -> None:
    loop = LoopAprendizado(session)
    _acumular(loop, usuario.id, CNAE_HOTEL, Intencao.INTERESSE.value, MINIMO_AMOSTRAS_RAMO)
    _acumular(
        loop, usuario.id, CNAE_MERCADO, Intencao.PEDIDO_OPT_OUT.value, MINIMO_AMOSTRAS_RAMO
    )

    ajuste = loop.recalcular_ramos(usuario.id)
    assert ajuste.aplicado, ajuste.motivo

    fatores = loop.fatores_de_ramo(usuario.id)
    assert fatores[CNAE_HOTEL] > 1.0
    assert fatores[CNAE_MERCADO] < 1.0


def test_o_fator_nunca_zera_um_ramo(session, usuario) -> None:
    """Piso e teto, e um loop guloso batendo neles vinte vezes seguidas.

    Sem piso, um ramo com historico ruim sairia da mira para sempre — e a unica
    evidencia seria a ausencia de leads daquele ramo, que nao aparece em tela
    nenhuma.
    """
    loop = LoopAprendizado(session)
    _acumular(
        loop, usuario.id, CNAE_HOTEL, Intencao.PEDIDO_OPT_OUT.value, MINIMO_AMOSTRAS_RAMO
    )
    _acumular(loop, usuario.id, CNAE_MERCADO, Intencao.INTERESSE.value, MINIMO_AMOSTRAS_RAMO)

    for _ in range(20):
        loop.recalcular_ramos(usuario.id)

    fatores = loop.fatores_de_ramo(usuario.id)
    assert fatores[CNAE_HOTEL] >= FATOR_MINIMO
    assert fatores[CNAE_MERCADO] <= FATOR_MAXIMO
    assert fatores[CNAE_HOTEL] > 0, "o ramo continua sendo procurado"


def test_o_fator_inclina_o_score_sem_mandar_nele(session, usuario) -> None:
    """O Cerebro continua no comando: o fator multiplica, nao substitui."""
    from app.services.cerebro import Expansao, RamoRelevante
    from app.services.scoring import ScoringService

    expansao = Expansao(
        servico="manutencao de ar-condicionado",
        regiao="Fortaleza, CE",
        ramos=[
            RamoRelevante(codigo=CNAE_HOTEL, descricao="Hoteis", distancia=0.2, peso=0.8)
        ],
    )
    lead = Lead(
        user_id=usuario.id,
        cnpj="44555666000199",
        razao_social="HOTEL X",
        email="x@exemplo.com",
        cnae_principal=CNAE_HOTEL,
        porte=Porte.EPP,
        provenance={"fonte_primaria": "teste"},
    )

    neutro = ScoringService().pontuar(lead, expansao)
    aprendido = ScoringService(None, {CNAE_HOTEL: 1.3}).pontuar(lead, expansao)
    punido = ScoringService(None, {CNAE_HOTEL: 0.6}).pontuar(lead, expansao)

    assert aprendido.score > neutro.score > punido.score
    assert punido.componentes["aderencia_cnae"] > 0, "punido, nao apagado"


def test_a_mira_de_um_tenant_nao_vaza_para_outro(session, usuario) -> None:
    """O ativo e o historico do cliente. Vazar seria entregar o fosso."""
    from app.models.user import User

    outro = User(email="outro@prospector.local", nome="Outro")
    session.add(outro)
    session.flush()

    loop = LoopAprendizado(session)
    _acumular(loop, usuario.id, CNAE_HOTEL, Intencao.INTERESSE.value, MINIMO_AMOSTRAS_RAMO)
    loop.recalcular_ramos(usuario.id)

    assert loop.fatores_de_ramo(usuario.id)[CNAE_HOTEL] > 1.0
    assert loop.fatores_de_ramo(outro.id) == {}


def test_restaurar_padrao_desfaz_os_dois_eixos(session, usuario) -> None:
    """Restaurar so metade e pior que nao restaurar: da falsa sensacao de reset."""
    loop = LoopAprendizado(session)
    _acumular(loop, usuario.id, CNAE_HOTEL, Intencao.INTERESSE.value, MINIMO_AMOSTRAS_RAMO)
    loop.recalcular_ramos(usuario.id)

    loop.restaurar_padrao(usuario.id)

    assert loop.fatores_de_ramo(usuario.id) == {}
    assert loop.estado(usuario.id)["amostras"] == 0
    assert loop.mira(usuario.id) == []


# --- Visibilidade: aprendizado invisivel e supersticao -----------------------
def test_a_mira_diz_quanto_falta_para_aprender(session, usuario) -> None:
    loop = LoopAprendizado(session)
    _acumular(loop, usuario.id, CNAE_HOTEL, Intencao.INTERESSE.value, 4)

    ramo = loop.mira(usuario.id)[0]
    assert ramo["amostras"] == 4
    assert ramo["faltam_amostras"] == MINIMO_AMOSTRAS_RAMO - 4
    assert ramo["intencoes"] == {"interesse": 4}


def test_api_devolve_a_mira_e_recalcula_os_dois_eixos(client, usuario) -> None:
    estado = client.get("/v1/cerebro/pesos").json()
    assert estado["mira"] == []

    ajuste = client.post("/v1/cerebro/pesos/recalcular").json()
    assert ajuste["aplicado"] is False
    assert ajuste["ramos"]["aplicado"] is False
    assert ajuste["ramos"]["motivo"]
