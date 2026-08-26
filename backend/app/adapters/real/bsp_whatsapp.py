"""BSPAdapter — WhatsAppPort real (Meta Cloud API). FASE 7, implementado.

GUARDRAILS, que aqui sao codigo e nao recomendacao:
  * template so sai com WHATSAPP_TEMPLATE_ENABLED=true;
  * mensagem de texto livre so vale dentro da janela de 24h aberta pelo
    contato — ou seja, INBOUND. Fora dela, a Meta exige template aprovado;
  * disparo frio para pessoa fisica nao esta implementado e nao deve ser.

Endpoint: POST https://graph.facebook.com/v21.0/{phone_id}/messages
"""

from __future__ import annotations

import re

from app.core.config import Settings, get_settings
from app.core.errors import BloqueadoPorCompliance, ProviderNotConfigured
from app.core.http_client import HttpClient
from app.core.logging import get_logger
from app.ports.dto import SendResult, WhatsAppMessage
from app.services.cost import CostRecorder, CostSpec

log = get_logger("whatsapp_bsp")

VERSAO_API = "v21.0"
BASE_URL = f"https://graph.facebook.com/{VERSAO_API}"


class BSPAdapter:
    provedor = "whatsapp"
    modo = "real"

    def __init__(
        self,
        http: HttpClient | None = None,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http
        self.cost = cost
        if not (self.settings.whatsapp_bsp_token and self.settings.whatsapp_phone_id):
            raise ProviderNotConfigured(
                "WHATSAPP_BSP_TOKEN / WHATSAPP_PHONE_ID vazios. "
                "Preencha o .env antes de WHATSAPP_MODE=real."
            )

    def enviar(self, mensagem: WhatsAppMessage) -> SendResult:
        if mensagem.template and not self.settings.whatsapp_template_enabled:
            raise BloqueadoPorCompliance(
                "Template de WhatsApp desabilitado. Ative WHATSAPP_TEMPLATE_ENABLED "
                "explicitamente e confirme que o destino e pessoa juridica."
            )

        destino = _normalizar(mensagem.para)
        if not destino:
            return SendResult(sucesso=False, erro="Telefone invalido", modo=self.modo)

        if mensagem.template:
            corpo = {
                "messaging_product": "whatsapp",
                "to": destino,
                "type": "template",
                "template": {
                    "name": mensagem.template,
                    "language": {"code": "pt_BR"},
                    "components": (
                        [
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": p} for p in mensagem.parametros
                                ],
                            }
                        ]
                        if mensagem.parametros
                        else []
                    ),
                },
            }
            chave_preco = "whatsapp.template.utility"
        else:
            # Texto livre: so entrega dentro da janela de 24h (conversa iniciada
            # pelo contato). A Meta recusa fora dela — e isso e desejado.
            corpo = {
                "messaging_product": "whatsapp",
                "to": destino,
                "type": "text",
                "text": {"body": mensagem.corpo or ""},
            }
            chave_preco = "whatsapp.template.utility"

        try:
            resposta = self.http.request(
                "POST",
                f"{BASE_URL}/{self.settings.whatsapp_phone_id}/messages",
                headers={
                    "Authorization": f"Bearer {self.settings.whatsapp_bsp_token}",
                    "Content-Type": "application/json",
                },
                json=corpo,
                operacao="send",
                idempotency_key=mensagem.idempotency_key,
                custo=CostSpec(
                    provedor=self.provedor,
                    operacao="send",
                    chave_preco=chave_preco,
                    quantidade=1,
                    metadados={"para": destino, "template": mensagem.template},
                ),
            )
        except Exception as exc:
            log.error("whatsapp_falhou", para=destino, erro=str(exc)[:200])
            return SendResult(sucesso=False, erro=str(exc)[:500], modo=self.modo)

        dados = resposta.json or {}
        ids = dados.get("messages") or []
        provider_id = ids[0].get("id") if ids else None
        log.info("whatsapp_enviado", para=destino, provider_message_id=provider_id)
        return SendResult(sucesso=True, provider_message_id=provider_id, modo=self.modo)


def _normalizar(telefone: str | None) -> str | None:
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return None
    if not digitos.startswith("55") and len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos if len(digitos) >= 12 else None
