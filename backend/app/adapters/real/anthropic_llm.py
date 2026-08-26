"""AnthropicAdapter — LLMPort real. FASE 7, implementado.

Modelo padrao: claude-opus-5 (settings.llm_model).

Usa o SDK oficial da Anthropic — nao reimplementamos o cliente deles. Mas TODA
chamada continua passando pelo HttpClient central via `guard()`, que aplica
rate limit, circuit breaker, log estruturado e `cost_event`. Assim a regra da
arquitetura vale para SDK tambem.

Pontos que mudaram na geracao atual (e que costumam vir errados de memoria):
  * `budget_tokens` NAO existe mais — use `output_config.effort`;
  * pensamento: `thinking={"type": "adaptive"}`;
  * a server tool de busca e `web_search_20260209` (a `web_search_20250305` e a
    variante antiga, para modelos anteriores);
  * prefill de assistant retorna 400.

O loop de tool use vive AQUI dentro, nunca no dominio. O dominio so chama
`LLMPort.orquestrar_descoberta(...)`; o FakeLLM devolve o equivalente
deterministico.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import ProviderNotConfigured, UpstreamError
from app.core.http_client import HttpClient
from app.core.logging import get_logger
from app.ports.dto import DiscoveryPlan, EmbeddingResponse, LLMRequest, LLMResponse
from app.services.cost import CostRecorder, CostSpec

log = get_logger("anthropic")

VERSAO_WEB_SEARCH = "web_search_20260209"
MAX_VOLTAS_TOOL_USE = 6

SISTEMA_DESCOBERTA = """Voce ajuda um prestador de servico B2B no Brasil a
descobrir QUAIS RAMOS DE EMPRESA compram o servico dele.

Regras:
1. Procure quem CONSOME o servico, nunca quem o presta (concorrente).
2. Prefira ramos com necessidade recorrente, nao compra unica.
3. Use `buscar_empresas` para validar se o termo realmente traz empresas na regiao.
4. Use `web_search` no maximo 2 vezes, e so se precisar confirmar um sinal de mercado.
5. Ao terminar, responda APENAS com JSON:
   {"termos": [...], "cnaes_alvo": [...], "excluir_termos": [...], "justificativa": "..."}
