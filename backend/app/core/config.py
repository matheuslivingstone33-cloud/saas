"""Configuracao central.

REGRA DE OURO: nenhuma chave e necessaria nas Fases 0-6. Todo provedor tem um
modo (`mock` | `real`); o default global e `mock`. Os campos `*_MODE` vazios
herdam o `PROVIDER_MODE`.
"""

from __future__ import annotations

import os
import tempfile
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
    #: HMAC dos webhooks de entrada. VAZIO fecha a rota — ver services/webhook.py.
    webhook_secret: str = ""

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
    #: Origens que podem chamar a API pelo navegador, separadas por virgula.
    #: Vazio = o padrao de `origens_cors()`. Ver o metodo para o porque.
    cors_origins: str = ""
    whatsapp_template_enabled: bool = False
    seed_on_start: bool = True

    # --- Acesso --------------------------------------------------------------
    #: E-mails de quem opera o SaaS, separados por virgula. So eles veem a
    #: visao de todos os clientes (margem consolidada). Vazio = ninguem: o
    #: sistema nao tem papel de administrador no banco, e um padrao que
    #: liberasse para "qualquer logado" foi exatamente a brecha fechada aqui.
    admin_emails: str = ""
    #: Tentativas de senha erradas por e-mail antes de travar, e a janela.
    login_max_falhas: int = 5
    login_janela_minutos: int = 15
    #: Teto por IP, para quem testa uma senha em muitas contas.
    login_max_falhas_por_ip: int = 30
    #: Cadastros por IP numa hora. Cada conta nova ganha creditos: sem teto,
    #: criar contas em serie vira fonte de credito gratis.
    cadastro_max_por_ip_hora: int = 5
    #: Registros de acesso (IP + data/hora). O Marco Civil (art. 15) manda o
    #: provedor de aplicacao guardar por 6 meses; depois disso, apagar.
    retencao_registros_acesso_dias: int = 180

    # --- Limites de envio (Fase 3 refina) -----------------------------------
    max_envios_por_campanha_dia: int = 200
    max_envios_por_usuario_dia: int = 500

    # --- Cadencia (Motor 5) --------------------------------------------------
    # Tres toques: D0 (o insight), D+3 (a prova), D+7 (a saida). Os dias sao
    # contados a partir do ULTIMO envio, nao do primeiro: se um toque atrasou,
    # o proximo atrasa junto em vez de sair colado nele.
    cadencia_ativa: bool = True
    cadencia_max_toques: int = 3
    cadencia_dias_para_toque2: int = 3
    cadencia_dias_para_toque3: int = 4

    # --- Entregabilidade -----------------------------------------------------
    # Acima desta taxa de retorno a campanha PAUSA. Dominio queimado nao volta,
    # e leva junto o e-mail que o cliente usa para faturar.
    bounce_taxa_maxima: float = 0.02
    # Abaixo desta amostra a taxa nao significa nada: 1 bounce em 3 envios e
    # 33%, e nao diz nada sobre reputacao.
    bounce_amostra_minima: int = 20

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

    @field_validator("database_url", mode="after")
    @classmethod
    def _driver_do_postgres(cls, v: str) -> str:
        """`postgres://` e `postgresql://` passam a usar o psycopg 3.

        E o formato que o Neon (e quase todo Postgres gerenciado) entrega. Sem
        o `+psycopg`, o SQLAlchemy procura o psycopg2, que nao esta instalado,
        e a API cai na primeira consulta com um erro que nao fala de URL.
        """
        for prefixo in ("postgres://", "postgresql://"):
            if v.startswith(prefixo):
                return "postgresql+psycopg://" + v[len(prefixo):]
        return v

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

    def origens_cors(self) -> list[str]:
        """Quem pode chamar esta API pelo navegador.

        A lista era fixa em `localhost:5173` — a porta do Vite. Funcionava em
        desenvolvimento e quebrava em producao, onde o frontend e servido por
        nginx em outra porta: o cadastro morria com `TypeError: Failed to
        fetch`, que nao diz nada sobre CORS a quem esta olhando a tela.

        `CORS_ORIGINS` explicito ganha de tudo — e o unico jeito de cobrir
        cenarios que nao dao para adivinhar, como acesso por tunel SSH. Sem
        ele, o padrao segue o ambiente: em dev, o Vite; em producao, a origem
        publica do proprio frontend.
        """
        if self.cors_origins.strip():
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.app_env in {"dev", "test"}:
            return ["http://localhost:5173", "http://127.0.0.1:5173"]
        return [self.url_publica.rstrip("/")] if self.url_publica else []

    @property
    def em_producao(self) -> bool:
        """Qualquer ambiente que nao seja o de desenvolvimento ou o da suite."""
        return self.app_env not in {"dev", "test"}

    @property
    def sem_servidor(self) -> bool:
        """Rodando como funcao do Vercel: disco so de leitura, sem processo fixo."""
        return bool(os.environ.get("VERCEL"))

    def e_admin(self, email: str | None) -> bool:
        if not email:
            return False
        admins = {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}
        return email.strip().lower() in admins

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
        """Onde o e-mail simulado e gravado.

        No Vercel o disco do projeto e so de leitura: sem o desvio para a pasta
        temporaria, o primeiro envio simulado derrubaria a requisicao.
        """
        p = Path(self.outbox_dir)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            p = Path(tempfile.gettempdir()) / "outbox"
            p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
