"""Limite de tentativas no login e no cadastro (18/09).

Nada limitava quem testa senhas em serie, nem quem cria contas em serie para
juntar os creditos de boas-vindas. Os testes verificam o que o sistema RECUSA
e, com o mesmo cuidado, que ele nao trava quem usa normalmente.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.ids import now
from app.models.acesso import TentativaDeAcesso
from app.services.limite_acesso import LimiteDeAcesso

CONTA = {
    "email": "dona@empresa.com.br",
    "nome": "Dona da Conta",
    "senha": "a-senha-certa-e-longa",
}


def _entrar(cliente, senha: str, email: str = CONTA["email"]):  # noqa: ANN001, ANN202
    return cliente.post("/v1/auth/entrar", json={"email": email, "senha": senha})


@pytest.fixture
def conta(client_anonimo):  # noqa: ANN201
    r = client_anonimo.post("/v1/auth/registrar", json=CONTA)
    assert r.status_code == 201, r.text
    return client_anonimo


def test_cinco_senhas_erradas_travam_ate_a_senha_certa(conta, settings) -> None:
    for _ in range(settings.login_max_falhas):
        assert _entrar(conta, "senha-errada-123").status_code == 401

    r = _entrar(conta, CONTA["senha"])
    assert r.status_code == 429, "travado, nem a senha certa entra ate a janela passar"
    assert int(r.headers["Retry-After"]) == settings.login_janela_minutos * 60
    assert "Muitas tentativas" in r.json()["detail"]


def test_a_trava_passa_quando_a_janela_passa(conta, session, settings) -> None:
    for _ in range(settings.login_max_falhas):
        _entrar(conta, "senha-errada-123")

    passado = now() - timedelta(minutes=settings.login_janela_minutos + 1)
    session.execute(update(TentativaDeAcesso).values(created_at=passado))
    session.commit()

    assert _entrar(conta, CONTA["senha"]).status_code == 200


def test_acertar_zera_as_falhas_anteriores(conta, settings) -> None:
    """Quem erra algumas vezes e acerta nao carrega os erros para depois."""
    quase = settings.login_max_falhas - 1
    for _ in range(quase):
        _entrar(conta, "senha-errada-123")
    assert _entrar(conta, CONTA["senha"]).status_code == 200

    for _ in range(quase):
        assert _entrar(conta, "senha-errada-123").status_code == 401
    assert _entrar(conta, CONTA["senha"]).status_code == 200


def test_erros_numa_conta_nao_travam_outra(conta, settings) -> None:
    for _ in range(settings.login_max_falhas):
        _entrar(conta, "senha-errada-123", email="outra@empresa.com.br")

    assert _entrar(conta, CONTA["senha"]).status_code == 200


def test_muitas_contas_testadas_do_mesmo_ip_travam(conta, settings, monkeypatch) -> None:
    """Quem testa UMA senha em muitas contas nao passa pelo limite por e-mail."""
    monkeypatch.setattr(settings, "login_max_falhas_por_ip", 6)
    for i in range(6):
        _entrar(conta, "senha-errada-123", email=f"alvo{i}@empresa.com.br")

    assert _entrar(conta, CONTA["senha"]).status_code == 429


def test_cadastros_em_serie_do_mesmo_ip_travam(client_anonimo, settings) -> None:
    """Cada conta nova ganha creditos: sem teto, vira fonte de credito gratis."""
    for i in range(settings.cadastro_max_por_ip_hora):
        r = client_anonimo.post(
            "/v1/auth/registrar", json={**CONTA, "email": f"conta{i}@empresa.com.br"}
        )
        assert r.status_code == 201, r.text

    r = client_anonimo.post("/v1/auth/registrar", json={**CONTA, "email": "mais@empresa.com.br"})
    assert r.status_code == 429


def test_registro_de_acesso_mais_velho_que_o_prazo_e_apagado(session, settings) -> None:
    """Marco Civil: guardar 6 meses — e nao para sempre."""
    velho = now() - timedelta(days=settings.retencao_registros_acesso_dias + 1)
    session.add(
        TentativaDeAcesso(
            acao="login", email_normalizado="antigo@x.com", ip="1.2.3.4", sucesso=True,
            created_at=velho, updated_at=velho,
        )
    )
    session.flush()

    LimiteDeAcesso(session, settings).registrar_login("novo@x.com", "1.2.3.4", sucesso=True)

    emails = set(session.execute(select(TentativaDeAcesso.email_normalizado)).scalars())
    assert emails == {"novo@x.com"}


def test_ip_do_encaminhamento_so_vale_no_vercel(settings, monkeypatch) -> None:
    """Fora do Vercel o `x-forwarded-for` e escrito por quem quiser."""
    from starlette.requests import Request

    from app.services.limite_acesso import ip_de

    escopo = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
        "client": ("10.0.0.1", 5000),
    }
    monkeypatch.delenv("VERCEL", raising=False)
    assert ip_de(Request(escopo), settings) == "10.0.0.1"

    monkeypatch.setenv("VERCEL", "1")
    assert ip_de(Request(escopo), settings) == "203.0.113.9"
