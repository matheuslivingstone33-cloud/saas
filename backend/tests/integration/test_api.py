"""API HTTP: saude, provedores, campanhas, leads, mensagens, custo e auditoria."""

from __future__ import annotations

from app.models.enums import NivelAutonomia
from app.repositories.misc import UserRepository


def test_health_nao_exige_banco(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_mostra_tudo_em_mock(client, usuario) -> None:
    r = client.get("/v1/health/ready")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["banco"] == "ok"
    assert corpo["tudo_mock"] is True
    assert corpo["provedores"]["places"]["rede_habilitada"] is False


def test_providers_lista_modo_de_cada_porta(client, usuario) -> None:
    r = client.get("/v1/providers")
    assert r.status_code == 200
    provedores = r.json()["provedores"]
    assert set(provedores) == {
        "places",
        "llm",
        "search",
        "email",
        "whatsapp",
        "enrichment",
        "billing",
    }
    assert all(p["modo"] == "mock" for p in provedores.values())


def test_criar_listar_e_executar_campanha(client, usuario, session) -> None:
    r = client.post(
        "/v1/campaigns",
        json={
            "nome": "API - climatizacao",
            "servico": "manutencao de ar condicionado para empresas",
            "regiao": "Fortaleza, CE",
            "meta_leads": 10,
        },
    )
    assert r.status_code == 201, r.text
    campanha = r.json()
    assert campanha["status"] == "rascunho"

    listagem = client.get("/v1/campaigns").json()
    assert listagem["total"] >= 1
    assert listagem["pagina"] == 1
    assert "paginas" in listagem

    execucao = client.post(
        f"/v1/campaigns/{campanha['id']}/run", json={"limite_leads": 3}
    )
    assert execucao.status_code == 200, execucao.text
    resultado = execucao.json()
    assert resultado["descobertos"] == 3
    assert resultado["modo_provedores"]["places"] == "mock"
    assert resultado["custo"]["balde_1_dados"]["eventos"] > 0

    leads = client.get("/v1/leads", params={"campaign_id": campanha["id"]}).json()
    assert leads["total"] == 3
    assert all("provenance" in item for item in leads["itens"])


def test_aprovacao_manual_envia_para_outbox(client, usuario, session, settings) -> None:
    UserRepository(session).assinatura(usuario.id).autonomy_level = NivelAutonomia.ASSISTIDO
    session.flush()

    campanha = client.post(
        "/v1/campaigns",
        json={
            "nome": "API - aprovacao",
            "servico": "manutencao de ar condicionado para empresas",
            "regiao": "Fortaleza, CE",
        },
    ).json()
    client.post(f"/v1/campaigns/{campanha['id']}/run", json={"limite_leads": 3})

    mensagens = client.get(
        "/v1/messages", params={"campaign_id": campanha["id"], "status": "aguardando_aprovacao"}
    ).json()
    assert mensagens["total"] > 0
    alvo = mensagens["itens"][0]
    assert alvo["declaracao_ia"]
    assert alvo["link_descadastro"]

    antes = len(list(settings.outbox_path.glob("*.json")))
    aprovada = client.post(f"/v1/messages/{alvo['id']}/aprovar")
    assert aprovada.status_code == 200, aprovada.text
    assert aprovada.json()["status"] == "enviada"
    assert len(list(settings.outbox_path.glob("*.json"))) == antes + 1

    # aprovar de novo deve falhar: a mensagem ja saiu do estado de aprovacao
    de_novo = client.post(f"/v1/messages/{alvo['id']}/aprovar")
    assert de_novo.status_code == 409


def test_transicao_invalida_de_lead_retorna_409(client, usuario) -> None:
    campanha = client.post(
        "/v1/campaigns",
        json={
            "nome": "API - transicao",
            "servico": "manutencao de ar condicionado para empresas",
            "regiao": "Fortaleza, CE",
        },
    ).json()
    client.post(f"/v1/campaigns/{campanha['id']}/run", json={"limite_leads": 2})
    lead = client.get("/v1/leads", params={"campaign_id": campanha["id"]}).json()["itens"][0]

    permitidas = client.get(f"/v1/leads/{lead['id']}/transicoes").json()
    assert permitidas["atual"] in {"qualificado", "abordado", "descartado", "enfileirado"}

    r = client.post(
        f"/v1/leads/{lead['id']}/transicao",
        json={"status": "convertido", "motivo": "pulo indevido"},
    )
    assert r.status_code == 409
    assert "Transicao invalida" in r.json()["detail"]


def test_custo_e_auditoria_expostos(client, usuario) -> None:
    campanha = client.post(
        "/v1/campaigns",
        json={
            "nome": "API - custo",
            "servico": "manutencao de ar condicionado para empresas",
            "regiao": "Fortaleza, CE",
        },
    ).json()
    client.post(f"/v1/campaigns/{campanha['id']}/run", json={"limite_leads": 2})

    resumo = client.get("/v1/costs/summary", params={"campaign_id": campanha["id"]}).json()
    assert resumo["balde_1_dados"]["eventos"] > 0
    assert resumo["balde_2_ia"]["eventos"] > 0
    assert resumo["total_usd"] >= 0

    custos = client.get("/v1/costs", params={"campaign_id": campanha["id"]}).json()
    assert custos["total"] > 0
    assert {"places", "llm", "enrichment"} & {c["provedor"] for c in custos["itens"]}

    auditoria = client.get("/v1/audit").json()
    assert auditoria["total"] > 0

    integridade = client.get("/v1/audit/integridade").json()
    assert integridade["integra"] is True


def test_paginacao_respeita_limite(client, usuario) -> None:
    campanha = client.post(
        "/v1/campaigns",
        json={
            "nome": "API - paginacao",
            "servico": "manutencao de ar condicionado para empresas",
            "regiao": "Fortaleza, CE",
        },
    ).json()
    client.post(f"/v1/campaigns/{campanha['id']}/run", json={"limite_leads": 3})

    pagina = client.get("/v1/leads", params={"por_pagina": 2, "pagina": 1}).json()
    assert len(pagina["itens"]) <= 2
    assert pagina["paginas"] >= 2

    excedente = client.get("/v1/leads", params={"por_pagina": 9999})
    assert excedente.status_code == 422  # limite maximo aplicado pela API


def test_onboarding_salva_a_regiao_e_a_busca_nao_pergunta_de_novo(client, usuario) -> None:
    """O onboarding perguntava a regiao e jogava fora.

    O usuario respondia empresa, servico E regiao e, na tela seguinte, a busca
    abria em branco — como se nada tivesse sido respondido. Agora os tres ficam
    no perfil, e e de la que a busca se preenche.
    """
    antes = client.get("/v1/me").json()
    assert "regiao_padrao" in antes, "o perfil precisa devolver a regiao"

    r = client.patch(
        "/v1/me",
        json={
            "empresa": "Refrigeracao Ceara Servicos",
            "servico_padrao": "manutencao preventiva de ar condicionado para empresas",
            "regiao_padrao": "Fortaleza, CE",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["regiao_padrao"] == "Fortaleza, CE"
    assert r.json()["onboarding_completo"] is True

    depois = client.get("/v1/me").json()
    assert depois["regiao_padrao"] == "Fortaleza, CE"
    assert depois["servico_padrao"].startswith("manutencao preventiva")
