"""A interface compilada e a API convivem no mesmo processo.

Servir o `frontend/dist` pelo backend derruba o consumo de memoria (um
processo em vez de dois, sem Node nem esbuild) e elimina CORS. O risco de
fazer isso e o coringa de SPA engolir rota de API: um erro de digitacao em
`/v1/...` passaria a devolver o HTML do app com status 200, e o cliente
receberia uma pagina onde esperava JSON — falha silenciosa, a pior especie.

Estes testes fixam a fronteira.
"""

from __future__ import annotations

import pytest

from app.api import estatico


@pytest.fixture
def interface_compilada() -> bool:
    """Ha build da interface? Sem ele, os testes de HTML nao fazem sentido."""
    return estatico.diretorio_da_interface() is not None


def test_api_responde_json_e_nao_html(client, usuario) -> None:
    """As rotas de API continuam devolvendo JSON, com ou sem interface."""
    for rota in ("/health", "/v1/providers"):
        r = client.get(rota)
        assert r.status_code == 200, rota
        assert r.headers["content-type"].startswith("application/json"), rota


def test_rota_de_api_inexistente_da_404_e_nao_o_app(client, usuario) -> None:
    """O coringa NAO pode capturar `/v1/...`.

    Se capturasse, um endpoint errado devolveria a pagina do app com 200 e o
    erro passaria despercebido ate muito depois.
    """
    r = client.get("/v1/rota-que-nao-existe")
    assert r.status_code == 404
    assert "text/html" not in r.headers.get("content-type", "")


@pytest.mark.parametrize("reservado", ["v1", "health", "docs", "openapi.json"])
def test_prefixos_reservados_nunca_viram_pagina(reservado: str) -> None:
    """A lista de reservados protege todo prefixo que pertence a API."""
    assert reservado in estatico.RESERVADOS


def test_raiz_serve_o_app_quando_compilado(client, usuario, interface_compilada) -> None:
    if not interface_compilada:
        pytest.skip("frontend/dist ausente — rode `npm run build`")
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<div id=\"root\">" in r.text


def test_rota_do_spa_devolve_o_app(client, usuario, interface_compilada) -> None:
    """Recarregar em /campanhas tem que abrir o app, nao dar 404."""
    if not interface_compilada:
        pytest.skip("frontend/dist ausente — rode `npm run build`")
    r = client.get("/campanhas")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


def test_index_nao_e_cacheado(client, usuario, interface_compilada) -> None:
    """O index aponta para os arquivos com hash; se ficar em cache, o navegador
    continua pedindo a versao antiga depois de um build novo."""
    if not interface_compilada:
        pytest.skip("frontend/dist ausente — rode `npm run build`")
    r = client.get("/")
    assert "no-store" in r.headers.get("cache-control", "")


def test_raiz_sem_build_devolve_recepcao_da_api(client, usuario, monkeypatch) -> None:
    """Sem `dist`, a raiz volta a ser o mapa da API — nunca 404 seco."""
    monkeypatch.setattr(estatico, "diretorio_da_interface", lambda: None)
    r = client.get("/")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["documentacao"] == "/docs"
    assert "tudo_mock" in corpo
