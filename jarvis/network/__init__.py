"""
JARVIS Network Module

Provides server-client communication infrastructure for distributed JARVIS deployment.
Supports gRPC for real-time communication and WebSocket for dashboard streaming.
"""

from jarvis.network.server import JarvisServer
from jarvis.network.client import JarvisClient
from jarvis.network.discovery import NetworkDiscovery
from jarvis.network.iot import IoTManager

__all__ = [
    "JarvisServer",
    "JarvisClient", 
    "NetworkDiscovery",
    "IoTManager",
]
