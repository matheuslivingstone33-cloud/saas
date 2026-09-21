"""Trilha de auditoria imutavel, encadeada por hash.

Cada registro carrega o hash do anterior. Alterar um registro antigo quebra a
cadeia de todos os seguintes — e `verificar_cadeia()` denuncia. No PostgreSQL,
uma trigger ainda bloqueia UPDATE/DELETE na tabela (migration 0001).

O que e obrigatorio auditar (LGPD + Marco da IA):
  * origem de todo dado pessoal/corporativo coletado (provenance);
  * toda transicao de estado de lead, campanha e assinatura;
  * toda mensagem gerada, aprovada, enviada ou bloqueada;
  * todo opt-out;
  * toda decisao tomada pela IA.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ids import now
from app.core.logging import get_logger
from app.models.audit_log import AuditLog
from app.models.enums import Ator, TipoEvento

log = get_logger("auditoria")

GENESIS = "0" * 64


def _iso(dt) -> str:  # noqa: ANN001
    """Timestamp canonico em UTC.

    Necessario porque o SQLite devolve datetime NAIVE (sem tzinfo) enquanto o
    PostgreSQL devolve AWARE. Sem normalizar, a mesma linha geraria hashes
    diferentes nos dois bancos e a verificacao da cadeia falharia.
    """
    from datetime import UTC

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _canonico(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def calcular_hash(anterior: str | None, payload: dict[str, Any]) -> str:
    base = f"{anterior or GENESIS}|{_canonico(payload)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- escrita --------------------------------------------------------------
    def registrar(
        self,
        *,
        evento: TipoEvento,
        entidade_tipo: str,
        entidade_id: uuid.UUID | None = None,
        dados: dict[str, Any] | None = None,
        ator: Ator = Ator.SISTEMA,
        user_id: uuid.UUID | None = None,
        base_legal: str | None = None,
    ) -> AuditLog:
        anterior = self._ultimo()
        seq = (anterior.seq + 1) if anterior else 1
        criado_em = now()
        payload = {
            "seq": seq,
            "user_id": str(user_id) if user_id else None,
            "ator": ator.value,
            "evento": evento.value,
            "entidade_tipo": entidade_tipo,
            "entidade_id": str(entidade_id) if entidade_id else None,
            "dados": dados or {},
            "base_legal": base_legal,
            "created_at": _iso(criado_em),
        }
        registro = AuditLog(
            seq=seq,
            user_id=user_id,
            ator=ator,
            evento=evento,
            entidade_tipo=entidade_tipo,
            entidade_id=entidade_id,
            dados=dados or {},
            base_legal=base_legal,
            hash_anterior=anterior.hash if anterior else None,
            hash=calcular_hash(anterior.hash if anterior else None, payload),
            created_at=criado_em,
            updated_at=criado_em,
        )
        self.session.add(registro)
        self.session.flush()
        log.info(
            "auditoria",
            seq=seq,
            evento=evento.value,
            entidade=entidade_tipo,
            entidade_id=str(entidade_id) if entidade_id else None,
            ator=ator.value,
        )
        return registro

    def transicao_lead(
        self,
        *,
        lead_id: uuid.UUID,
        de: str,
        para: str,
        motivo: str | None = None,
        user_id: uuid.UUID | None = None,
        ator: Ator = Ator.SISTEMA,
    ) -> AuditLog:
        return self.registrar(
            evento=TipoEvento.LEAD_TRANSICAO,
            entidade_tipo="lead",
            entidade_id=lead_id,
            dados={"de": de, "para": para, "motivo": motivo},
            ator=ator,
            user_id=user_id,
        )

    def dado_coletado(
        self,
        *,
        entidade_id: uuid.UUID,
        provenance: dict[str, Any],
        user_id: uuid.UUID | None = None,
        base_legal: str = "legitimo_interesse",
    ) -> AuditLog:
        # A trilha e imutavel e sobrevive a eliminacao do lead. O `place_id` e a
        # chave estavel do Google para aquela empresa: gravado cru, reidentificava
        # o lead anonimizado com uma consulta. Fica o hash, que ainda prova a
        # origem para quem tiver o place_id em maos.
        dados = dict(provenance)
        if dados.get("place_id"):
            dados["place_id_sha256"] = hashlib.sha256(
                str(dados.pop("place_id")).encode()
            ).hexdigest()[:32]
        return self.registrar(
            evento=TipoEvento.DADO_COLETADO,
            entidade_tipo="lead",
            entidade_id=entidade_id,
            dados=dados,
            ator=Ator.SISTEMA,
            user_id=user_id,
            base_legal=base_legal,
        )

    def decisao_ia(
        self,
        *,
        entidade_tipo: str,
        entidade_id: uuid.UUID | None,
        dados: dict[str, Any],
        user_id: uuid.UUID | None = None,
    ) -> AuditLog:
        return self.registrar(
            evento=TipoEvento.DECISAO_IA,
            entidade_tipo=entidade_tipo,
            entidade_id=entidade_id,
            dados=dados,
            ator=Ator.IA,
            user_id=user_id,
        )

    # -- leitura / integridade ------------------------------------------------
    def _ultimo(self) -> AuditLog | None:
        return self.session.execute(
            select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)
        ).scalar_one_or_none()

    def total(self) -> int:
        return int(self.session.execute(select(func.count(AuditLog.id))).scalar_one())

    def verificar_cadeia(self) -> tuple[bool, int | None]:
        """Revalida a cadeia inteira. Devolve (integra, seq_do_primeiro_erro)."""
        registros = self.session.execute(select(AuditLog).order_by(AuditLog.seq)).scalars().all()
        anterior_hash: str | None = None
        for r in registros:
            payload = {
                "seq": r.seq,
                "user_id": str(r.user_id) if r.user_id else None,
                "ator": r.ator.value if hasattr(r.ator, "value") else str(r.ator),
                "evento": r.evento.value if hasattr(r.evento, "value") else str(r.evento),
                "entidade_tipo": r.entidade_tipo,
                "entidade_id": str(r.entidade_id) if r.entidade_id else None,
                "dados": r.dados or {},
                "base_legal": r.base_legal,
                "created_at": _iso(r.created_at),
            }
            if r.hash_anterior != anterior_hash or r.hash != calcular_hash(anterior_hash, payload):
                return False, r.seq
            anterior_hash = r.hash
        return True, None
