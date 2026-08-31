"""Devolve o banco de desenvolvimento ao estado de seed.

Serve para quando os dados de demonstracao ficam sujos — por execucao repetida,
por teste manual, ou pelo residuo de um bug. Nao e ferramenta de producao: em
producao dado de cliente nao se apaga por conveniencia.

    python scripts/limpar_demo.py            # mostra o que seria apagado
    python scripts/limpar_demo.py --aplicar  # apaga de verdade

O que apaga: leads, mensagens, eventos de custo, campanhas geradas e a trilha
de auditoria correspondente.

O que PRESERVA: usuario, assinatura, base de CNAEs do Cerebro, opt-outs e as
duas campanhas de exemplo do seed — recolocadas em rascunho, prontas para rodar.

Os opt-outs ficam de proposito: sao pedidos de exclusao de titular. Apagar um
opt-out para "limpar a demo" seria voltar a contatar quem pediu para nao ser
contatado — exatamente o erro que o produto existe para nao cometer.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from app.db.session import session_scope  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
from app.models.cost_event import CostEvent  # noqa: E402
from app.models.credit_ledger import CreditLedger  # noqa: E402
from app.models.enums import StatusCampanha, TipoCredito  # noqa: E402
from app.models.lead import Lead  # noqa: E402
from app.models.message import Message  # noqa: E402
from app.models.opt_out import OptOut  # noqa: E402
from app.models.user import Subscription  # noqa: E402

#: Eventos de auditoria ligados ao ciclo de campanha. A auditoria de opt-out e
#: de direitos do titular NAO entra aqui: e prova de conformidade.
EVENTOS_DE_CAMPANHA = (
    "dado_coletado",
    "lead_transicao",
    "campanha_transicao",
    "mensagem_gerada",
    "mensagem_aprovada",
    "mensagem_enviada",
    "mensagem_bloqueada",
    "decisao_ia",
)


def contar(session) -> dict[str, int]:  # noqa: ANN001
    def n(modelo) -> int:  # noqa: ANN001
        return int(session.execute(select(func.count()).select_from(modelo)).scalar_one())

    return {
        "leads": n(Lead),
        "mensagens": n(Message),
        "eventos_de_custo": n(CostEvent),
        "campanhas": n(Campaign),
        "auditoria": n(AuditLog),
        "opt_outs": n(OptOut),
    }


def main() -> int:
    aplicar = "--aplicar" in sys.argv

    with session_scope() as session:
        antes = contar(session)
        print("Antes:")
        for chave, valor in antes.items():
            print(f"  {chave:18} {valor}")

        if not aplicar:
            print(
                "\nNada foi alterado. Rode com --aplicar para limpar de verdade.\n"
                "Preservados sempre: usuario, assinatura, CNAEs, opt-outs."
            )
            return 0

        # Ordem importa: filhos antes dos pais, por causa das chaves estrangeiras.
        session.execute(delete(Message))
        session.execute(delete(CostEvent))
        session.execute(delete(Lead))
        session.execute(
            delete(AuditLog).where(AuditLog.evento.in_(EVENTOS_DE_CAMPANHA))
        )
        session.execute(
            delete(CreditLedger).where(
                CreditLedger.tipo.in_(
                    [
                        TipoCredito.CONSUMO_DESCOBERTA,
                        TipoCredito.CONSUMO_IA,
                        TipoCredito.CONSUMO_ENVIO,
                        TipoCredito.OVERAGE,
                    ]
                )
            )
        )

        # Campanhas criadas durante o uso somem; as do seed voltam a rascunho.
        do_seed = {"Climatizacao - Fortaleza", "Manutencao predial - Fortaleza"}
        for campanha in session.execute(select(Campaign)).scalars().all():
            if campanha.nome in do_seed:
                campanha.status = StatusCampanha.RASCUNHO
                campanha.expansao = None
            else:
                session.delete(campanha)

        # Saldo volta ao que o extrato agora diz.
        for assinatura in session.execute(select(Subscription)).scalars().all():
            saldo = int(
                session.execute(
                    select(func.coalesce(func.sum(CreditLedger.quantidade), 0)).where(
                        CreditLedger.user_id == assinatura.user_id
                    )
                ).scalar_one()
            )
            assinatura.saldo_creditos = saldo
            assinatura.leads_consumidos_mes = 0

        session.flush()
        depois = contar(session)

    print("\nDepois:")
    for chave, valor in depois.items():
        print(f"  {chave:18} {valor}")
    print("\nLimpo. Rode uma busca nova para a descoberta encontrar empresas de novo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
