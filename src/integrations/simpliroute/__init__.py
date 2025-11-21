"""Integração com SimpliRoute (módulos auxiliares).

Este pacote expõe o objeto `app` do módulo `app` para facilitar imports
como `from src.integrations.simpliroute import app` nos testes.
"""

from .app import app  # expoe o objeto FastAPI
from . import client, mapper

__all__ = ["app", "client", "mapper"]
