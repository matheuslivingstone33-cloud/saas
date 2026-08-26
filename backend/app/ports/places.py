"""Porta de descoberta de empresas.

GUARDRAIL: a unica fonte permitida e a Google Places API (New).
Scraping de Google Maps/Earth e proibido e nao sera implementado.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ports.dto import PlaceResult, PlacesQuery, PlacesResponse


@runtime_checkable
class PlacesPort(Protocol):
    provedor: str
    modo: str

    def buscar(self, query: PlacesQuery) -> PlacesResponse:
        """Text Search: descobre empresas por termo + regiao."""
        ...

    def detalhes(self, place_id: str) -> PlaceResult | None:
        """Place Details: campos adicionais (field mask enxuta)."""
        ...
