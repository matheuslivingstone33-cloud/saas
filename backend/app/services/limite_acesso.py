"""Limite de tentativas no login e no cadastro.

Sem isto, nada impedia alguem de testar senhas sem parar numa conta, nem de
criar contas em serie para juntar os creditos de boas-vindas. O bcrypt de
custo 12 encarece cada tentativa (~250 ms), mas isso e mitigacao, nao defesa.

As contagens vivem no BANCO, nao na memoria do processo: no Vercel cada
requisicao pode cair numa instancia diferente, e um contador em memoria
zeraria a cada troca.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ids import now
from app.core.logging import get_logger
from app.models.acesso import TentativaDeAcesso

log = get_logger("limite_acesso")

LOGIN = "login"
CADASTRO = "cadastro"


class MuitasTentativas(Exception):  # noqa: N818 — nome de dominio, nao "Error"
    """Travado por excesso. `minutos` e quanto esperar antes de tentar de novo."""

    def __init__(self, minutos: int) -> None:
        self.minutos = minutos
        super().__init__(f"Muitas tentativas. Tente de novo em {minutos} minutos.")


def ip_de(request: Request, settings: Settings | None = None) -> str | None:
    """IP de quem chamou.

    No Vercel a requisicao chega por um proxy, e o IP real vem no
    `x-forwarded-for` — que o proprio Vercel reescreve, entao o visitante nao
    consegue forjar. Fora dele o cabecalho seria escrito por quem quisesse, e
    vale o IP da conexao.
    """
    s = settings or get_settings()
    if s.sem_servidor:
        encaminhado = request.headers.get("x-forwarded-for", "")
        primeiro = encaminhado.split(",")[0].strip()
        if primeiro:
            return primeiro[:64]
    return request.client.host[:64] if request.client else None


class LimiteDeAcesso:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # -- login ------------------------------------------------------------------
    def conferir_login(self, email: str, ip: str | None) -> None:
        """Levanta `MuitasTentativas` se o e-mail ou o IP ja erraram demais."""
        s = self.settings
        janela = now() - timedelta(minutes=s.login_janela_minutos)

        # So contam as falhas DEPOIS do ultimo acerto: quem erra duas vezes e
        # acerta na terceira nao carrega as duas para a proxima sessao.
        ultimo_acerto = self.session.execute(
            select(func.max(TentativaDeAcesso.created_at)).where(
                TentativaDeAcesso.acao == LOGIN,
                TentativaDeAcesso.email_normalizado == email,
                TentativaDeAcesso.sucesso.is_(True),
                TentativaDeAcesso.created_at >= janela,
            )
        ).scalar_one_or_none()
        desde = ultimo_acerto if ultimo_acerto is not None else janela

        falhas_email = self._contar(
            TentativaDeAcesso.email_normalizado == email, desde=desde, acerto=False
        )
        if falhas_email >= s.login_max_falhas:
            log.warning("login_travado_por_email", falhas=falhas_email)
            raise MuitasTentativas(s.login_janela_minutos)

        if ip:
            falhas_ip = self._contar(TentativaDeAcesso.ip == ip, desde=janela, acerto=False)
            if falhas_ip >= s.login_max_falhas_por_ip:
                log.warning("login_travado_por_ip", falhas=falhas_ip)
                raise MuitasTentativas(s.login_janela_minutos)

    def registrar_login(self, email: str, ip: str | None, *, sucesso: bool) -> None:
        self._registrar(LOGIN, email, ip, sucesso=sucesso)

    # -- cadastro ---------------------------------------------------------------
    def conferir_cadastro(self, ip: str | None) -> None:
        if not ip:
            return
        desde = now() - timedelta(hours=1)
        feitos = self._contar(
            TentativaDeAcesso.ip == ip, desde=desde, acao=CADASTRO, acerto=True
        )
        if feitos >= self.settings.cadastro_max_por_ip_hora:
            log.warning("cadastro_travado_por_ip", cadastros=feitos)
            raise MuitasTentativas(60)

    def registrar_cadastro(self, email: str, ip: str | None) -> None:
        self._registrar(CADASTRO, email, ip, sucesso=True)

    # -- internos ---------------------------------------------------------------
    def _contar(self, filtro, *, desde, acerto: bool, acao: str = LOGIN) -> int:  # noqa: ANN001
        return self.session.execute(
            select(func.count(TentativaDeAcesso.id)).where(
                TentativaDeAcesso.acao == acao,
                filtro,
                TentativaDeAcesso.sucesso.is_(acerto),
                TentativaDeAcesso.created_at > desde,
            )
        ).scalar_one()

    def _registrar(self, acao: str, email: str, ip: str | None, *, sucesso: bool) -> None:
        agora = now()
        self.session.add(
            TentativaDeAcesso(
                acao=acao,
                email_normalizado=email,
                ip=ip,
                sucesso=sucesso,
                created_at=agora,
                updated_at=agora,
            )
        )
        # O registro de acesso tem prazo: passou dos 6 meses, sai.
        corte = agora - timedelta(days=self.settings.retencao_registros_acesso_dias)
        self.session.execute(
            delete(TentativaDeAcesso).where(TentativaDeAcesso.created_at < corte)
        )
        self.session.flush()
