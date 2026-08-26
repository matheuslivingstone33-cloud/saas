"""HttpClient: retry, backoff, rate limit, circuit breaker e custo."""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import CircuitOpen, UpstreamError
from app.core.http_client import CircuitBreaker, HttpClient, RateLimiter
from app.services.cost import CostRecorder, CostSpec, MemoryCostSink


def _client(handler, sink=None, **kwargs) -> HttpClient:  # noqa: ANN001
    """Cliente em modo real, mas com transporte falso: continua sem tocar a rede."""
    return HttpClient(
        "places",
        modo="real",
        cost=CostRecorder(sink) if sink else None,
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
        **kwargs,
    )


def test_sucesso_registra_cost_event() -> None:
    sink = MemoryCostSink()
    client = _client(lambda _r: httpx.Response(200, json={"ok": True}), sink)
    resp = client.request(
        "POST",
        "https://places.googleapis.com/v1/places:searchText",
        custo=CostSpec(provedor="places", operacao="text_search", chave_preco="places.text_search"),
    )
    assert resp.status_code == 200
    assert resp.json == {"ok": True}
    assert len(sink.eventos) == 1
    assert sink.eventos[0].balde == 1  # dados
    assert sink.eventos[0].valor_micros == 32_000
    assert sink.eventos[0].modo == "real"


def test_retry_em_status_transitorio() -> None:
    tentativas = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        tentativas["n"] += 1
        if tentativas["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"tentativa": tentativas["n"]})

    resp = _client(handler).request("GET", "https://exemplo.local/x")
    assert tentativas["n"] == 3
    assert resp.json == {"tentativa": 3}


def test_erro_permanente_nao_faz_retry() -> None:
    tentativas = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        tentativas["n"] += 1
        return httpx.Response(400, json={"erro": "payload invalido"})

    with pytest.raises(UpstreamError) as exc:
        _client(handler).request("GET", "https://exemplo.local/x")
    assert tentativas["n"] == 1
    assert exc.value.status_code == 400


def test_idempotency_key_vai_no_header() -> None:
    vistos: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.update(dict(request.headers))
        return httpx.Response(200, json={})

    _client(handler).request("POST", "https://exemplo.local/x", idempotency_key="abc-123")
    assert vistos["idempotency-key"] == "abc-123"
    assert "x-request-id" in vistos


def test_rate_limiter_pede_espera_quando_estoura() -> None:
    limiter = RateLimiter(capacidade=2, por_segundo=1)
    assert limiter.adquirir(agora=0) == 0
    assert limiter.adquirir(agora=0) == 0
    assert limiter.adquirir(agora=0) > 0  # terceiro precisa esperar


def test_circuit_breaker_abre_e_bloqueia() -> None:
    breaker = CircuitBreaker(limite=2, reset_segundos=60)
    breaker.falha()
    breaker.checar()  # ainda fechado
    breaker.falha()
    assert breaker.estado == "aberto"
    with pytest.raises(CircuitOpen):
        breaker.checar()
    breaker.sucesso()
    assert breaker.estado == "fechado"


def test_timeout_esgota_tentativas() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("estourou")

    with pytest.raises(UpstreamError):
        _client(handler).request("GET", "https://exemplo.local/x")
