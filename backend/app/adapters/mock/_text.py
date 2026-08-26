"""Utilitarios de texto e embedding deterministico (pt-BR).

O FakeLLM precisa ser DETERMINISTICO: a mesma entrada gera sempre a mesma
saida. Isso torna os testes das Fases 0-6 estaveis sem nenhuma chave.

O embedding e um hashing vectorizer (bag-of-words com sinal). Nao tem semantica
de modelo real, mas preserva sobreposicao lexical — suficiente para o matching
servico -> CNAE do Motor 2 rodar e ser testavel.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata

STOPWORDS = frozenset(
    """
    a as o os um uma uns umas de do da dos das em no na nos nas por para com sem sob
    ao aos e ou que se ja mais menos muito pouco meu minha nosso nossa seu sua este
    esta isso aquilo qual quais quando onde como porque entre sobre ate apos antes
    ser estar ter fazer faz feito sao eh e2
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    return sem_acento((texto or "").strip().lower())


def tokenizar(texto: str, remover_stopwords: bool = True) -> list[str]:
    tokens = _TOKEN_RE.findall(normalizar(texto))
    if remover_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 2]
    return tokens


def _hash(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")


def embutir(texto: str, dim: int) -> list[float]:
    """Vetor unitario deterministico de dimensao `dim`."""
    vetor = [0.0] * dim
    tokens = tokenizar(texto)
    if not tokens:
        vetor[0] = 1.0
        return vetor
    for token in tokens:
        h = _hash(token)
        idx = h % dim
        sinal = 1.0 if (h >> 17) % 2 == 0 else -1.0
        vetor[idx] += sinal
        # Prefixo de 4 letras: aproxima variacoes morfologicas (padaria/padarias).
        if len(token) > 4:
            hp = _hash(token[:4])
            vetor[hp % dim] += 0.5 * (1.0 if (hp >> 17) % 2 == 0 else -1.0)
    norma = math.sqrt(sum(v * v for v in vetor))
    if norma == 0:
        vetor[0] = 1.0
        return vetor
    return [v / norma for v in vetor]


def similaridade_cosseno(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    produto = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return produto / (na * nb)


def distancia_cosseno(a: list[float], b: list[float]) -> float:
    return 1.0 - similaridade_cosseno(a, b)


def contar_tokens(texto: str) -> int:
    """Aproximacao de tokens de LLM (~4 caracteres por token)."""
    return max(1, math.ceil(len(texto or "") / 4))


def slug(texto: str, tamanho: int = 40) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")
    return base[:tamanho] or "item"


def dominio_de(url: str | None) -> str | None:
    if not url:
        return None
    limpo = re.sub(r"^https?://", "", url.strip().lower())
    limpo = limpo.split("/")[0]
    return limpo.removeprefix("www.") or None


def telefone_normalizado(telefone: str | None) -> str | None:
    if not telefone:
        return None
    digitos = re.sub(r"\D", "", telefone)
    if not digitos:
        return None
    if not digitos.startswith("55") and len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos
