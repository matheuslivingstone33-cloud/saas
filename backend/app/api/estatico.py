"""Serve a interface compilada pelo proprio backend.

Por que existe: em desenvolvimento sao dois processos (Vite na 5173 + API na
8000). O Vite mantem um servico filho do esbuild e come algumas centenas de
megabytes — em maquina apertada de memoria ele morre, o esbuild some junto e a
tela fica em branco com erro 500 em todo transform.

Servindo `frontend/dist` daqui, o app inteiro roda em UM processo: sem Node,
sem esbuild, sem CORS (mesma origem). Perde-se a recarga automatica ao editar,
que so importa para quem esta mexendo no codigo.

Ativacao: se `frontend/dist/index.html` existir, a interface aparece na raiz.
Se nao existir, a raiz continua devolvendo a recepcao da API em JSON. Nada de
configuracao — basta rodar `npm run build`.

IMPORTANTE: isto e montado DEPOIS de todas as rotas de API. O coringa de SPA
so responde ao que nao casou com rota nenhuma, e ainda assim recusa prefixos
reservados, para um erro de digitacao em `/v1/...` devolver 404 de verdade em
vez de mandar o HTML do app.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.logging import get_logger

log = get_logger("estatico")

#: Caminhos que pertencem a API. O coringa nunca os captura.
RESERVADOS = ("v1", "health", "docs", "redoc", "openapi.json", "descadastro", "privacidade")


def diretorio_da_interface() -> Path | None:
    """Devolve `frontend/dist` se houver build ali, senao None."""
    raiz = Path(__file__).resolve().parents[3]
    dist = raiz / "frontend" / "dist"
    return dist if (dist / "index.html").is_file() else None


def montar(app: FastAPI) -> bool:
    """Monta a interface compilada. Devolve se montou."""
    dist = diretorio_da_interface()
    if dist is None:
        log.info("interface_nao_compilada", dica="rode `npm run build` em frontend/")
        return False

    # Os arquivos com hash no nome podem ser cacheados para sempre; o index.html
    # nao (senao o navegador segura a versao velha depois de um novo build).
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    publico = dist.parent / "public"
    if (dist / "assets").is_dir() is False and publico.is_dir():  # pragma: no cover
        app.mount("/public", StaticFiles(directory=publico), name="public")

    @app.get("/{caminho:path}", include_in_schema=False)
    def interface(caminho: str) -> FileResponse:
        """Coringa de SPA: qualquer rota desconhecida devolve o index.html.

        E o que faz `#/campanhas` e recarregar a pagina funcionarem.
        """
        primeiro = caminho.split("/", 1)[0]
        if primeiro in RESERVADOS:
            raise HTTPException(status_code=404, detail="Not Found")

        # Arquivo real (favicon.svg, logo.svg...) e servido direto.
        alvo = (dist / caminho).resolve()
        if caminho and alvo.is_file() and alvo.is_relative_to(dist.resolve()):
            return FileResponse(alvo)

        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})

    log.info("interface_montada", origem=str(dist))
    return True
