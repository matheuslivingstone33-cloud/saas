"""MOTOR 4 — Conversa.

Ate aqui o sistema era de mao unica: gerava, enviava, registrava. Os estados
`respondido` e `convertido` existiam na maquina de estados e nunca aconteciam,
porque nada os preenchia. Este modulo fecha esse buraco.

O que ele faz quando uma resposta chega:

  1. registra a mensagem de ENTRADA na conversa do lead;
  2. classifica a INTENCAO da resposta;
  3. decide o que fazer — e a decisao mais importante e quando NAO responder.

Sobre não responder. Um agente que insiste depois de "nao tenho interesse", ou
que argumenta contra "me tire da lista", destroi a reputacao do remetente e
expoe o cliente juridicamente. Por isso a classificacao vem ANTES da redacao, e
tres intencoes encerram a conversa sem nenhuma resposta:

  * PEDIDO_OPT_OUT  -> registra a supressao e para. Para sempre.
  * RECUSA          -> respeita o nao e descarta o lead.
  * PEDIDO_HUMANO   -> devolve para a pessoa, mesmo em piloto automatico.

Ausencia (resposta automatica de ferias) tambem nao gera resposta: nao e uma
resposta de verdade e o lead nem leu a mensagem ainda.
"""

from __future__ import annotations

import html
import quopri
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.core.errors import BloqueadoPorCompliance
from app.core.ids import now
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    Canal,
    Direcao,
    NivelAutonomia,
    OrigemOptOut,
    StatusLead,
    StatusMensagem,
    TipoContato,
    TipoEvento,
)
from app.models.lead import Lead
from app.models.message import Message
from app.models.user import User
from app.ports.dto import LLMMessage, LLMRequest
from app.repositories.misc import MessageRepository, OptOutRepository, UserRepository
from app.services.audit import AuditService
from app.services.compliance import mascarar_contato as _mascarar_contato
from app.services.envio import SendService
from app.services.leads import LeadService
from app.services.personalizacao import LINHA_DESCADASTRO

log = get_logger("conversa")


class Intencao(StrEnum):
    """O que o lead quis dizer. Determina se e como respondemos."""

    INTERESSE = "interesse"
    DUVIDA = "duvida"
    OBJECAO = "objecao"
    RECUSA = "recusa"
    PEDIDO_OPT_OUT = "pedido_opt_out"
    PEDIDO_HUMANO = "pedido_humano"
    AUSENCIA = "ausencia"
    INDEFINIDA = "indefinida"


#: Intencoes que ENCERRAM a conversa sem resposta automatica.
SEM_RESPOSTA = frozenset(
    {Intencao.PEDIDO_OPT_OUT, Intencao.RECUSA, Intencao.PEDIDO_HUMANO, Intencao.AUSENCIA}
)

#: Intencoes que indicam lead quente — a interface destaca e sugere fechar.
QUENTES = frozenset({Intencao.INTERESSE})


@dataclass(slots=True)
class ResultadoConversa:
    lead_id: uuid.UUID
    intencao: Intencao
    respondeu: bool = False
    encerrou: bool = False
    motivo: str = ""
    mensagem_id: uuid.UUID | None = None
    resposta_id: uuid.UUID | None = None
    aguardando_aprovacao: bool = False
    detalhes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "lead_id": str(self.lead_id),
            "intencao": self.intencao.value,
            "respondeu": self.respondeu,
            "encerrou": self.encerrou,
            "motivo": self.motivo,
            "mensagem_id": str(self.mensagem_id) if self.mensagem_id else None,
            "resposta_id": str(self.resposta_id) if self.resposta_id else None,
            "aguardando_aprovacao": self.aguardando_aprovacao,
            "lead_quente": self.intencao in QUENTES,
            **self.detalhes,
        }


@dataclass(slots=True)
class ResultadoManual:
    """Resultado de uma mensagem escrita por uma pessoa."""

    lead_id: uuid.UUID
    mensagem_id: uuid.UUID | None = None
    enviada: bool = False
    assumida: bool = False
    motivo: str = ""

    def to_dict(self) -> dict:
        return {
            "lead_id": str(self.lead_id),
            "mensagem_id": str(self.mensagem_id) if self.mensagem_id else None,
            "enviada": self.enviada,
            "assumida": self.assumida,
            "motivo": self.motivo,
        }


