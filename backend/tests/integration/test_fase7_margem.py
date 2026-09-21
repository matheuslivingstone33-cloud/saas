"""FASE 7 — painel de margem: receita reconhecida contra os dois baldes."""

from __future__ import annotations

from app.models.campaign import Campaign
from app.models.enums import NivelAutonomia, Plano, StatusCampanha, TipoCredito
from app.repositories.misc import UserRepository
from app.services.creditos import CATALOGO, CreditService
from app.services.margem import MargemService
from app.services.pipeline import PipelineStub

SERVICO = "instalacao e manutencao de ar condicionado para empresas"


def _zerar_saldo(session, usuario) -> None:  # noqa: ANN001
    """Zera o saldo por AJUSTE_MANUAL (fora do eixo de consumo/receita)."""
    servico = CreditService(session)
    saldo = servico.ledger.saldo(usuario.id)
    if saldo:
        servico.ledger.lancar(
            user_id=usuario.id,
            tipo=TipoCredito.AJUSTE_MANUAL,
            quantidade=-saldo,
            descricao="zerado no teste",
        )
    session.flush()


def _rodar(session, usuario, portas_db, nome="Margem"):  # noqa: ANN001
    campanha = Campaign(
        user_id=usuario.id,
        nome=nome,
        servico=SERVICO,
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.RASCUNHO,
        autonomy_override=NivelAutonomia.AUTOMATICO,
    )
    session.add(campanha)
    session.flush()
    PipelineStub(session, portas_db).executar(campanha, limite_leads=3)
    return campanha


def test_margem_soma_os_dois_baldes(session, usuario, portas_db) -> None:
    _rodar(session, usuario, portas_db)
    margem = MargemService(session).por_usuario(usuario.id).to_dict()

    assert margem["custo"]["balde_1_dados_usd"] > 0
    assert margem["custo"]["balde_2_ia_usd"] > 0
    assert margem["custo"]["total_usd"] == round(
        margem["custo"]["balde_1_dados_usd"] + margem["custo"]["balde_2_ia_usd"], 6
    )
    assert margem["creditos_consumidos"] > 0
    assert margem["por_lead"]["leads"] > 0
    assert margem["por_lead"]["custo_brl"] > 0


def test_trial_tem_receita_zero_e_margem_negativa(session, usuario, portas_db) -> None:
    """No trial o custo e real e a receita e zero: isso e CAC, nao lucro."""
    _rodar(session, usuario, portas_db, nome="Trial")
    margem = MargemService(session).por_usuario(usuario.id).to_dict()
    assert margem["receita_brl"] == 0.0
    assert margem["margem_brl"] < 0


def test_plano_pago_tem_margem_positiva(session, usuario, portas_db) -> None:
    from app.services.creditos import CATALOGO, CreditService

    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.plano = Plano.PRO
    assinatura.teto_leads_mes = CATALOGO[Plano.PRO].teto_leads_mes
    session.flush()
    CreditService(session).creditar(usuario.id, CATALOGO[Plano.PRO].creditos_mes)

    _rodar(session, usuario, portas_db, nome="Pro")
    margem = MargemService(session).por_usuario(usuario.id).to_dict()

    assert margem["receita_brl"] > 0
    assert margem["margem_brl"] > 0, "no plano Pro cada lead precisa se pagar"
    assert margem["margem_pct"] > 50
    assert margem["por_lead"]["receita_brl"] > margem["por_lead"]["custo_brl"]


def test_overage_conta_receita_pelo_preco_de_overage(session, usuario) -> None:
    """Credito de overage rende o preco de overage, nao o preco-base do plano.

    O painel ja conta o credito de overage como receita reconhecida (esta em
    `CONSUMO`), mas o valorizava pelo preco-base amortizado do plano. O cliente
    paga pelo overage o `overage_centavos_por_credito` do plano — mais caro que o
    credito-base. Valorizar tudo a um preco so subestimava a receita do overage e
    fazia a margem parecer pior do que a real, dentro de um numero que ninguem
    questiona. O preco de overage ja e decidido (esta no catalogo e no painel de
    billing); aqui so aplicamos ele.
    """
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.plano = Plano.PRO
    assinatura.teto_leads_mes = CATALOGO[Plano.PRO].teto_leads_mes
    assinatura.overage_habilitado = True
    session.flush()

    _zerar_saldo(session, usuario)  # sem saldo: todo debito seguinte vira overage

    servico = CreditService(session)
    n = 4
    for _ in range(n):
        servico.debitar(usuario.id, "contato_revelado")
    session.flush()

    catalogo = CATALOGO[Plano.PRO]
    preco_base = (catalogo.preco_centavos / 100) / catalogo.creditos_mes
    preco_overage = catalogo.overage_centavos_por_credito / 100
    assert preco_overage != preco_base, "cenario invalido: precos iguais nao distinguem"

    margem = MargemService(session).por_usuario(usuario.id).to_dict()

    assert margem["creditos_consumidos"] == n
    # Receita pelo preco de OVERAGE, nao pelo preco-base do plano.
    assert margem["receita_brl"] == round(n * preco_overage, 2)
    assert margem["receita_brl"] != round(n * preco_base, 2)


