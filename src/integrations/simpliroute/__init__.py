"""Integração com SimpliRoute (módulos auxiliares).

Este pacote expõe o objeto `app` para facilitar imports nos testes
e onde for necessário: `from src.integrations.simpliroute import app`.
"""

from .app import app  # expor o FastAPI app
from . import client, mapper

__all__ = ["app", "client", "mapper"]