# --- Classificacao -----------------------------------------------------------
# Sinais lexicais em pt-BR. Sao a PRIMEIRA linha: quando o texto e inequivoco
# ("me tire da lista"), nao gastamos chamada de LLM nem corremos o risco de o
# modelo errar num caso onde errar custa caro.
_SINAIS: list[tuple[Intencao, tuple[str, ...]]] = [
    (
        Intencao.PEDIDO_OPT_OUT,
        (
            "descadastr", "remover da lista", "me tire da lista", "tire meu",
            "nao quero receber", "não quero receber", "parar de receber",
            "cancelar inscricao", "cancelar inscrição", "unsubscribe",
            "sair da lista", "nao me envie", "não me envie",
            # "Pare de me enviar/mandar" nao tem leitura de interesse. As demais
            # frases de saida — remover, remocao, "nao desejo receber", opt-out —
            # so valem com o PROPRIO contato como objeto: ver
            # `_RE_OPT_OUT_EXPLICITO`, logo abaixo.
            "pare de me enviar", "parem de me enviar",
            "pare de me mandar", "parem de me mandar",
        ),
    ),
    (
        Intencao.PEDIDO_HUMANO,
        (
            "falar com uma pessoa", "falar com alguem", "falar com alguém",
            "atendente", "falar com humano", "quero falar com o responsavel",
            "quero falar com o responsável", "isso e um robo", "isso é um robô",
        ),
    ),
    (
        Intencao.RECUSA,
        (
            "nao tenho interesse", "não tenho interesse", "sem interesse",
            "nao temos interesse", "não temos interesse", "ja temos fornecedor",
            "já temos fornecedor", "nao precisamos", "não precisamos",
            "obrigado, mas nao", "obrigado, mas não",
        ),
    ),
    (
        Intencao.AUSENCIA,
        (
            "estou de ferias", "estou de férias", "ausente do escritorio",
            "ausente do escritório", "out of office", "resposta automatica",
            "resposta automática", "retorno no dia",
        ),
    ),
    (
        Intencao.INTERESSE,
        (
            "tenho interesse", "me manda mais", "me envia mais", "quero saber mais",
            "podemos conversar", "vamos marcar", "qual o valor", "qual o custo",
            "quanto custa", "manda a proposta", "envie a proposta", "orcamento",
            "orçamento", "pode enviar", "tenho sim", "temos interesse",
        ),
    ),
    (
        Intencao.OBJECAO,
        (
            "muito caro", "esta caro", "está caro", "sem orcamento", "sem orçamento",
            "agora nao e o momento", "agora não é o momento", "talvez mais para frente",
            "no proximo ano", "no próximo ano",
        ),
    ),
]

#: Frases de saida que so sao opt-out quando o objeto e o proprio contato.
#:
#: Em 20/09 elas entraram como pedaco solto de texto, e opt-out e terminal:
#: "preciso remover meu ar-condicionado antigo", "solicito a remocao do
#: entulho", "nao desejo receber ligacoes, prefiro e-mail", "voces tem
#: opt-out?" e ate "nao me remova da lista, tenho interesse" viravam pedido
#: de saida — e o lead que queria comprar se perdia para sempre. Agora cada
#: uma exige o que esta sendo removido (e-mail, contato, cadastro, dados, a
#: lista) ou o proprio "me", e o "nao" logo antes anula.
_OBJETO_CONTATO = (
    r"(?:o\s+|os\s+|a\s+)?(?:meus?|minhas?|nossos?|nossas?)\s+"
    r"(?:e-?mails?|endere[cç]os?|contatos?|cadastros?|dados|nomes?|telefones?|n[uú]meros?)"
)
_NAO_ANTES = r"(?<!não )(?<!nao )"
_RE_OPT_OUT_EXPLICITO = re.compile(
    r"|".join(
        (
            # remova-me / me remova / remover-me (da lista, da base...)
            _NAO_ANTES + r"\b(?:remova-me|remover-me|removam-me|me\s+remova[m]?)\b",
            # remova meu e-mail / remover o meu contato / removam meus dados
            _NAO_ANTES + r"\bremov(?:a|am|er|e)\s+" + _OBJETO_CONTATO,
            # solicito (a) remocao do meu contato / da lista / da base / dos dados
            r"\bsolicito\s+(?:a\s+)?remo[cç][aã]o\s+(?:d[oa]s?\s+)?"
            r"(?:meus?|minhas?|lista|base|cadastro|dados|e-?mails?|contatos?)\b",
            # nao desejo receber mais / e-mails / mensagens / contato / isso
            r"\bn[aã]o\s+desejo\s+receber\s+"
            r"(?:mais|e-?mails?|mensage[mn]s?|contatos?|comunica[cç][oõ]es|seus|suas|esse|este|essas|esses|isso|nada)\b",
            # "quero opt out" / "please opt-out me" / "opt out from" — nao o
            # "opt-out" citado como assunto nem o rodape em ingles de uma assinatura.
            r"\b(?:quero|please|i\s+want\s+to|want\s+to)\s+opt[- ]?out\b",
            r"\bopt[- ]?out\s+(?:me|desta|dessa|from)\b",
        )
    )
)


#: Intencoes cujo sinal e procurado no texto INTEIRO, e nao so na resposta nova.
#:
#: So o opt-out entra aqui, e de proposito: "opt-out duvidoso e opt-out". Um
#: pedido de saida escrito embaixo de uma citacao nao pode se perder — o direito
#: do titular ganha do negocio, entao para ELE a varredura e a mais ampla
#: possivel. Todos os outros sinais (recusa, interesse, objecao...) olham so a
#: resposta nova: um "nao tenho interesse" copiado de uma troca antiga nao pode
#: descartar um lead que acabou de dizer sim.
_SOBRE_TEXTO_INTEIRO = frozenset({Intencao.PEDIDO_OPT_OUT})

#: Uma linha comeca uma citacao (`>`), a assinatura de quem foi citado
#: ("... escreveu:" / "... wrote:"), ou um separador de mensagem original.
#: Deste ponto para baixo e historico, nao resposta nova.
_RE_LINHA_CITADA = re.compile(r"^\s*>")
_RE_SEPARADOR = re.compile(
    r"^\s*-{2,}\s*"
    r"(mensagem original|original message|forwarded message|mensagem encaminhada)"
    r"\b.*$",
    re.IGNORECASE,
)
_RE_REGUA = re.compile(r"^\s*_{5,}\s*$")  # a regua de sublinhados do Outlook
_FIM_ATRIBUICAO = ("escreveu:", "wrote:")

