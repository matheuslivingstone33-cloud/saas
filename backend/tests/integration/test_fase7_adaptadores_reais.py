"""FASE 7 — testes de CONTRATO dos adaptadores reais, sem nenhuma chave.

O ponto destes testes: provar que o codigo que vai falar com Google, Anthropic,
AWS, Meta e Stripe monta o payload certo e le a resposta certa — ANTES de a
primeira chave existir. O transporte e um httpx.MockTransport (nunca sai da
maquina) e os SDKs sao substituidos por dublês que gravam o que receberam.

Sem isso, a Fase 7 vira "preencher a chave e torcer".
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.adapters.real.anthropic_llm import AnthropicAdapter
from app.adapters.real.anthropic_search import AnthropicWebSearchAdapter
from app.adapters.real.bsp_whatsapp import BSPAdapter
from app.adapters.real.google_places import GooglePlacesAdapter
from app.adapters.real.ses_email import (
    RetornoSES,
    SESAdapter,
    classificar_falha_ses,
    classificar_retorno_ses,
    url_de_confirmacao_sns,
)
from app.adapters.real.stripe_billing import StripeAdapter
from app.core.config import Settings
from app.core.errors import BloqueadoPorCompliance, ProviderNotConfigured
from app.core.http_client import HttpClient
from app.ports.dto import EmailMessage, LLMMessage, LLMRequest, PlacesQuery, WhatsAppMessage
from app.services.cost import CostRecorder, MemoryCostSink
from app.services.entregabilidade import TipoRetorno


def _settings(**extra: Any) -> Settings:
    base = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "google_maps_api_key": "chave-de-teste",
        "anthropic_api_key": "chave-de-teste",
        "openai_api_key": "chave-de-teste",
        "aws_access_key_id": "AKIATESTE",
        "aws_secret_access_key": "segredo",
        "aws_region": "us-east-1",
        "ses_from_email": "contato@exemplo.com.br",
        "whatsapp_bsp_token": "token",
        "whatsapp_phone_id": "123456",
        "stripe_secret_key": "sk_test_x",
    }
    base.update(extra)
    return Settings(**base)


def _http(handler, sink: MemoryCostSink, provedor: str) -> HttpClient:  # noqa: ANN001
    return HttpClient(
        provedor,
        modo="real",
        settings=_settings(),
        cost=CostRecorder(sink),
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )


# =============================================================================
# Google Places
# =============================================================================
RESPOSTA_PLACES = {
    "places": [
        {
            "id": "ChIJ_exemplo",
            "displayName": {"text": "Boa Compra Supermercados", "languageCode": "pt-BR"},
            "formattedAddress": "Av. Santos Dumont, 3300 - Papicu, Fortaleza - CE",
            "internationalPhoneNumber": "+55 85 3344-5566",
            "websiteUri": "https://boacompra.com.br",
            "location": {"latitude": -3.7325, "longitude": -38.4784},
            "types": ["supermarket", "store"],
            "rating": 4.3,
            "userRatingCount": 2140,
        },
        {
            "id": "ChIJ_residencial",
            "displayName": {"text": "Condominio Residencial Vista Mar"},
            "formattedAddress": "Rua X, 10 - Fortaleza - CE",
            "types": ["premise"],
        },
    ],
    "nextPageToken": "TOKEN_PAGINA_2",
}


def test_places_monta_requisicao_correta() -> None:
    capturado: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["headers"] = dict(request.headers)
        capturado["body"] = request.read().decode()
        return httpx.Response(200, json=RESPOSTA_PLACES)

    sink = MemoryCostSink()
    adaptador = GooglePlacesAdapter(_http(handler, sink, "places"), CostRecorder(sink), _settings())
    resposta = adaptador.buscar(
        PlacesQuery(termo="supermercado", regiao="Fortaleza, CE", max_resultados=20)
    )

    assert capturado["url"].endswith("/places:searchText")
    assert capturado["headers"]["x-goog-api-key"] == "chave-de-teste"
    # Field mask enxuta: cada campo extra muda o SKU cobrado.
    mask = capturado["headers"]["x-goog-fieldmask"]
    assert "places.id" in mask and "places.displayName" in mask
    assert "places.reviews" not in mask
    assert "supermercado em Fortaleza, CE" in capturado["body"]

    assert resposta.modo == "real"
    assert resposta.proximo_token == "TOKEN_PAGINA_2"
    primeiro = resposta.itens[0]
    assert primeiro.place_id == "ChIJ_exemplo"
    assert primeiro.nome == "Boa Compra Supermercados"
    assert primeiro.telefone == "+55 85 3344-5566"
    assert primeiro.latitude == pytest.approx(-3.7325)
    assert primeiro.total_avaliacoes == 2140


def test_places_registra_custo_no_balde_1() -> None:
    sink = MemoryCostSink()
    adaptador = GooglePlacesAdapter(
        _http(lambda _r: httpx.Response(200, json=RESPOSTA_PLACES), sink, "places"),
        CostRecorder(sink),
        _settings(),
    )
    adaptador.buscar(PlacesQuery(termo="hotel", regiao="Fortaleza"))
    eventos = [e for e in sink.eventos if e.provedor == "places"]
    assert len(eventos) == 1
    assert eventos[0].balde == 1
    assert eventos[0].modo == "real"
    assert eventos[0].valor_micros == 32_000


def test_places_aplica_termos_negativos_na_resposta() -> None:
    sink = MemoryCostSink()
    adaptador = GooglePlacesAdapter(
        _http(lambda _r: httpx.Response(200, json=RESPOSTA_PLACES), sink, "places"),
        CostRecorder(sink),
        _settings(),
    )
    resposta = adaptador.buscar(
        PlacesQuery(termo="supermercado", regiao="Fortaleza", excluir_termos=["residencial"])
    )
    assert [i.place_id for i in resposta.itens] == ["ChIJ_exemplo"]


def test_places_campo_nulo_no_meio_nao_derruba_a_resposta_inteira() -> None:
    """Um place com `types: null` no meio nao pode estourar a conversao e levar
    junto os resultados bons da mesma resposta.

    O mock devolve `types` como lista limpa; o Google real manda a chave PRESENTE
    com valor `null`. `list(bruto.get("types", []))` so usa o default `[]` quando
    a chave esta AUSENTE — com valor `null` vira `list(None)` -> TypeError. Esse
    erro nao e nenhum dos que `executar_plano` intercepta (RateLimited/Upstream/
    Circuit), entao sobe e ABORTA a rodada, perdendo os leads ja achados e o SKU
    ja gasto. Um resultado sujo entre 20 nao pode custar a rodada."""
    resposta = {
        "places": [
            {
                "id": "ChIJ_bom",
                "displayName": {"text": "Hotel Boa Vista"},
                "formattedAddress": "Rua A, 1 - Fortaleza - CE",
                "types": ["lodging"],
            },
            {  # sujo: chaves presentes, valores null (formato real, nao do mock)
                "id": "ChIJ_sujo",
                "displayName": {"text": "Clinica Sao Lucas"},
                "types": None,
                "location": None,
            },
        ]
    }
    sink = MemoryCostSink()
    adaptador = GooglePlacesAdapter(
        _http(lambda _r: httpx.Response(200, json=resposta), sink, "places"),
        CostRecorder(sink),
        _settings(),
    )
    itens = adaptador.buscar(PlacesQuery(termo="hotel", regiao="Fortaleza")).itens
    assert [i.place_id for i in itens] == ["ChIJ_bom", "ChIJ_sujo"]
    assert itens[1].tipos == []  # null normalizado, sem crash


def test_places_place_sem_id_nem_nome_nao_quebra_a_conversao() -> None:
    """`id` e `displayName` ausentes ou `null` nao podem virar ValidationError.

    `place_id` e `nome` sao `str` OBRIGATORIOS no DTO. `bruto.get("id", "")`
    devolve `None` quando a chave vem com valor `null` (o default so vale para
    chave ausente), e `PlaceResult(place_id=None)` estoura na validacao. Um place
    degenerado assim vira strings vazias — o filtro B2B a jusante descarta o
    registro sem nome —, mas a conversao em si nao pode derrubar a resposta."""
    resposta = {"places": [{"id": None, "displayName": None, "types": None, "location": None}]}
    sink = MemoryCostSink()
    adaptador = GooglePlacesAdapter(
        _http(lambda _r: httpx.Response(200, json=resposta), sink, "places"),
        CostRecorder(sink),
        _settings(),
    )
    itens = adaptador.buscar(PlacesQuery(termo="x", regiao="y")).itens
    assert len(itens) == 1
    assert itens[0].place_id == ""
    assert itens[0].nome == ""
    assert itens[0].tipos == []


def test_places_nulo_no_topo_da_resposta_nao_derruba_a_rodada() -> None:
    """`"places": null` no topo da resposta nao pode virar `list(None)`.

    E o mesmo formato "chave presente com valor null" que ja derrubava os campos
    internos (corrigido em 16/09 com `... or <default>`), so que um nivel acima,
    em `buscar`. `dados.get("places", [])` so cai no default `[]` quando a chave
    esta AUSENTE; com valor `null` devolve `None`, e o list comprehension estoura
    `TypeError`. Esse erro nao e nenhum dos que `executar_plano` intercepta
    (RateLimited/Upstream/Circuit), entao sobe e ABORTA a rodada, perdendo os
    leads ja achados nas consultas anteriores e o SKU ja gasto. Uma resposta sem
    resultado tem que virar zero leads, nao um crash — e a doc do Text Search diz
    que vazio costuma vir como `{}`, mas o formato `null` nao pode custar a rodada."""
    resposta = {"places": None, "nextPageToken": None}
    sink = MemoryCostSink()
    adaptador = GooglePlacesAdapter(
        _http(lambda _r: httpx.Response(200, json=resposta), sink, "places"),
        CostRecorder(sink),
        _settings(),
    )
    resultado = adaptador.buscar(PlacesQuery(termo="hotel", regiao="Fortaleza"))
    assert resultado.itens == []
    assert resultado.proximo_token is None


def test_places_grampeia_raio_no_maximo_da_api() -> None:
    """Raio acima de 50 km responde 400 (INVALID_ARGUMENT) e derruba a consulta.

    `maxResultCount` ja e grampeado (`min(20, ...)`); o raio do `locationBias`
    nao era. Ele vem do filtro do usuario (`raio_km`) SEM teto, e a Places API
    (New) so aceita raio de circulo entre 0 e 50.000 m — acima disso responde
    400 e mata a consulta inteira. No mock isso nunca aparece porque o raio e
    ignorado. Grampeamos na fronteira com o Google, no maximo que a API aceita."""
    capturado: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["body"] = json.loads(request.read())
        return httpx.Response(200, json=RESPOSTA_PLACES)

    sink = MemoryCostSink()
    adaptador = GooglePlacesAdapter(_http(handler, sink, "places"), CostRecorder(sink), _settings())
    adaptador.buscar(
        PlacesQuery(
            termo="hotel",
            regiao="Fortaleza, CE",
            latitude=-3.73,
            longitude=-38.52,
            raio_m=100_000,  # 100 km: acima do teto de 50 km da API
        )
    )
    raio = capturado["body"]["locationBias"]["circle"]["radius"]
    assert raio == 50_000.0, "raio acima do maximo da API tem que ser grampeado, nao mandado cru"


def test_places_raio_dentro_do_limite_passa_intacto() -> None:
    """Um raio valido (e o default) nao pode ser mexido pelo grampo."""
    capturado: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["body"] = json.loads(request.read())
        return httpx.Response(200, json=RESPOSTA_PLACES)

    sink = MemoryCostSink()
    adaptador = GooglePlacesAdapter(_http(handler, sink, "places"), CostRecorder(sink), _settings())
    adaptador.buscar(
        PlacesQuery(
            termo="hotel", regiao="Fortaleza", latitude=-3.73, longitude=-38.52, raio_m=15_000
        )
    )
    assert capturado["body"]["locationBias"]["circle"]["radius"] == 15_000.0


def test_places_sem_chave_falha_alto() -> None:
    with pytest.raises(ProviderNotConfigured):
        GooglePlacesAdapter(
            HttpClient("places", modo="real"), None, _settings(google_maps_api_key="")
        )


# =============================================================================
# Anthropic — LLM e loop de tool use
# =============================================================================
class _Bloco(SimpleNamespace):
    pass


class _RespostaFake(SimpleNamespace):
    pass


class _MessagesFake:
    def __init__(self, respostas: list[Any]) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[dict] = []

    def create(self, **kwargs: Any):  # noqa: ANN201
        self.chamadas.append(kwargs)
        return self.respostas.pop(0)


class _ClienteFake:
    def __init__(self, respostas: list[Any]) -> None:
        self.messages = _MessagesFake(respostas)


def _ultimo_tool_result(mensagens: list[dict]) -> dict:
    """Acha o ultimo bloco tool_result devolvido ao modelo."""
    for msg in reversed(mensagens):
        conteudo = msg.get("content")
        if msg.get("role") == "user" and isinstance(conteudo, list):
            blocos = [b for b in conteudo if isinstance(b, dict) and b.get("type") == "tool_result"]
            if blocos:
                return blocos[0]
    raise AssertionError("nenhum tool_result foi devolvido ao modelo")


def _resposta_texto(texto: str, entrada: int = 100, saida: int = 50, stop: str = "end_turn"):  # noqa: ANN202
    return _RespostaFake(
        content=[_Bloco(type="text", text=texto)],
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=entrada, output_tokens=saida),
    )


def test_llm_usa_thinking_adaptativo_e_nao_budget_tokens() -> None:
    """budget_tokens foi removido nesta geracao: enviar isso retorna 400."""
    sink = MemoryCostSink()
    cliente = _ClienteFake([_resposta_texto("Ola, equipe.")])
    adaptador = AnthropicAdapter(
        _http(lambda _r: httpx.Response(200), sink, "llm"),
        CostRecorder(sink),
        _settings(),
        cliente=cliente,
    )
    resposta = adaptador.completar(
        LLMRequest(
            system="Voce escreve e-mails B2B.",
            mensagens=[LLMMessage(role="user", content="Escreva para a Boa Compra")],
            tarefa="email_abordagem",
        )
    )
    chamada = cliente.messages.chamadas[0]
    assert chamada["model"] == "claude-opus-5"
    assert chamada["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in str(chamada)
    assert chamada["output_config"]["effort"]
    assert resposta.texto == "Ola, equipe."
    assert resposta.tokens_entrada == 100 and resposta.tokens_saida == 50

    ia = [e for e in sink.eventos if e.balde == 2]
    assert len(ia) == 2  # input e output, sempre separados


def test_loop_de_tool_use_delega_ao_places_port() -> None:
    """A tool `buscar_empresas` NAO pode chamar a Google direto — usa a porta."""
    chamadas_places: list[str] = []

    class PlacesEspiao:
        def buscar(self, query: PlacesQuery):  # noqa: ANN201
            chamadas_places.append(query.termo)
            from app.ports.dto import PlaceResult, PlacesResponse

            return PlacesResponse(
                itens=[PlaceResult(place_id="p1", nome="Hotel Teste", tipos=["lodging"])],
                modo="real",
            )

    pedido_tool = _RespostaFake(
        content=[
            _Bloco(
                type="tool_use",
                id="toolu_1",
                name="buscar_empresas",
                input={"termo": "hotel", "regiao": "Fortaleza, CE"},
            )
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=200, output_tokens=80),
    )
    final = _resposta_texto(
        '{"termos": ["hotel", "clinica"], "cnaes_alvo": ["5510801"], '
        '"excluir_termos": ["residencial"], "justificativa": "hoteis usam climatizacao"}',
        entrada=300,
        saida=120,
    )

    sink = MemoryCostSink()
    cliente = _ClienteFake([pedido_tool, final])
    adaptador = AnthropicAdapter(
        _http(lambda _r: httpx.Response(200), sink, "llm"),
        CostRecorder(sink),
        _settings(),
        cliente=cliente,
        places=PlacesEspiao(),
    )
    plano = adaptador.orquestrar_descoberta("ar condicionado", "Fortaleza, CE", {"max_termos": 5})

    assert chamadas_places == ["hotel"], "a tool tem que passar pelo PlacesPort"
    assert plano.termos == ["hotel", "clinica"]
    assert plano.cnaes_alvo == ["5510801"]
    assert plano.justificativa
    # tokens das duas voltas somados
    assert plano.tokens_entrada == 500 and plano.tokens_saida == 200

    # A segunda chamada recebeu o tool_result de volta.
    resultado = _ultimo_tool_result(cliente.messages.chamadas[1]["messages"])
    assert resultado["type"] == "tool_result"
    assert resultado["tool_use_id"] == "toolu_1"
    assert "Hotel Teste" in resultado["content"]


def test_loop_declara_web_search_na_versao_corrente() -> None:
    sink = MemoryCostSink()
    cliente = _ClienteFake([_resposta_texto('{"termos": []}')])
    adaptador = AnthropicAdapter(
        _http(lambda _r: httpx.Response(200), sink, "llm"),
        CostRecorder(sink),
        _settings(),
        cliente=cliente,
    )
    adaptador.orquestrar_descoberta("servico", "Fortaleza", {})
    ferramentas = cliente.messages.chamadas[0]["tools"]
    tipos = {f.get("type") for f in ferramentas}
    assert "web_search_20260209" in tipos, "variante antiga (20250305) e de modelos anteriores"
    nomes = {f.get("name") for f in ferramentas}
    assert "buscar_empresas" in nomes


def test_erro_de_ferramenta_volta_como_tool_result_com_is_error() -> None:
    class PlacesQuebrado:
        def buscar(self, query: PlacesQuery):  # noqa: ANN201, ARG002
            raise RuntimeError("cota estourada")

    pedido = _RespostaFake(
        content=[
            _Bloco(type="tool_use", id="t1", name="buscar_empresas",
                   input={"termo": "x", "regiao": "y"})
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    sink = MemoryCostSink()
    cliente = _ClienteFake([pedido, _resposta_texto('{"termos": ["x"]}')])
    adaptador = AnthropicAdapter(
        _http(lambda _r: httpx.Response(200), sink, "llm"),
        CostRecorder(sink),
        _settings(),
        cliente=cliente,
        places=PlacesQuebrado(),
    )
    plano = adaptador.orquestrar_descoberta("servico", "regiao", {})
    resultado = _ultimo_tool_result(cliente.messages.chamadas[1]["messages"])
    assert resultado["is_error"] is True
    assert "cota estourada" in resultado["content"]
    assert plano.termos == ["x"], "o loop continua mesmo com ferramenta falhando"


def test_json_do_modelo_em_cerca_de_codigo_e_lido() -> None:
    sink = MemoryCostSink()
    cliente = _ClienteFake([_resposta_texto('```json\n{"termos": ["padaria"]}\n```')])
    adaptador = AnthropicAdapter(
        _http(lambda _r: httpx.Response(200), sink, "llm"),
        CostRecorder(sink),
        _settings(),
        cliente=cliente,
    )
    assert adaptador.orquestrar_descoberta("s", "r", {}).termos == ["padaria"]


def test_embeddings_mantem_384_dimensoes() -> None:
    """O schema pgvector e vector(384) desde a Fase 0: nao pode mudar."""
    capturado: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        capturado.update(_json.loads(request.read()))
        return httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1] * 384}],
                "usage": {"total_tokens": 7},
            },
        )

    sink = MemoryCostSink()
    adaptador = AnthropicAdapter(
        _http(handler, sink, "llm"), CostRecorder(sink), _settings()
    )
    resposta = adaptador.embutir(["padaria industrial"])
    assert capturado["dimensions"] == 384
    assert len(resposta.vetores[0]) == 384


# =============================================================================
# Anthropic — web search
# =============================================================================
def test_web_search_conta_buscas_para_cobrar() -> None:
    resposta = _RespostaFake(
        content=[
            _Bloco(
                type="web_search_tool_result",
                content=[SimpleNamespace(title="Hotel X anuncia reforma", url="https://a.com")],
            ),
            _Bloco(type="text", text="Hotel X anuncia reforma (a.com)"),
        ],
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=500,
            output_tokens=120,
            server_tool_use=SimpleNamespace(web_search_requests=2),
        ),
    )
    sink = MemoryCostSink()
    adaptador = AnthropicWebSearchAdapter(
        _http(lambda _r: httpx.Response(200), sink, "search"),
        CostRecorder(sink),
        _settings(),
        cliente=_ClienteFake([resposta]),
    )
    saida = adaptador.buscar("Hotel X Fortaleza")

    assert saida.buscas_realizadas == 2
    assert saida.resultados[0].titulo.startswith("Hotel X")
    busca = next(e for e in sink.eventos if e.operacao == "web_search")
    assert busca.balde == 2
    assert busca.valor_micros == 20_000  # 2 buscas x US$0,01


def test_web_search_com_erro_nao_quebra() -> None:
    """Erro de server tool vem com HTTP 200 e content OBJETO, nao lista."""
    resposta = _RespostaFake(
        content=[
            _Bloco(type="web_search_tool_result", content={"error_code": "max_uses_exceeded"}),
            _Bloco(type="text", text="SEM SINAL"),
        ],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=3),
    )
    sink = MemoryCostSink()
    adaptador = AnthropicWebSearchAdapter(
        _http(lambda _r: httpx.Response(200), sink, "search"),
        CostRecorder(sink),
        _settings(),
        cliente=_ClienteFake([resposta]),
    )
    saida = adaptador.buscar("empresa qualquer")
    assert saida.resultados == []


# =============================================================================
# SES
# =============================================================================
class _SESFake:
    def __init__(self, erro: Exception | None = None) -> None:
        self.erro = erro
        self.chamadas: list[dict] = []

    def send_email(self, **kwargs: Any) -> dict:
        self.chamadas.append(kwargs)
        if self.erro:
            raise self.erro
        return {"MessageId": "010001-abc"}


def test_ses_envia_com_list_unsubscribe() -> None:
    sink = MemoryCostSink()
    fake = _SESFake()
    adaptador = SESAdapter(
        _http(lambda _r: httpx.Response(200), sink, "email"),
        CostRecorder(sink),
        _settings(),
        cliente=fake,
    )
    resultado = adaptador.enviar(
        EmailMessage(
            para="contato@lead.com.br",
            assunto="Proposta",
            corpo_texto="Ola",
            headers={"List-Unsubscribe": "<https://app/desc/abc>"},
            idempotency_key="camp:lead:email",
        )
    )
    assert resultado.sucesso and resultado.provider_message_id == "010001-abc"
    enviado = fake.chamadas[0]
    assert enviado["FromEmailAddress"] == "contato@exemplo.com.br"
    assert enviado["Destination"]["ToAddresses"] == ["contato@lead.com.br"]
    cabecalhos = {h["Name"]: h["Value"] for h in enviado["Content"]["Simple"]["Headers"]}
    assert "List-Unsubscribe" in cabecalhos, "1 clique exige o header"
    custo = next(e for e in sink.eventos if e.provedor == "email")
    assert custo.balde == 1


@pytest.mark.parametrize(
    "codigo,mensagem,esperado",
    [
        # `MessageRejected` cru e AMBIGUO (conteudo? sandbox? supressao?): na
        # duvida NAO suprime, senao uma recusa por conteudo — que atinge TODOS
        # os destinatarios — viraria supressao em massa, um por um.
        ("MessageRejected", "Email rejected due to content policy", "transitoria"),
        # Sandbox: identidade nao verificada NAO e endereco morto. Tratar como
        # destinatario suprimiria todo alvo durante o teste/warmup.
        ("MessageRejected", "Email address is not verified.", "transitoria"),
        # So a lista de supressao da conta (bounce anterior) e do destinatario.
        (
            "MessageRejected",
            "The email address is on the account-level suppression list",
            "destinatario",
        ),
        # Conta/remetente: atinge tudo -> PAUSA, nao suprime.
        ("AccountSuspendedException", "Your account is suspended", "conta"),
        ("SendingPausedException", "Sending is paused for your account", "conta"),
        ("MailFromDomainNotVerifiedException", "MAIL FROM domain not verified", "conta"),
        # Throttle/5xx: passageiro, so tenta de novo depois.
        ("Throttling", "Maximum sending rate exceeded", "transitoria"),
    ],
)
def test_ses_classifica_falha_sincrona_por_escopo(codigo, mensagem, esperado) -> None:  # noqa: ANN001
    assert classificar_falha_ses(codigo, mensagem).value == esperado


def test_ses_falha_sincrona_expoe_escopo_no_detalhes() -> None:
    """O SendService le `escopo_falha`, nao o codigo cru do SES."""
    erro = Exception("The email address is on the account-level suppression list")
    erro.response = {"Error": {"Code": "MessageRejected"}}  # type: ignore[attr-defined]
    sink = MemoryCostSink()
    adaptador = SESAdapter(
        _http(lambda _r: httpx.Response(200), sink, "email"),
        CostRecorder(sink),
        _settings(),
        cliente=_SESFake(erro=erro),
    )
    resultado = adaptador.enviar(
        EmailMessage(para="morto@lead.com.br", assunto="x", corpo_texto="y")
    )
    assert resultado.sucesso is False
    assert resultado.detalhes["escopo_falha"] == "destinatario"
    assert resultado.detalhes["codigo"] == "MessageRejected"


def test_ses_sem_variavel_falha_alto() -> None:
    with pytest.raises(ProviderNotConfigured) as exc:
        SESAdapter(None, None, _settings(ses_from_email=""))
    assert "SES_FROM_EMAIL" in str(exc.value)


# =============================================================================
# SES — retorno assincrono (bounce e reclamacao via SNS)
# =============================================================================
# O envio da 200 e o endereco so bounce-ia DEPOIS, por notificacao SNS. Sem
# traduzir esse formato, a reclamacao de spam nunca chega em `opt_outs` — e e a
# reclamacao que queima a reputacao do dominio. Estes testes provam a traducao
# ANTES de a primeira notificacao real existir.


def _envelope_sns(evento: dict) -> dict:
    """Como o SNS entrega: o evento do SES vira uma STRING JSON em `Message`."""
    return {
        "Type": "Notification",
        "MessageId": "sns-1",
        "TopicArn": "arn:aws:sns:us-east-1:1:retornos",
        "Message": json.dumps(evento),
    }


def _bounce(bounce_type: str, *enderecos: str, sub: str = "General") -> dict:
    return {
        "notificationType": "Bounce",
        "bounce": {
            "bounceType": bounce_type,
            "bounceSubType": sub,
            "bouncedRecipients": [
                {"emailAddress": e, "diagnosticCode": f"smtp; 550 {e} inexistente"}
                for e in enderecos
            ],
        },
        "mail": {"messageId": "010001-msg", "source": "contato@meudominio.com.br"},
    }


def _reclamacao(*enderecos: str, feedback: str = "abuse") -> dict:
    return {
        "notificationType": "Complaint",
        "complaint": {
            "complainedRecipients": [{"emailAddress": e} for e in enderecos],
            "complaintFeedbackType": feedback,
        },
        "mail": {"messageId": "010002-msg"},
    }


def test_sns_bounce_permanente_vira_retorno_permanente() -> None:
    retornos = classificar_retorno_ses(_envelope_sns(_bounce("Permanent", "morto@lead.com.br")))
    assert len(retornos) == 1
    r = retornos[0]
    assert isinstance(r, RetornoSES)
    assert r.tipo is TipoRetorno.PERMANENTE
    assert r.contato == "morto@lead.com.br"
    assert r.provider_message_id == "010001-msg"
    assert "inexistente" in r.diagnostico


def test_sns_bounce_transitorio_nao_suprime() -> None:
    """Caixa cheia hoje nao e endereco morto: o downstream nao pode suprimir."""
    retornos = classificar_retorno_ses(_envelope_sns(_bounce("Transient", "cheia@lead.com.br")))
    assert retornos[0].tipo is TipoRetorno.TRANSITORIO


def test_sns_bounce_undetermined_tratado_como_transitorio() -> None:
    """Na duvida sobre a entrega, nao se queima um endereco possivelmente bom."""
    retornos = classificar_retorno_ses(_envelope_sns(_bounce("Undetermined", "talvez@lead.com.br")))
    assert retornos[0].tipo is TipoRetorno.TRANSITORIO


def test_sns_bounce_de_lote_devolve_um_retorno_por_destinatario() -> None:
    evento = _bounce("Permanent", "a@lead.com.br", "b@lead.com.br", "c@lead.com.br")
    retornos = classificar_retorno_ses(_envelope_sns(evento))
    assert [r.contato for r in retornos] == ["a@lead.com.br", "b@lead.com.br", "c@lead.com.br"]
    assert all(r.tipo is TipoRetorno.PERMANENTE for r in retornos)


def test_sns_reclamacao_vira_reclamacao_com_feedback() -> None:
    retornos = classificar_retorno_ses(_envelope_sns(_reclamacao("chateado@lead.com.br")))
    assert len(retornos) == 1
    assert retornos[0].tipo is TipoRetorno.RECLAMACAO
    assert retornos[0].diagnostico == "abuse"


def test_sns_extrai_endereco_de_nome_com_email() -> None:
    """`Nome <e-mail>` guardado inteiro nao casaria com o e-mail do lead."""
    evento = _bounce("Permanent", "Fulano de Tal <fulano@lead.com.br>")
    assert classificar_retorno_ses(_envelope_sns(evento))[0].contato == "fulano@lead.com.br"


def test_sns_aceita_evento_ja_desembrulhado() -> None:
    """Alem do envelope, aceita o evento cru — util para reprocessar de log."""
    retornos = classificar_retorno_ses(_bounce("Permanent", "morto@lead.com.br"))
    assert retornos[0].contato == "morto@lead.com.br"


def test_sns_aceita_formato_de_event_publishing() -> None:
    """Event publishing usa `eventType` no lugar de `notificationType`."""
    evento = {
        "eventType": "Complaint",
        "complaint": {"complainedRecipients": [{"emailAddress": "x@lead.com.br"}]},
        "mail": {"messageId": "ev-1"},
    }
    retornos = classificar_retorno_ses(evento)
    assert retornos[0].tipo is TipoRetorno.RECLAMACAO


def test_sns_delivery_nao_gera_retorno() -> None:
    evento = {"notificationType": "Delivery", "delivery": {}, "mail": {"messageId": "d-1"}}
    assert classificar_retorno_ses(_envelope_sns(evento)) == []


def test_sns_confirmacao_de_inscricao_e_ignorada_mas_expoe_url() -> None:
    confirmacao = {
        "Type": "SubscriptionConfirmation",
        "Message": "You have chosen to subscribe...",
        "SubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&Token=x",
    }
    assert classificar_retorno_ses(confirmacao) == []
    assert url_de_confirmacao_sns(confirmacao).startswith("https://sns.")
    assert url_de_confirmacao_sns(_envelope_sns(_bounce("Permanent", "a@b.com"))) is None


def test_sns_payload_malformado_nunca_quebra() -> None:
    """Um webhook que estoura vira 500, e o SNS reenvia em laco."""
    assert classificar_retorno_ses(None) == []
    assert classificar_retorno_ses({}) == []
    assert classificar_retorno_ses({"Type": "Notification", "Message": "nao e json {"}) == []
    assert classificar_retorno_ses(_bounce("Permanent")) == []  # sem destinatarios


# =============================================================================
# WhatsApp
# =============================================================================
def test_whatsapp_template_bloqueado_por_padrao() -> None:
    sink = MemoryCostSink()
    adaptador = BSPAdapter(
        _http(lambda _r: httpx.Response(200, json={}), sink, "whatsapp"),
        CostRecorder(sink),
        _settings(),
    )
    with pytest.raises(BloqueadoPorCompliance):
        adaptador.enviar(WhatsAppMessage(para="+5585999998888", template="abordagem"))


def test_whatsapp_texto_livre_monta_payload_da_meta() -> None:
    capturado: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        capturado["url"] = str(request.url)
        capturado["body"] = _json.loads(request.read())
        capturado["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    sink = MemoryCostSink()
    adaptador = BSPAdapter(
        _http(handler, sink, "whatsapp"), CostRecorder(sink), _settings()
    )
    resultado = adaptador.enviar(
        WhatsAppMessage(para="(85) 99999-8888", corpo="Oi, retornando seu contato")
    )
    assert resultado.sucesso and resultado.provider_message_id == "wamid.X"
    assert "/123456/messages" in capturado["url"]
    assert capturado["auth"] == "Bearer token"
    assert capturado["body"]["messaging_product"] == "whatsapp"
    assert capturado["body"]["to"] == "5585999998888"


# =============================================================================
# Stripe
# =============================================================================
class _StripeFake:
    def __init__(self) -> None:
        self.criado: dict | None = None
        self.checkout = SimpleNamespace(sessions=self)

    def create(self, params: dict):  # noqa: ANN201
        self.criado = params
        return SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.com/cs_test_123")

    def retrieve(self, sessao_id: str):  # noqa: ANN201
        return SimpleNamespace(id=sessao_id, payment_status="paid")


def test_stripe_cria_checkout_em_brl() -> None:
    sink = MemoryCostSink()
    fake = _StripeFake()
    adaptador = StripeAdapter(
        _http(lambda _r: httpx.Response(200), sink, "billing"),
        CostRecorder(sink),
        _settings(),
        cliente=fake,
    )
    sessao = adaptador.criar_checkout("user-1", "recarga_500", 39_900)
    assert sessao.id == "cs_test_123"
    assert fake.criado["line_items"][0]["price_data"]["currency"] == "brl"
    assert fake.criado["line_items"][0]["price_data"]["unit_amount"] == 39_900
    assert fake.criado["client_reference_id"] == "user-1"
    assert adaptador.confirmar("cs_test_123") is True


# =============================================================================
# Guardrail que sobrevive a Fase 7
# =============================================================================
def test_guard_do_http_client_tambem_bloqueia_em_modo_mock() -> None:
    from app.core.errors import NetworkDisabledInMockMode

    cliente = HttpClient("llm", modo="mock")
    with pytest.raises(NetworkDisabledInMockMode), cliente.guard("qualquer"):
        pass


def test_guard_abre_circuito_apos_falhas_seguidas() -> None:
    from app.core.errors import CircuitOpen

    cliente = HttpClient("llm", modo="real", settings=_settings(), sleep=lambda _s: None)
    for _ in range(cliente.breaker.limite):
        with pytest.raises(RuntimeError), cliente.guard("op"):
            raise RuntimeError("provedor fora do ar")
    with pytest.raises(CircuitOpen), cliente.guard("op"):
        pass
