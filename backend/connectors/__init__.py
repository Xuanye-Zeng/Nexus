"""Connector package. Importing this module registers all known connectors
into the CONNECTORS registry in base.py.
"""
# Importing each connector module fires its @register_connector decorator.
from . import adzuna, greenhouse, lever  # noqa: F401
from .base import (  # noqa: F401
    CONNECTORS,
    JobConnector,
    NormalizedListing,
    get_connector,
    list_connectors,
    register_connector,
)

__all__ = [
    "CONNECTORS",
    "JobConnector",
    "NormalizedListing",
    "get_connector",
    "list_connectors",
    "register_connector",
]
