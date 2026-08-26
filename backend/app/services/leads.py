"""Servico de lead: transicoes de estado validadas + auditadas.

Nenhum outro lugar do sistema escreve `lead.status` diretamente.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.adapters.mock._text import dominio_de, telefone_normalizado
from app.core.ids import now
from app.core.logging import get_logger
from app.domain import lead_state
from app.models.enums import Ator, StatusLead
from app.models.lead import Lead
from app.ports.dto import CompanyRecord, PlaceResult
from app.repositories.leads import LeadRepository
from app.services.aprendizado import LoopAprendizado
from app.services.audit import AuditService

log = get_logger("leads")

BASE_LEGAL_PADRAO = "legitimo_interesse"


class LeadService:
    def __init__(
        self,
        session: Session,
        audit: AuditService,
        aprendizado: LoopAprendizado | None = None,
    ) -> None:
        self.session = session
        self.audit = audit
        self.repo = LeadRepository(session)
        self.aprendizado = aprendizado or LoopAprendizado(session)

    # -- transicoes -----------------------------------------------------------
    def transicionar(
        self,
        lead: Lead,
        novo: StatusLead,
        *,
        motivo: str | None = None,
        ator: Ator = Ator.SISTEMA,
    ) -> Lead:
        atual = lead.status
        lead_state.validar(atual, novo)
        lead.status = novo
        if novo is StatusLead.DESCARTADO and motivo:
            lead.motivo_descarte = motivo
        self.session.flush()

        # Gancho do loop de aprendizado: desfecho de lead realimenta os pesos
        # do ScoringService daquele tenant (Fase 1).
        self.aprendizado.observar(
            user_id=lead.user_id,
            resultado=novo,
            componentes=(lead.score_breakdown or {}).get("componentes"),
        )
        self.audit.transicao_lead(
            lead_id=lead.id,
            de=atual.value,
            para=novo.value,
            motivo=motivo,
            user_id=lead.user_id,
            ator=ator,
        )
        log.info("lead_transicao", lead_id=str(lead.id), de=atual.value, para=novo.value)
        return lead

    # -- criacao a partir das portas -----------------------------------------
    def criar_de_place(
        self,
        *,
        user_id: uuid.UUID,
        campaign_id: uuid.UUID,
        place: PlaceResult,
        empresa: CompanyRecord | None,
        termo_busca: str,
    ) -> Lead | None:
        """Cria o lead ja com PROVENIENCIA registrada. Devolve None se duplicado."""
        fone = telefone_normalizado(place.telefone or (empresa.telefone if empresa else None))
        dominio = dominio_de(place.website)
        cnpj = empresa.cnpj if empresa else None

        duplicado = self.repo.encontrar_duplicado(
            user_id,
            cnpj=cnpj,
            place_id=place.place_id,
            telefone_normalizado=fone,
            dominio=dominio,
        )
        if duplicado is not None:
            log.info(
                "lead_duplicado_ignorado",
                place_id=place.place_id,
                existente=str(duplicado.id),
            )
            return None

        provenance = {
            "fonte_primaria": place.fonte,
            "place_id": place.place_id,
            "termo_busca": termo_busca,
            "coletado_em": now().isoformat(),
            "base_legal": BASE_LEGAL_PADRAO,
            "finalidade": "prospeccao_b2b",
            "campos": {
                "nome": place.fonte,
                "endereco": place.fonte,
                "telefone": place.fonte,
                "website": place.fonte,
            },
        }
        if empresa is not None:
            provenance["fonte_secundaria"] = empresa.fonte
            provenance["campos"].update(
                {
                    "cnpj": empresa.fonte,
                    "razao_social": empresa.fonte,
                    "cnae_principal": empresa.fonte,
                    "porte": empresa.fonte,
                    "email": empresa.fonte,
                }
            )

        lead = Lead(
            user_id=user_id,
            campaign_id=campaign_id,
            cnpj=cnpj,
            razao_social=empresa.razao_social if empresa else place.nome,
            nome_fantasia=(empresa.nome_fantasia if empresa else None) or place.nome,
            cnae_principal=empresa.cnae_principal if empresa else None,
            cnaes_secundarios=empresa.cnaes_secundarios if empresa else None,
            porte=_porte(empresa),
            endereco=place.endereco_formatado,
            bairro=empresa.bairro if empresa else None,
            municipio=empresa.municipio if empresa else _municipio_de(place.endereco_formatado),
            uf=empresa.uf if empresa else _uf_de(place.endereco_formatado),
            cep=empresa.cep if empresa else None,
            latitude=place.latitude,
            longitude=place.longitude,
            telefone=place.telefone or (empresa.telefone if empresa else None),
            telefone_normalizado=fone,
            email=empresa.email if empresa else None,
            website=place.website,
            dominio=dominio,
            place_id=place.place_id,
            status=StatusLead.DESCOBERTO,
            provenance=provenance,
            contexto={
                "tipos_google": place.tipos,
                "nota": place.nota,
                "avaliacoes": place.total_avaliacoes,
            },
        )
        self.repo.add(lead)
        self.audit.dado_coletado(
            entidade_id=lead.id,
            provenance=provenance,
            user_id=user_id,
            base_legal=BASE_LEGAL_PADRAO,
        )
        return lead


def _porte(empresa: CompanyRecord | None) -> str:
    from app.models.enums import Porte

    if empresa is None:
        return Porte.DESCONHECIDO
    try:
        return Porte(empresa.porte)
    except ValueError:
        return Porte.DESCONHECIDO


def _municipio_de(endereco: str | None) -> str | None:
    if not endereco or "," not in endereco:
        return None
    cauda = endereco.split("-")[-2] if endereco.count("-") >= 2 else endereco.split(",")[-1]
    return cauda.strip() or None


def _uf_de(endereco: str | None) -> str | None:
    if not endereco:
        return None
    cauda = endereco.strip()[-2:]
    return cauda.upper() if cauda.isalpha() else None
