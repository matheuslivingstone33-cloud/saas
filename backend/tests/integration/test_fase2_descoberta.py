"""FASE 2 — Motor 1 (Descoberta): QueryBuilder, enriquecimento, dedup e B2B."""

from __future__ import annotations

import pytest

from app.models.campaign import Campaign
from app.models.enums import StatusCampanha
from app.ports.dto import PlaceResult
from app.services.cerebro import Expansao, ExpansorDeServico, RamoRelevante
from app.services.descoberta import DiscoveryService, _uf_do_endereco, eh_empresa
from app.services.query_builder import QueryBuilder

SERVICO = "instalacao e manutencao de ar condicionado para empresas"


def _expansao(termos: list[str], regiao: str = "Fortaleza, CE") -> Expansao:
    return Expansao(
        servico=SERVICO,
        regiao=regiao,
        ramos=[RamoRelevante("4711302", "Supermercados", 0.4, 0.8, ["supermercado"])],
        termos=termos,
        excluir_termos=["residencial"],
    )


def _campanha(session, usuario, filtros=None, nome="Descoberta") -> Campaign:  # noqa: ANN001
    campanha = Campaign(
        user_id=usuario.id,
        nome=nome,
        servico=SERVICO,
        regiao="Fortaleza, CE",
        filtros=filtros or {},
        status=StatusCampanha.RASCUNHO,
    )
    session.add(campanha)
    session.flush()
    return campanha


# --- QueryBuilder (puro, sem I/O) --------------------------------------------
def test_query_builder_distribui_entre_termos() -> None:
    plano = QueryBuilder().construir(_expansao(["supermercado", "hotel", "clinica"]), meta_leads=9)
    termos = [c.termo for c in plano.consultas]
    assert termos == ["supermercado", "hotel", "clinica"]
    assert len(set(termos)) == len(termos), "nenhum termo pode repetir na mesma rodada"


def test_query_builder_nunca_esgota_a_cota_no_primeiro_termo() -> None:
    plano = QueryBuilder().construir(_expansao(["a", "b", "c", "d", "e"]), meta_leads=3)
    assert len(plano.consultas) >= 5, "todos os termos devem ser consultados ao menos uma vez"


def test_query_builder_respeita_teto_de_consultas() -> None:
    muitos = [f"termo{i}" for i in range(100)]
    plano = QueryBuilder(max_consultas=10).construir(_expansao(muitos), meta_leads=500)
    assert len(plano.consultas) == 10


def test_query_builder_explode_bairros() -> None:
    plano = QueryBuilder().construir(
        _expansao(["hotel"]), meta_leads=6, filtros={"bairros": ["Meireles", "Aldeota"]}
    )
    regioes = {c.regiao for c in plano.consultas}
    assert regioes == {"Meireles, Fortaleza, CE", "Aldeota, Fortaleza, CE"}


def test_query_builder_propaga_exclusoes_e_raio() -> None:
    plano = QueryBuilder().construir(
        _expansao(["hotel"]),
        meta_leads=3,
        filtros={"raio_km": 25, "excluir_termos": ["particular"]},
    )
    consulta = plano.consultas[0]
    assert consulta.raio_m == 25_000
    assert "residencial" in consulta.excluir_termos
    assert "particular" in consulta.excluir_termos


def test_query_builder_estima_custo_antes_de_gastar() -> None:
    plano = QueryBuilder().construir(_expansao(["hotel", "clinica"]), meta_leads=6)
    # 32.000 micro-USD por Text Search (tabela de precos)
    assert plano.custo_estimado_micros == 32_000 * len(plano.consultas)


def test_query_builder_sem_termos_nao_gera_consulta() -> None:
    assert len(QueryBuilder().construir(_expansao([]), meta_leads=10).consultas) == 0


def test_query_builder_usa_termos_fixados_no_filtro() -> None:
    plano = QueryBuilder().construir(
        _expansao(["hotel"]), meta_leads=3, filtros={"termos": ["padaria", "acougue"]}
    )
    assert {c.termo for c in plano.consultas} == {"padaria", "acougue"}


# --- Guardrail B2B (puro) -----------------------------------------------------
@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("Boa Compra Supermercados", True),
        ("Condominio Residencial Vista Mar", False),
        ("Casa particular do Joao", False),
        ("Hotel Brisa Mar", True),
    ],
)
def test_filtro_b2b(nome: str, esperado: bool) -> None:
    place = PlaceResult(place_id="x", nome=nome, endereco_formatado="Rua Y, 10 - Fortaleza, CE")
    assert eh_empresa(place) is esperado


