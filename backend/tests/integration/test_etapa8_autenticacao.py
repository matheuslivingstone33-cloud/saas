"""ETAPA 8 — autenticacao de verdade.

Ate a Etapa 7 o usuario vinha de `X-User-Email`, com fallback no usuario de
seed. O produto inteiro funcionava; so nao havia como saber quem estava
perguntando.

Como nas outras etapas, o grosso destes testes verifica o que o sistema
RECUSA. Autenticacao quebrada nao produz sintoma nenhum — tudo continua
respondendo 200, so que para qualquer um.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from app.models.campaign import Campaign
from app.models.enums import Plano, StatusAssinatura
from app.models.user import Subscription, User
from app.services.auth import (
    MINUTOS_ACESSO,
    TIPO_ACESSO,
    TIPO_RENOVACAO,
    CredencialInvalida,
    SenhaFraca,
    conferir_senha,
    emitir_par,
    hash_senha,
    ler_token,
    verificar_segredo_de_producao,
)
from app.services.webhook import assinar

CADASTRO = {
    "email": "novo@empresa.com.br",
    "nome": "Fulano de Tal",
    "senha": "uma-senha-comprida",
    "empresa": "Refrigeracao Fulano",
}


# --- Cadastro e login --------------------------------------------------------
def test_cadastro_cria_conta_com_assinatura_e_ja_devolve_sessao(client_anonimo) -> None:
    r = client_anonimo.post("/v1/auth/registrar", json=CADASTRO)
    assert r.status_code == 201, r.text

    corpo = r.json()
    assert corpo["acesso"] and corpo["renovacao"]
    assert corpo["tipo"] == "Bearer"
    assert corpo["expira_em_segundos"] == MINUTOS_ACESSO * 60

    # O token que acabou de sair tem que servir para entrar de fato.
    eu = client_anonimo.get(
        "/v1/auth/eu", headers={"Authorization": f"Bearer {corpo['acesso']}"}
    )
    assert eu.status_code == 200
    assert eu.json()["email"] == CADASTRO["email"]

    # E a conta nasce utilizavel: sem assinatura, a primeira busca falharia.
    me = client_anonimo.get("/v1/me", headers={"Authorization": f"Bearer {corpo['acesso']}"})
    assert me.status_code == 200
    assert me.json()["saldo"]["creditos"] > 0


def test_cadastro_repetido_e_409_e_nao_sobrescreve(client_anonimo) -> None:
    assert client_anonimo.post("/v1/auth/registrar", json=CADASTRO).status_code == 201
    r = client_anonimo.post("/v1/auth/registrar", json={**CADASTRO, "nome": "Outro"})
    assert r.status_code == 409


def test_email_so_muda_de_caixa_continua_sendo_a_mesma_conta(client_anonimo) -> None:
    """`Novo@Empresa` e `novo@empresa` nao podem virar duas contas.

    O login normaliza para minusculo: se as duas existissem, a segunda nunca
    mais conseguiria entrar — e o dono dela nao teria como descobrir por que.
    """
    assert client_anonimo.post("/v1/auth/registrar", json=CADASTRO).status_code == 201
    r = client_anonimo.post(
        "/v1/auth/registrar", json={**CADASTRO, "email": "NOVO@Empresa.Com.Br"}
    )
    assert r.status_code == 409


def test_login_devolve_a_mesma_mensagem_para_email_e_senha_errados(client_anonimo) -> None:
    """Distinguir os dois transforma o login num verificador de quem tem conta."""
    client_anonimo.post("/v1/auth/registrar", json=CADASTRO)

    senha_errada = client_anonimo.post(
        "/v1/auth/entrar", json={"email": CADASTRO["email"], "senha": "outra-senha-longa"}
    )
    inexistente = client_anonimo.post(
        "/v1/auth/entrar", json={"email": "ninguem@exemplo.com", "senha": "outra-senha-longa"}
    )

    assert senha_errada.status_code == inexistente.status_code == 401
    assert senha_errada.json()["detail"] == inexistente.json()["detail"]


def test_o_usuario_de_seed_consegue_entrar(client_anonimo, usuario) -> None:
    """`demo@prospector.local` e nome reservado (RFC 6762).

    Com `EmailStr` no login, a rota respondia 422 e o usuario de demonstracao
    nao entrava em lugar nenhum — o produto inteiro ficava inacessivel em
    desenvolvimento. Validar formato e trabalho do CADASTRO; o login so precisa
    saber se a credencial confere.
    """
    from app.db.seed import SENHA_DEMO

    r = client_anonimo.post(
        "/v1/auth/entrar", json={"email": usuario.email, "senha": SENHA_DEMO}
    )
    assert r.status_code == 200, r.text
    assert r.json()["acesso"]


def test_email_malformado_no_login_e_401_e_nao_422(client_anonimo, usuario) -> None:
    """422 diria ao visitante qual formato o sistema aceita. 401 nao diz nada."""
    r = client_anonimo.post("/v1/auth/entrar", json={"email": "nao-e-email", "senha": "12345678"})
    assert r.status_code == 401


def test_conta_desativada_nao_entra(client_anonimo, session) -> None:
    client_anonimo.post("/v1/auth/registrar", json=CADASTRO)
    from app.repositories.misc import UserRepository

    user = UserRepository(session).por_email(CADASTRO["email"])
    user.ativo = False
    session.flush()

    r = client_anonimo.post(
        "/v1/auth/entrar", json={"email": CADASTRO["email"], "senha": CADASTRO["senha"]}
    )
    assert r.status_code == 403


# --- A porta fechada ---------------------------------------------------------
@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("get", "/v1/me"),
        ("get", "/v1/leads"),
        ("get", "/v1/campaigns"),
        ("get", "/v1/messages"),
        ("get", "/v1/cerebro/pesos"),
        ("get", "/v1/dashboard"),
        ("post", "/v1/cerebro/pesos/recalcular"),
    ],
)
def test_sem_token_ninguem_entra(client_anonimo, usuario, metodo: str, caminho: str) -> None:
    """Antes desta etapa TODAS estas rotas respondiam 200 sem credencial."""
    r = getattr(client_anonimo, metodo)(caminho)
    assert r.status_code == 401, f"{caminho} respondeu {r.status_code}"
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_o_header_antigo_nao_autentica_mais(client_anonimo, usuario) -> None:
    """`X-User-Email` era a autenticacao inteira. Nao pode ter sobrado nada dele."""
    r = client_anonimo.get("/v1/me", headers={"X-User-Email": usuario.email})
    assert r.status_code == 401


def test_token_assinado_com_outro_segredo_e_recusado(client_anonimo, usuario) -> None:
    """O caso que um teste ingenuo nao pega: token bem formado, chave errada."""
    import jwt

    forjado = jwt.encode(
        {"sub": str(usuario.id), "tipo": TIPO_ACESSO, "exp": time.time() + 3600},
        "segredo-do-atacante",
        algorithm="HS256",
    )
    r = client_anonimo.get("/v1/me", headers={"Authorization": f"Bearer {forjado}"})
    assert r.status_code == 401


def test_token_de_renovacao_nao_serve_como_acesso(client_anonimo, usuario) -> None:
    """Senao a expiracao curta do acesso nao teria servido para nada."""
    par = emitir_par(usuario.id)
    r = client_anonimo.get("/v1/me", headers={"Authorization": f"Bearer {par.renovacao}"})
    assert r.status_code == 401


def test_token_de_dono_que_nao_existe_e_recusado(client_anonimo, usuario) -> None:
    """Assinado por nos, e ainda assim invalido: a conta sumiu."""
    par = emitir_par(uuid.uuid4())
    r = client_anonimo.get("/v1/me", headers={"Authorization": f"Bearer {par.acesso}"})
    assert r.status_code == 401


def test_renovacao_devolve_par_novo(client_anonimo, usuario) -> None:
    par = emitir_par(usuario.id)
    r = client_anonimo.post("/v1/auth/renovar", json={"renovacao": par.renovacao})
    assert r.status_code == 200
    assert r.json()["acesso"]

    # E um token de ACESSO nao serve para renovar — o inverso tambem vale.
    assert (
        client_anonimo.post("/v1/auth/renovar", json={"renovacao": par.acesso}).status_code
        == 401
    )


# --- Isolamento entre tenants ------------------------------------------------
@pytest.fixture
def vizinho(session, usuario):  # noqa: ANN201
    """Outro cliente, com uma campanha propria."""
    outro = User(
        email="vizinho@empresa.com",
        nome="Vizinho",
        senha_hash=hash_senha("senha-do-vizinho"),
    )
    session.add(outro)
    session.flush()
    session.add(
        Subscription(
            user_id=outro.id,
            plano=Plano.TRIAL,
            status=StatusAssinatura.ATIVA,
            saldo_creditos=100,
        )
    )
    campanha = Campaign(
        user_id=outro.id,
        nome="Campanha do vizinho",
        servico="manutencao predial",
        regiao="Recife, PE",
        filtros={},
    )
    session.add(campanha)
    session.flush()
    return outro, campanha


def test_um_tenant_nao_ve_a_campanha_do_outro(client, vizinho) -> None:
    """Havia filtro por `user_id` nos repositorios e nenhum teste via HTTP."""
    _, campanha_alheia = vizinho

    lista = client.get("/v1/campaigns").json()
    assert all(c["id"] != str(campanha_alheia.id) for c in lista["itens"])

    direto = client.get(f"/v1/campaigns/{campanha_alheia.id}")
    assert direto.status_code == 404, "ler pelo id nao pode furar o filtro da listagem"


def test_um_tenant_nao_executa_a_campanha_do_outro(client, vizinho) -> None:
    """Pior que ler: gastaria o credito do vizinho e mandaria e-mail no nome dele."""
    _, campanha_alheia = vizinho
    r = client.post(f"/v1/campaigns/{campanha_alheia.id}/run", json={"limite_leads": 1})
    assert r.status_code in (403, 404), r.text



def _lead(session, dono_id, campanha_id, email):  # noqa: ANN001, ANN202
    from app.models.lead import Lead

    lead = Lead(
        user_id=dono_id,
        campaign_id=campanha_id,
        razao_social="Empresa do teste",
        email=email,
        provenance={"fonte": "teste"},
    )
    session.add(lead)
    session.flush()
    return lead


def _pedido(session, contato):  # noqa: ANN001, ANN202
    """Pedido aberto pelo formulario publico: nasce sem `user_id`."""
    from app.models.enums import TipoSolicitacao
    from app.services.compliance import PrivacyService

    return PrivacyService(session).abrir(contato=contato, tipo=TipoSolicitacao.ACESSO)


def test_um_tenant_nao_ve_pedido_de_privacidade_sobre_lead_do_outro(
    client, session, vizinho
) -> None:
    """A rota listava os pedidos de TODAS as contas, com o e-mail do titular."""
    outro, campanha_alheia = vizinho
    _lead(session, outro.id, campanha_alheia.id, "compras@alheia.com.br")
    pedido = _pedido(session, "compras@alheia.com.br")
    session.commit()

    r = client.get("/v1/compliance/solicitacoes")
    assert r.status_code == 200
    protocolos = {p["protocolo"] for p in r.json()["itens"]}
    assert str(pedido.id) not in protocolos
    assert "compras@alheia.com.br" not in r.text


def test_cliente_ve_pedido_sobre_o_proprio_lead(client, session, usuario) -> None:
    """O filtro nao pode esconder o que e do cliente: ele precisa responder ao titular.

    O e-mail do lead vem com maiuscula (como o site da empresa publica) e o
    pedido e normalizado em minuscula — os dois precisam se encontrar.
    """
    campanha = Campaign(
        user_id=usuario.id, nome="Minha", servico="limpeza", regiao="Natal, RN", filtros={}
    )
    session.add(campanha)
    session.flush()
    _lead(session, usuario.id, campanha.id, "Contato@MinhaCliente.com.br")
    pedido = _pedido(session, "contato@minhacliente.com.br")
    session.commit()

    itens = client.get("/v1/compliance/solicitacoes").json()["itens"]
    assert str(pedido.id) in {p["protocolo"] for p in itens}


def test_expurgo_global_nao_e_rota_do_cliente(client) -> None:
    """Qualquer conta logada disparava o expurgo da base inteira."""
    r = client.post("/v1/compliance/retencao", params={"dry_run": "false"})
    assert r.status_code in (404, 405), r.text


# --- Webhooks assinados ------------------------------------------------------
def test_webhook_sem_assinatura_e_recusado(client_anonimo, usuario) -> None:
    """Antes, qualquer pessoa registrava uma resposta de qualquer lead."""
    r = client_anonimo.post(
        "/v1/inbound/email", json={"remetente": "alguem@exemplo.com", "corpo": "oi"}
    )
    assert r.status_code == 401


def test_webhook_com_assinatura_de_outro_segredo_e_recusado(webhook, usuario) -> None:
    r = webhook(
        "/v1/inbound/email",
        {"remetente": "alguem@exemplo.com", "corpo": "oi"},
        segredo="segredo-do-atacante",
    )
    assert r.status_code == 401


def test_webhook_antigo_nao_pode_ser_reenviado(webhook, usuario) -> None:
    """Sem timestamp assinado, capturar uma requisicao valida a torna eterna."""
    r = webhook(
        "/v1/inbound/retorno",
        {"contato": "alguem@exemplo.com", "tipo": "permanente"},
        timestamp=int(time.time()) - 3600,
    )
    assert r.status_code == 401


def test_assinatura_valida_de_corpo_diferente_nao_cola(client_anonimo, usuario) -> None:
    """Assinar um corpo e enviar outro e o ataque obvio — tem que falhar."""
    import os

    assinado = json.dumps({"contato": "a@exemplo.com", "tipo": "temporaria"}).encode()
    enviado = json.dumps({"contato": "vitima@exemplo.com", "tipo": "permanente"}).encode()
    ts = int(time.time())

    r = client_anonimo.post(
        "/v1/inbound/retorno",
        content=enviado,
        headers={
            "Content-Type": "application/json",
            "X-Assinatura-Timestamp": str(ts),
            "X-Assinatura": assinar(
                assinado, timestamp=ts, segredo=os.environ["WEBHOOK_SECRET"]
            ),
        },
    )
    assert r.status_code == 401


def test_sem_segredo_configurado_a_rota_fecha_em_vez_de_abrir(
    client_anonimo, usuario, monkeypatch
) -> None:
    """O default inseguro seria "sem chave, aceita todo mundo"."""
    from app.core import config as cfg

    monkeypatch.setenv("WEBHOOK_SECRET", "")
    cfg.get_settings.cache_clear()
    try:
        r = client_anonimo.post(
            "/v1/inbound/email", json={"remetente": "alguem@exemplo.com", "corpo": "oi"}
        )
        assert r.status_code == 401
    finally:
        cfg.get_settings.cache_clear()


# --- Senha e segredo ---------------------------------------------------------
def test_custo_do_bcrypt_baixo_vale_so_na_suite(monkeypatch) -> None:
    """A reducao existe para a suite nao triplicar de tempo.

    Se ela vazasse para producao, o sintoma seria nenhum — ate o dia em que o
    banco vazasse e as senhas caissem em horas em vez de anos.
    """
    from app.core import config as cfg
    from app.services.auth import CUSTO_BCRYPT, CUSTO_BCRYPT_TESTE, custo_bcrypt

    assert custo_bcrypt() == CUSTO_BCRYPT_TESTE  # estamos em APP_ENV=test

    for ambiente in ("producao", "dev", "staging"):
        monkeypatch.setenv("APP_ENV", ambiente)
        cfg.get_settings.cache_clear()
        try:
            assert custo_bcrypt() == CUSTO_BCRYPT, ambiente
        finally:
            cfg.get_settings.cache_clear()


def test_senha_curta_e_recusada() -> None:
    with pytest.raises(SenhaFraca):
        hash_senha("curta")


def test_senha_longa_demais_e_recusada_em_vez_de_truncada() -> None:
    """bcrypt corta em 72 bytes SEM avisar: aceitar seria conferir so o comeco."""
    with pytest.raises(SenhaFraca):
        hash_senha("a" * 73)


def test_hash_nao_guarda_a_senha_e_nao_se_repete() -> None:
    senha = "uma-senha-comprida"
    a, b = hash_senha(senha), hash_senha(senha)
    assert senha not in a
    assert a != b, "sem sal, senhas iguais teriam hash igual"
    assert conferir_senha(senha, a) and conferir_senha(senha, b)


def test_usuario_sem_senha_nao_entra_por_senha_nenhuma() -> None:
    """Contas anteriores a esta etapa tem `senha_hash` nulo."""
    assert conferir_senha("qualquer-coisa", None) is False
    assert conferir_senha("qualquer-coisa", "") is False


def test_token_expirado_e_recusado(usuario) -> None:
    import jwt

    from app.core.config import get_settings

    vencido = jwt.encode(
        {"sub": str(usuario.id), "tipo": TIPO_ACESSO, "exp": time.time() - 10},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(CredencialInvalida):
        ler_token(vencido, tipo=TIPO_ACESSO)


def test_token_com_algoritmo_none_e_recusado(usuario) -> None:
    """O ataque classico de JWT: trocar o algoritmo no cabecalho do proprio token."""
    import jwt

    sem_assinatura = jwt.encode(
        {"sub": str(usuario.id), "tipo": TIPO_ACESSO, "exp": time.time() + 3600},
        key="",
        algorithm="none",
    )
    with pytest.raises(CredencialInvalida):
        ler_token(sem_assinatura, tipo=TIPO_ACESSO)


def test_producao_recusa_subir_com_segredo_de_desenvolvimento(monkeypatch) -> None:
    """Esquecer o JWT_SECRET no .env nao produz sintoma nenhum — so deixa
    qualquer leitor deste repositorio assinar um token para qualquer conta."""
    from app.core import config as cfg

    monkeypatch.setenv("APP_ENV", "producao")
    cfg.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            verificar_segredo_de_producao()
    finally:
        cfg.get_settings.cache_clear()


def test_producao_recusa_segredo_curto(monkeypatch) -> None:
    from app.core import config as cfg

    monkeypatch.setenv("APP_ENV", "producao")
    monkeypatch.setenv("JWT_SECRET", "curto-demais")
    cfg.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            verificar_segredo_de_producao()
    finally:
        cfg.get_settings.cache_clear()


def test_desenvolvimento_sobe_com_o_padrao(monkeypatch) -> None:
    """A trava nao pode atrapalhar quem so quer rodar o projeto na propria maquina."""
    from app.core import config as cfg

    monkeypatch.setenv("APP_ENV", "dev")
    cfg.get_settings.cache_clear()
    try:
        verificar_segredo_de_producao()
    finally:
        cfg.get_settings.cache_clear()


def test_tipos_de_token_sao_distintos(usuario) -> None:
    par = emitir_par(usuario.id)
    assert ler_token(par.acesso, tipo=TIPO_ACESSO) == usuario.id
    assert ler_token(par.renovacao, tipo=TIPO_RENOVACAO) == usuario.id
    with pytest.raises(CredencialInvalida):
        ler_token(par.acesso, tipo=TIPO_RENOVACAO)
