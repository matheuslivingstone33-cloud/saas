"""Seed: dados minimos para tudo rodar sem provedor real.

    python -m app.db.seed          # popula (idempotente)
    python -m app.db.seed --reset  # limpa e repopula

Cria: 1 usuario demo + assinatura (assistido), creditos iniciais, base pequena
de CNAEs vetorizada (Cerebro), 1 opt-out de exemplo e 2 campanhas em rascunho.
"""

from __future__ import annotations

import json
import sys

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.adapters.mock.fake_llm import FakeLLM
from app.core.config import get_settings
from app.core.ids import now
from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    Canal,
    NivelAutonomia,
    OrigemOptOut,
    Plano,
    StatusAssinatura,
    StatusCampanha,
    TipoContato,
    TipoCredito,
    TipoEvento,
)
from app.models.lead import Lead, RamoCnae
from app.models.message import Message
from app.models.opt_out import OptOut
from app.models.user import Subscription, User
from app.repositories.misc import CreditLedgerRepository, UserRepository
from app.services.audit import AuditService
from app.services.auth import hash_senha

log = get_logger("seed")

EMAIL_DEMO = "demo@prospector.local"
#: Senha do usuario de demonstracao. Existe porque, desde a Etapa 8, nao ha
#: usuario implicito: sem senha o demo seria criado e nao conseguiria entrar em
#: lugar nenhum. E previsivel de proposito — e um seed de desenvolvimento, e o
#: compose de producao roda com `SEED_ON_START=false`.
SENHA_DEMO = "prospector-demo"


def carregar_cnaes() -> list[dict]:
    """Base do Cerebro vinda de data/cnae/cnaes_b2b.json (dado publico da CNAE)."""
    caminho = get_settings().resolve_path("data/cnae/cnaes_b2b.json")
    if not caminho.exists():
        log.warning("base_cnae_ausente", caminho=str(caminho))
        return []
    with caminho.open(encoding="utf-8") as fh:
        return json.load(fh).get("ramos", [])


CAMPANHAS_DEMO = [
    (
        "Climatizacao - Fortaleza",
        "instalacao e manutencao preventiva de ar condicionado para empresas",
        "Fortaleza, CE",
        {"portes": ["me", "epp", "demais"], "raio_km": 25},
    ),
    (
        "Manutencao predial - Fortaleza",
        "manutencao predial preventiva: eletrica, hidraulica e climatizacao",
        "Fortaleza, CE",
        {"portes": ["epp", "demais"], "raio_km": 30},
    ),
]


def limpar(session: Session) -> None:
    for modelo in (Message, Lead, Campaign, OptOut, Subscription, RamoCnae):
        session.execute(delete(modelo))
    session.execute(delete(User))
    log.info("seed_limpo")


def carregar_catalogo(session: Session) -> int:
    """Carrega o catalogo de ramos (base do Cerebro). Idempotente.

    Separado do `semear` porque o catalogo NAO e dado de demonstracao: sem ele
    a busca roda com zero ramos e nao acha cliente nenhum. Em producao o seed
    de demo fica desligado, entao o deploy chama esta funcao sozinha.
    Devolve quantos ramos foram acrescentados.
    """
    existentes = {c for (c,) in session.execute(select(RamoCnae.codigo)).all()}
    faltando = [r for r in carregar_cnaes() if r["codigo"] not in existentes]
    if not faltando:
        return 0
    llm = FakeLLM()
    # DECISAO IMPORTANTE: o vetor do ramo representa O QUE ELE CONSOME,
    # nao o que ele faz. Se vetorizassemos a descricao, o servico
    # "ar condicionado" casaria com o CNAE de quem INSTALA ar condicionado
    # (o concorrente) em vez de quem PRECISA dele (supermercado, hotel).
    textos = [
        "Necessidades recorrentes: {perfil}. Contexto do negocio: {termos}".format(
            perfil=", ".join(r.get("perfil", [])) or r["descricao"],
            termos=", ".join(r.get("termos", [])),
        )
        for r in faltando
    ]
    emb = llm.embutir(textos)
    for ramo, vetor in zip(faltando, emb.vetores, strict=True):
        session.add(
            RamoCnae(
                codigo=ramo["codigo"],
                descricao=ramo["descricao"],
                secao=ramo.get("secao"),
                divisao=ramo["codigo"][:2],
                termos_busca=[*ramo.get("termos", []), *ramo.get("perfil", [])],
                embedding=vetor,
            )
        )
    session.flush()
    log.info("catalogo_carregado", ramos=len(faltando))
    return len(faltando)


