"""Excecoes de dominio e de infraestrutura."""

from __future__ import annotations


class ProspectorError(Exception):
    """Base de todos os erros da aplicacao."""


# --- Provedores --------------------------------------------------------------
class ProviderError(ProspectorError):
    pass


class ProviderNotConfigured(ProviderError):
    """Adaptador real acionado sem as chaves necessarias (ou ainda nao escrito)."""


class NetworkDisabledInMockMode(ProviderError):
    """Tentativa de tocar a rede com o provedor em modo mock.

    Isso e um guardrail: nas Fases 0-6 nenhuma requisicao real pode sair.
    """


class RateLimited(ProviderError):
    pass


class CircuitOpen(ProviderError):
    """Circuit breaker aberto para o provedor."""


class UpstreamError(ProviderError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# --- Dominio -----------------------------------------------------------------
class DomainError(ProspectorError):
    pass


class TransicaoInvalida(DomainError):
    def __init__(self, entidade: str, de: str, para: str) -> None:
        super().__init__(f"Transicao invalida em {entidade}: {de} -> {para}")
        self.entidade = entidade
        self.de = de
        self.para = para


class SaldoInsuficiente(DomainError):
    pass


class BloqueadoPorCompliance(DomainError):
    """Envio barrado por opt-out, guardrail B2B ou canal proibido."""


class NaoEncontrado(DomainError):
    pass