#: Bloco de cabecalho que o Outlook (e alguns webmails) intercala antes do
#: historico citado, SEM a regua de sublinhados e SEM prefixo `>`:
#:
#:     De: Fulano <fulano@x.com>
#:     Enviada em: terca-feira, 9 de setembro de 2026 10:15
#:     Para: voce@exemplo.com
#:     Assunto: RE: proposta
#:
#: So os rotulos conhecidos de e-mail contam. Com um deles solto uma resposta de
#: verdade poderia comecar com "Assunto: ..." — por isso o corte so vale com DUAS
#: linhas de cabecalho SEGUIDAS. E "De acordo, ..." nao vira fronteira porque nao
#: ha ":" logo depois de "De".
_RE_CABECALHO_ENCAMINHADO = re.compile(
    r"^\s*(?:de|para|assunto|data|cc|cco|bcc|enviad[ao](?:\s+em)?"
    r"|responder(?:\s+(?:a|para))?|from|to|subject|sent|date|reply-to)\s*:",
    re.IGNORECASE,
)


def _e_fronteira_de_citacao(linha: str) -> bool:
    baixo = linha.strip().lower()
    if _RE_LINHA_CITADA.match(linha):
        return True
    if baixo.endswith(_FIM_ATRIBUICAO):
        return True
    if _RE_SEPARADOR.match(linha) or _RE_REGUA.match(linha):
        return True
    return False


def _abre_bloco_encaminhado(linhas: list[str], i: int) -> bool:
    """Duas linhas de cabecalho de e-mail seguidas abrem o historico citado."""
    if not _RE_CABECALHO_ENCAMINHADO.match(linhas[i]):
        return False
    return i + 1 < len(linhas) and bool(_RE_CABECALHO_ENCAMINHADO.match(linhas[i + 1]))


def remover_historico_citado(texto: str) -> str:
    """Devolve so a RESPOSTA NOVA, cortando o historico citado que vem colado.

    E-mail de verdade nao chega limpo como o mock: a resposta vem em cima de
    tudo o que ja foi trocado — a mensagem anterior citada com `>`, a linha
    "Em <data>, Fulano escreveu:", o "-----Mensagem original-----", ou o bloco
    de cabecalho "De:/Enviada em:/Para:/Assunto:" que o Outlook intercala.
    Classificar a intencao de negocio sobre esse bolo faz um "nao tenho
    interesse" antigo descartar um "sim" recem-escrito.

    O corte e CONSERVADOR: so acontece numa fronteira inequivoca, e tudo o que
    esta ACIMA dela e preservado. Sem fronteira, o texto volta inteiro. Assim o
    metodo nunca engole a resposta nova — no maximo deixa historico passar, que
    e o lado seguro de errar.
    """
    if not texto:
        return texto
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        if _e_fronteira_de_citacao(linha) or _abre_bloco_encaminhado(linhas, i):
            return "\n".join(linhas[:i]).strip()
    return texto


#: Linhas com o NOSSO link de descadastro. Toda resposta real traz a mensagem
#: anterior citada, e o opt-out e procurado no texto INTEIRO. No dia em que o link
#: for para o corpo do e-mail, a linha dele ("Para sair da lista, descadastre-se:
#: https://.../descadastro/...") voltaria citada em toda resposta — e todo "tenho
#: interesse" viraria pedido de saida. Opt-out e terminal: o lead seria perdido
#: para sempre por ter respondido que queria comprar.
#:
#: A linha inteira sai (rotulo junto), por isso o rodape deve manter rotulo e link
#: na mesma linha. As palavras do titular continuam valendo: "quero me
#: descadastrar" escrito por ele e opt-out.
_RE_LINHA_DO_NOSSO_LINK = re.compile(r"^.*/descadastro/.*$", re.IGNORECASE | re.MULTILINE)


#: Assinatura do quoted-printable: um "=" seguido de dois hex (`=C3`) ou de
#: quebra de linha (soft break). Texto comum quase nunca traz isso — "custo = 4"
#: tem espaco depois do "=" e nao casa.
_PARECE_QP = re.compile(r"=(?:[0-9A-Fa-f]{2}|\r?\n)")


def decodificar_quoted_printable(texto: str) -> str:
    """Decodifica corpo em quoted-printable para texto legivel.

    E aqui que mora o pior caso do e-mail real: um opt-out que o classificador
    NAO ve. O provedor manda "nao" como `n=C3=A3o` e quebra palavra longa com
    soft break (`desca=\\ndastrar`), entao "descadastr"/"nao quero receber" nao
    casam com marca nenhuma — e a pessoa que pediu para sair continua
    recebendo.

    So decodifica quando o texto TEM cara de QP, e volta ao original se algo
    der errado: normalizar de menos e melhor do que corromper resposta comum.
    """
    if not texto or not _PARECE_QP.search(texto):
        return texto
    try:
        # QP legitimo e ASCII (o nao-ASCII vira `=XX`); surrogateescape so
        # protege contra bytes estranhos que tenham escapado ate aqui.
        bruto = quopri.decodestring(texto.encode("utf-8", "surrogateescape"))
        return bruto.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — decodificacao best-effort, nunca fatal
        return texto


#: Assinatura de HTML: uma tag de FECHAMENTO (`</x`) ou uma tag de abertura
#: CONHECIDA. Texto comum com "custo < 4 mil" ou "a -> b" nao casa — o `<` de
#: verdade vem seguido de espaco ou de digito, nunca de "/" nem de nome de tag.
#: So convertemos quando o corpo REALMENTE parece HTML: em texto puro um `<`
#: solto nao pode virar inicio de tag e engolir a resposta ate o proximo `>`.
_PARECE_HTML = re.compile(
    r"</[a-zA-Z]"
    r"|<(?:br|p|div|span|table|thead|tbody|tr|td|th|ul|ol|li|a|b|i|u|em|strong|"
    r"font|small|center|pre|blockquote|h[1-6]|hr|img|meta|link|title|style|"
    r"script|html|body|head|o:p)\b",
    re.IGNORECASE,
)

