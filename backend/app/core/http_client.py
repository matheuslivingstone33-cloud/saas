"""Cliente HTTP central. TODA chamada externa passa por aqui.

Responsabilidades:
  * timeout por requisicao;
  * retry com backoff exponencial + jitter (so em erro transitorio);
  * rate limiting por provedor (token bucket);
  * circuit breaker por provedor;
  * emissao de cost_event a cada chamada;
  * log estruturado (request_id, latencia, custo);
  * idempotencia (chave repassada ao provedor quando ele suporta).

GUARDRAIL: em modo mock o cliente NAO TOCA A REDE. Qualquer tentativa levanta
NetworkDisabledInMockMode. E assim que garantimos que as Fases 0-6 nao fazem
nenhuma requisicao real.
"""

from __future__ import annotations

import random
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import (
    CircuitOpen,
    NetworkDisabledInMockMode,
    RateLimited,
    UpstreamError,
)
from app.core.ids import request_id as gen_request_id
from app.core.logging import get_logger
from app.services.cost import CostRecorder, CostSpec

log = get_logger("http")

STATUS_RETRIAVEIS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


@dataclass(slots=True)
class RateLimiter:
    """Token bucket simples, por provedor."""

    capacidade: float
    por_segundo: float
    _tokens: float = field(init=False)
    _ultimo: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = self.capacidade
        self._ultimo = time.monotonic()

    def adquirir(self, agora: float | None = None) -> float:
        """Devolve quantos segundos e preciso esperar (0 = pode seguir)."""
        agora = agora if agora is not None else time.monotonic()
        decorrido = max(0.0, agora - self._ultimo)
        self._ultimo = agora
        self._tokens = min(self.capacidade, self._tokens + decorrido * self.por_segundo)
        if self._tokens >= 1:
            self._tokens -= 1
            return 0.0
        return (1 - self._tokens) / self.por_segundo


class CircuitBreaker:
    """Fecha o acesso ao provedor apos N falhas seguidas."""

    def __init__(self, limite: int, reset_segundos: float) -> None:
        self.limite = limite
        self.reset_segundos = reset_segundos
        self.falhas = 0
        self.aberto_ate: float | None = None

    @property
    def estado(self) -> str:
        if self.aberto_ate is None:
            return "fechado"
        return "aberto" if time.monotonic() < self.aberto_ate else "meio_aberto"

    def checar(self) -> None:
        if self.estado == "aberto":
            raise CircuitOpen("Circuito aberto para o provedor; tente novamente mais tarde.")

    def sucesso(self) -> None:
        self.falhas = 0
        self.aberto_ate = None

    def falha(self) -> None:
        self.falhas += 1
        if self.falhas >= self.limite:
            self.aberto_ate = time.monotonic() + self.reset_segundos


@dataclass(slots=True)
class HttpResponse:
    status_code: int
    json: Any
    headers: dict[str, str]
    latencia_ms: int
    request_id: str


# Limites conservadores por provedor (revisar na Fase 7 com a cota real).
LIMITES_PADRAO: dict[str, tuple[float, float]] = {
    "places": (10, 5),
    "llm": (5, 2),
    "search": (3, 1),
    "email": (14, 14),
    "whatsapp": (10, 5),
    "billing": (5, 2),
}


