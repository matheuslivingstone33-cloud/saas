"""Passo de build do backend no Vercel (`[tool.vercel.scripts] build`).

Roda depois de instalar as dependencias e antes de publicar a funcao. Faz
tres coisas, nesta ordem:

1. Traz para dentro de `backend/` os arquivos que a API le em tempo de
   execucao e que vivem na raiz do repositorio: `data/` (catalogo de ramos e
   amostra da Receita) e os textos juridicos de `docs/`. O projeto do Vercel
   tem `backend` como raiz, e o que fica fora dela nao entra na funcao — sem
   esta copia a busca roda com zero ramos e `/legal/privacidade` da 404.
2. Atualiza o banco (`alembic upgrade head`).
3. Carrega o catalogo de ramos, que nao e dado de demonstracao.

Os passos 2 e 3 rodam SO no deploy de producao. O de pre-visualizacao usa o
mesmo banco, e uma migration de um ramo em teste nao pode alterar o banco de
verdade antes de ir para a versao principal.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
RAIZ = BACKEND.parent

TEXTOS_PUBLICOS = (
    "POLITICA-DE-PRIVACIDADE.md",
    "DECLARACAO-DE-IA.md",
    "TERMOS-DE-USO.md",
)


def log(msg: str) -> None:
    print(f"[vercel_build] {msg}", flush=True)


def copiar_arquivos_da_raiz() -> None:
    origem_dados = RAIZ / "data"
    if origem_dados.is_dir():
        shutil.copytree(origem_dados, BACKEND / "data", dirs_exist_ok=True)
        log("data/ copiado para dentro do backend")
    else:
        log("AVISO: data/ nao encontrado na raiz; o catalogo de ramos ficara vazio")

    destino_docs = BACKEND / "docs"
    destino_docs.mkdir(exist_ok=True)
    for nome in TEXTOS_PUBLICOS:
        origem = RAIZ / "docs" / nome
        if origem.is_file():
            shutil.copy2(origem, destino_docs / nome)
            log(f"docs/{nome} copiado")
        else:
            log(f"AVISO: docs/{nome} nao encontrado; a pagina publica dara 404")


def banco_de_producao() -> str | None:
    """URL para migrar: a direta, sem o pooler, quando o provedor oferecer."""
    for nome in ("DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING", "DATABASE_URL"):
        valor = os.environ.get(nome, "").strip()
        if valor:
            return valor
    return None


def migrar_e_carregar(url: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    log("alembic upgrade head")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True
    )
    log("carregando o catalogo de ramos")
    codigo = (
        "from app.db.seed import carregar_catalogo\n"
        "from app.db.session import session_scope\n"
        "with session_scope() as s:\n"
        "    print('[vercel_build] ramos acrescentados:', carregar_catalogo(s))\n"
    )
    subprocess.run([sys.executable, "-c", codigo], cwd=BACKEND, env=env, check=True)


def main() -> int:
    copiar_arquivos_da_raiz()

    ambiente = os.environ.get("VERCEL_ENV", "")
    if ambiente != "production":
        log(f"ambiente '{ambiente or 'local'}': banco nao e tocado neste build")
        return 0

    url = banco_de_producao()
    if not url or url.startswith("sqlite"):
        log("ERRO: sem banco Postgres configurado (DATABASE_URL). Conecte o Neon ao projeto.")
        return 1

    migrar_e_carregar(url)
    log("pronto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