#: Conteudo de <script>/<style> NAO e texto de leitura. Uma palavra perdida numa
#: folha de estilo ou num script ("nao tenho interesse" dentro de um seletor) nao
#: pode votar na intencao — sai inteiro, antes de qualquer outra limpeza.
_RE_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)

#: Tags de bloco e o <br> viram QUEBRA DE LINHA. Sem isso o HTML cola a resposta,
#: o historico citado e a linha do nosso link numa unica linha — e tanto
#: `remover_historico_citado` quanto a protecao do `/descadastro/` trabalham por
#: linha. Perder a fronteira de linha faria um "nao tenho interesse" citado
#: descartar um lead que disse sim.
_RE_QUEBRA_HTML = re.compile(
    r"<\s*/?\s*(?:br|p|div|tr|table|blockquote|li|ul|ol|h[1-6]|hr|"
    r"header|footer|section|article|o:p)\b[^>]*>",
    re.IGNORECASE,
)

#: Qualquer tag restante (inline: <span>, <a href=...>, <font>). `[^<>]` — e nao
#: `[^>]` — impede que um `<` solto que tenha sobrado engula tudo ate o proximo `>`.
_RE_TAG_RESTANTE = re.compile(r"<[^<>]+>")
_RE_LINHAS_VAZIAS = re.compile(r"\n{3,}")


def html_para_texto(texto: str) -> str:
    """Converte corpo em HTML para texto legivel, antes de classificar.

    E-mail real chega com frequencia em HTML: `<br>`, `<div>`, `&nbsp;` e
    entidades como `n&atilde;o`. Sem converter, o casamento lexical trabalha
    sobre `<p>N&atilde;o tenho interesse</p>` e nao acha "nao tenho interesse";
    pior, um opt-out entidade-codificado (`n&atilde;o me envie`) escaparia — e a
    pessoa que pediu para sair continuaria recebendo. Opt-out duvidoso e opt-out,
    e um opt-out que o classificador NAO ve e o pior caso.

    So converte quando o texto TEM cara de HTML (`_PARECE_HTML`): em texto puro
    um `<` de "custo < 4 mil" nao pode virar inicio de tag. O conteudo de
    <script>/<style> sai inteiro, as tags de bloco viram quebra de linha (o corte
    por linha depende disso) e as entidades sao expandidas POR ULTIMO — depois de
    tirar as tags, para que `&lt;` escrito pelo remetente vire texto, nao tag.
    Volta ao original se algo der errado: normalizar de menos e melhor do que
    corromper resposta.
    """
    if not texto or not _PARECE_HTML.search(texto):
        return texto
    try:
        t = _RE_SCRIPT_STYLE.sub(" ", texto)
        t = _RE_QUEBRA_HTML.sub("\n", t)
        t = _RE_TAG_RESTANTE.sub("", t)
        t = html.unescape(t)
        # HTML gera muita linha vazia; o corte por linha nao precisa delas.
        # Linha a linha, e nao por regex: `[ \t]*\n...` sobre uma sequencia longa
        # de espacos sem quebra volta atras a cada posicao — 40 mil espacos
        # num corpo de resposta levavam segundos, e o corpo vem do lead.
        linhas = [linha.strip(" \t") for linha in t.split("\n")]
        t = _RE_LINHAS_VAZIAS.sub("\n\n", "\n".join(linhas))
        return t.strip()
    except Exception:  # noqa: BLE001 — conversao best-effort, nunca fatal
        return texto


#: Caracteres invisiveis que NAO sao espaco (o `\s` do `_normalizar` nao os pega)
#: e que, plantados no meio de uma palavra, partem o casamento lexical: hifen
#: suave (U+00AD), largura-zero (U+200B ZWSP, U+200C ZWNJ, U+200D ZWJ), juntador
#: de palavra (U+2060) e o BOM/ZWNBSP (U+FEFF). Um "desca<U+200B>dastrar" nao casa
#: com "descadastr" — e a pessoa que pediu para sair continua recebendo.
_RE_INVISIVEIS = re.compile("[­​‌‍⁠﻿]")


def remover_invisiveis(texto: str) -> str:
    """Remove caracteres invisiveis que partem palavra, JUNTANDO os pedacos.

    E o analogo do soft break do quoted-printable e das entidades de HTML: mais
    um jeito de esconder um opt-out do classificador. O provedor (ou o cliente de
    e-mail) enfia um caractere de largura zero ou um hifen suave no meio de
    "descadastrar" — as vezes vindo como entidade (`desca&#8203;dastrar`), que o
    `html.unescape` transforma no U+200B literal — e "descadastr" nao casa. Some
    o invisivel e "desca<zero>dastrar" volta a ser "descadastrar".

    Remover so JUNTA vizinhos: nunca inventa marca onde nao havia, e o unico
    risco (revelar um opt-out que estava escondido) e exatamente o lado seguro de
    errar. Espaco de verdade, acento e quebra de linha nao sao tocados.
    """
    if not texto:
        return texto
    return _RE_INVISIVEIS.sub("", texto)


