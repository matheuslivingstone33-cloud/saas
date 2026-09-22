from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import JSONType, LongText
from app.models.enums import Canal, Direcao, StatusMensagem, pg_enum


class Message(Base, UUIDPk, Timestamps):
    """Mensagem de abordagem (saida) ou resposta do lead (entrada)."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_user_status", "user_id", "status"),
        Index("ix_messages_campaign_status", "campaign_id", "status"),
        Index("ix_messages_lead", "lead_id"),
        Index("ix_messages_thread", "lead_id", "ordem"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )

    # Ordem DENTRO da conversa daquele lead.
    #
    # Relogio nao serve como chave de ordem aqui: a pergunta do lead e a
    # replica da IA nascem no mesmo turno, e `datetime.now()` no Windows tem
    # granularidade de ~15ms — as duas saiam com o mesmo carimbo e a thread
    # aparecia invertida, com a resposta antes da pergunta. Mesma solucao que
    # `audit_logs.seq` usa.
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    canal: Mapped[Canal] = mapped_column(pg_enum(Canal, "canal"), nullable=False)
    direcao: Mapped[Direcao] = mapped_column(
        pg_enum(Direcao, "direcao"), default=Direcao.SAIDA, nullable=False
    )
    status: Mapped[StatusMensagem] = mapped_column(
        pg_enum(StatusMensagem, "status_mensagem"), default=StatusMensagem.RASCUNHO, nullable=False
    )

    destinatario: Mapped[str | None] = mapped_column(String(320))
    # Em mensagem de ENTRADA, `destinatario` somos nos e `remetente` e o lead.
    # Guardar o endereco real importa para auditoria e para casar a resposta
    # com o lead certo quando o contato responde de outro e-mail.
    remetente: Mapped[str | None] = mapped_column(String(320), index=True)
    assunto: Mapped[str | None] = mapped_column(String(300))
    corpo: Mapped[str] = mapped_column(LongText, nullable=False)
    #: O texto como a IA escreveu, guardado quando o cliente edita antes de
    #: aprovar. A diferenca entre os dois vira instrucao para as proximas
    #: mensagens (services/voz.py) — a correcao dele vale mais que regra de
    #: estilo nossa.
    corpo_original: Mapped[str | None] = mapped_column(LongText)
    declaracao_ia: Mapped[str | None] = mapped_column(String(300))

    @property
    def gerado_por_ia(self) -> bool:
        """Quem escreveu: o agente ou uma pessoa.

        Era deduzido da presenca da declaracao de IA no corpo. Com a declaracao
        opcional (DECLARAR_IA), toda mensagem pareceria escrita a mao — inclusive
        na tela do proprio cliente, que precisa saber o que o agente mandou em
        nome dele.
        """
        return (self.metadados or {}).get("gerado_por") == "ia"
    link_descadastro: Mapped[str | None] = mapped_column(String(500))

    provider_message_id: Mapped[str | None] = mapped_column(String(255), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), index=True)
    erro: Mapped[str | None] = mapped_column(LongText)
    tentativas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # O que o provedor devolveu DEPOIS do envio: 'permanente' (o endereco nao
    # existe), 'transitorio' (caixa cheia, servidor fora) ou 'reclamacao' (a
    # pessoa marcou como spam). Coluna, e nao chave no JSON, porque e disto que
    # sai a taxa de retorno da campanha — e essa conta precisa rodar igual no
    # SQLite e no PostgreSQL.
    retorno: Mapped[str | None] = mapped_column(String(20), index=True)

    custo_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    agendado_para: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadados: Mapped[dict | None] = mapped_column(JSONType)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Message {self.canal}/{self.status} -> {self.destinatario}>"