class HttpClient:
    """Um cliente por provedor. Criado pelo registry, nunca no meio do dominio."""

    def __init__(
        self,
        provedor: str,
        *,
        modo: str = "mock",
        settings: Settings | None = None,
        cost: CostRecorder | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,  # noqa: ANN001 - injetavel nos testes
    ) -> None:
        self.provedor = provedor
        self.modo = modo
        self.settings = settings or get_settings()
        self.cost = cost
        self._sleep = sleep
        cap, taxa = LIMITES_PADRAO.get(provedor, (5, 2))
        self.limiter = RateLimiter(cap, taxa)
        self.breaker = CircuitBreaker(
            self.settings.circuit_breaker_threshold, self.settings.circuit_breaker_reset_seconds
        )
        self._transport = transport
        self._client: httpx.Client | None = None

    # -- ciclo de vida --------------------------------------------------------
    @property
    def client(self) -> httpx.Client:
        if self.modo != "real":
            raise NetworkDisabledInMockMode(
                f"Provedor {self.provedor!r} esta em modo {self.modo!r}: rede desabilitada."
            )
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.settings.http_timeout_seconds, transport=self._transport
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # -- guarda para chamadas que NAO passam por request() --------------------
    @contextmanager
    def guard(
        self,
        operacao: str,
        custo: CostSpec | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> Iterator[str]:
        """Aplica rate limit, circuit breaker, log e custo em torno de um SDK.

        Alguns provedores tem SDK oficial que vale usar (Anthropic, AWS, Stripe).
        Em vez de reimplementar o cliente deles, embrulhamos a chamada aqui:
        assim continua valendo a regra de que TODA chamada externa passa pelo
        HttpClient central — inclusive as que ele nao executa diretamente.

            with portas.http(Provider.LLM).guard("mensagem", custo) as rid:
                resposta = client.messages.create(...)
        """
        if self.modo != "real":
            raise NetworkDisabledInMockMode(
                f"Chamada bloqueada: {self.provedor} esta em modo {self.modo}."
            )
        self.breaker.checar()
        espera = self.limiter.adquirir()
        if espera > 0:
            self._sleep(espera)

        rid = idempotency_key or gen_request_id()
        inicio = time.monotonic()
        try:
            yield rid
        except Exception as exc:
            self.breaker.falha()
            latencia = int((time.monotonic() - inicio) * 1000)
            log.error(
                "sdk_falhou",
                provedor=self.provedor,
                operacao=operacao,
                erro=str(exc)[:300],
                latencia_ms=latencia,
                request_id=rid,
            )
            self._registrar_custo(custo, rid, latencia, operacao, sucesso=False)
            raise
        else:
            self.breaker.sucesso()
            latencia = int((time.monotonic() - inicio) * 1000)
            log.info(
                "sdk_ok",
                provedor=self.provedor,
                operacao=operacao,
                latencia_ms=latencia,
                request_id=rid,
            )
            self._registrar_custo(custo, rid, latencia, operacao, sucesso=True)

    # -- requisicao -----------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        custo: CostSpec | None = None,
        idempotency_key: str | None = None,
        operacao: str | None = None,
    ) -> HttpResponse:
        if self.modo != "real":
            raise NetworkDisabledInMockMode(
                f"Chamada bloqueada: {self.provedor} esta em modo {self.modo}. "
                "Use o adaptador mock ou vire o flag para real (Fase 7)."
            )

        self.breaker.checar()
        rid = gen_request_id()
        headers = dict(headers or {})
        if idempotency_key:
            headers.setdefault("Idempotency-Key", idempotency_key)
        headers.setdefault("X-Request-Id", rid)

        espera = self.limiter.adquirir()
        if espera > 0:
            log.info("rate_limit_espera", provedor=self.provedor, segundos=round(espera, 3))
            self._sleep(espera)

        tentativa = 0
        inicio_total = time.monotonic()
        ultimo_erro: Exception | None = None

        while tentativa <= self.settings.http_max_retries:
            tentativa += 1
            inicio = time.monotonic()
            try:
                resp = self.client.request(method, url, headers=headers, json=json, params=params)
                latencia_ms = int((time.monotonic() - inicio) * 1000)

                if resp.status_code in STATUS_RETRIAVEIS:
                    ultimo_erro = UpstreamError(
                        f"{self.provedor} respondeu {resp.status_code}", resp.status_code
                    )
                    log.warning(
                        "http_retriavel",
                        provedor=self.provedor,
                        status=resp.status_code,
                        tentativa=tentativa,
                        request_id=rid,
                    )
                    if tentativa > self.settings.http_max_retries:
                        break
                    self._sleep(self._backoff(tentativa, resp.headers.get("Retry-After")))
                    continue

                if resp.status_code >= 400:
                    self.breaker.falha()
                    self._registrar_custo(custo, rid, latencia_ms, operacao, sucesso=False)
                    raise UpstreamError(
                        f"{self.provedor} respondeu {resp.status_code}: {resp.text[:300]}",
                        resp.status_code,
                    )

                self.breaker.sucesso()
                corpo = resp.json() if resp.content else None
                self._registrar_custo(custo, rid, latencia_ms, operacao, sucesso=True)
                log.info(
                    "http_ok",
                    provedor=self.provedor,
                    status=resp.status_code,
                    latencia_ms=latencia_ms,
                    tentativa=tentativa,
                    request_id=rid,
                )
                return HttpResponse(resp.status_code, corpo, dict(resp.headers), latencia_ms, rid)

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                ultimo_erro = exc
                log.warning(
                    "http_falha_transporte",
                    provedor=self.provedor,
                    erro=str(exc),
                    tentativa=tentativa,
                    request_id=rid,
                )
                if tentativa > self.settings.http_max_retries:
                    break
                self._sleep(self._backoff(tentativa, None))

        self.breaker.falha()
        total_ms = int((time.monotonic() - inicio_total) * 1000)
        log.error(
            "http_esgotou_tentativas",
            provedor=self.provedor,
            tentativas=tentativa,
            latencia_ms=total_ms,
            request_id=rid,
        )
        if isinstance(ultimo_erro, UpstreamError) and ultimo_erro.status_code == 429:
            raise RateLimited(str(ultimo_erro)) from ultimo_erro
        raise UpstreamError(
            f"Falha ao chamar {self.provedor} apos {tentativa} tentativas: {ultimo_erro}"
        ) from ultimo_erro

    # -- internos -------------------------------------------------------------
    def _backoff(self, tentativa: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.settings.http_backoff_max_seconds)
            except ValueError:
                pass
        base = self.settings.http_backoff_base_seconds * (2 ** (tentativa - 1))
        return min(base, self.settings.http_backoff_max_seconds) * (0.5 + random.random() / 2)

    def _registrar_custo(
        self,
        custo: CostSpec | None,
        rid: str,
        latencia_ms: int,
        operacao: str | None,
        *,
        sucesso: bool,
    ) -> None:
        if custo is None or self.cost is None:
            return
        if operacao:
            custo.operacao = operacao
        custo.metadados = {**(custo.metadados or {}), "sucesso": sucesso}
        self.cost.registrar(custo, modo=self.modo, request_id=rid, latencia_ms=latencia_ms)
