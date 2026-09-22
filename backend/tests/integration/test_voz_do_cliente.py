"""A voz do cliente: perfil, o que deu certo e a correcao dele virando regra.

Ate 22/09 a instrucao dada a IA era a mesma para todo cliente: as mensagens
saiam corretas e genericas. Estes testes fixam as tres fontes que personalizam
sem treinar modelo nenhum — e que, por serem contexto, valem ja na proxima
mensagem.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.enums import (
    Canal,
    Direcao,
    NivelAutonomia,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
)
from app.models.lead import Lead
from app.models.message import Message
from app.services.personalizacao import PersonalizationService
from app.services.voz import voz_do_cliente

SERVICO = "manutencao preventiva de ar condicionado para empresas"


def _campanha(session, usuario) -> Campaign:  # noqa: ANN001
    campanha = Campaign(
        user_id=usuario.id, nome="Voz", servico=SERVICO, regiao="Fortaleza, CE",
        filtros={}, status=StatusCampanha.EXECUTANDO,
        autonomy_override=NivelAutonomia.ASSISTIDO,
    )
    session.add(campanha)
    session.flush()
    return campanha


def _lead(session, usuario, campanha, *, email="contato@hotelalfa.com.br") -> Lead:  # noqa: ANN001
    lead = Lead(
        user_id=usuario.id, campaign_id=campanha.id, razao_social="HOTEL ALFA LTDA",
        email=email, municipio="Fortaleza", uf="CE", status=StatusLead.QUALIFICADO,
        provenance={"fonte": "teste"}, score=70,
    )
    session.add(lead)
    session.flush()
    return lead


def _saida(session, usuario, campanha, lead, corpo, **extra) -> Message:  # noqa: ANN001
    extra.setdefault("status", StatusMensagem.ENVIADA)
    mensagem = Message(
        user_id=usuario.id, campaign_id=campanha.id, lead_id=lead.id, canal=Canal.EMAIL,
        direcao=Direcao.SAIDA, destinatario=lead.email, corpo=corpo, **extra,
    )
    session.add(mensagem)
    session.flush()
    return mensagem


# --- 1. Perfil ----------------------------------------------------------------
def test_perfil_do_cliente_entra_na_instrucao(session, usuario) -> None:
    usuario.empresa = "Refrigeracao Ceara"
    usuario.tom_de_voz = "direto, sem rodeios"
    usuario.diferenciais = "atendimento em 4 horas em toda a Grande Fortaleza"
    usuario.provas = "atendemos 3 redes de hotel ha 6 anos"
    usuario.evitar = "nunca prometer desconto"
    session.flush()

    voz = voz_do_cliente(session, usuario)

    assert "Refrigeracao Ceara" in voz
    assert "direto, sem rodeios" in voz
    assert "4 horas" in voz
    assert "3 redes de hotel" in voz
    assert "nunca prometer desconto" in voz


def test_conta_sem_perfil_nao_muda_a_instrucao(session, usuario) -> None:
    """Conta nova escreve com a instrucao padrao, como antes."""
    usuario.empresa = None
    usuario.nome = ""
    session.flush()
    assert voz_do_cliente(session, usuario) == ""


def test_perfil_pela_api_vai_e_volta(client, usuario) -> None:
    r = client.patch(
        "/v1/me",
        json={
            "tom_de_voz": "caloroso",
            "diferenciais": "equipe propria, sem terceirizar",
            "provas": "Hotel Brisa Mar, ha 4 anos",
            "evitar": "nao citar concorrente pelo nome",
        },
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["tom_de_voz"] == "caloroso"
    assert corpo["evitar"] == "nao citar concorrente pelo nome"
    assert client.get("/v1/me").json()["diferenciais"].startswith("equipe propria")


# --- 2. O que ja deu certo ------------------------------------------------------
def test_mensagem_que_recebeu_resposta_vira_exemplo(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario)
    respondeu = _lead(session, usuario, campanha)
    respondeu.status = StatusLead.RESPONDIDO
    _saida(session, usuario, campanha, respondeu, "Oi Alfa, a conta de energia do ar...")

    calado = _lead(session, usuario, campanha, email="contato@hotelbeta.com.br")
    _saida(session, usuario, campanha, calado, "Texto que ninguem respondeu jamais")
    session.flush()

    voz = voz_do_cliente(session, usuario)
    assert "conta de energia" in voz
    assert "ninguem respondeu" not in voz, "so o que deu resposta vira exemplo"


def test_exemplo_de_um_cliente_nao_vaza_para_outro(session, usuario, portas_db) -> None:
    from app.models.user import User

    campanha = _campanha(session, usuario)
    lead = _lead(session, usuario, campanha)
    lead.status = StatusLead.CONVERTIDO
    _saida(session, usuario, campanha, lead, "segredo comercial do cliente A")
    vizinho = User(email="b@empresa.com.br", nome="Cliente B", empresa="B")
    session.add(vizinho)
    session.flush()

    assert "segredo comercial" not in voz_do_cliente(session, vizinho)


# --- 3. A correcao vira regra ---------------------------------------------------
def test_edicao_antes_de_aprovar_guarda_o_original(client, session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario)
    lead = _lead(session, usuario, campanha)
    mensagem = _saida(
        session, usuario, campanha, lead, "Texto da IA, meio formal.",
        status=StatusMensagem.AGUARDANDO_APROVACAO, metadados={"gerado_por": "ia"},
    )
    session.commit()

    r = client.patch(f"/v1/messages/{mensagem.id}", json={"corpo": "Fala, pessoal do Alfa!"})
    assert r.status_code == 200, r.text

    session.refresh(mensagem)
    assert mensagem.corpo == "Fala, pessoal do Alfa!"
    assert mensagem.corpo_original == "Texto da IA, meio formal."
    assert mensagem.metadados["editado_pelo_cliente"] is True


def test_nao_da_para_editar_depois_de_enviada(client, session, usuario, portas_db) -> None:
    """O e-mail ja saiu: editar aqui so mentiria para o proprio cliente."""
    campanha = _campanha(session, usuario)
    lead = _lead(session, usuario, campanha)
    mensagem = _saida(session, usuario, campanha, lead, "ja foi")
    session.commit()

    r = client.patch(f"/v1/messages/{mensagem.id}", json={"corpo": "outra coisa"})
    assert r.status_code == 409


def test_correcao_do_cliente_instrui_a_proxima_mensagem(
    session, usuario, portas_db
) -> None:
    """A diferenca entre o que a IA escreveu e o que o dono mandou vira instrucao."""
    campanha = _campanha(session, usuario)
    lead = _lead(session, usuario, campanha)
    _saida(
        session, usuario, campanha, lead, "Fala, pessoal do Alfa!",
        corpo_original="Prezados senhores, venho por meio desta",
        status=StatusMensagem.APROVADA,
    )
    session.flush()

    voz = voz_do_cliente(session, usuario)
    assert "Prezados senhores" in voz and "Fala, pessoal" in voz

    # E chega de verdade ao pedido feito ao modelo.
    outro = _lead(session, usuario, campanha, email="contato@hotelgama.com.br")
    PersonalizationService(session, portas_db).gerar(outro, campanha, None, usuario)
    ultima = portas_db.llm.chamadas[-1]
    assert "Prezados senhores" in (ultima.system or "")


def test_instrucao_padrao_continua_quando_nao_ha_voz(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario)
    lead = _lead(session, usuario, campanha)
    usuario.empresa = None
    usuario.nome = ""
    session.flush()

    PersonalizationService(session, portas_db).gerar(lead, campanha, None, usuario)
    ultima = portas_db.llm.chamadas[-1]
    assert (ultima.system or "").startswith("Voce redige abordagens comerciais B2B")
    assert "SOBRE QUEM ASSINA" not in (ultima.system or "")


@pytest.mark.parametrize("campo", ["diferenciais", "provas", "evitar"])
def test_texto_muito_longo_e_cortado(session, usuario, campo: str) -> None:
    """O perfil nao pode virar um pedido gigante a cada mensagem."""
    setattr(usuario, campo, "x" * 5_000)
    session.flush()
    assert len(voz_do_cliente(session, usuario)) < 2_000


def test_mensagem_editada_aparece_na_lista_com_o_original(client, session, usuario) -> None:
    """A tela precisa conseguir mostrar o que foi corrigido."""
    campanha = _campanha(session, usuario)
    lead = _lead(session, usuario, campanha)
    _saida(
        session, usuario, campanha, lead, "depois", corpo_original="antes",
        status=StatusMensagem.APROVADA,
    )
    session.commit()

    itens = client.get("/v1/messages").json()["itens"]
    alvo = next(m for m in itens if m["corpo"] == "depois")
    assert alvo["corpo_original"] == "antes"
    assert session.execute(select(Message.corpo_original)).scalars().first() == "antes"
