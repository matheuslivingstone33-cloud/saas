"""Contexto compartilhado por todos os adaptadores.

Guarda o que todo provedor precisa: settings, cliente HTTP central e o
registrador de custo. Adaptadores NUNCA criam httpx.Client por conta propria.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.core.http_client import HttpClient
    from app.services.cost import CostRecorder


class Adapter(Protocol):
    """Todo adaptador declara seu provedor e seu modo."""

    provedor: str
    modo: str


@dataclass(slots=True)
class ProviderContext:
    settings: Settings
    cost: CostRecorder
    http: HttpClient | None = None
    user_id: object | None = None
    campaign_id: object | None = None
