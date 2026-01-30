"""
JARVIS Core Engine

The central orchestrator that manages all components, handles their lifecycle,
and coordinates communication between voice, AI, and plugin systems.
"""

import asyncio
from pathlib import Path

from loguru import logger

from jarvis.core.config import Config
from jarvis.core.events import EventBus, EventType, Event, get_event_bus
from jarvis.core.security import SecurityManager


class JarvisEngine:
    """
    Main engine for JARVIS assistant.
    
    Manages:
    - Component lifecycle (voice, AI, plugins)
    - Event routing and processing
    - Mode switching (voice, CLI, web)
    """
    
    def __init__(self, config: Config):
        """
        Initialize the JARVIS engine.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.name = config.get("core.name", "Jarvis")
        
        # Core components
        self.event_bus: EventBus = get_event_bus()
        self.security = SecurityManager(config)
        
        # Optional components (lazy loaded)
        self._voice_manager = None
        self._ai_manager = None
        self._plugin_manager = None
        self._cli_interface = None
        self._web_app = None
        
        # State
        self._initialized = False
        self._running = False
        self._tasks: list[asyncio.Task] = []
    
    async def initialize(self) -> None:
        """Initialize all components."""
        if self._initialized:
            return
        
        logger.info(f"Initializing {self.name}...")
        
        # Create data directories
        data_dir = Path(self.config.get("core.data_dir", "data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "logs").mkdir(exist_ok=True)
        
        # Start event bus
        await self.event_bus.start()
        
        # Register core event handlers
        self._register_handlers()
        
        # Initialize plugin system
        if self.config.get("plugins.enabled", True):
            await self._init_plugins()
        
        # Initialize AI system
        await self._init_ai()
        
        self._initialized = True
        await self.event_bus.emit(EventType.SYSTEM_READY, source="engine")
        logger.info(f"{self.name} initialization complete!")
    
    def _register_handlers(self) -> None:
        """Register core event handlers."""
        self.event_bus.subscribe(EventType.USER_INPUT, self._handle_user_input)
        self.event_bus.subscribe(EventType.COMMAND_RECEIVED, self._handle_command)
        self.event_bus.subscribe(EventType.SYSTEM_ERROR, self._handle_error)
    
    async def _init_plugins(self) -> None:
        """Initialize the plugin system."""
        try:
            from jarvis.plugins.manager import PluginManager
            self._plugin_manager = PluginManager(self.config, self.event_bus)
            await self._plugin_manager.load_plugins()
            logger.info("Plugin system initialized")
        except Exception as e:
            logger.warning(f"Plugin system initialization failed: {e}")
    
    async def _init_ai(self) -> None:
        """Initialize the AI system."""
        try:
            from jarvis.ai.llm import LLMManager
            self._ai_manager = LLMManager(self.config)
            await self._ai_manager.initialize()
            logger.info("AI system initialized")
        except Exception as e:
            logger.warning(f"AI system initialization failed: {e}")
    
    async def _init_voice(self) -> None:
        """Initialize the voice system."""
        try:
            from jarvis.voice.manager import VoiceManager
            self._voice_manager = VoiceManager(self.config, self.event_bus)
            await self._voice_manager.initialize()
            logger.info("Voice system initialized")
        except Exception as e:
            logger.error(f"Voice system initialization failed: {e}")
            raise
    
    async def _handle_user_input(self, event: Event) -> None:
        """Handle user input events."""
        text = event.data.get("text", "")
        source = event.data.get("source", "unknown")
        
        logger.info(f"User input from {source}: {text}")
        
        if not text.strip():
            return
        
        # Check for exit commands
        if text.lower() in ("exit", "quit", "goodbye", "bye"):
            await self._say("Goodbye!")
            self._running = False
            return
        
        # Process through AI
        response = await self._process_with_ai(text)
        
        # Send response
        await self.event_bus.emit(
            EventType.ASSISTANT_RESPONSE,
            {"text": response, "source": "engine"},
            source="engine"
        )
        
        # Speak response if voice is active
        await self._say(response)
    
    async def _handle_command(self, event: Event) -> None:
        """Handle command execution events."""
        command = event.data.get("command", "")
        plugin = event.data.get("plugin")
        
        logger.info(f"Executing command: {command}")
        
        # Security check
        check = self.security.check_command(command)
        
        if not check.allowed:
            logger.warning(f"Command blocked: {check.reason}")
            await self._say(f"I can't do that. {check.reason}")
            return
        
        if check.requires_confirmation:
            # TODO: Implement confirmation flow
            logger.info(f"Command requires confirmation: {command}")
        
        # Execute through plugin if specified
        if plugin and self._plugin_manager:
            result = await self._plugin_manager.execute(plugin, command, event.data)
            if result:
                await self._say(result)
    
    async def _handle_error(self, event: Event) -> None:
        """Handle system errors."""
        error = event.data.get("error", "Unknown error")
        source = event.data.get("source", "unknown")
        logger.error(f"System error from {source}: {error}")
    
    async def _process_with_ai(self, text: str) -> str:
        """Process user input with AI."""
        if not self._ai_manager:
            return self._fallback_response(text)
        
        try:
            response = await self._ai_manager.process(text)
            return response
        except Exception as e:
            logger.error(f"AI processing failed: {e}")
            return self._fallback_response(text)
    
    def _fallback_response(self, text: str) -> str:
        """Generate fallback response when AI is unavailable."""
        text_lower = text.lower()
        
        # Simple pattern matching for basic commands
        if "hello" in text_lower or "hi" in text_lower:
            return f"Hello! I'm {self.name}, your AI assistant. How can I help you?"
        
        if "time" in text_lower:
            from datetime import datetime
            return f"The current time is {datetime.now().strftime('%I:%M %p')}"
        
        if "date" in text_lower:
            from datetime import datetime
            return f"Today is {datetime.now().strftime('%A, %B %d, %Y')}"
        
        if any(word in text_lower for word in ["cpu", "memory", "ram", "disk", "system"]):
            return self._get_system_info()
        
        return "I heard you, but I'm not sure how to help with that. Try asking about the time, date, or system status."
    
    def _get_system_info(self) -> str:
        """Get basic system information."""
        try:
            import psutil
            
            cpu = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return (
                f"System Status: "
                f"CPU at {cpu}%, "
                f"Memory {memory.percent}% used ({memory.used // (1024**3)}/{memory.total // (1024**3)} GB), "
                f"Disk {disk.percent}% used"
            )
        except Exception as e:
            return f"Unable to get system info: {e}"
    
    async def _say(self, text: str) -> None:
        """Speak text through TTS if voice is active."""
        if self._voice_manager:
            await self._voice_manager.speak(text)
        else:
            logger.info(f"[JARVIS]: {text}")
    
    async def run_voice_mode(self) -> None:
        """Run in voice-controlled mode."""
        if not self._voice_manager:
            await self._init_voice()
        
        self._running = True
        logger.info("Starting voice mode...")
        
        await self._say(f"Hello! {self.name} is ready and listening.")
        
        while self._running:
            try:
                # Voice manager handles wake word detection and recording
                await self._voice_manager.listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Voice mode error: {e}")
                await asyncio.sleep(1)
    
    async def run_cli_mode(self) -> None:
        """Run in CLI mode."""
        from jarvis.interface.cli import CLIInterface
        
        self._cli_interface = CLIInterface(self.config, self.event_bus)
        self._running = True
        
        logger.info("Starting CLI mode...")
        print(f"\n🤖 {self.name} CLI Mode")
        print("=" * 40)
        print("Type 'help' for commands, 'exit' to quit\n")
        
        await self._cli_interface.run()
    
    async def run_web_mode(self) -> None:
        """Run with web interface."""
        from jarvis.interface.web.app import create_app
        import uvicorn
        
        self._running = True
        host = self.config.get("web.host", "0.0.0.0")
        port = int(self.config.get("web.port", 8000))
        
        logger.info(f"Starting web mode on {host}:{port}...")
        
        app = create_app(self.config, self.event_bus, self)
        
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
    
    async def run_all_modes(self) -> None:
        """Run all modes concurrently."""
        self._running = True
        
        tasks = []
        
        # Start voice mode in background
        if self.config.get("voice.enabled", True):
            try:
                await self._init_voice()
                tasks.append(asyncio.create_task(self.run_voice_mode()))
            except Exception as e:
                logger.warning(f"Voice mode not available: {e}")
        
        # Start web mode in background
        if self.config.get("web.enabled", True):
            tasks.append(asyncio.create_task(self.run_web_mode()))
        
        self._tasks = tasks
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def shutdown(self) -> None:
        """Gracefully shutdown all components."""
        logger.info("Shutting down JARVIS...")
        
        self._running = False
        
        # Cancel running tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Shutdown components
        if self._voice_manager:
            await self._voice_manager.shutdown()
        
        if self._plugin_manager:
            await self._plugin_manager.shutdown()
        
        if self._ai_manager:
            await self._ai_manager.shutdown()
        
        # Stop event bus
        await self.event_bus.stop()
        
        await self.event_bus.emit(EventType.SYSTEM_SHUTDOWN, source="engine")
        logger.info("JARVIS shutdown complete")
