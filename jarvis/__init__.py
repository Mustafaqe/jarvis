"""
JARVIS AI Assistant

A comprehensive AI-powered assistant for Linux featuring voice interaction,
task automation, system control, and contextual awareness.
"""

__version__ = "0.1.0"
__author__ = "Mustafa"
__description__ = "AI-Powered Voice Assistant for Linux"

from jarvis.core.engine import JarvisEngine
from jarvis.core.config import Config

__all__ = ["JarvisEngine", "Config", "__version__"]