def recompor_acentos(texto: str) -> str:
    """Recompoe o texto na forma canonica NFC antes de classificar.

    Mais um jeito de o MESMO texto esconder uma marca do casamento lexical: o
    acento pode chegar DECOMPOSTO (NFD), com o til/agudo/circunflexo como um
    caractere combinante SEPARADO logo depois da vogal — "na" + U+0303 + "o" no
    lugar do "não" pronto. macOS e alguns provedores serializam assim. Nessa
    forma, "não me envie" nao casa nem com "não me envie" nem com "nao me
    envie", e a pessoa que pediu para sair continua recebendo. E o analogo do
    soft break do quoted-printable e do largura-zero — o mesmo pior caso: um
    opt-out que o classificador NAO ve.

    NFC e a forma canonica dos nossos sinais (o codigo-fonte escreve "não"
    composto), entao recompor o corpo faz os dois casarem. E seguro e SEM gate:
    em texto ja composto (o caso comum) e no-op; nunca tira acento nem muda a
    leitura — so junta a vogal e o combinante num caractere so. Como o
    `remover_invisiveis`, o unico efeito e revelar marca escondida, nunca
    inventar. Roda DEPOIS de `remover_invisiveis` de proposito: um invisivel
    entre a vogal e o combinante bloquearia a composicao; tirado o invisivel, o
    NFC compoe.
    """
    if not texto:
        return texto
    return unicodedata.normalize("NFC", texto)


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip().lower())


def classificar_por_sinal(texto: str) -> Intencao | None:
    """Classificacao lexical. Devolve None quando o texto nao e inequivoco.

    A ORDEM importa: opt-out e pedido de humano vem antes de tudo. Uma mensagem
    como "nao quero receber mais, mas qual o valor?" tem que ser tratada como
    opt-out — em caso de duvida, o direito do titular ganha do negocio.

    O ESCOPO tambem importa. Opt-out e procurado no texto inteiro (ver
    `_SOBRE_TEXTO_INTEIRO`); os demais sinais, so na resposta nova, para que o
    historico citado nao vote na intencao de negocio.

    O corpo e normalizado ANTES de tudo, e nesta ordem: primeiro o
    quoted-printable (a quebra suave `=\\n` parte palavras, a linha do nosso link
    e as marcas de citacao), depois o HTML (tags e entidades), depois os
    caracteres invisiveis (largura-zero, hifen suave) e por ultimo o NFC, que
    recompoe acento decomposto (`na` + til combinante -> `não`). E a ordem do
    e-mail real — o HTML chega codificado em quoted-printable, entao decodificar
    QP primeiro entrega o HTML inteiro para `html_para_texto`; o invisivel vem
    depois porque uma entidade como `&#8203;` so vira o caractere literal depois
    do HTML; e o NFC por ultimo porque um invisivel entre a vogal e o combinante
    bloquearia a composicao.
    """
    texto = decodificar_quoted_printable(texto)
    texto = html_para_texto(texto)
    texto = remover_invisiveis(texto)
    texto = recompor_acentos(texto)
    inteiro = _normalizar(_RE_LINHA_DO_NOSSO_LINK.sub("", texto or ""))
    if not inteiro:
        return None
    novo = _normalizar(remover_historico_citado(texto))
    if _RE_OPT_OUT_EXPLICITO.search(inteiro):
        return Intencao.PEDIDO_OPT_OUT
    for intencao, marcas in _SINAIS:
        alvo = inteiro if intencao in _SOBRE_TEXTO_INTEIRO else novo
        if alvo and any(marca in alvo for marca in marcas):
            return intencao
    return None


