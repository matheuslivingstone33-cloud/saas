"""A descoberta nao pode perder a rodada inteira por uma consulta que falhou.

Hoje o Places roda em mock e `buscar` nunca levanta excecao. Quando a API real
entrar, uma consulta no meio de um plano de dezenas pode bater rate limit, 5xx
ou circuito aberto — e cada `buscar` ja passou pelo retry do HttpClient antes de
a excecao chegar ao dominio.

Antes deste guardrail, `executar_plano` chamava `buscar` sem try/except: um
unico 503 no meio do plano derrubava a rodada inteira, jogando fora tudo o que
ja fora descoberto (e o custo ja gasto). Este arquivo fixa os dois desfechos:

  * falha ISOLADA: pula a consulta e a rodada continua, entregando os leads das
    consultas que deram certo;
  * falha SUSTENTADA: apos `BUSCAS_COM_ERRO_MAX` seguidas a rodada para com um
    sinal honesto (`interrompido_por_erro`), sem varrer o plano inteiro so para
    repetir a falha.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import UpstreamError
from app.models.campaign import Campaign
from app.models.enums import StatusCampanha
from app.ports.dto import PlacesQuery, PlacesResponse
from app.services.cerebro import ExpansorDeServico
from app.services.descoberta import BUSCAS_COM_ERRO_MAX, DiscoveryService
from app.services.leads import LeadService
from app.services.observador import ColetorDeEventos


class _PlacesInstavel:
    """Envolve o PlacesPort real e levanta erro de transporte em consultas
    escolhidas (por ordem de chamada, 1-indexado)."""

    provedor = "places"
    modo = "mock"

    def __init__(self, base: Any, falhar_em: set[int]) -> None:
        self._base = base
        self.falhar_em = falhar_em
        self.chamadas = 0

    def buscar(self, query: PlacesQuery) -> PlacesResponse:
        self.chamadas += 1
        if self.chamadas in self.falhar_em:
            raise UpstreamError("503 do provedor", status_code=503)
        return self._base.buscar(query)

    def detalhes(self, place_id: str):  # noqa: ANN201
        return self._base.detalhes(place_id)


class _PortasComPlacesInstavel:
    """Espelha o registry, trocando SO a porta `places` pela instavel."""

    def __init__(self, base: Any, falhar_em: set[int]) -> None:
        self._base = base
        self.places = _PlacesInstavel(base.places, falhar_em)

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._base, nome)


def _campanha(session, usuario, nome: str) -> Campaign:  # noqa: ANN001
    campanha = Campaign(
        user_id=usuario.id,
        nome=nome,
        servico="instalacao e manutencao de ar condicionado para empresas",
        regiao="Fortaleza, CE",
        filtros={},
        status=StatusCampanha.RASCUNHO,
    )
    session.add(campanha)
    session.flush()
    return campanha


def _servico(session, portas, cerebro) -> DiscoveryService:  # noqa: ANN001
    return DiscoveryService(
        session, portas, cerebro.audit, LeadService(session, cerebro.audit)
    )


def test_falha_isolada_nao_derruba_a_rodada(session, usuario, portas_db) -> None:  # noqa: ANN001
    """Uma consulta que estoura no meio do plano nao pode zerar a descoberta."""
    campanha = _campanha(session, usuario, "Falha isolada")
    cerebro = ExpansorDeServico(session, portas_db)
    expansao = cerebro.expandir(campanha.servico, campanha.regiao)

    portas = _PortasComPlacesInstavel(portas_db, falhar_em={1})
    coletor = ColetorDeEventos()
    servico = _servico(session, portas, cerebro)

    # Sem o try/except isto levantava UpstreamError e a rodada inteira caia.
    resultado = servico.descobrir(campanha, expansao, meta_leads=50, observador=coletor)

    assert resultado.consultas_com_erro == 1
    assert resultado.interrompido_por_erro is False
    assert resultado.criados > 0, "as consultas seguintes tinham que salvar a rodada"
    assert "erro_busca" in coletor.etapas


def test_falha_sustentada_para_com_sinal_honesto(session, usuario, portas_db) -> None:  # noqa: ANN001
    """Provedor fora do ar: para apos o limite, sem varrer o plano inteiro."""
    campanha = _campanha(session, usuario, "Provedor fora do ar")
    cerebro = ExpansorDeServico(session, portas_db)
    expansao = cerebro.expandir(campanha.servico, campanha.regiao)

    portas = _PortasComPlacesInstavel(portas_db, falhar_em=set(range(1, 1000)))
    coletor = ColetorDeEventos()
    servico = _servico(session, portas, cerebro)

    resultado = servico.descobrir(campanha, expansao, meta_leads=50, observador=coletor)

    assert resultado.interrompido_por_erro is True
    assert resultado.criados == 0
    # Parou no limite: nao insistiu no plano inteiro so para repetir a falha.
    assert resultado.consultas_com_erro == BUSCAS_COM_ERRO_MAX
    assert portas.places.chamadas == BUSCAS_COM_ERRO_MAX
    assert "interrompido" in coletor.etapas
