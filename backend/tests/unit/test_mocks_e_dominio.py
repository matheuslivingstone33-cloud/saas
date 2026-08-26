"""Mocks deterministicos, custo por balde e maquinas de estado."""

from __future__ import annotations

import json

import pytest

from app.core.errors import TransicaoInvalida
from app.core.pricing import PRECOS, Balde, balde_de
from app.domain import campaign_state, lead_state, subscription_state
from app.models.enums import (
    NivelAutonomia,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
)
from app.ports.dto import EmailMessage, PlacesQuery


# --- Mocks deterministicos ---------------------------------------------------
def test_fake_places_e_deterministico(portas) -> None:
    q = PlacesQuery(termo="supermercado", regiao="Fortaleza")
    a = portas.places.buscar(q)
    b = portas.places.buscar(q)
    assert [i.place_id for i in a.itens] == [i.place_id for i in b.itens]
    assert a.modo == "mock"
    # Sao empresas REAIS da fixture — nada sintetizado quando o termo casa.
    assert len(a.itens) >= 2
    assert all(i.place_id.startswith("mock_place_") for i in a.itens)


def test_fake_places_sempre_devolve_algo_mesmo_sem_fixture(portas) -> None:
    resp = portas.places.buscar(PlacesQuery(termo="fabrica de guarda-chuva", regiao="Sobral"))
    assert len(resp.itens) >= 3


def test_fake_llm_e_deterministico(portas) -> None:
    a = portas.llm.orquestrar_descoberta("manutencao de ar condicionado", "Fortaleza, CE", {})
    b = portas.llm.orquestrar_descoberta("manutencao de ar condicionado", "Fortaleza, CE", {})
    assert a.termos == b.termos
    assert a.cnaes_alvo == b.cnaes_alvo
    assert "supermercado" in a.termos


def test_embeddings_tem_dimensao_configurada_e_sao_estaveis(portas, settings) -> None:
    r1 = portas.llm.embutir(["padaria industrial"])
    r2 = portas.llm.embutir(["padaria industrial"])
    assert len(r1.vetores[0]) == settings.embedding_dim
    assert r1.vetores[0] == r2.vetores[0]


def test_receita_local_enriquece_por_cnpj_sem_chave(portas) -> None:
    empresa = portas.enrichment.por_cnpj("22333444000172")
    assert empresa is not None
    assert empresa.razao_social == "SUPERMERCADO BOA COMPRA LTDA"
    assert empresa.fonte == "receita_federal_dados_abertos"


def test_fake_email_grava_em_outbox_e_nao_envia(portas, settings) -> None:
    resultado = portas.email.enviar(
        EmailMessage(para="contato@exemplo.com.br", assunto="Oi", corpo_texto="Corpo")
    )
    assert resultado.sucesso and resultado.modo == "mock"
    arquivo = settings.outbox_path / resultado.detalhes["arquivo"].split("\\")[-1].split("/")[-1]
    assert arquivo.exists()
    payload = json.loads(arquivo.read_text(encoding="utf-8"))
    assert payload["para"] == "contato@exemplo.com.br"
    assert payload["modo"] == "mock"


# --- Custo -------------------------------------------------------------------
def test_baldes_nunca_se_misturam() -> None:
    for chave, preco in PRECOS.items():
        if chave.startswith(("places.", "email.", "whatsapp.", "enrichment.")):
            assert preco.balde is Balde.DADOS, chave
        if chave.startswith(("llm.", "search.")):
            assert preco.balde is Balde.IA, chave


def test_places_e_dados_llm_e_ia(portas, sink) -> None:
    portas.places.buscar(PlacesQuery(termo="hotel", regiao="Fortaleza"))
    assert hasattr(portas.llm, "completar")
    assert balde_de("places.text_search") is Balde.DADOS
    assert balde_de("llm.claude-opus-5.input") is Balde.IA
    assert sink.total_micros(Balde.DADOS) > 0
    assert sink.total_micros(Balde.IA) == 0


def test_custo_de_llm_gera_dois_eventos(portas, sink) -> None:
    portas.llm.orquestrar_descoberta("ar condicionado", "Fortaleza", {})
    eventos = [e for e in sink.eventos if e.provedor == "llm"]
    assert len(eventos) == 2
    assert {e.operacao for e in eventos} == {
        "orquestrar_descoberta.input",
        "orquestrar_descoberta.output",
    }
    assert all(e.balde == int(Balde.IA) for e in eventos)


# --- Maquinas de estado ------------------------------------------------------
def test_fluxo_feliz_do_lead() -> None:
    fluxo = [
        StatusLead.DESCOBERTO,
        StatusLead.QUALIFICADO,
        StatusLead.ENFILEIRADO,
        StatusLead.ABORDADO,
        StatusLead.RESPONDIDO,
        StatusLead.CONVERTIDO,
    ]
    for de, para in zip(fluxo, fluxo[1:], strict=False):
        lead_state.validar(de, para)


def test_lead_nao_pula_etapas() -> None:
    with pytest.raises(TransicaoInvalida):
        lead_state.validar(StatusLead.DESCOBERTO, StatusLead.ABORDADO)


def test_opt_out_e_terminal_e_irreversivel() -> None:
    assert lead_state.eh_terminal(StatusLead.OPT_OUT)
    for destino in StatusLead:
        assert not lead_state.pode_transicionar(StatusLead.OPT_OUT, destino)


def test_opt_out_alcancavel_de_qualquer_estado_ativo() -> None:
    ativos = [
        StatusLead.DESCOBERTO,
        StatusLead.QUALIFICADO,
        StatusLead.ENFILEIRADO,
        StatusLead.ABORDADO,
        StatusLead.RESPONDIDO,
        StatusLead.CONVERTIDO,
    ]
    for estado in ativos:
        assert lead_state.pode_transicionar(estado, StatusLead.OPT_OUT)


def test_campanha_nao_pula_para_executando() -> None:
    with pytest.raises(TransicaoInvalida):
        campaign_state.validar(StatusCampanha.RASCUNHO, StatusCampanha.EXECUTANDO)


def test_campanha_concluida_pode_iniciar_nova_rodada() -> None:
    campaign_state.validar(StatusCampanha.CONCLUIDA, StatusCampanha.DESCOBRINDO)
    campaign_state.validar(StatusCampanha.PRONTA, StatusCampanha.DESCOBRINDO)


def test_autonomia_define_onde_a_mensagem_nasce() -> None:
    assert (
        subscription_state.status_inicial_mensagem(NivelAutonomia.ASSISTIDO)
        is StatusMensagem.AGUARDANDO_APROVACAO
    )
    assert (
        subscription_state.status_inicial_mensagem(NivelAutonomia.AUTOMATICO)
        is StatusMensagem.APROVADA
    )


def test_troca_de_autonomia_e_transicao_validada() -> None:
    subscription_state.validar_autonomia(NivelAutonomia.ASSISTIDO, NivelAutonomia.AUTOMATICO)
    with pytest.raises(TransicaoInvalida):
        subscription_state.validar_autonomia(NivelAutonomia.ASSISTIDO, NivelAutonomia.ASSISTIDO)