class ServicoDeConversa:
    """Motor 4. Recebe resposta, decide e — quando cabe — responde."""

    def __init__(
        self,
        session: Session,
        portas: ProviderRegistry,
        audit: AuditService | None = None,
    ) -> None:
        self.session = session
        self.portas = portas
        self.audit = audit or AuditService(session)
        self.leads = LeadService(session, self.audit)
        self.mensagens = MessageRepository(session)
        self.opt_outs = OptOutRepository(session)
        self.usuarios = UserRepository(session)
        self.envio = SendService(session, portas, self.audit, self.leads)

    # -- entrada --------------------------------------------------------------
    def receber(
        self,
        *,
        lead: Lead,
        corpo: str,
        remetente: str | None = None,
        assunto: str | None = None,
        canal: Canal = Canal.EMAIL,
        provider_message_id: str | None = None,
    ) -> ResultadoConversa:
        """Ponto de entrada de toda resposta, venha de webhook ou de simulacao."""
        entrada = self.mensagens.add(
            Message(
                user_id=lead.user_id,
                campaign_id=lead.campaign_id,
                lead_id=lead.id,
                canal=canal,
                direcao=Direcao.ENTRADA,
                status=StatusMensagem.RESPONDIDA,
                remetente=remetente or lead.email,
                destinatario=None,
                assunto=assunto,
                corpo=corpo,
                provider_message_id=provider_message_id,
                enviado_em=now(),
                ordem=self._proxima_ordem(lead),
                created_at=now(),
            )
        )

        intencao = self.classificar(corpo, lead)
        resultado = ResultadoConversa(
            lead_id=lead.id, intencao=intencao, mensagem_id=entrada.id
        )

        self.audit.registrar(
            evento=TipoEvento.RESPOSTA_RECEBIDA,
            entidade_tipo="mensagem",
            entidade_id=entrada.id,
            dados={
                "lead_id": str(lead.id),
                "canal": canal.value,
                "intencao": intencao.value,
                # Mascarado: a trilha e imutavel e sobrevive a eliminacao.
                "remetente": _mascarar_contato(remetente or lead.email),
            },
            ator=Ator.PROVEDOR,
            user_id=lead.user_id,
        )

        # O que esta resposta ensinou sobre a MIRA. Este e o unico lugar que
        # credita o sinal: as transicoes abaixo passam `aprender=False` para nao
        # contar o mesmo fato duas vezes, com o agravante de que a transicao
        # para `respondido` nao sabe se a resposta foi "manda a proposta" ou
        # "me tire da lista" — e as duas ensinam coisas opostas.
        self.leads.aprendizado.observar_intencao(
            user_id=lead.user_id,
            intencao=intencao.value,
            cnae=lead.cnae_principal,
            componentes=(lead.score_breakdown or {}).get("componentes"),
        )

        # O lead respondeu — isso vale mesmo quando a resposta e um "nao".
        if lead.status is StatusLead.ABORDADO:
            self.leads.transicionar(
                lead,
                StatusLead.RESPONDIDO,
                motivo=f"respondeu ({intencao.value})",
                aprender=False,
            )

        if intencao in SEM_RESPOSTA:
            return self._encerrar(lead, intencao, resultado)

        # Conversa que uma pessoa assumiu: o agente para de escrever.
        #
        # Esta checagem vem DEPOIS de `SEM_RESPOSTA` de proposito. Opt-out,
        # recusa e pedido de humano continuam sendo processados mesmo aqui: o
        # direito do titular nao depende de quem esta conduzindo a conversa, e
        # um "me tire da lista" que chegasse numa conversa assumida nao pode
        # ficar sem supressao registrada.
        if lead.assumido_em is not None:
            resultado.motivo = "conversa assumida por uma pessoa; o agente nao responde"
            return resultado

        return self._responder(lead, intencao, resultado)

    # -- decisao --------------------------------------------------------------
    def _encerrar(
        self, lead: Lead, intencao: Intencao, resultado: ResultadoConversa
    ) -> ResultadoConversa:
        resultado.encerrou = True

        if intencao is Intencao.PEDIDO_OPT_OUT:
            contato = (lead.email or "").strip().lower()
            if contato:
                self.opt_outs.registrar(
                    contato=contato,
                    contato_normalizado=contato,
                    tipo_contato=TipoContato.EMAIL,
                    origem=OrigemOptOut.RESPOSTA_MANUAL,
                    user_id=lead.user_id,
                    motivo="pedido explicito na resposta do lead",
                )
            self.leads.transicionar(
                lead, StatusLead.OPT_OUT, motivo="pediu descadastro", aprender=False
            )
            resultado.motivo = "opt-out registrado; nao respondemos e nao voltamos a contatar"

        elif intencao is Intencao.RECUSA:
            self.leads.transicionar(
                lead,
                StatusLead.DESCARTADO,
                motivo="declarou que nao tem interesse",
                aprender=False,
            )
            resultado.motivo = "recusa respeitada; conversa encerrada sem resposta"

        elif intencao is Intencao.PEDIDO_HUMANO:
            resultado.motivo = "pediu falar com uma pessoa; devolvido para atendimento humano"

        else:  # AUSENCIA
            resultado.motivo = "resposta automatica de ausencia; nada a responder"

        self.audit.registrar(
            evento=TipoEvento.CONVERSA_ENCERRADA,
            entidade_tipo="lead",
            entidade_id=lead.id,
            dados={"intencao": intencao.value, "motivo": resultado.motivo},
            ator=Ator.SISTEMA,
            user_id=lead.user_id,
        )
        log.info(
            "conversa_encerrada",
            lead_id=str(lead.id),
            intencao=intencao.value,
            motivo=resultado.motivo,
        )
        return resultado

    def _responder(
        self, lead: Lead, intencao: Intencao, resultado: ResultadoConversa
    ) -> ResultadoConversa:
        """Redige a resposta. Envia ou deixa aprovando, conforme a autonomia."""
        campanha = (
            self.session.get(Campaign, lead.campaign_id) if lead.campaign_id else None
        )
        nivel = self.envio.nivel_de(campanha) if campanha else NivelAutonomia.ASSISTIDO

        # O guardrail de envio vale igual aqui: opt-out entrado no meio da
        # conversa, limite diario estourado, canal proibido.
        destino = (lead.email or "").strip().lower()
        bloqueio = self.envio.checar_bloqueios(campanha, lead, destino)
        if bloqueio is not None:
            resultado.encerrou = True
            resultado.motivo = f"resposta bloqueada: {bloqueio.motivo}"
            return resultado

        texto = self._redigir(lead, campanha, intencao)
        remetente_user = self.usuarios.get(lead.user_id)
        empresa = getattr(remetente_user, "empresa", None) or "nossa equipe"
        declaracao = (
            "Esta mensagem foi redigida por um agente de inteligencia artificial "
            f"a servico de {empresa}. Responda a este e-mail para falar com uma pessoa."
        )

        anteriores = self._historico(lead)
        chave = f"{lead.campaign_id}:{lead.id}:resposta:{len(anteriores)}"
        if self.mensagens.por_idempotency_key(chave) is not None:
            resultado.motivo = "resposta ja existente para este turno"
            return resultado

        automatica = nivel is NivelAutonomia.AUTOMATICO
        # O mesmo link assinado do primeiro contato, no cabecalho e no texto.
        # Ate 18/09 a resposta da IA saia com um endereco de teste montado com o
        # id cru do lead — a pagina de descadastro recusava — e sem link no
        # corpo: justo a mensagem que responde a quem ja esta conversando.
        link = self.envio.compliance.link_para(lead, self.envio.settings.url_publica)
        rodape = LINHA_DESCADASTRO.format(link=link)
        mensagem = self.mensagens.add(
            Message(
                user_id=lead.user_id,
                campaign_id=lead.campaign_id,
                lead_id=lead.id,
                canal=Canal.EMAIL,
                direcao=Direcao.SAIDA,
                status=(
                    StatusMensagem.APROVADA
                    if automatica
                    else StatusMensagem.AGUARDANDO_APROVACAO
                ),
                destinatario=lead.email,
                assunto=self._assunto_de_resposta(campanha),
                corpo=f"{texto}\n\n---\n{declaracao}\n{rodape}",
                declaracao_ia=declaracao,
                link_descadastro=link,
                idempotency_key=chave,
                aprovado_em=now() if automatica else None,
                # Sempre DEPOIS da mensagem que a originou.
                ordem=self._proxima_ordem(lead),
                created_at=now(),
                metadados={
                    "gerado_por": "ia",
                    "turno": len(anteriores),
                    "intencao": intencao.value,
                },
            )
        )
        resultado.resposta_id = mensagem.id

        self.audit.registrar(
            evento=TipoEvento.CONVERSA_RESPONDIDA,
            entidade_tipo="mensagem",
            entidade_id=mensagem.id,
            dados={
                "lead_id": str(lead.id),
                "intencao": intencao.value,
                "automatica": automatica,
            },
            ator=Ator.IA,
            user_id=lead.user_id,
        )

        if automatica:
            enviado = self.envio.despachar(mensagem)
            resultado.respondeu = enviado
            resultado.motivo = "respondida e enviada" if enviado else "falha ao enviar a resposta"
        else:
            resultado.aguardando_aprovacao = True
            resultado.motivo = "resposta redigida, aguardando sua aprovacao"

        log.info(
            "conversa_respondida",
            lead_id=str(lead.id),
            intencao=intencao.value,
            automatica=automatica,
        )
        return resultado

    # -- a pessoa assume ------------------------------------------------------
    def responder_manualmente(
        self,
        *,
        lead: Lead,
        corpo: str,
        autor: User,
        assunto: str | None = None,
    ) -> ResultadoManual:
        """Uma PESSOA escreve, e o sistema envia.

        Antes disto, "assumir a conversa" abria um `mailto:` — e a conversa
        saia do produto no momento em que ela mais valia. A resposta do lead
        voltava para a caixa pessoal, o Motor 4 ficava cego justamente no lead
        que estava dando certo, e a auditoria perdia o trecho mais importante.

        Tres decisoes que este metodo carrega:

        1. **Sem declaracao de IA.** O Marco da IA manda declarar quando e IA;
           nao manda mentir que e. Carimbar "escrita por um agente" numa
           mensagem que uma pessoa digitou seria declaracao falsa.
        2. **Com link de descadastro.** LGPD nao muda porque quem digitou foi
           gente: continua sendo contato comercial nao solicitado.
        3. **Os guardrails valem igual.** Opt-out em especial: nenhum humano
           passa por cima de "nao me contate" — o direito e do titular, nao do
           remetente.
        """
        texto = (corpo or "").strip()
        if not texto:
            raise BloqueadoPorCompliance("Mensagem vazia: nao ha o que enviar.")

        campanha = self.session.get(Campaign, lead.campaign_id) if lead.campaign_id else None
        destino = (lead.email or "").strip().lower()
        bloqueio = self.envio.checar_bloqueios(campanha, lead, destino)
        if bloqueio is not None:
            raise BloqueadoPorCompliance(
                f"Envio bloqueado ({bloqueio.motivo}): {bloqueio.detalhe}".strip(": ")
            )

        ordem = self._proxima_ordem(lead)
        chave = f"{lead.campaign_id}:{lead.id}:manual:{ordem}"
        if self.mensagens.por_idempotency_key(chave) is not None:
            return ResultadoManual(
                lead_id=lead.id, motivo="mensagem ja registrada para este turno"
            )

        # A conversa passa a ser da pessoa. Sem isto, o toque 2 da cadencia
        # sairia por cima do que ela acabou de escrever.
        assumida_agora = lead.assumido_em is None
        if assumida_agora:
            lead.assumido_em = now()

        mensagem = self.mensagens.add(
            Message(
                user_id=lead.user_id,
                campaign_id=lead.campaign_id,
                lead_id=lead.id,
                canal=Canal.EMAIL,
                direcao=Direcao.SAIDA,
                # Quem escreveu foi gente: pedir que ela aprove a propria
                # mensagem seria teatro de aprovacao.
                status=StatusMensagem.APROVADA,
                destinatario=lead.email,
                assunto=(assunto or self._assunto_de_resposta(campanha))[:300],
                corpo=texto,
                declaracao_ia=None,
                link_descadastro=self.envio.compliance.link_para(
                    lead, self.envio.settings.url_publica
                ),
                idempotency_key=chave,
                aprovado_em=now(),
                ordem=ordem,
                created_at=now(),
                metadados={"gerado_por": "humano", "autor": str(autor.id)},
            )
        )

        self.audit.registrar(
            evento=TipoEvento.MENSAGEM_GERADA,
            entidade_tipo="mensagem",
            entidade_id=mensagem.id,
            dados={
                "lead_id": str(lead.id),
                "gerado_por": "humano",
                "autor": str(autor.id),
                "declara_ia": False,
                "assumiu_a_conversa": assumida_agora,
            },
            ator=Ator.USUARIO,
            user_id=lead.user_id,
        )

        enviada = self.envio.despachar(mensagem)
        log.info(
            "resposta_manual",
            lead_id=str(lead.id),
            enviada=enviada,
            assumiu=assumida_agora,
        )
        return ResultadoManual(
            lead_id=lead.id,
            mensagem_id=mensagem.id,
            enviada=enviada,
            assumida=True,
            motivo="mensagem enviada" if enviada else (mensagem.erro or "falha ao enviar"),
        )

    def devolver_para_ia(self, lead: Lead, autor: User) -> bool:
        """Devolve a conversa ao agente. Assumir nao pode ser porta sem volta.

        Sem isto, um clique errado calaria a cadencia daquele lead para sempre
        — e o usuario nao teria como perceber, porque a ausencia de mensagem
        nao aparece em lugar nenhum.
        """
        if lead.assumido_em is None:
            return False
        lead.assumido_em = None
        self.session.flush()
        self.audit.registrar(
            evento=TipoEvento.LEAD_TRANSICAO,
            entidade_tipo="lead",
            entidade_id=lead.id,
            dados={"acao": "devolvida_para_ia", "autor": str(autor.id)},
            ator=Ator.USUARIO,
            user_id=lead.user_id,
        )
        log.info("conversa_devolvida_para_ia", lead_id=str(lead.id))
        return True

    def _assunto_de_resposta(self, campanha: Campaign | None) -> str:
        """"Re:" do servico da campanha, cortado em palavra inteira.

        Cortar em contagem de caractere produzia "Re: manutencao predial
        preventiva: eletrica, hidraulica e climat" — a linha que a pessoa le
        antes de decidir se abre.
        """
        if campanha is None:
            return "Re: sua mensagem"
        servico = campanha.servico.strip()
        if len(servico) > 60:
            # As reticencias nao sao enfeite: sem elas o corte cai no meio de
            # uma enumeracao e o assunto termina em "hidraulica e", que parece
            # erro de digitacao em vez de texto cortado.
            servico = servico[:60].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
        return f"Re: {servico}"

    # -- auxiliares -----------------------------------------------------------
    def classificar(self, texto: str, lead: Lead | None = None) -> Intencao:
        """Sinal lexical primeiro; LLM so quando o texto e ambiguo.

        A ordem economiza chamada paga e, mais importante, tira o caso critico
        (opt-out) das maos do modelo: "me tire da lista" nao pode depender de
        interpretacao.
        """
        direto = classificar_por_sinal(texto)
        if direto is not None:
            return direto

        # Sem sinal claro, o modelo decide — mas sobre a RESPOSTA NOVA, nao
        # sobre o historico citado colado embaixo. O opt-out ja foi procurado no
        # texto inteiro em `classificar_por_sinal` acima, entao estreitar o
        # escopo aqui nao arrisca perder um pedido de saida. Mesma normalizacao
        # do sinal lexical (QP, HTML, os invisiveis e o NFC) para o modelo nao
        # ver tag, entidade, largura-zero nem acento decomposto em vez de texto.
        texto = decodificar_quoted_printable(texto)
        texto = html_para_texto(texto)
        texto = remover_invisiveis(texto)
        texto = recompor_acentos(texto)
        novo = remover_historico_citado(texto) or texto
        resposta = self.portas.llm.completar(
            LLMRequest(
                system=(
                    "Voce classifica respostas de prospeccao B2B. Responda com UMA "
                    "palavra entre: interesse, duvida, objecao, recusa, "
                    "pedido_opt_out, pedido_humano, ausencia."
                ),
                mensagens=[LLMMessage(role="user", content=novo[:2000])],
                tarefa="classificar_resposta",
                contexto={"texto": novo[:2000]},
            )
        )
        bruto = _normalizar(resposta.texto).split()
        for palavra in bruto:
            try:
                return Intencao(palavra.strip(".,;:!?"))
            except ValueError:
                continue
        return Intencao.INDEFINIDA

    def _redigir(self, lead: Lead, campanha: Campaign | None, intencao: Intencao) -> str:
        historico = self._historico(lead)
        resposta = self.portas.llm.completar(
            LLMRequest(
                system=(
                    "Voce responde leads B2B em portugues do Brasil. Seja curto, "
                    "concreto e proponha um proximo passo claro. Nunca invente preco."
                ),
                mensagens=[
                    LLMMessage(
                        role="assistant" if m.direcao is Direcao.SAIDA else "user",
                        content=m.corpo[:1500],
                    )
                    for m in historico[-6:]
                ],
                tarefa="resposta_conversa",
                contexto={
                    "intencao": intencao.value,
                    "nome": lead.nome_fantasia or lead.razao_social or "equipe",
                    "servico": campanha.servico if campanha else "nosso servico",
                    "municipio": lead.municipio or "sua regiao",
                    "porte": (
                        lead.porte.value if hasattr(lead.porte, "value") else str(lead.porte)
                    ),
                },
            )
        )
        return resposta.texto

    def _proxima_ordem(self, lead: Lead) -> int:
        """Proximo numero na conversa daquele lead."""
        atual = self.session.execute(
            select(func.coalesce(func.max(Message.ordem), 0)).where(Message.lead_id == lead.id)
        ).scalar_one()
        return int(atual) + 1

    def _historico(self, lead: Lead) -> list[Message]:
        return list(
            self.session.execute(
                select(Message)
                .where(Message.lead_id == lead.id)
                .order_by(Message.ordem, Message.created_at)
            )
            .scalars()
            .all()
        )
