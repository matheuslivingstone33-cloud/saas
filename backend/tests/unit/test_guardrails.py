"""Guardrails nao-negociaveis. Se um destes quebrar, algo grave mudou."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import BloqueadoPorCompliance, NetworkDisabledInMockMode
from app.core.http_client import HttpClient
from app.ports.dto import WhatsAppMessage

REPO_RAIZ = Path(__file__).resolve().parents[3]


def test_modo_padrao_e_mock_em_todos_os_provedores(settings) -> None:
    assert settings.provider_mode == "mock"
    assert settings.is_all_mock()
    assert set(settings.modes().values()) == {"mock"}


def test_http_client_nao_toca_a_rede_em_modo_mock() -> None:
    client = HttpClient("places", modo="mock")
    with pytest.raises(NetworkDisabledInMockMode):
        client.request("GET", "https://places.googleapis.com/v1/places:searchText")
    with pytest.raises(NetworkDisabledInMockMode):
        _ = client.client


def test_registry_em_mock_nao_abre_cliente_http(portas) -> None:
    """Exercita as portas e garante que nenhum httpx.Client foi criado."""
    from app.ports.dto import PlacesQuery

    portas.llm.orquestrar_descoberta("ar condicionado", "Fortaleza, CE", {})
    portas.places.buscar(PlacesQuery(termo="supermercado", regiao="Fortaleza"))
    portas.enrichment.buscar("Boa Compra", uf="CE")
    assert portas._clients == {}


def test_whatsapp_template_bloqueado_por_padrao(portas) -> None:
    with pytest.raises(BloqueadoPorCompliance):
        portas.whatsapp.enviar(
            WhatsAppMessage(para="+5585999999999", template="abordagem_b2b", parametros=["x"])
        )


def test_env_example_nao_tem_chave_preenchida() -> None:
    """Nenhuma chave real pode estar commitada no .env.example."""
    conteudo = (REPO_RAIZ / ".env.example").read_text(encoding="utf-8")
    sensiveis = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_MAPS_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "WHATSAPP_BSP_TOKEN",
        "STRIPE_SECRET_KEY",
    ]
    for linha in conteudo.splitlines():
        nome, _, valor = linha.partition("=")
        if nome.strip() in sensiveis:
            assert valor.strip() == "", f"{nome} deveria estar vazio no .env.example"


def test_gitignore_bloqueia_env() -> None:
    conteudo = (REPO_RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in conteudo
    assert "!.env.example" in conteudo


def test_adaptadores_reais_estao_inertes_sem_chave(settings) -> None:
    """Sem chave, instanciar um adaptador real falha alto — nunca silenciosamente."""
    from app.adapters.real.anthropic_llm import AnthropicAdapter
    from app.adapters.real.google_places import GooglePlacesAdapter
    from app.core.errors import ProviderNotConfigured

    with pytest.raises(ProviderNotConfigured):
        GooglePlacesAdapter(HttpClient("places", modo="real"), None, settings)
    with pytest.raises(ProviderNotConfigured):
        AnthropicAdapter(HttpClient("llm", modo="real"), None, settings)
