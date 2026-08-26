"""Configuracao central.

REGRA DE OURO: nenhuma chave e necessaria nas Fases 0-6. Todo provedor tem um
modo (`mock` | `real`); o default global e `mock`. Os campos `*_MODE` vazios
herdam o `PROVIDER_MODE`.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["mock", "real"]


class Provider(StrEnum):
    """Provedores externos. Cada um tem porta, mock e (Fase 7) adaptador real."""

    PLACES = "places"
    LLM = "llm"
    SEARCH = "search"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    ENRICHMENT = "enrichment"  # Receita Federal: dado aberto, SEM chave
    BILLING = "billing"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App -----------------------------------------------------------------
    app_name: str = "Prospector AI"
    app_env: str = "dev"
    debug: bool = True
    api_prefix: str = "/v1"

    # --- Infra ---------------------------------------------------------------
    # Default SQLite permite rodar testes e o stub sem Docker. O compose injeta
    # a URL do Postgres+pgvector.
    database_url: str = "sqlite+pysqlite:///./prospector.db"
    redis_url: str = ""  # vazio => fila inline (executa na hora, sem Redis)
    app_secret: str = "dev-app-secret-trocar-em-producao"
    jwt_secret: str = "dev-jwt-secret-trocar-em-producao"

    # --- Selecao de provedores ----------------------------------------------
    provider_mode: Mode = "mock"
    places_mode: Mode | None = None
    llm_mode: Mode | None = None
    search_mode: Mode | None = None
    email_mode: Mode | None = None
    whatsapp_mode: Mode | None = None
    billing_mode: Mode | None = None

    # --- Chaves reais (vazias ate a Fase 7) ----------------------------------
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_maps_api_key: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = ""
    ses_from_email: str = ""
    whatsapp_bsp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_business_id: str = ""
    stripe_secret_key: str = ""

    # --- Dados abertos / artefatos ------------------------------------------
    receita_dataset_path: str = "data/receita/cnpj_sample.csv"
    fixtures_path: str = "data/fixtures"
    outbox_dir: str = "outbox"

    # --- Financeiro ----------------------------------------------------------
    # Provedores cobram em USD; o cliente paga em BRL. Atualizar em producao.
    usd_brl: float = 5.40

    # --- Modelos / embeddings ------------------------------------------------
    llm_model: str = "claude-opus-5"
    embedding_dim: int = 384

    # --- HTTP ----------------------------------------------------------------
    http_timeout_seconds: float = 20.0
    http_max_retries: int = 3
    http_backoff_base_seconds: float = 0.25
    http_backoff_max_seconds: float = 8.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: float = 30.0

    # --- Guardrails de compliance -------------------------------------------
    b2b_only: bool = True
    # Retencao (Fase 4). Lead sem interacao expira; mensagem tem corpo expurgado.
    retencao_leads_dias: int = 180
    retencao_mensagens_dias: int = 365
    url_publica: str = "https://app.prospector.local"
    encarregado_email: str = "privacidade@prospector.local"
    whatsapp_template_enabled: bool = False
    seed_on_start: bool = True

    # --- Limites de envio (Fase 3 refina) -----------------------------------
    max_envios_por_campanha_dia: int = 200
    max_envios_por_usuario_dia: int = 500

    @field_validator(
        "places_mode", "llm_mode", "search_mode", "email_mode", "whatsapp_mode",
        "billing_mode", mode="before",
    )
    @classmethod
    def _empty_string_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("database_url", "redis_url", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    # --- Resolucao de modo ---------------------------------------------------
    def mode_for(self, provider: Provider | str) -> Mode:
        """Modo efetivo do provedor: especifico se definido, senao o global."""
        provider = Provider(provider)
        if provider is Provider.ENRICHMENT:
            # Receita Federal e dado aberto: sempre o dataset local, sem chave.
            return "mock"
        especifico: Mode | None = getattr(self, f"{provider.value}_mode", None)
        return especifico or self.provider_mode

    def modes(self) -> dict[str, str]:
        return {p.value: self.mode_for(p) for p in Provider}

    def is_all_mock(self) -> bool:
        return all(m == "mock" for m in self.modes().values())

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def base_dir(self) -> Path:
        """Raiz do backend (onde vive o pacote app/)."""
        return Path(__file__).resolve().parents[2]

    def resolve_path(self, caminho: str | Path) -> Path:
        """Resolve caminhos de dados sem depender do diretorio de execucao.

        Procura em: cwd -> backend/ -> raiz do repo. Isso faz o mesmo codigo
        funcionar em `python -m app...`, em pytest e dentro do container.
        """
        p = Path(caminho)
        if p.is_absolute():
            return p
        for base in (Path.cwd(), self.base_dir, self.base_dir.parent):
            candidato = base / p
            if candidato.exists():
                return candidato
        return Path.cwd() / p

    @property
    def outbox_path(self) -> Path:
        p = Path(self.outbox_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