def test_debito_que_cruza_o_teto_nao_valoriza_o_base_como_overage(session, usuario) -> None:
    """Um debito que ATRAVESSA o teto do plano nao pode marcar 100% como overage.

    Com saldo 1 e uma operacao de custo 2 (`sinal_intencao`, overage habilitado),
    1 credito ainda esta DENTRO do plano (base) e so 1 e overage. Marcar o debito
    inteiro como OVERAGE valoriza o credito-base ao preco de overage (mais caro) e
    infla a receita/margem do painel — ficcao, do lado da receita, dentro de um
    numero que ninguem questiona. Nao e decisao de preco: base e overage ja tem
    preco decidido no catalogo; aqui so aplicamos cada um ao credito certo.
    """
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.plano = Plano.PRO
    assinatura.teto_leads_mes = CATALOGO[Plano.PRO].teto_leads_mes
    assinatura.overage_habilitado = True
    session.flush()

    _zerar_saldo(session, usuario)
    servico = CreditService(session)
    servico.creditar(usuario.id, 1, descricao="um credito ainda dentro do plano")

    # custo 2 com saldo 1: 1 credito e base (cabe no plano), 1 e overage.
    servico.debitar(usuario.id, "sinal_intencao")
    session.flush()

    catalogo = CATALOGO[Plano.PRO]
    preco_base = (catalogo.preco_centavos / 100) / catalogo.creditos_mes
    preco_overage = catalogo.overage_centavos_por_credito / 100
    assert preco_overage != preco_base, "cenario invalido: precos iguais nao distinguem"

    margem = MargemService(session).por_usuario(usuario.id).to_dict()

    assert margem["creditos_consumidos"] == 2
    # 1 credito base + 1 overage — NAO 2 x overage.
    assert margem["receita_brl"] == round(preco_base + preco_overage, 2)
    assert margem["receita_brl"] != round(2 * preco_overage, 2)


def test_margem_por_campanha_conta_receita_de_envio_nao_so_de_revelacao(
    session, usuario, portas_db
) -> None:
    """A receita por campanha tem de incluir os creditos de ENVIO/IA, nao so os
    de revelacao.

    `mensagem_enviada` e `sinal_intencao` sao debitados referenciando o id da
    MENSAGEM; `contato_revelado`, o id do LEAD. O filtro da campanha so casava
    ids de lead, entao dropava a receita de envio/IA enquanto o custo da campanha
    era contado inteiro — a margem da campanha aparecia pior do que a real, dentro
    de um numero que ninguem questiona. Mesmo eixo deste radar, do lado da receita.
    """
    from sqlalchemy import func, select

    from app.models.lead import Lead

    # PRO para cada credito consumido ter preco (no trial a receita e zero).
    assinatura = UserRepository(session).assinatura(usuario.id)
    assinatura.plano = Plano.PRO
    assinatura.teto_leads_mes = CATALOGO[Plano.PRO].teto_leads_mes
    session.flush()
    CreditService(session).creditar(usuario.id, CATALOGO[Plano.PRO].creditos_mes)

    campanha = _rodar(session, usuario, portas_db, nome="Campanha unica")

    svc = MargemService(session)
    por_campanha = svc.por_usuario(usuario.id, campanha.id).to_dict()
    do_usuario = svc.por_usuario(usuario.id).to_dict()

    reveladas = int(
        session.execute(
            select(func.count(Lead.id)).where(
                Lead.campaign_id == campanha.id, Lead.revelado_em.is_not(None)
            )
        ).scalar_one()
    )
    # O envio consumiu credito alem da revelacao: ha MAIS credito que revelacoes.
    assert por_campanha["creditos_consumidos"] > reveladas > 0
    # Uma unica campanha: todo consumo do usuario pertence a ela.
    assert por_campanha["creditos_consumidos"] == do_usuario["creditos_consumidos"]
    # Logo a receita da campanha nao pode cair para so-revelacao.
    assert por_campanha["receita_brl"] == do_usuario["receita_brl"] > 0


def test_margem_por_campanha_isola_o_custo(session, usuario, portas_db) -> None:
    primeira = _rodar(session, usuario, portas_db, nome="C1")
    _rodar(session, usuario, portas_db, nome="C2")

    total = MargemService(session).por_usuario(usuario.id).to_dict()
    apenas_uma = MargemService(session).por_usuario(usuario.id, primeira.id).to_dict()

    assert apenas_uma["custo"]["total_usd"] < total["custo"]["total_usd"]
    assert apenas_uma["escopo"] == "campanha"


def test_consolidado_agrega_todos_os_clientes(session, usuario, portas_db) -> None:
    _rodar(session, usuario, portas_db, nome="Consolidado")
    consolidado = MargemService(session).consolidado()

    assert consolidado["global"]["leads"] > 0
    assert consolidado["global"]["custo"]["total_brl"] > 0
    assert consolidado["por_cliente"]
    assert consolidado["taxa_usd_brl"] > 0
    assert "mock" in consolidado["aviso"]


def test_api_expoe_margem(client, usuario, session, portas_db) -> None:
    _rodar(session, usuario, portas_db, nome="API margem")

    r = client.get("/v1/margem")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["custo"]["balde_1_dados_usd"] >= 0
    assert corpo["custo"]["balde_2_ia_usd"] >= 0


def test_margem_consolidada_so_para_quem_opera_o_saas(
    client, usuario, session, portas_db, monkeypatch
) -> None:
    """Receita e custo de TODOS os clientes: era aberta a qualquer conta logada."""
    from app.core.config import get_settings

    _rodar(session, usuario, portas_db, nome="API consolidado")

    monkeypatch.setattr(get_settings(), "admin_emails", "")
    assert client.get("/v1/margem/consolidado").status_code == 404

    admins = f"outra@empresa.com, {usuario.email.upper()}"
    monkeypatch.setattr(get_settings(), "admin_emails", admins)
    consolidado = client.get("/v1/margem/consolidado")
    assert consolidado.status_code == 200
    assert "global" in consolidado.json()
