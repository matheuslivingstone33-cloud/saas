"""SESAdapter — EmailPort real (AWS SES v2). FASE 7, implementado.

Usa boto3 (SDK oficial) dentro do `guard()` do HttpClient, entao rate limit,
circuit breaker e cost_event continuam valendo.

CHECKLIST antes de virar EMAIL_MODE=real (o smoke test cobra cada item):
  * dominio verificado no SES com SPF, DKIM e DMARC publicados;
  * saida do sandbox aprovada;
  * configuration set com SNS de bounce/complaint alimentando `opt_outs`;
  * warmup: comecar baixo e subir volume ao longo de semanas;
  * link de descadastro de 1 clique + header List-Unsubscribe (ja implementado).

Reputacao de dominio nao se recupera rapido. E por isso que o SendService
consulta a lista de supressao IMEDIATAMENTE antes de cada envio, e nao na
geracao da mensagem.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import ProviderNotConfigured
from app.core.http_client import HttpClient
from app.core.logging import get_logger
from app.ports.dto import EmailMessage, SendResult
from app.services.cost import CostRecorder, CostSpec

log = get_logger("ses")

#: Erros do SES que devem virar opt-out automatico (endereco morto).
ERROS_PERMANENTES = frozenset(
    {"MessageRejected", "MailFromDomainNotVerifiedException", "AccountSuspendedException"}
)


class SESAdapter:
    provedor = "email"
    modo = "real"

    def __init__(
        self,
        http: HttpClient | None = None,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
        cliente: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http
        self.cost = cost
        faltando = [
            nome
            for nome, valor in (
                ("AWS_ACCESS_KEY_ID", self.settings.aws_access_key_id),
                ("AWS_SECRET_ACCESS_KEY", self.settings.aws_secret_access_key),
                ("AWS_REGION", self.settings.aws_region),
                ("SES_FROM_EMAIL", self.settings.ses_from_email),
            )
            if not valor
        ]
        if faltando:
            raise ProviderNotConfigured("Faltam variaveis para o SES: " + ", ".join(faltando))
        self._cliente = cliente

    @property
    def cliente(self):  # noqa: ANN201
        if self._cliente is None:
            import boto3

            self._cliente = boto3.client(
                "sesv2",
                region_name=self.settings.aws_region,
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
            )
        return self._cliente

    def enviar(self, mensagem: EmailMessage) -> SendResult:
        de = mensagem.de or self.settings.ses_from_email
        corpo: dict[str, Any] = {
            "FromEmailAddress": de,
            "Destination": {"ToAddresses": [mensagem.para]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": mensagem.assunto, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": mensagem.corpo_texto, "Charset": "UTF-8"}},
                }
            },
        }
        if mensagem.corpo_html:
            corpo["Content"]["Simple"]["Body"]["Html"] = {
                "Data": mensagem.corpo_html,
                "Charset": "UTF-8",
            }
        if mensagem.responder_para:
            corpo["ReplyToAddresses"] = [mensagem.responder_para]
        # List-Unsubscribe entra como header nomeado (exigido para 1 clique).
        cabecalhos = [
            {"Name": nome, "Value": valor} for nome, valor in (mensagem.headers or {}).items()
        ]
        if cabecalhos:
            corpo["Content"]["Simple"]["Headers"] = cabecalhos

        custo = CostSpec(
            provedor=self.provedor,
            operacao="send",
            chave_preco="email.ses.send",
            quantidade=1,
            metadados={"para": mensagem.para},
        )

        try:
            with self.http.guard("send", custo, idempotency_key=mensagem.idempotency_key):
                resposta = self.cliente.send_email(**corpo)
        except Exception as exc:
            codigo = _codigo_do_erro(exc)
            log.error("ses_falhou", para=mensagem.para, codigo=codigo, erro=str(exc)[:200])
            return SendResult(
                sucesso=False,
                erro=f"{codigo}: {exc}"[:500],
                modo=self.modo,
                detalhes={"permanente": codigo in ERROS_PERMANENTES},
            )

        message_id = (resposta or {}).get("MessageId")
        log.info("ses_enviado", para=mensagem.para, message_id=message_id)
        return SendResult(
            sucesso=True,
            provider_message_id=message_id,
            modo=self.modo,
            detalhes={"de": de},
        )


def _codigo_do_erro(exc: Exception) -> str:
    resposta = getattr(exc, "response", None)
    if isinstance(resposta, dict):
        return str((resposta.get("Error") or {}).get("Code") or exc.__class__.__name__)
    return exc.__class__.__name__
