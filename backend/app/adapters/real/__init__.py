"""Adaptadores REAIS — inertes ate a Fase 7.

Cada classe aqui ja tem a forma final (assinatura identica a do mock) mas ainda
nao executa: levanta ProviderNotConfigured. Isso e proposital — o codigo de
dominio ja compila contra elas, e a Fase 7 so preenche o corpo dos metodos e
vira o flag `*_MODE=real`, sem refatorar nada.

Roteiro da virada (um provedor por vez):
  1. preencher a chave no .env;
  2. trocar UM flag para real;
  3. rodar o smoke test daquele provedor;
  4. so entao passar para o proximo.
"""

from app.adapters.real.anthropic_llm import AnthropicAdapter
from app.adapters.real.anthropic_search import AnthropicWebSearchAdapter
from app.adapters.real.bsp_whatsapp import BSPAdapter
from app.adapters.real.google_places import GooglePlacesAdapter
from app.adapters.real.ses_email import SESAdapter
from app.adapters.real.stripe_billing import StripeAdapter

__all__ = [
    "AnthropicAdapter",
    "AnthropicWebSearchAdapter",
    "BSPAdapter",
    "GooglePlacesAdapter",
    "SESAdapter",
    "StripeAdapter",
]
