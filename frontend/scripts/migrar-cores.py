"""Migra as classes de cor cruas do Tailwind para os tokens do tema.

Rodou uma vez na virada visual. Fica no repositorio para documentar o mapa
exato usado — se aparecer cor crua de novo, e so rodar outra vez.

Regra: nenhum componente pode citar cor literal (slate-200, emerald-600...).
Cor literal so funciona em um tema; token funciona nos dois.
"""

from __future__ import annotations

import pathlib
import re
import sys

PREFIXOS = "text|bg|border|ring|divide|fill|stroke|from|to|via|shadow|outline|decoration|placeholder|accent|caret"

# Familia crua -> par (token forte, token fraco)
SEMANTICA = {
    "emerald": ("positivo", "positivo-fraco"),
    "green": ("positivo", "positivo-fraco"),
    "teal": ("positivo", "positivo-fraco"),
    "rose": ("perigo", "perigo-fraco"),
    "red": ("perigo", "perigo-fraco"),
    "amber": ("atencao", "atencao-fraco"),
    "yellow": ("atencao", "atencao-fraco"),
    "orange": ("atencao", "atencao-fraco"),
    "sky": ("acento", "acento/10"),
    "cyan": ("acento", "acento/10"),
    "blue": ("acento", "acento/10"),
    "indigo": ("marca", "marca-fraca"),
    "violet": ("marca", "marca-fraca"),
    "purple": ("marca", "marca-fraca"),
    "fuchsia": ("marca", "marca-fraca"),
}


def traduzir(prefixo: str, familia: str, tom: int) -> str | None:
    """Devolve a classe com token, ou None se nao houver troca a fazer."""
    if familia == "slate" or familia == "gray" or familia == "zinc" or familia == "neutral":
        if prefixo == "text":
            if tom >= 800:
                return "text-texto"
            if tom >= 600:
                return "text-texto-medio"
            return "text-texto-fraco"
        if prefixo == "bg":
            if tom <= 50:
                return "bg-superficie-2"
            if tom <= 200:
                return "bg-superficie-3"
            if tom <= 400:
                return "bg-borda-forte"
            return "bg-texto-fraco"
        if prefixo in ("border", "divide", "ring", "outline"):
            return f"{prefixo}-borda-forte" if tom >= 300 else f"{prefixo}-borda"
        return f"{prefixo}-texto-fraco"

    if familia == "marca":
        # A escala antiga do tema (marca-500/600/50) vira o token unico.
        if tom >= 600:
            return f"{prefixo}-marca-forte"
        if tom <= 100:
            return f"{prefixo}-marca-fraca"
        return f"{prefixo}-marca"

    par = SEMANTICA.get(familia)
    if par is None:
        return None
    forte, fraco = par

    if prefixo == "text":
        return f"text-{forte}"
    if prefixo == "bg":
        # Fundo claro (tom baixo) vira o token fraco; fundo solido vira o forte.
        return f"bg-{fraco}" if tom <= 200 else f"bg-{forte}"
    if prefixo in ("border", "divide", "ring", "outline"):
        return f"{prefixo}-{forte}/30"
    return f"{prefixo}-{forte}"


PADRAO = re.compile(rf"\b({PREFIXOS})-(slate|gray|zinc|neutral|marca|{'|'.join(SEMANTICA)})-(\d{{2,3}})\b")


def migrar(texto: str) -> tuple[str, int]:
    trocas = 0

    def troca(m: re.Match[str]) -> str:
        nonlocal trocas
        novo = traduzir(m.group(1), m.group(2), int(m.group(3)))
        if novo is None:
            return m.group(0)
        trocas += 1
        return novo

    return PADRAO.sub(troca, texto), trocas


def main(alvos: list[str]) -> int:
    total = 0
    for padrao in alvos:
        for caminho in pathlib.Path(".").glob(padrao):
            original = caminho.read_text(encoding="utf-8")
            novo, n = migrar(original)
            if n:
                caminho.write_text(novo, encoding="utf-8")
                print(f"{caminho}: {n} classes migradas")
                total += n
    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["src/**/*.tsx"]))