def semear(session: Session, reset: bool = False) -> dict[str, int]:
    if reset:
        limpar(session)

    usuarios = UserRepository(session)
    ledger = CreditLedgerRepository(session)
    audit = AuditService(session)
    contadores = {"usuarios": 0, "cnaes": 0, "campanhas": 0, "opt_outs": 0}

    usuario = usuarios.por_email(EMAIL_DEMO)
    if usuario is None:
        usuario = usuarios.add(
            User(
                email=EMAIL_DEMO,
                nome="Usuario Demo",
                senha_hash=hash_senha(SENHA_DEMO),
                empresa="Refrigeracao Ceara Servicos",
                cnpj="00000000000191",
                ativo=True,
                servico_padrao="instalacao e manutencao de ar condicionado para empresas",
            )
        )
        session.add(
            Subscription(
                user_id=usuario.id,
                plano=Plano.TRIAL,
                status=StatusAssinatura.ATIVA,
                autonomy_level=NivelAutonomia.ASSISTIDO,
                saldo_creditos=500,
                teto_leads_mes=100,
                periodo_inicio=now(),
            )
        )
        session.flush()
        ledger.lancar(
            user_id=usuario.id,
            tipo=TipoCredito.CREDITO_INICIAL,
            quantidade=500,
            descricao="Creditos de cortesia do trial",
        )
        audit.registrar(
            evento=TipoEvento.CREDITO_MOVIMENTADO,
            entidade_tipo="usuario",
            entidade_id=usuario.id,
            dados={"tipo": "credito_inicial", "quantidade": 500},
            ator=Ator.SISTEMA,
            user_id=usuario.id,
        )
        contadores["usuarios"] = 1
    elif not usuario.senha_hash:
        # Banco semeado antes da Etapa 8: o demo existe e nao tem senha. Sem
        # isto ele continuaria sem conseguir entrar, e o sintoma seria um login
        # que recusa a senha documentada sem dizer por que.
        usuario.senha_hash = hash_senha(SENHA_DEMO)
        session.flush()
        log.info("senha_demo_definida")

    # --- base do Cerebro (Motor 2) -------------------------------------------
    contadores["cnaes"] = carregar_catalogo(session)

    # --- opt-out de exemplo (guardrail testavel desde a Fase 0) --------------
    contato = "naoquero@exemplo.com.br"
    ja_existe = session.execute(
        select(OptOut).where(OptOut.contato_normalizado == contato)
    ).scalar_one_or_none()
    if ja_existe is None:
        session.add(
            OptOut(
                user_id=None,  # global
                tipo_contato=TipoContato.EMAIL,
                contato=contato,
                contato_normalizado=contato,
                origem=OrigemOptOut.LINK_DESCADASTRO,
                motivo="Exemplo de supressao global usado nos testes",
            )
        )
        contadores["opt_outs"] = 1

    # --- campanhas demo ------------------------------------------------------
    for nome, servico, regiao, filtros in CAMPANHAS_DEMO:
        existe = session.execute(
            select(Campaign).where(Campaign.user_id == usuario.id, Campaign.nome == nome)
        ).scalar_one_or_none()
        if existe is None:
            session.add(
                Campaign(
                    user_id=usuario.id,
                    nome=nome,
                    servico=servico,
                    regiao=regiao,
                    filtros=filtros,
                    status=StatusCampanha.RASCUNHO,
                    canal_padrao=Canal.EMAIL,
                    meta_leads=25,
                )
            )
            contadores["campanhas"] += 1

    session.flush()
    log.info("seed_concluido", **contadores)
    return contadores


def main() -> int:
    reset = "--reset" in sys.argv
    with session_scope() as session:
        contadores = semear(session, reset=reset)
    print(f"seed ok: {contadores}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
