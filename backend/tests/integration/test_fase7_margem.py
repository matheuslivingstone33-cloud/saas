"""FASE 7 — painel de margem: receita reconhecida contra os dois baldes."""

from __future__ import annotations

from app.models.campaign import Campaign
from app.models.enums import NivelAutonomia, Plano, StatusCampanha
from app.repositories.misc import UserRepository
from app.services.margem import MargemService
from app.services.pipeline import PipelineStub

SERVICO = "instalacao e manutencao de ar condicionado para empresas"


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
