"""FakeWhatsApp — mock do WhatsAppPort. Grava em outbox/whatsapp/.

GUARDRAILS aplicados aqui e repetidos no SendService (defesa em profundidade):
  * template ativo so com settings.whatsapp_template_enabled = True;
  * disparo frio para pessoa fisica e recusado — o canal preferencial e INBOUND.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.mock._text import slug, telefone_normalizado
from app.core.config import Settings, get_settings
from app.core.errors import BloqueadoPorCompliance
from app.core.logging import get_logger
from app.ports.dto import SendResult, WhatsAppMessage
from app.services.cost import CostRecorder, CostSpec

log = get_logger("fake_whatsapp")


class FakeWhatsApp:
    provedor = "whatsapp"
    modo = "mock"

    def __init__(
        self,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
        outbox: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.cost = cost
        base = outbox or self.settings.outbox_path
        self.outbox = base / "whatsapp"
        self.outbox.mkdir(parents=True, exist_ok=True)

    def enviar(self, mensagem: WhatsAppMessage) -> SendResult:
        if mensagem.template and not self.settings.whatsapp_template_enabled:
            raise BloqueadoPorCompliance(
                "Template de WhatsApp desabilitado. Ative WHATSAPP_TEMPLATE_ENABLED "
                "explicitamente e confirme que o destino e pessoa juridica."
            )

        destino = telefone_normalizado(mensagem.para)
        if not destino:
            return SendResult(sucesso=False, erro="Telefone invalido", modo=self.modo)

        agora = datetime.now(UTC)
        caminho = self.outbox / f"{agora:%Y%m%dT%H%M%S}-{slug(destino, 20)}.json"
        payload = {
            "modo": "mock",
            "gravado_em": agora.isoformat(),
            "para": destino,
            "template": mensagem.template,
            "parametros": mensagem.parametros,
            "corpo": mensagem.corpo,
            "idempotency_key": mensagem.idempotency_key,
        }
        caminho.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if self.cost is not None:
            chave = (
                "whatsapp.template.utility" if mensagem.template else "whatsapp.template.marketing"
            )
            self.cost.registrar(
                CostSpec(
                    provedor=self.provedor,
                    operacao="send",
                    chave_preco=chave,
                    quantidade=1,
                    metadados={"para": destino, "arquivo": caminho.name},
                ),
                modo=self.modo,
            )

        log.info("whatsapp_gravado_outbox", para=destino, arquivo=str(caminho))
        return SendResult(
            sucesso=True,
            provider_message_id=f"mock-wa-{caminho.stem}",
            modo=self.modo,
            detalhes={"arquivo": str(caminho)},
        )
