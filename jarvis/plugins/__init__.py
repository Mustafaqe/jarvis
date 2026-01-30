"""Plugin module for JARVIS - Extensible plugin system."""

from jarvis.plugins.base import Plugin, PluginInfo
from jarvis.plugins.manager import PluginManager

__all__ = ["Plugin", "PluginInfo", "PluginManager"]
