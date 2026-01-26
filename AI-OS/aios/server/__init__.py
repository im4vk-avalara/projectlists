"""
AIOS HTTP Server

FastAPI-based server exposing the AIOS kernel via REST API.
"""

from aios.server.app import create_app, AIOSServer

__all__ = ["create_app", "AIOSServer"]

