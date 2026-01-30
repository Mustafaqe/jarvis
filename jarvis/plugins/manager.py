"""
JARVIS Plugin Manager

Handles plugin discovery, loading, and lifecycle management.
"""

import importlib
import importlib.util
from pathlib import Path
from typing import Any

from loguru import logger

from jarvis.core.events import EventBus
from jarvis.plugins.base import Plugin


class PluginManager:
    """
    Manages plugin lifecycle and execution.
    
    Features:
    - Auto-discovery of plugins
    - Dynamic loading/unloading
    - Command routing to appropriate plugins
    """
    
    def __init__(self, config, event_bus: EventBus):
        """
        Initialize plugin manager.
        
        Args:
            config: Configuration object
            event_bus: Event bus for communication
        """
        self.config = config
        self.event_bus = event_bus
        self.plugins: dict[str, Plugin] = {}
        
        # Default plugin directory
        self.plugin_dir = Path(__file__).parent
    
    async def load_plugins(self) -> None:
        """Load all configured plugins."""
        autoload = self.config.get("plugins.autoload", [])
        
        if not autoload:
            logger.info("No plugins configured for autoload")
            return
        
        for plugin_name in autoload:
            try:
                await self.load_plugin(plugin_name)
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_name}: {e}")
        
        logger.info(f"Loaded {len(self.plugins)} plugins")
    
    async def load_plugin(self, name: str) -> Plugin | None:
        """
        Load a single plugin by name.
        
        Args:
            name: Plugin module name (e.g., 'system_control')
            
        Returns:
            Loaded plugin instance or None
        """
        if name in self.plugins:
            logger.debug(f"Plugin {name} already loaded")
            return self.plugins[name]
        
        try:
            # Try to import the plugin module
            module_name = f"jarvis.plugins.{name}"
            module = importlib.import_module(module_name)
            
            # Find the plugin class (subclass of Plugin)
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, Plugin) and 
                    attr is not Plugin):
                    plugin_class = attr
                    break
            
            if not plugin_class:
                logger.warning(f"No Plugin class found in {module_name}")
                return None
            
            # Instantiate and initialize
            plugin = plugin_class(self.config, self.event_bus)
            await plugin.initialize()
            
            self.plugins[name] = plugin
            logger.info(f"Loaded plugin: {plugin.info.name} v{plugin.info.version}")
            
            return plugin
            
        except ImportError as e:
            logger.warning(f"Plugin {name} not found: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading plugin {name}: {e}")
            return None
    
    async def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin.
        
        Args:
            name: Plugin name
            
        Returns:
            True if unloaded successfully
        """
        if name not in self.plugins:
            return False
        
        try:
            plugin = self.plugins[name]
            await plugin.shutdown()
            del self.plugins[name]
            logger.info(f"Unloaded plugin: {name}")
            return True
        except Exception as e:
            logger.error(f"Error unloading plugin {name}: {e}")
            return False
    
    def find_plugin(self, text: str) -> Plugin | None:
        """
        Find a plugin that can handle the input.
        
        Args:
            text: User input text
            
        Returns:
            Plugin that can handle the input, or None
        """
        for plugin in self.plugins.values():
            if plugin.can_handle(text):
                return plugin
        return None
    
    async def execute(
        self,
        plugin_name: str | None,
        command: str,
        params: dict[str, Any]
    ) -> str | None:
        """
        Execute a command through a plugin.
        
        Args:
            plugin_name: Specific plugin to use (or None to auto-detect)
            command: Command to execute
            params: Additional parameters
            
        Returns:
            Response text or None
        """
        # Find plugin
        if plugin_name and plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
        else:
            plugin = self.find_plugin(command)
        
        if not plugin:
            return None
        
        try:
            result = await plugin.execute(command, params)
            return result
        except Exception as e:
            logger.error(f"Plugin execution error: {e}")
            return f"Error executing command: {e}"
    
    async def process(self, text: str) -> str | None:
        """
        Process user input through plugins.
        
        Args:
            text: User input
            
        Returns:
            Response from plugin or None
        """
        plugin = self.find_plugin(text)
        
        if not plugin:
            return None
        
        return await plugin.execute(text, {})
    
    def list_plugins(self) -> list[dict]:
        """List all loaded plugins with their info."""
        return [
            {
                "name": plugin.info.name,
                "description": plugin.info.description,
                "version": plugin.info.version,
                "commands": plugin.info.commands,
            }
            for plugin in self.plugins.values()
        ]
    
    async def shutdown(self) -> None:
        """Shutdown all plugins."""
        for name in list(self.plugins.keys()):
            await self.unload_plugin(name)
        logger.info("Plugin manager shutdown complete")
