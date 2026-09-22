"""A voz do cliente: o que o agente precisa saber antes de escrever por ele.

Ate 22/09 a instrucao era a mesma para todo mundo — "abordagens B2B curtas, sem
promessas exageradas" — e o resultado era correto e generico. Faltava o que so o
dono do negocio sabe, e tres fontes disso ja existem no proprio sistema:

1. **O perfil**, respondido uma vez: o que diferencia, provas, o que nao dizer e
   o tom de voz.
2. **O que ja deu certo**: a mensagem que abriu conversa com um lead que
   respondeu vale mais que qualquer regra de estilo.
3. **A correcao do dono**: quando ele edita a mensagem antes de aprovar, a
   diferenca entre o que a IA escreveu e o que ele mandou e a licao mais direta
   que existe. Guardamos o antes e o depois e mostramos os dois.

Tudo isso vira UM bloco de texto anexado a instrucao do sistema. Nada de
treinar modelo: e contexto, montado na hora, e por isso muda no minuto seguinte
a uma correcao.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Direcao, StatusLead, StatusMensagem
from app.models.lead import Lead
from app.models.message import Message
from app.models.user import User

#: Teto de caracteres por trecho citado. Exemplo inteiro de e-mail antigo
#: encheria o pedido de token sem melhorar a proxima mensagem.
LIMITE_TRECHO = 600
MAX_EXEMPLOS = 2
MAX_CORRECOES = 2


def _cortar(texto: str | None, limite: int = LIMITE_TRECHO) -> str:
    limpo = (texto or "").strip()
    return limpo if len(limpo) <= limite else limpo[:limite].rstrip() + "…"


def _perfil(user: User | None) -> list[str]:
    if user is None:
        return []
    linhas: list[str] = []
    empresa = user.empresa or user.nome
    if empresa:
        linhas.append(f"Voce escreve em nome de {empresa}.")
    if user.tom_de_voz:
        linhas.append(f"Tom de voz: {_cortar(user.tom_de_voz, 200)}")
    if user.diferenciais:
        linhas.append(f"O que diferencia este negocio: {_cortar(user.diferenciais)}")
    if user.provas:
        linhas.append(
            "Provas que podem ser citadas (so se couberem naturalmente, sem inventar "
            f"numero): {_cortar(user.provas)}"
        )
    if user.evitar:
        linhas.append(f"NAO diga, em hipotese nenhuma: {_cortar(user.evitar)}")
    return linhas


def _exemplos_que_funcionaram(session: Session, user_id, limite: int) -> list[str]:  # noqa: ANN001
    """Mensagens enviadas a leads que acabaram respondendo."""
    corpos = (
        session.execute(
            select(Message.corpo)
            .join(Lead, Message.lead_id == Lead.id)
            .where(
                Message.user_id == user_id,
                Message.direcao == Direcao.SAIDA,
                Message.status == StatusMensagem.ENVIADA,
                Lead.status.in_([StatusLead.RESPONDIDO, StatusLead.CONVERTIDO]),
            )
            .order_by(Message.created_at.desc())
            .limit(limite)
        )
        .scalars()
        .all()
    )
    return [_cortar(c) for c in corpos if (c or "").strip()]


def _correcoes(session: Session, user_id, limite: int) -> list[tuple[str, str]]:  # noqa: ANN001
    linhas = session.execute(
        select(Message.corpo_original, Message.corpo)
        .where(Message.user_id == user_id, Message.corpo_original.is_not(None))
        .order_by(Message.created_at.desc())
        .limit(limite)
    ).all()
    return [(_cortar(antes), _cortar(depois)) for antes, depois in linhas]


def voz_do_cliente(
    session: Session,
    user: User | None,
    *,
    exemplos: int = MAX_EXEMPLOS,
    correcoes: int = MAX_CORRECOES,
) -> str:
    """Bloco de instrucao com o perfil, o que deu certo e o que foi corrigido.

    Devolve string vazia quando nao ha nada — conta nova escreve com a instrucao
    padrao, como antes.
    """
    if user is None:
        return ""

    blocos: list[str] = []
    perfil = _perfil(user)
    if perfil:
        blocos.append("SOBRE QUEM ASSINA A MENSAGEM\n" + "\n".join(f"- {li}" for li in perfil))

    if exemplos > 0:
        anteriores = _exemplos_que_funcionaram(session, user.id, exemplos)
        if anteriores:
            blocos.append(
                "MENSAGENS DESTE CLIENTE QUE RECEBERAM RESPOSTA — siga o estilo, "
                "nao copie o conteudo:\n"
                + "\n".join(f'--- exemplo ---\n"""{c}"""' for c in anteriores)
            )

    if correcoes > 0:
        pares = _correcoes(session, user.id, correcoes)
        if pares:
            blocos.append(
                "CORRECOES QUE O CLIENTE JA FEZ antes de aprovar. Escreva desde o "
                "inicio no jeito da coluna DEPOIS:\n"
                + "\n".join(
                    f'--- antes ---\n"""{antes}"""\n--- depois ---\n"""{depois}"""'
                    for antes, depois in pares
                )
            )

    return "\n\n".join(blocos)
