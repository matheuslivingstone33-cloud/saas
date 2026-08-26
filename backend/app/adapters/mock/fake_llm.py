"""FakeLLM — implementacao mock do LLMPort, 100% deterministica.

Nao ha aleatoriedade nem rede: a mesma entrada devolve sempre a mesma saida.
Isso e o que permite testar Motor 2 (Cerebro), Motor 3 (Abordagem) e o loop de
orquestracao nas Fases 1-6 sem nenhuma chave.

O adaptador real (Fase 7) implementa o MESMO contrato via SDK da Anthropic,
incluindo o loop de tool use com `buscar_empresas` (PlacesPort) e `web_search`.
"""

from __future__ import annotations

from app.adapters.mock._text import contar_tokens, embutir, tokenizar
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ports.dto import (
    DiscoveryPlan,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
)
from app.services.cost import CostRecorder

log = get_logger("fake_llm")

# Expansoes canonicas por familia de servico — deterministicas e auditaveis.
EXPANSOES: dict[str, dict[str, list[str]]] = {
    "climatizacao": {
        "gatilhos": ["ar", "condicionado", "climatizacao", "refrigeracao", "hvac", "split"],
        "termos": [
            "supermercado",
            "restaurante",
            "hotel",
            "clinica",
            "academia",
            "colegio",
            "distribuidora de frios",
        ],
        "cnaes": ["4711302", "5611201", "5510801", "8630503", "9313100", "8513900", "4634601"],
    },
    "manutencao_predial": {
        "gatilhos": ["predial", "manutencao", "eletrica", "hidraulica", "reforma"],
        "termos": ["hotel", "colegio", "clinica", "edificio comercial", "condominio"],
        "cnaes": ["5510801", "8513900", "8630503", "6822600"],
    },
    "alimentacao": {
        "gatilhos": ["forno", "cozinha", "panificacao", "padaria", "gastronomia"],
        "termos": ["padaria", "restaurante", "lanchonete", "hotel"],
        "cnaes": ["1091102", "5611201", "5611203", "5510801"],
    },
    "logistica": {
        "gatilhos": ["frota", "transporte", "logistica", "veiculo", "caminhao"],
        "termos": ["transportadora", "distribuidora", "industria", "supermercado"],
        "cnaes": ["4930202", "4634601", "2512800", "4711302"],
    },
}

_FAMILIA_PADRAO = "climatizacao"


def _familia(servico: str) -> str:
    tokens = set(tokenizar(servico))
    melhor, pontos = _FAMILIA_PADRAO, 0
    for nome, conf in EXPANSOES.items():
        acertos = len(tokens & set(conf["gatilhos"]))
        if acertos > pontos:
            melhor, pontos = nome, acertos
    return melhor


class FakeLLM:
    """Mock do LLMPort. NUNCA toca a rede."""

    provedor = "llm"
    modo = "mock"

    def __init__(self, cost: CostRecorder | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cost = cost
        self.modelo = "mock"
        self.chamadas: list[LLMRequest] = []

    # -- LLMPort --------------------------------------------------------------
    def completar(self, req: LLMRequest) -> LLMResponse:
        self.chamadas.append(req)
        texto = self._responder(req)
        entrada = contar_tokens((req.system or "") + " ".join(m.content for m in req.mensagens))
        saida = contar_tokens(texto)
        self._custo("completar", entrada, saida)
        return LLMResponse(
            texto=texto,
            modelo=self.modelo,
            tokens_entrada=entrada,
            tokens_saida=saida,
            modo=self.modo,
        )

    def embutir(self, textos: list[str]) -> EmbeddingResponse:
        dim = self.settings.embedding_dim
        vetores = [embutir(t, dim) for t in textos]
        tokens = sum(contar_tokens(t) for t in textos)
        if self.cost is not None:
            self.cost.registrar_llm(
                provedor=self.provedor,
                modelo="embedding",
                operacao="embutir",
                tokens_entrada=tokens,
                tokens_saida=0,
                modo=self.modo,
            )
        return EmbeddingResponse(
            vetores=vetores, modelo="mock-embedding-384", tokens=tokens, modo=self.modo
        )

    def orquestrar_descoberta(self, servico: str, regiao: str, contexto: dict) -> DiscoveryPlan:
        """Equivalente deterministico do loop de tool use do adaptador real."""
        familia = _familia(servico)
        conf = EXPANSOES[familia]
        max_termos = int(contexto.get("max_termos", 5))
        termos = conf["termos"][:max_termos]
        entrada = contar_tokens(servico + regiao)
        saida = contar_tokens(" ".join(termos))
        self._custo("orquestrar_descoberta", entrada, saida)
        log.info("plano_descoberta_mock", familia=familia, termos=termos, regiao=regiao)
        return DiscoveryPlan(
            termos=termos,
            regioes=[regiao],
            cnaes_alvo=conf["cnaes"][:max_termos],
            excluir_termos=["residencial", "particular"],
            justificativa=(
                f"Servico classificado na familia '{familia}'. Foram priorizados ramos B2B "
                f"com necessidade recorrente do servico em {regiao}."
            ),
            tokens_entrada=entrada,
            tokens_saida=saida,
        )

    # -- internos -------------------------------------------------------------
    def _responder(self, req: LLMRequest) -> str:
        ctx = req.contexto or {}
        if req.tarefa == "email_abordagem":
            return self._email(ctx)
        if req.tarefa == "resumo_lead":
            return (
                f"{ctx.get('nome', 'A empresa')} atua em {ctx.get('ramo', 'seu ramo')} "
                f"em {ctx.get('municipio', 'sua regiao')}. "
                f"Porte {ctx.get('porte', 'nao informado')}. "
                "Perfil compativel com o servico ofertado."
            )
        if req.tarefa == "expansao_servico":
            familia = _familia(ctx.get("servico", ""))
            return ", ".join(EXPANSOES[familia]["termos"])
        ultima = req.mensagens[-1].content if req.mensagens else ""
        return f"[mock] {ultima[:280]}"

    def _email(self, ctx: dict) -> str:
        nome = ctx.get("nome", "equipe")
        servico = ctx.get("servico", "nosso servico")
        municipio = ctx.get("municipio", "sua regiao")
        gancho = ctx.get("gancho", "a operacao de voces")
        return (
            f"Ola, equipe da {nome}.\n\n"
            f"Trabalhamos com {servico} atendendo empresas em {municipio}. "
            f"Olhando {gancho}, imagino que uma parada nao programada custe caro por aqui.\n\n"
            "Faz sentido eu enviar uma proposta de avaliacao sem compromisso? "
            "Se preferir, respondo com dois horarios esta semana.\n\n"
            "Abraco."
        )

    def _custo(self, operacao: str, entrada: int, saida: int) -> None:
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
