"""O que o deploy no Vercel exige e que so quebraria la, sem aviso aqui."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[2]


def _requirements(nome: str) -> set[str]:
    linhas = (BACKEND / nome).read_text(encoding="utf-8").splitlines()
    return {
        linha.strip().lower()
        for linha in linhas
        if linha.strip() and not linha.strip().startswith(("#", "-r"))
    }


def test_pyproject_espelha_os_requirements() -> None:
    """O Vercel instala pelo pyproject; o Docker, pelos requirements.

    Se um divergir do outro, um dos dois ambientes sobe sem uma dependencia —
    e o erro so aparece la, na primeira importacao.
    """
    projeto = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    no_pyproject = {d.lower() for d in projeto["project"]["dependencies"]}
    nos_requirements = _requirements("requirements.txt") | _requirements("requirements-prod.txt")
    assert no_pyproject == nos_requirements


def test_versao_do_python_fixada_em_3_12() -> None:
    """Sem isto o Vercel escolhe a versao dele, e as rodas fixadas podem nao existir."""
    assert (BACKEND / ".python-version").read_text().strip() == "3.12"


def test_url_do_neon_ganha_o_driver_psycopg() -> None:
    for bruta in ("postgres://u:p@h/db", "postgresql://u:p@h/db?sslmode=require"):
        url = Settings(database_url=bruta).database_url
        assert url.startswith("postgresql+psycopg://"), url
    assert Settings(database_url="sqlite+pysqlite:///x.db").database_url.startswith("sqlite")


def test_caixa_de_saida_desvia_quando_o_disco_e_so_de_leitura(tmp_path, monkeypatch) -> None:
    """No Vercel o disco do projeto e so de leitura; o envio simulado nao pode cair."""
    arquivo = tmp_path / "nao-e-pasta"
    arquivo.write_text("x")
    settings = Settings(outbox_dir=str(arquivo / "outbox"))
    destino = settings.outbox_path
    assert destino.is_dir()
    assert not re.search(re.escape(str(arquivo)), str(destino))


def test_catalogo_carrega_sem_dados_de_demonstracao(session) -> None:
    """Em producao o seed de demo fica desligado; o catalogo de ramos, nao."""
    from sqlalchemy import func, select

    from app.db.seed import carregar_catalogo
    from app.models.lead import RamoCnae
    from app.models.user import User

    acrescentados = carregar_catalogo(session)
    assert acrescentados > 0
    assert carregar_catalogo(session) == 0, "rodar de novo nao duplica"
    assert session.execute(select(func.count(RamoCnae.id))).scalar_one() == acrescentados
    assert session.execute(select(func.count(User.id))).scalar_one() == 0
