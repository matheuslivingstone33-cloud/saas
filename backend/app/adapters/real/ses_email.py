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

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import Settings, get_settings
from app.core.errors import ProviderNotConfigured
from app.core.http_client import HttpClient
from app.core.logging import get_logger
from app.ports.dto import EmailMessage, SendResult
from app.services.cost import CostRecorder, CostSpec

if TYPE_CHECKING:
    from app.services.entregabilidade import EscopoFalhaEnvio, TipoRetorno

log = get_logger("ses")

#: Falhas de CONTA/REMETENTE: atingem TODOS os destinatarios. A acao e PAUSAR,
#: nunca suprimir — suprimir aqui apagaria a base durante uma suspensao de conta.
ERROS_DE_CONTA = frozenset(
    {
        "AccountSuspendedException",
        "SendingPausedException",
        "MailFromDomainNotVerifiedException",
    }
)

#: Marcas, no texto do erro, de que um `MessageRejected` veio da lista de
#: supressao da conta (endereco morto de um bounce anterior) — e nao de conteudo
#: recusado ou identidade nao verificada no sandbox, que atingem todo mundo.
_MARCAS_SUPRESSAO = ("suppression list", "on the suppression", "suppressed")


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
            escopo = classificar_falha_ses(codigo, str(exc))
            log.error(
                "ses_falhou",
                para=mensagem.para,
                codigo=codigo,
                escopo=escopo.value,
                erro=str(exc)[:200],
            )
            return SendResult(
                sucesso=False,
                erro=f"{codigo}: {exc}"[:500],
                modo=self.modo,
                # `escopo_falha` diz ao SendService o que fazer: pausar a
                # campanha (conta), suprimir o contato (destinatario) ou so
                # marcar FALHOU (transitoria). Vocabulario neutro de provedor.
                detalhes={"escopo_falha": escopo.value, "codigo": codigo},
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


def classificar_falha_ses(codigo: str, mensagem: str = "") -> EscopoFalhaEnvio:
    """Classifica uma falha SINCRONA do SES pelo ESCOPO do dano.

    O `permanente` booleano de antes juntava dois mundos que pedem acoes opostas:
    um endereco morto (suprime AQUELE contato) e uma conta/remetente quebrada
    (PAUSA tudo). Agir sobre o booleano suprimiria o destinatario durante uma
    suspensao de conta e apagaria a base inteira.

    `MessageRejected` e SOBRECARREGADO no SES: pode ser um endereco na lista de
    supressao da conta (aquele contato esta morto), conteudo recusado por
    politica, ou — no sandbox — identidade nao verificada. So o primeiro e do
    destinatario; os outros atingem TODOS. Por isso um `MessageRejected` so vira
    `DESTINATARIO` quando o texto do erro diz explicitamente que veio da lista de
    supressao; na duvida cai em `TRANSITORIA`, que nao suprime ninguem. O sinal
    definitivo de endereco morto e o bounce assincrono (via SNS), tratado a parte.
    """
    from app.services.entregabilidade import EscopoFalhaEnvio

    codigo = (codigo or "").strip()
    texto = (mensagem or "").lower()

    if codigo in ERROS_DE_CONTA:
        return EscopoFalhaEnvio.CONTA
    if codigo == "MessageRejected" and any(marca in texto for marca in _MARCAS_SUPRESSAO):
        return EscopoFalhaEnvio.DESTINATARIO
    return EscopoFalhaEnvio.TRANSITORIA


# =============================================================================
# Retorno assincrono do SES (bounce e reclamacao via SNS)
# =============================================================================
# O envio sincrono e metade da historia: o SES aceita a mensagem (200 + um
# MessageId) e so DEPOIS descobre que o endereco nao existe ou que a pessoa
# marcou como spam. Esse retorno chega por uma notificacao SNS, e e ele que
# alimenta a supressao. Sem traduzir esse formato, ligar EMAIL_MODE=real deixa
# a reclamacao de spam sem caminho ate `opt_outs`: a taxa de reclamacao sobe
# sem freio, o SES suspende a conta, e o dominio do cliente morre junto.
#
# A rota `/v1/inbound/retorno` (assinada por HMAC) fala o formato normalizado
# do `ServicoDeEntregabilidade.registrar`. Estas funcoes fazem a ponte: pegam a
# notificacao crua do SES e devolvem exatamente os campos daquele `registrar`.
# O que continua sendo trabalho da rota, de proposito: verificar a assinatura
# do SNS e fazer o GET no SubscribeURL do handshake.


@dataclass(slots=True)
class RetornoSES:
    """Um retorno do SES ja traduzido para o vocabulario da entregabilidade.

    Os campos batem 1:1 com os kwargs de `ServicoDeEntregabilidade.registrar`,
    de proposito: quem consome so precisa percorrer a lista e repassar.
    """

    contato: str
    tipo: TipoRetorno
    provider_message_id: str | None = None
    diagnostico: str | None = None


def classificar_retorno_ses(payload: Any) -> list[RetornoSES]:
    """Traduz uma notificacao do SES para a lista de retornos normalizados.

    Aceita o envelope cru do SNS (com o evento serializado em `Message`), o
    evento do SES ja desembrulhado, ou o formato de event publishing (que usa
    `eventType` no lugar de `notificationType`). Uma unica notificacao pode
    citar VARIOS destinatarios (bounce de lote), por isso devolve lista.

    Nunca levanta excecao: um webhook que estoura vira 500, e o SNS reenvia em
    laco. Formato que nao reconhece — Delivery, Send, Open, confirmacao de
    inscricao — devolve `[]`, porque nao ha nada a suprimir.
    """
    from app.services.entregabilidade import TipoRetorno

    if not isinstance(payload, dict):
        return []
    if payload.get("Type") in {"SubscriptionConfirmation", "UnsubscribeConfirmation"}:
        # Handshake do SNS: quem confirma e a rota (GET no SubscribeURL).
        return []

    evento = _evento_sns(payload)
    tipo_evento = (evento.get("notificationType") or evento.get("eventType") or "").strip()
    message_id = (evento.get("mail") or {}).get("messageId")

    if tipo_evento == "Bounce":
        bounce = evento.get("bounce") or {}
        tipo = _tipo_de_bounce(bounce.get("bounceType"))
        contexto = _texto(bounce.get("bounceType"), bounce.get("bounceSubType"))
        retornos: list[RetornoSES] = []
        for recipiente in bounce.get("bouncedRecipients") or []:
            endereco = _endereco((recipiente or {}).get("emailAddress"))
            if endereco is None:
                continue
            retornos.append(
                RetornoSES(
                    contato=endereco,
                    tipo=tipo,
                    provider_message_id=message_id,
                    diagnostico=(recipiente or {}).get("diagnosticCode") or contexto,
                )
            )
        return retornos

    if tipo_evento == "Complaint":
        complaint = evento.get("complaint") or {}
        diagnostico = complaint.get("complaintFeedbackType") or "reclamacao de spam"
        retornos = []
        for recipiente in complaint.get("complainedRecipients") or []:
            endereco = _endereco((recipiente or {}).get("emailAddress"))
            if endereco is None:
                continue
            retornos.append(
                RetornoSES(
                    contato=endereco,
                    tipo=TipoRetorno.RECLAMACAO,
                    provider_message_id=message_id,
                    diagnostico=diagnostico,
                )
            )
        return retornos

    return []


def url_de_confirmacao_sns(payload: Any) -> str | None:
    """SubscribeURL do handshake, quando a notificacao for uma confirmacao.

    A rota tem que fazer um GET nessa URL, senao o SNS nunca comeca a entregar
    bounce/complaint — e a supressao por retorno nunca liga.
    """
    if isinstance(payload, dict) and payload.get("Type") in {
        "SubscriptionConfirmation",
        "UnsubscribeConfirmation",
    }:
        return payload.get("SubscribeURL")
    return None


def _evento_sns(payload: dict) -> dict:
    """Desembrulha o evento do SES de dentro do envelope do SNS.

    O SNS entrega o evento como uma STRING JSON no campo `Message`. Se o evento
    ja veio desembrulhado (tem `notificationType`/`eventType`), passa direto.
    """
    if "notificationType" in payload or "eventType" in payload:
        return payload
    bruto = payload.get("Message")
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except (ValueError, TypeError):
            return {}
    return bruto if isinstance(bruto, dict) else {}


def _tipo_de_bounce(bounce_type: str | None) -> TipoRetorno:
    """Permanent suprime; Transient e Undetermined nao.

    Undetermined cai no lado conservador: suprimir um endereco possivelmente bom
    perde um lead, mas nao machuca ninguem — e a decisao e reversivel. O que nao
    volta e a reputacao do dominio, e essa quem queima e a reclamacao, tratada
    a parte.
    """
    from app.services.entregabilidade import TipoRetorno

    if (bounce_type or "").strip().lower() == "permanent":
        return TipoRetorno.PERMANENTE
    return TipoRetorno.TRANSITORIO


def _endereco(bruto: str | None) -> str | None:
    """Extrai o endereco puro. O SES quase sempre manda so o e-mail, mas as
    vezes vem como `Nome <e-mail>` — guardar a supressao sob a forma com nome
    faria a proxima checagem de opt-out nao casar com o e-mail do lead."""
    if not bruto:
        return None
    texto = bruto.strip()
    if "<" in texto and ">" in texto:
        texto = texto[texto.rfind("<") + 1 : texto.rfind(">")]
    return texto.strip() or None


def _texto(*partes: str | None) -> str:
    return "/".join(p for p in partes if p)
