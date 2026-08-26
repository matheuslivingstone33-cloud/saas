"""FASE 7 — smoke test de UM provedor por vez.

    python scripts/smoke.py places
    python scripts/smoke.py llm
    python scripts/smoke.py search
    python scripts/smoke.py email --para voce@seudominio.com.br
    python scripts/smoke.py whatsapp --para +5585999998888
    python scripts/smoke.py billing
    python scripts/smoke.py enrichment      # dado aberto: roda sem chave
    python scripts/smoke.py todos           # so os que ja estao em modo real

REGRA DA VIRADA: preencha a chave, mude UM `*_MODE` para `real`, rode o smoke
daquele provedor, confira o custo estimado contra o faturado, e so entao passe
para o proximo. Nunca vire todos juntos.

O script recusa rodar se o provedor ainda estiver em modo mock — assim ele nao
"passa" por engano contra o adaptador falso.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.registry import ProviderRegistry  # noqa: E402
from app.core.config import Provider, get_settings  # noqa: E402
from app.core.pricing import micros_para_usd  # noqa: E402
from app.ports.dto import (  # noqa: E402
    EmailMessage,
    LLMMessage,
    LLMRequest,
    PlacesQuery,
    WhatsAppMessage,
)
from app.services.cost import CostRecorder, MemoryCostSink  # noqa: E402

VERDE, VERMELHO, AMARELO, FIM = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


@dataclass
class Resultado:
    provedor: str
    ok: bool
    detalhe: str
    custo_micros: int = 0
    eventos: int = 0


def _registry() -> tuple[ProviderRegistry, MemoryCostSink]:
    sink = MemoryCostSink()
    return ProviderRegistry(cost=CostRecorder(sink)), sink


def _exigir_real(provider: Provider) -> None:
    modo = get_settings().mode_for(provider)
    if modo != "real":
        raise SystemExit(
            f"{AMARELO}[pulado]{FIM} {provider.value} esta em modo '{modo}'. "
            f"Defina {provider.value.upper()}_MODE=real no .env antes do smoke."
        )


# --- um smoke por provedor ----------------------------------------------------
def smoke_places(args) -> Resultado:  # noqa: ANN001
    _exigir_real(Provider.PLACES)
    portas, sink = _registry()
    resposta = portas.places.buscar(
        PlacesQuery(termo=args.termo or "supermercado", regiao=args.regiao, max_resultados=5)
    )
    if not resposta.itens:
        return Resultado("places", False, "a busca real nao devolveu nenhum resultado", 0, 0)
    exemplo = resposta.itens[0]
    detalhe = f"{len(resposta.itens)} resultados. Primeiro: {exemplo.nome} — {exemplo.telefone}"
    return Resultado("places", True, detalhe, sink.total_micros(), len(sink.eventos))


def smoke_llm(args) -> Resultado:  # noqa: ANN001
    _exigir_real(Provider.LLM)
    portas, sink = _registry()
    resposta = portas.llm.completar(
        LLMRequest(
            system="Responda em portugues do Brasil, em uma frase.",
            mensagens=[LLMMessage(role="user", content="Diga que o smoke test passou.")],
            max_tokens=100,
        )
    )
    ok = bool(resposta.texto.strip()) and resposta.tokens_saida > 0
    detalhe = (
        f"modelo={resposta.modelo} tokens={resposta.tokens_entrada}/{resposta.tokens_saida} "
        f"resposta={resposta.texto[:80]!r}"
    )
    return Resultado("llm", ok, detalhe, sink.total_micros(), len(sink.eventos))


def smoke_search(args) -> Resultado:  # noqa: ANN001
    _exigir_real(Provider.SEARCH)
    portas, sink = _registry()
    resposta = portas.search.buscar(args.termo or "Hotel Gran Marquise Fortaleza", max_resultados=3)
    detalhe = f"buscas={resposta.buscas_realizadas} sinais={len(resposta.resultados)}"
    if resposta.resultados:
        detalhe += f" | {resposta.resultados[0].titulo[:70]}"
    return Resultado("search", True, detalhe, sink.total_micros(), len(sink.eventos))


def smoke_email(args) -> Resultado:  # noqa: ANN001
    _exigir_real(Provider.EMAIL)
    if not args.para:
        raise SystemExit("Informe --para com um endereco SEU (nunca um lead real no smoke).")
    portas, sink = _registry()
    resposta = portas.email.enviar(
        EmailMessage(
            para=args.para,
            assunto="[smoke] Prospector AI — teste de entrega",
            corpo_texto=(
                "Este e um teste de entrega do Prospector AI.\n\n"
                "Se voce recebeu, confira no cabecalho: SPF=pass, DKIM=pass, DMARC=pass.\n"
                "Confira tambem se o link de descadastro aparece no cliente de e-mail."
            ),
            headers={"List-Unsubscribe": "<https://app.prospector.local/descadastro/teste>"},
            idempotency_key="smoke-email",
        )
    )
    detalhe = f"id={resposta.provider_message_id} erro={resposta.erro}"
    detalhe += "\n  -> confira SPF/DKIM/DMARC no cabecalho da mensagem recebida"
    return Resultado("email", resposta.sucesso, detalhe, sink.total_micros(), len(sink.eventos))


def smoke_whatsapp(args) -> Resultado:  # noqa: ANN001
    _exigir_real(Provider.WHATSAPP)
    if not args.para:
        raise SystemExit("Informe --para com um numero SEU, que ja tenha te escrito.")
    portas, sink = _registry()
    resposta = portas.whatsapp.enviar(
        WhatsAppMessage(para=args.para, corpo="[smoke] Prospector AI — teste de canal.")
    )
    return Resultado(
        "whatsapp",
        resposta.sucesso,
        f"id={resposta.provider_message_id} erro={resposta.erro}",
        sink.total_micros(),
        len(sink.eventos),
    )


def smoke_billing(args) -> Resultado:  # noqa: ANN001
    _exigir_real(Provider.BILLING)
    portas, sink = _registry()
    sessao = portas.billing.criar_checkout("smoke-user", "recarga_100", 9_900)
    return Resultado(
        "billing",
        bool(sessao.url),
        f"checkout={sessao.id} url={sessao.url[:60]}",
        sink.total_micros(),
        len(sink.eventos),
    )


def smoke_enrichment(args) -> Resultado:  # noqa: ANN001
    """Dado aberto da Receita: nao tem chave e nao tem modo real."""
    portas, sink = _registry()
    total = len(getattr(portas.enrichment, "_por_cnpj", {}))
    amostra = portas.enrichment.buscar("supermercado", uf="CE")
    ok = total > 0
    detalhe = f"{total} CNPJs carregados; busca por 'supermercado/CE' devolveu {len(amostra)}"
    if total < 1000:
        detalhe += f"\n  {AMARELO}aviso{FIM}: dataset pequeno — importe o dump completo em producao"
    return Resultado("enrichment", ok, detalhe, sink.total_micros(), len(sink.eventos))


SMOKES = {
    "places": smoke_places,
    "llm": smoke_llm,
    "search": smoke_search,
    "email": smoke_email,
    "whatsapp": smoke_whatsapp,
    "billing": smoke_billing,
    "enrichment": smoke_enrichment,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test de um provedor por vez (Fase 7).")
    parser.add_argument("provedor", choices=[*SMOKES, "todos"])
    parser.add_argument("--para", help="destinatario do teste (email/whatsapp)")
    parser.add_argument("--termo", help="termo de busca")
    parser.add_argument("--regiao", default="Fortaleza, CE")
    args = parser.parse_args()

    settings = get_settings()
    print(f"\nmodos atuais: {settings.modes()}\n")

    alvos = list(SMOKES) if args.provedor == "todos" else [args.provedor]
    resultados: list[Resultado] = []

    for nome in alvos:
        print(f"--- {nome} ---")
        try:
            resultado = SMOKES[nome](args)
        except SystemExit as exc:
            print(f"{exc}\n")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"{VERMELHO}[falhou]{FIM} {exc}")
            traceback.print_exc(limit=2)
            resultados.append(Resultado(nome, False, str(exc)[:200]))
            print()
            continue

        cor = VERDE if resultado.ok else VERMELHO
        rotulo = "[ok]" if resultado.ok else "[falhou]"
        print(f"{cor}{rotulo}{FIM} {resultado.detalhe}")
        print(
            f"  custo estimado: US$ {micros_para_usd(resultado.custo_micros):.6f} "
            f"em {resultado.eventos} evento(s)"
        )
        print("  -> compare com o valor faturado pelo provedor e ajuste core/pricing.py\n")
        resultados.append(resultado)

    if not resultados:
        print(f"{AMARELO}Nenhum provedor em modo real.{FIM} Vire um *_MODE por vez no .env.")
        return 0

    falhas = [r for r in resultados if not r.ok]
    print("=" * 70)
    print(f"{len(resultados) - len(falhas)}/{len(resultados)} provedores passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
