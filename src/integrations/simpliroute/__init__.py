"""Integração com SimpliRoute (módulos auxiliares).

Este pacote expõe o objeto `app` do módulo `app` para facilitar imports
como `from src.integrations.simpliroute import app` nos testes.
"""

from . import client, mapper

try:  # opcional: só expõe o FastAPI quando dependência estiver instalada
	from .app import app  # type: ignore
except ModuleNotFoundError:  # FastAPI não é requisito no modo CLI
	app = None  # type: ignore

__all__ = ["app", "client", "mapper"]