"""


def _ferramentas() -> list[dict[str, Any]]:
    return [
        {
            "name": "buscar_empresas",
            "description": (
                "Descobre empresas reais por ramo/regiao via Google Places. "
                "Use para validar se um termo de busca traz resultados uteis."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "ramo ou tipo de negocio"},
                    "regiao": {"type": "string", "description": "cidade e UF"},
                },
                "required": ["termo", "regiao"],
                "additionalProperties": False,
            },
        },
        {"type": VERSAO_WEB_SEARCH, "name": "web_search", "max_uses": 2},
    ]


class AnthropicAdapter:
    provedor = "llm"
    modo = "real"

    def __init__(
        self,
        http: HttpClient | None = None,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
        cliente: Any = None,
        places=None,  # noqa: ANN001 — PlacesPort, injetado pelo registry
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http
        self.cost = cost
        self.modelo = self.settings.llm_model
        self.places = places
        if not self.settings.anthropic_api_key:
            raise ProviderNotConfigured(
                "ANTHROPIC_API_KEY vazia. Preencha o .env antes de LLM_MODE=real."
            )
        self._cliente = cliente

    @property
    def cliente(self):  # noqa: ANN201
        if self._cliente is None:
            import anthropic

            self._cliente = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        return self._cliente

    # -- LLMPort --------------------------------------------------------------
    def completar(self, req: LLMRequest) -> LLMResponse:
        mensagens = [{"role": m.role, "content": m.content} for m in req.mensagens]
        if req.contexto:
            extra = json.dumps(req.contexto, ensure_ascii=False)
            mensagens[-1]["content"] += f"\n\nContexto: {extra}"

        with self._guarda("completar"):
            resposta = self.cliente.messages.create(
                model=self.modelo,
                max_tokens=req.max_tokens,
                system=req.system or "",
                messages=mensagens,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
            )

        texto = _texto_de(resposta)
        entrada, saida = _uso(resposta)
        self._registrar_tokens("completar", entrada, saida)
        return LLMResponse(
            texto=texto,
            modelo=self.modelo,
            tokens_entrada=entrada,
            tokens_saida=saida,
            motivo_parada=getattr(resposta, "stop_reason", "end_turn") or "end_turn",
            modo=self.modo,
        )

    def embutir(self, textos: list[str]) -> EmbeddingResponse:
        """Embeddings de 384 dimensoes.

        A Anthropic nao expoe endpoint de embedding. Usamos
        text-embedding-3-small com `dimensions=384` para NAO mexer no schema do
        pgvector (a coluna e vector(384) desde a Fase 0).
        """
        if not self.settings.openai_api_key:
            raise ProviderNotConfigured(
                "OPENAI_API_KEY vazia: necessaria para embeddings de 384 dimensoes. "
                "Alternativa: apontar para outro provedor mantendo dimensions=384."
            )
        corpo = {
            "model": "text-embedding-3-small",
            "input": textos,
            "dimensions": self.settings.embedding_dim,
        }
        resposta = self.http.request(
            "POST",
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json=corpo,
            operacao="embutir",
            custo=CostSpec(
                provedor=self.provedor,
                operacao="embutir",
                chave_preco="llm.embedding.input",
                quantidade=sum(len(t) for t in textos) / 4,
            ),
        )
        dados = resposta.json or {}
        vetores = [item["embedding"] for item in dados.get("data", [])]
        if len(vetores) != len(textos):
            raise UpstreamError("Provedor de embeddings devolveu quantidade inesperada de vetores")
        return EmbeddingResponse(
            vetores=vetores,
            modelo="text-embedding-3-small-384",
            tokens=int((dados.get("usage") or {}).get("total_tokens", 0)),
            modo=self.modo,
        )

    def orquestrar_descoberta(self, servico: str, regiao: str, contexto: dict) -> DiscoveryPlan:
        """Loop de tool use. O modelo pede `buscar_empresas`; nos executamos."""
        executores = {"buscar_empresas": self._executar_buscar_empresas}
        mensagens: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"Servico prestado: {servico}\nRegiao de atuacao: {regiao}\n"
                    f"Maximo de termos: {contexto.get('max_termos', 6)}"
                ),
            }
        ]

        entrada_total = saida_total = 0
        texto_final = ""

        for volta in range(MAX_VOLTAS_TOOL_USE):
            with self._guarda("orquestrar_descoberta"):
                resposta = self.cliente.messages.create(
                    model=self.modelo,
                    max_tokens=4096,
                    system=SISTEMA_DESCOBERTA,
                    messages=mensagens,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "high"},
                    tools=_ferramentas(),
                )
            entrada, saida = _uso(resposta)
            entrada_total += entrada
            saida_total += saida
            mensagens.append({"role": "assistant", "content": resposta.content})

            chamadas = [
                bloco
                for bloco in resposta.content
                if getattr(bloco, "type", None) == "tool_use" and bloco.name in executores
            ]
            if getattr(resposta, "stop_reason", None) != "tool_use" or not chamadas:
                texto_final = _texto_de(resposta)
                break

            resultados = []
            for bloco in chamadas:
                try:
                    saida_tool = executores[bloco.name](**bloco.input)
                    conteudo = json.dumps(saida_tool, ensure_ascii=False)
                    erro = False
                except Exception as exc:  # a ferramenta falhou: o modelo precisa saber
                    conteudo = json.dumps({"erro": str(exc)[:200]}, ensure_ascii=False)
                    erro = True
                resultados.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": bloco.id,
                        "content": conteudo,
                        **({"is_error": True} if erro else {}),
                    }
                )
            mensagens.append({"role": "user", "content": resultados})
            log.info("tool_use_volta", volta=volta + 1, chamadas=len(chamadas))

        self._registrar_tokens("orquestrar_descoberta", entrada_total, saida_total)
        plano = _extrair_json(texto_final)
        return DiscoveryPlan(
            termos=[str(t) for t in plano.get("termos", [])][: contexto.get("max_termos", 6)],
            regioes=[regiao],
            cnaes_alvo=[str(c) for c in plano.get("cnaes_alvo", [])],
            excluir_termos=[str(t) for t in plano.get("excluir_termos", [])],
            justificativa=str(plano.get("justificativa", "")),
            tokens_entrada=entrada_total,
            tokens_saida=saida_total,
        )

    # -- internos -------------------------------------------------------------
    def _executar_buscar_empresas(self, termo: str, regiao: str) -> dict:
        """A tool `buscar_empresas` DELEGA ao PlacesPort — nunca chama a Google direto."""
        if self.places is None:
            return {"erro": "PlacesPort indisponivel neste contexto"}
        from app.ports.dto import PlacesQuery

        resposta = self.places.buscar(PlacesQuery(termo=termo, regiao=regiao, max_resultados=5))
        return {
            "total": len(resposta.itens),
            "exemplos": [
                {"nome": i.nome, "tipos": i.tipos[:3], "tem_site": bool(i.website)}
                for i in resposta.itens[:5]
            ],
        }

    def _guarda(self, operacao: str):  # noqa: ANN202
        from contextlib import nullcontext

        if self.http is None:  # pragma: no cover - so em teste unitario direto
            return nullcontext()
        return self.http.guard(operacao)

    def _registrar_tokens(self, operacao: str, entrada: int, saida: int) -> None:
        if self.cost is None:
            return
        self.cost.registrar_llm(
            provedor=self.provedor,
            modelo=self.modelo,
            operacao=operacao,
            tokens_entrada=entrada,
            tokens_saida=saida,
            modo=self.modo,
        )


# --- helpers de resposta ------------------------------------------------------
def _texto_de(resposta: Any) -> str:
    partes = [
        bloco.text
        for bloco in getattr(resposta, "content", [])
        if getattr(bloco, "type", None) == "text"
    ]
    return "".join(partes).strip()


def _uso(resposta: Any) -> tuple[int, int]:
    uso = getattr(resposta, "usage", None)
    if uso is None:
        return 0, 0
    return int(getattr(uso, "input_tokens", 0)), int(getattr(uso, "output_tokens", 0))


def _extrair_json(texto: str) -> dict:
    """O modelo pode devolver o JSON cercado de texto ou de cerca de codigo."""
    if not texto:
        return {}
    limpo = texto.strip()
    if limpo.startswith("```"):
        limpo = limpo.split("```")[1]
        limpo = limpo.removeprefix("json").strip()
    inicio, fim = limpo.find("{"), limpo.rfind("}")
    if inicio == -1 or fim == -1:
        return {}
    try:
        return json.loads(limpo[inicio : fim + 1])
    except json.JSONDecodeError:
        log.warning("json_do_modelo_invalido", trecho=limpo[:200])
        return {}
