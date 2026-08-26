"""Demo da FASE 0 — fluxo stub ponta a ponta, SEM NENHUMA CHAVE.

    python scripts/demo_fase0.py

Faz:
  1. mostra o modo de cada provedor (tudo mock);
  2. roda uma campanha em modo ASSISTIDO   -> mensagens aguardando aprovacao;
  3. aprova uma mensagem                    -> e-mail vai para outbox/;
  4. roda uma campanha em modo AUTOMATICO  -> dispara sozinho para outbox/;
  5. imprime leads, maquina de estados, custo por balde e integridade da
     trilha de auditoria.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.adapters.registry import ProviderRegistry  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.seed import semear  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
from app.models.cost_event import CostEvent  # noqa: E402
from app.models.enums import NivelAutonomia, StatusCampanha, StatusMensagem  # noqa: E402
from app.models.lead import Lead  # noqa: E402
from app.models.message import Message  # noqa: E402
from app.repositories.leads import LeadRepository  # noqa: E402
from app.repositories.misc import CostEventRepository, UserRepository  # noqa: E402
from app.services.audit import AuditService  # noqa: E402
from app.services.cost import CostRecorder  # noqa: E402
from app.services.pipeline import PipelineStub  # noqa: E402

LINHA = "=" * 78


def titulo(texto: str) -> None:
    print(f"\n{LINHA}\n{texto}\n{LINHA}")


def preparar(session, campanha: Campaign) -> None:
    """Deixa a demo repetivel e independente entre as duas campanhas.

    Limpa TODOS os leads do tenant, nao so os da campanha: o dedup e por tenant,
    entao sem isso a segunda campanha so encontraria empresas ja descobertas
    pela primeira (comportamento correto em producao, mas que esconderia o
    modo automatico na demo).
    """
    session.execute(delete(Message).where(Message.user_id == campanha.user_id))
    session.execute(delete(CostEvent).where(CostEvent.user_id == campanha.user_id))
    session.execute(delete(Lead).where(Lead.user_id == campanha.user_id))
    campanha.status = StatusCampanha.RASCUNHO
    session.flush()


def main() -> int:
    settings = get_settings()

    titulo("1. PROVEDORES — nenhuma chave necessaria")
    diagnostico = ProviderRegistry(settings=settings).diagnostico()
    print(json.dumps(diagnostico, indent=2, ensure_ascii=False))

    with session_scope() as session:
        semear(session)
        usuarios = UserRepository(session)
        usuario = usuarios.por_email("demo@prospector.local")
        assinatura = usuarios.assinatura(usuario.id)
        campanhas = list(
            session.execute(
                select(Campaign).where(Campaign.user_id == usuario.id).order_by(Campaign.nome)
            ).scalars()
        )

        # ---------------------------------------------------------------- 2
        titulo("2. CAMPANHA EM MODO ASSISTIDO (humano aprova antes de sair)")
        assinatura.autonomy_level = NivelAutonomia.ASSISTIDO
        session.flush()
        campanha = campanhas[0]
        preparar(session, campanha)
        portas = ProviderRegistry(
            cost=CostRecorder.para_sessao(session, user_id=usuario.id, campaign_id=campanha.id),
            settings=settings,
        )
        resultado = PipelineStub(session, portas).executar(campanha, limite_leads=3)
        print(json.dumps(resultado.to_dict(), indent=2, ensure_ascii=False))

        leads = LeadRepository(session).listar(usuario.id, campaign_id=campanha.id).itens
        print("\nLeads descobertos e qualificados:")
        for lead in leads:
            print(
                f"  - {lead.razao_social:<45} cnpj={lead.cnpj or '-':<14} "
                f"score={float(lead.score):5.1f} status={lead.status.value}"
            )

        # ---------------------------------------------------------------- 3
        titulo("3. APROVACAO MANUAL -> e-mail gravado em outbox/")
        pendentes = session.execute(
            select(Message).where(
                Message.campaign_id == campanha.id,
                Message.status == StatusMensagem.AGUARDANDO_APROVACAO,
            )
        ).scalars().all()
        print(f"mensagens aguardando aprovacao: {len(pendentes)}")
        if pendentes:
            msg = pendentes[0]
            print(f"\n--- previa da mensagem para {msg.destinatario} ---")
            print(msg.corpo[:400])
            print("--- fim da previa ---")

        # ---------------------------------------------------------------- 4
        titulo("4. CAMPANHA EM MODO AUTOMATICO (agente dispara sozinho)")
        assinatura.autonomy_level = NivelAutonomia.AUTOMATICO
        session.flush()
        campanha2 = campanhas[1]
        preparar(session, campanha2)
        portas2 = ProviderRegistry(
            cost=CostRecorder.para_sessao(session, user_id=usuario.id, campaign_id=campanha2.id),
            settings=settings,
        )
        resultado2 = PipelineStub(session, portas2).executar(campanha2, limite_leads=3)
        print(json.dumps(resultado2.to_dict(), indent=2, ensure_ascii=False))

        # ---------------------------------------------------------------- 5
        titulo("5. CUSTO POR BALDE (1 = dados / 2 = IA) e AUDITORIA")
        resumo = CostEventRepository(session).resumo_por_balde(user_id=usuario.id)
        print(json.dumps(resumo, indent=2, ensure_ascii=False))

        audit = AuditService(session)
        integra, erro = audit.verificar_cadeia()
        print(f"\nregistros de auditoria: {audit.total()}")
        print(f"cadeia de hash integra: {integra} (primeiro erro: {erro})")

    caixa = settings.outbox_path
    arquivos = sorted(p.name for p in caixa.glob("*.json"))
    titulo(f"6. OUTBOX ({caixa.resolve()})")
    for nome in arquivos[-6:]:
        print(f"  - {nome}")
    print(f"\ntotal de e-mails gravados (nenhum enviado de verdade): {len(arquivos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
