"""Autenticacao: senha em bcrypt e sessao em JWT.

Ate a Etapa 7 nao havia login: o usuario vinha do header `X-User-Email`, com
fallback no usuario de seed. Era dev-only e estava documentado como tal, mas
era tambem uma porta aberta — `curl -H "X-User-Email: cliente@empresa.com"`
devolvia os leads daquele cliente, e o header nao prova nada sobre quem
enviou.

Duas decisoes que valem explicacao:

  * **bcrypt para senha, biblioteca para JWT.** Nao ha esquema proprio aqui.
    Assinatura e onde se erra silenciosamente (algoritmo `none` aceito,
    comparacao nao constante, expiracao ignorada), e errar ali nao aparece em
    teste nenhum — o sistema continua funcionando, so que para qualquer um.
  * **Dois tipos de token, e o tipo vai DENTRO do token.** Um refresh de 14
    dias que sirva como acesso anula a razao de o acesso durar 30 minutos.
    A distincao precisa ser assinada junto, senao e so uma convencao de nome.

O que esta etapa NAO faz, de proposito: revogacao. Deslogar apaga o token no
cliente, e um token roubado vale ate expirar. Uma lista de revogacao exige
estado compartilhado (Redis) e so faz sentido depois que houver sessao real
para revogar. Esta anotado no HANDOFF.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger("auth")

ALGORITMO = "HS256"
#: Acesso curto: e o token que trafega em toda requisicao.
MINUTOS_ACESSO = 30
#: Renovacao longa: e o que evita pedir senha toda hora.
DIAS_RENOVACAO = 14

TIPO_ACESSO = "acesso"
TIPO_RENOVACAO = "renovacao"

#: Segredos que existem para o `pytest` rodar sem `.env`. Em producao eles
#: derrubam a subida — ver `verificar_segredo_de_producao`.
SEGREDOS_DE_DESENVOLVIMENTO = frozenset(
    {"dev-jwt-secret-trocar-em-producao", "dev-app-secret-trocar-em-producao", "", "troque-me"}
)

#: Custo do bcrypt. 12 e o padrao atual da biblioteca (~250ms); abaixo de 10
#: um vazamento de banco vira lista de senhas em pouco tempo.
CUSTO_BCRYPT = 12
#: Custo na suite. O seed roda em quase todo teste, e a 12 isso sozinho
#: triplicava o tempo da suite — e suite lenta e suite que ninguem roda.
#: A reducao vale SO com APP_ENV=test, e ha teste fixando isso: um custo baixo
#: que vazasse para producao seria invisivel ate o dia do vazamento.
CUSTO_BCRYPT_TESTE = 4

#: Limite do bcrypt: ele TRUNCA silenciosamente em 72 bytes. Recusar e melhor
#: que aceitar uma senha longa e so conferir o comeco dela.
MAX_BYTES_SENHA = 72
MIN_CARACTERES_SENHA = 8


class CredencialInvalida(Exception):
    """Senha errada, token invalido, token expirado — de fora, tudo igual."""


class SenhaFraca(Exception):
    """A senha nao atende ao minimo exigido."""


@dataclass(slots=True)
class Par:
    """O que o login devolve."""

    acesso: str
    renovacao: str
    expira_em_segundos: int

    def to_dict(self) -> dict:
        return {
            "acesso": self.acesso,
            "renovacao": self.renovacao,
            "tipo": "Bearer",
            "expira_em_segundos": self.expira_em_segundos,
        }


# --- Senha -------------------------------------------------------------------
def validar_forca(senha: str) -> None:
    """Minimo defensavel, sem teatro de complexidade.

    Exigir maiuscula, numero e simbolo produz `Senha123!` em toda parte e nao
    aumenta entropia de verdade. Comprimento e o que aumenta.
    """
    if len(senha) < MIN_CARACTERES_SENHA:
        raise SenhaFraca(f"a senha precisa de ao menos {MIN_CARACTERES_SENHA} caracteres")
    if len(senha.encode("utf-8")) > MAX_BYTES_SENHA:
        raise SenhaFraca(
            f"a senha passa de {MAX_BYTES_SENHA} bytes, o limite do bcrypt. "
            "Use uma senha mais curta (acentos e emoji contam mais de um byte)."
        )


def custo_bcrypt(settings: Settings | None = None) -> int:
    """12 em qualquer lugar que nao seja a suite. Ver `CUSTO_BCRYPT_TESTE`."""
    return CUSTO_BCRYPT_TESTE if (settings or get_settings()).app_env == "test" else CUSTO_BCRYPT


def hash_senha(senha: str) -> str:
    validar_forca(senha)
    return bcrypt.hashpw(
        senha.encode("utf-8"), bcrypt.gensalt(rounds=custo_bcrypt())
    ).decode()


def conferir_senha(senha: str, hash_guardado: str | None) -> bool:
    """Compara em tempo constante. Devolve False para usuario sem senha.

    Usuario sem `senha_hash` existe: e o do seed, e sao os criados antes desta
    etapa. Eles nao entram por senha — precisam definir uma.
    """
    if not hash_guardado:
        return False
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), hash_guardado.encode())
    except ValueError:
        # Hash corrompido ou de outro algoritmo. Nao autentica, e nao explode.
        log.warning("hash_de_senha_ilegivel")
        return False


# --- Token -------------------------------------------------------------------
def _segredo(settings: Settings | None = None) -> str:
    return (settings or get_settings()).jwt_secret


def emitir_par(user_id: uuid.UUID, *, settings: Settings | None = None) -> Par:
    agora = datetime.now(UTC)
    acesso = _emitir(user_id, TIPO_ACESSO, agora + timedelta(minutes=MINUTOS_ACESSO), settings)
    renovacao = _emitir(
        user_id, TIPO_RENOVACAO, agora + timedelta(days=DIAS_RENOVACAO), settings
    )
    return Par(acesso, renovacao, MINUTOS_ACESSO * 60)


def _emitir(
    user_id: uuid.UUID, tipo: str, expira: datetime, settings: Settings | None
) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "tipo": tipo,
            "exp": expira,
            "iat": datetime.now(UTC),
        },
        _segredo(settings),
        algorithm=ALGORITMO,
    )


def ler_token(token: str, *, tipo: str, settings: Settings | None = None) -> uuid.UUID:
    """Devolve o id do usuario, ou levanta `CredencialInvalida`.

    `algorithms` fixo em HS256 e o que impede o ataque classico de trocar o
    algoritmo por `none` no cabecalho do proprio token.
    """
    try:
        claims = jwt.decode(token, _segredo(settings), algorithms=[ALGORITMO])
    except jwt.PyJWTError as erro:
        raise CredencialInvalida(str(erro)) from erro

    if claims.get("tipo") != tipo:
        # Um token de renovacao valendo como acesso anularia a expiracao curta.
        raise CredencialInvalida("token do tipo errado")
    try:
        return uuid.UUID(str(claims.get("sub")))
    except ValueError as erro:
        raise CredencialInvalida("token sem dono valido") from erro


# --- Trava de deploy ---------------------------------------------------------
def verificar_segredo_de_producao(settings: Settings | None = None) -> None:
    """Recusa subir em producao com o segredo de desenvolvimento.

    Sem isto, o unico sintoma de esquecer o `JWT_SECRET` no `.env` seria que
    qualquer pessoa que leia este repositorio consegue assinar um token valido
    para qualquer conta — e nada, em lugar nenhum, pareceria errado.
    """
    s = settings or get_settings()
    if s.app_env in {"dev", "test"}:
        return
    if s.jwt_secret in SEGREDOS_DE_DESENVOLVIMENTO:
        raise RuntimeError(
            "JWT_SECRET esta com o valor de desenvolvimento em APP_ENV="
            f"{s.app_env}. Defina um segredo forte antes de subir."
        )
    if len(s.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET curto demais: use ao menos 32 caracteres aleatorios.")
    # O APP_SECRET assina o link de descadastro e o checkout simulado. Com o
    # valor de desenvolvimento, que esta escrito neste repositorio, qualquer
    # leitor forjaria um descadastro em nome de outro lead ou uma compra paga.
    if s.app_secret in SEGREDOS_DE_DESENVOLVIMENTO or len(s.app_secret) < 32:
        raise RuntimeError(
            "APP_SECRET ausente, curto ou com o valor de desenvolvimento em "
            f"APP_ENV={s.app_env}. Use ao menos 32 caracteres aleatorios."
        )
