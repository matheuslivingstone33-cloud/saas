"""FakeEmail — mock do EmailPort. Grava em outbox/ em vez de enviar.

Nada sai de verdade nas Fases 0-6. Cada mensagem vira um arquivo .eml.json em
`settings.outbox_dir`, com o mesmo payload que o SESAdapter enviaria.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.mock._text import slug
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ports.dto import EmailMessage, SendResult
from app.services.cost import CostRecorder, CostSpec

log = get_logger("fake_email")


class FakeEmail:
    provedor = "email"
    modo = "mock"

    def __init__(
        self,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
        outbox: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.cost = cost
        self.outbox = outbox or self.settings.outbox_path
        self.outbox.mkdir(parents=True, exist_ok=True)

    def enviar(self, mensagem: EmailMessage) -> SendResult:
        agora = datetime.now(UTC)
        mid = mensagem.idempotency_key or f"{agora.timestamp():.0f}-{slug(mensagem.para, 24)}"
        caminho = self.outbox / f"{agora:%Y%m%dT%H%M%S}-{slug(mensagem.para, 24)}-{mid[:8]}.json"

        payload = {
            "modo": "mock",
            "gravado_em": agora.isoformat(),
            "de": mensagem.de or "nao-responda@prospector.local",
            "para": mensagem.para,
            "responder_para": mensagem.responder_para,
            "assunto": mensagem.assunto,
            "corpo_texto": mensagem.corpo_texto,
            "corpo_html": mensagem.corpo_html,
            "headers": mensagem.headers,
            "idempotency_key": mensagem.idempotency_key,
        }
        caminho.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if self.cost is not None:
            self.cost.registrar(
                CostSpec(
                    provedor=self.provedor,
                    operacao="send",
                    chave_preco="email.ses.send",
                    quantidade=1,
                    metadados={"para": mensagem.para, "arquivo": caminho.name},
                ),
                modo=self.modo,
            )

        log.info("email_gravado_outbox", para=mensagem.para, arquivo=str(caminho))
        return SendResult(
            sucesso=True,
            provider_message_id=f"mock-{mid}",
            modo=self.modo,
            detalhes={"arquivo": str(caminho)},
        )
