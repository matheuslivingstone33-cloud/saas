"""Assinatura dos webhooks de entrada (`/v1/inbound/*`).

Ate a Etapa 7 essas rotas aceitavam qualquer requisicao. Isso era ruim desde
sempre — qualquer pessoa registrava uma "resposta" de qualquer lead e sujava a
thread — e ficou pior com o aprendizado por intencao: uma resposta forjada
**move a mira** daquele cliente, empurrando o Cerebro para longe de um ramo bom
sem que nada em tela pareca errado.

O esquema e o mesmo que Stripe, SES e a maioria dos provedores usam:

    X-Assinatura-Timestamp: 1756668000
    X-Assinatura: sha256=<hex do HMAC de "<timestamp>.<corpo cru>">

Tres propriedades, e cada uma existe por um motivo:

  * **HMAC sobre o corpo CRU.** Assinar o JSON reserializado compararia uma
    coisa e processaria outra: `{"a":1}` e `{"a": 1}` sao o mesmo objeto e
    assinaturas diferentes.
  * **Timestamp dentro do que se assina.** Sem ele, capturar uma requisicao
    valida e reenviar mil vezes continua valido para sempre.
  * **Comparacao em tempo constante.** Comparar com `==` vaza o prefixo
    correto pelo tempo de resposta, e um atacante descobre a assinatura byte a
    byte.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger("webhook")

PREFIXO = "sha256="
#: Janela de aceite. Cinco minutos cobre relogio dessincronizado e retentativa
#: do provedor sem deixar uma captura util por muito tempo.
TOLERANCIA_SEGUNDOS = 300


class AssinaturaInvalida(Exception):
    """Assinatura ausente, malformada, vencida ou que nao confere."""


def assinar(corpo: bytes, *, timestamp: int, segredo: str) -> str:
    """Gera o valor do header. Usado pelos testes e pelo simulador local."""
    mensagem = f"{timestamp}.".encode() + corpo
    digest = hmac.new(segredo.encode(), mensagem, hashlib.sha256).hexdigest()
    return f"{PREFIXO}{digest}"


def conferir_assinatura(
    corpo: bytes,
    *,
    assinatura: str | None,
    timestamp: str | None,
    settings: Settings | None = None,
    agora: int | None = None,
) -> None:
    """Levanta `AssinaturaInvalida` se a requisicao nao for do provedor."""
    s = settings or get_settings()
    segredo = s.webhook_secret

    if not segredo:
        # Sem segredo configurado a rota fica FECHADA, nao aberta. Um webhook
        # que "funciona" porque ninguem definiu a chave e o pior dos mundos:
        # parece configurado e aceita o mundo inteiro.
        raise AssinaturaInvalida(
            "Webhook sem WEBHOOK_SECRET configurado no servidor; entrada recusada."
        )
    if not assinatura or not timestamp:
        raise AssinaturaInvalida("Faltam os cabecalhos X-Assinatura e X-Assinatura-Timestamp.")

    try:
        enviado_em = int(timestamp)
    except ValueError as erro:
        raise AssinaturaInvalida("X-Assinatura-Timestamp nao e um numero.") from erro

    distancia = abs((agora if agora is not None else int(time.time())) - enviado_em)
    if distancia > TOLERANCIA_SEGUNDOS:
        raise AssinaturaInvalida(
            f"Requisicao fora da janela de {TOLERANCIA_SEGUNDOS}s (diferenca de {distancia}s)."
        )

    esperada = assinar(corpo, timestamp=enviado_em, segredo=segredo)
    if not hmac.compare_digest(esperada, assinatura.strip()):
        log.warning("webhook_assinatura_invalida", bytes_corpo=len(corpo))
        raise AssinaturaInvalida("Assinatura invalida.")
