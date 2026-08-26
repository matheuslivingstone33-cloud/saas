"""A execucao ao vivo nao pode ser executada duas vezes.

Bug real e caro: abrir `GET /run/stream` EXECUTA a campanha, e o EventSource do
navegador reconecta sozinho quando o servidor fecha o fluxo. Cada reconexao era
uma execucao nova. Medido no preview: 1 clique -> 256 execucoes e 1020
consultas ao Places. Em producao seriam ~US$32 e 256x os creditos debitados.

Tres defesas, testadas aqui:
  1. trava em memoria: conexao concorrente recebe 409;
  2. status da campanha: se ja esta rodando, nao comeca de novo;
  3. `retry:` alto no proprio fluxo, para o navegador nao reabrir.
"""

from __future__ import annotations

import re
import uuid

from app.api.routes import stream as mod
from app.models.campaign import Campaign
from app.models.enums import StatusCampanha
from app.repositories.misc import CostEventRepository


def _criar(client, session, nome: str) -> dict:
    """Cria a campanha e COMMITA.

    A rota do stream abre sessao propria (ela precisa: a campanha roda numa
    thread que sobrevive ao fim da requisicao). Logo, ela so enxerga o que ja
    foi commitado — dado de teste pendente na sessao seria invisivel.
    """
    resposta = client.post(
        "/v1/campaigns",
        json={
            "nome": nome,
            "servico": "manutencao de ar condicionado para empresas",
            "regiao": "Fortaleza, CE",
        },
    )
    assert resposta.status_code == 201, resposta.text
    session.commit()
    return resposta.json()


def _consumir(client, campaign_id: str, limite: int = 3) -> str:
    """Consome o fluxo inteiro e devolve o corpo cru."""
    mod._ULTIMA_EXECUCAO.pop(uuid.UUID(campaign_id), None)
    with client.stream(
        "GET", f"/v1/campaigns/{campaign_id}/run/stream", params={"limite_leads": limite}
    ) as r:
        assert r.status_code == 200, r.text
        return "".join(r.iter_text())


def test_stream_narra_a_execucao(client, usuario, session) -> None:
    campanha = _criar(client, session, "Stream narra")
    corpo = _consumir(client, campanha["id"])

    eventos = set(re.findall(r"^event: (\w+)$", corpo, re.MULTILINE))
    assert {"aberto", "inicio", "cerebro", "busca", "qualificado", "fim", "encerrado"} <= eventos
    assert "Cerebro" in corpo or "ramos" in corpo


def test_stream_pede_para_o_navegador_nao_reconectar(client, usuario, session) -> None:
    """`retry:` alto e o freio no nivel do protocolo — sem ele, o navegador
    reabre sozinho e a campanha roda de novo."""
    campanha = _criar(client, session, "Stream retry")
    corpo = _consumir(client, campanha["id"])

    achado = re.search(r"^retry: (\d+)$", corpo, re.MULTILINE)
    assert achado, "o fluxo precisa mandar `retry:`"
    assert int(achado.group(1)) >= 3_600_000, "o retry precisa ser longo o bastante"


def test_reabrir_o_stream_nao_executa_de_novo(client, usuario, session) -> None:
    """A defesa que protege o dinheiro: rodar duas vezes tem que custar uma."""
    campanha = _criar(client, session, "Stream sem duplicar")
    _consumir(client, campanha["id"])

    custos = CostEventRepository(session)
    campaign_uuid = uuid.UUID(campanha["id"])

    def consultas_places() -> int:
        pagina = custos.listar(usuario.id, campaign_id=campaign_uuid, por_pagina=500)
        return len([c for c in pagina.itens if c.provedor == "places"])

    apos_primeira = consultas_places()
    assert apos_primeira > 0

    # Simula a reconexao do navegador com a campanha ainda marcada como em
    # andamento — exatamente o estado que gerava a reexecucao.
    alvo = session.get(Campaign, campaign_uuid)
    alvo.status = StatusCampanha.DESCOBRINDO
    session.commit()

    corpo = _consumir(client, campanha["id"])
    assert "ja esta em execucao" in corpo

    apos_segunda = consultas_places()
    assert apos_segunda == apos_primeira, (
        "a reconexao nao pode gastar mais nada: "
        f"{apos_primeira} -> {apos_segunda} consultas ao Places"
    )


def test_conexao_concorrente_recebe_409(client, usuario, session) -> None:
    """Duas abas abertas na mesma campanha: a segunda e recusada."""
    campanha = _criar(client, session, "Stream concorrente")
    campaign_uuid = uuid.UUID(campanha["id"])

    # Simula uma execucao em andamento neste processo.
    conseguiu, _ = mod._reservar(campaign_uuid)
    assert conseguiu is True
    try:
        resposta = client.get(f"/v1/campaigns/{campanha['id']}/run/stream")
        assert resposta.status_code == 409
        assert "ja esta em execucao" in resposta.json()["detail"]
    finally:
        mod._liberar(campaign_uuid)
        mod._ULTIMA_EXECUCAO.pop(campaign_uuid, None)


def test_intervalo_minimo_entre_execucoes(client, usuario, session) -> None:
    """Terceira defesa: mesmo sequencial, nao da para reexecutar em rajada.

    E o que teria contido o laco do React — a trava de concorrencia sozinha nao
    barra execucoes uma DEPOIS da outra.
    """
    campanha = _criar(client, session, "Stream intervalo")
    campaign_uuid = uuid.UUID(campanha["id"])
    try:
        _consumir(client, campanha["id"])

        # Logo em seguida, a mesma campanha e recusada.
        resposta = client.get(f"/v1/campaigns/{campanha['id']}/run/stream")
        assert resposta.status_code == 409
        assert "Aguarde" in resposta.json()["detail"]

        # Passado o intervalo, volta a rodar.
        mod._ULTIMA_EXECUCAO[campaign_uuid] = (
            mod.time.monotonic() - mod.INTERVALO_MINIMO_SEGUNDOS - 1
        )
        conseguiu, motivo = mod._reservar(campaign_uuid)
        assert conseguiu is True, motivo
    finally:
        mod._liberar(campaign_uuid)
        mod._ULTIMA_EXECUCAO.pop(campaign_uuid, None)


def test_trava_e_liberada_no_fim_da_execucao(client, usuario, session) -> None:
    campanha = _criar(client, session, "Stream libera")
    campaign_uuid = uuid.UUID(campanha["id"])
    try:
        _consumir(client, campanha["id"])
        assert campaign_uuid not in mod._EM_EXECUCAO, "a trava precisa ser liberada no finally"
    finally:
        mod._ULTIMA_EXECUCAO.pop(campaign_uuid, None)
