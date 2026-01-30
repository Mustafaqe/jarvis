"""
JARVIS Plugin Base

Defines the abstract base class and interfaces for plugins.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class PluginInfo:
    """Metadata about a plugin."""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "JARVIS"
    enabled: bool = True
    commands: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)


class Plugin(ABC):
    """
    Abstract base class for JARVIS plugins.
    
    Each plugin provides:
    - Commands it can handle
    - Intents it responds to
    - Execution logic
    """
    
    def __init__(self, config, event_bus):
        """
        Initialize plugin.
        
        Args:
            config: Configuration object
            event_bus: Event bus for communication
        """
        self.config = config
        self.event_bus = event_bus
        self._initialized = False
    
    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Return plugin metadata."""
        pass
    
    async def initialize(self) -> None:
        """Initialize plugin resources. Override in subclasses."""
        self._initialized = True
        logger.debug(f"Plugin {self.info.name} initialized")
    
    @abstractmethod
    async def execute(self, command: str, params: dict[str, Any]) -> str:
        """
        Execute a command.
        
        Args:
            command: The command to execute
            params: Additional parameters
            
        Returns:
            Response text
        """
        pass
    
    def can_handle(self, text: str) -> bool:
        """
        Check if this plugin can handle the input.
        
        Args:
            text: User input text
            
        Returns:
            True if plugin can handle this input
        """
        text_lower = text.lower()
        
        # Check command keywords
        for cmd in self.info.commands:
            if cmd.lower() in text_lower:
                return True
        
        # Check intent keywords
        for intent in self.info.intents:
            if intent.lower() in text_lower:
                return True
        
        return False
    
    async def shutdown(self) -> None:
        """Cleanup plugin resources. Override in subclasses."""
        self._initialized = False
        logger.debug(f"Plugin {self.info.name} shutdown")