# --- Extracao de UF do endereco (a virada mock -> Places real) ----------------
# O mock devolve endereco limpo terminando na UF ("... Fortaleza - CE"). O Google
# real anexa CEP e pais ("... Fortaleza - CE, 60150-160, Brasil"), entao pegar os
# dois ultimos caracteres dava "IL" (de "Brasil") — uma UF inventada que FILTRA
# fora todo match na Receita (`registro.uf != uf`), pior que nao filtrar nada.
@pytest.mark.parametrize(
    ("endereco", "esperado"),
    [
        # formato do mock (limpo, UF no fim) — continua funcionando
        ("Rua Barao de Aracati, 1200 - Aldeota, Fortaleza - CE", "CE"),
        # formato real do Places BR: UF + CEP + pais
        ("Av. Santos Dumont, 3300 - Papicu, Fortaleza - CE, 60150-160, Brasil", "CE"),
        # idem em ingles ("Brazil")
        ("Av. Paulista, 1578 - Bela Vista, Sao Paulo - SP, 01310-200, Brazil", "SP"),
        # sem CEP, so pais no fim
        ("R. da Consolacao - Consolacao, Sao Paulo - SP, Brasil", "SP"),
        # termina em CEP: a UF esta no meio, nao no fim
        ("Av. Paulista, 1578 - Sao Paulo - SP, 01310-200", "SP"),
        # sem estado nenhum: nao inventa UF a partir de "Brasil"
        ("Endereco sem estado, so cidade, Brasil", None),
        (None, None),
        ("", None),
    ],
)
def test_uf_do_endereco_tolera_formato_real_do_places(
    endereco: str | None, esperado: str | None
) -> None:
    assert _uf_do_endereco(endereco) == esperado


# --- DiscoveryService ---------------------------------------------------------
def test_descoberta_cria_leads_enriquecidos(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario)
    expansao = ExpansorDeServico(session, portas_db).expandir(
        SERVICO, "Fortaleza, CE", user_id=usuario.id
    )
    resultado = DiscoveryService(session, portas_db).descobrir(campanha, expansao, meta_leads=5)

    assert resultado.criados > 0
    assert resultado.consultas > 0
    com_cnpj = [lead for lead in resultado.leads if lead.cnpj]
    assert com_cnpj, "pelo menos um lead deveria casar com a base da Receita"
    for lead in com_cnpj:
        assert len(lead.cnpj) == 14
        assert lead.provenance["fonte_secundaria"] == "receita_federal_dados_abertos"


def test_descoberta_para_ao_atingir_a_meta(session, usuario, portas_db) -> None:
    campanha = _campanha(session, usuario, nome="Meta")
    expansao = ExpansorDeServico(session, portas_db).expandir(
        SERVICO, "Fortaleza, CE", user_id=usuario.id
    )
    resultado = DiscoveryService(session, portas_db).descobrir(campanha, expansao, meta_leads=2)
    assert resultado.criados == 2


def test_descoberta_deduplica_entre_campanhas(session, usuario, portas_db) -> None:
    expansao = ExpansorDeServico(session, portas_db).expandir(
        SERVICO, "Fortaleza, CE", user_id=usuario.id
    )
    servico = DiscoveryService(session, portas_db)

    primeira = servico.descobrir(_campanha(session, usuario, nome="D1"), expansao, meta_leads=5)
    segunda = servico.descobrir(_campanha(session, usuario, nome="D2"), expansao, meta_leads=5)

    assert primeira.criados > 0
    assert segunda.duplicados >= primeira.criados
    ids = {lead.place_id for lead in primeira.leads} & {lead.place_id for lead in segunda.leads}
    assert not ids, "o mesmo place_id nao pode virar lead duas vezes no tenant"


def test_descoberta_registra_custo_por_consulta(session, usuario, portas_db) -> None:
    from app.repositories.misc import CostEventRepository

    campanha = _campanha(session, usuario, nome="Custo Places")
    portas_db.cost.user_id = usuario.id
    portas_db.cost.campaign_id = campanha.id
    expansao = ExpansorDeServico(session, portas_db).expandir(
        SERVICO, "Fortaleza, CE", user_id=usuario.id
    )
    resultado = DiscoveryService(session, portas_db).descobrir(campanha, expansao, meta_leads=3)

    eventos = CostEventRepository(session).listar(usuario.id, campaign_id=campanha.id).itens
    places = [e for e in eventos if e.provedor == "places"]
    assert len(places) == resultado.consultas
    assert all(e.balde == 1 for e in places)


def test_enriquecimento_desempata_pelo_telefone(session, usuario, portas_db) -> None:
    servico = DiscoveryService(session, portas_db)
    place = PlaceResult(
        place_id="p1",
        nome="Supermercado Boa Compra",
        endereco_formatado="Av. Santos Dumont, 3300 - Papicu, Fortaleza - CE",
        telefone="+55 85 3344-5566",
    )
    empresa = servico.enriquecer(place)
    assert empresa is not None
    assert empresa.cnpj == "22333444000172"


def test_pipeline_reporta_metricas_do_motor_1(session, usuario, portas_db) -> None:
    from app.services.pipeline import PipelineStub

    campanha = _campanha(session, usuario, nome="Pipeline M1")
    resultado = PipelineStub(session, portas_db).executar(campanha, limite_leads=3)
    assert resultado.consultas_places > 0
    assert resultado.descobertos > 0
    assert "consultas_places" in resultado.to_dict()
