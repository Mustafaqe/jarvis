"""
JARVIS CLI Interface

Provides a rich command-line interface for text-based interaction.
"""

import asyncio
from datetime import datetime

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.text import Text

from jarvis.core.events import EventBus, EventType


class CLIInterface:
    """
    Rich CLI interface for JARVIS.
    
    Features:
    - Colorful output
    - Command history
    - Markdown rendering
    """
    
    def __init__(self, config, event_bus: EventBus):
        """
        Initialize CLI interface.
        
        Args:
            config: Configuration object
            event_bus: Event bus for communication
        """
        self.config = config
        self.event_bus = event_bus
        self.console = Console()
        self.name = config.get("core.name", "Jarvis")
        
        self._running = False
        self._response_received = asyncio.Event()
        self._last_response = ""
        
        # Commands
        self.commands = {
            "help": self._show_help,
            "clear": self._clear_screen,
            "status": self._show_status,
            "plugins": self._list_plugins,
            "exit": self._exit,
            "quit": self._exit,
        }
    
    async def run(self) -> None:
        """Main CLI loop."""
        self._running = True
        
        # Subscribe to response events
        self.event_bus.subscribe(EventType.ASSISTANT_RESPONSE, self._on_response)
        
        # Welcome message
        self._print_welcome()
        
        while self._running:
            try:
                # Get user input
                user_input = await self._get_input()
                
                if not user_input:
                    continue
                
                # Check for CLI commands
                if user_input.lower() in self.commands:
                    await self.commands[user_input.lower()]()
                    continue
                
                if user_input.startswith('/'):
                    cmd = user_input[1:].lower()
                    if cmd in self.commands:
                        await self.commands[cmd]()
                        continue
                
                # Reset response event
                self._response_received.clear()
                
                # Emit user input event
                await self.event_bus.emit(
                    EventType.USER_INPUT,
                    {"text": user_input, "source": "cli"},
                    source="cli"
                )
                
                # Wait for response with timeout
                try:
                    await asyncio.wait_for(
                        self._response_received.wait(),
                        timeout=30.0
                    )
                    self._print_response(self._last_response)
                except asyncio.TimeoutError:
                    self.console.print("[yellow]Response timed out[/yellow]")
                
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                await self._exit()
            except EOFError:
                await self._exit()
            except Exception as e:
                logger.error(f"CLI error: {e}")
                self.console.print(f"[red]Error: {e}[/red]")
    
    async def _get_input(self) -> str:
        """Get user input asynchronously."""
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None,
                lambda: Prompt.ask(f"\n[bold cyan]You[/bold cyan]")
            )
        except EOFError:
            return "exit"
    
    async def _on_response(self, event) -> None:
        """Handle assistant response events."""
        if event.source != "cli":
            self._last_response = event.data.get("text", "")
            self._response_received.set()
    
    def _print_welcome(self) -> None:
        """Print welcome message."""
        welcome = Text()
        welcome.append("\n")
        welcome.append("🤖 ", style="bold")
        welcome.append(f"{self.name}", style="bold blue")
        welcome.append(" CLI Interface\n", style="dim")
        welcome.append(f"Started at {datetime.now().strftime('%H:%M:%S')}\n", style="dim")
        welcome.append("\nType ", style="dim")
        welcome.append("help", style="bold green")
        welcome.append(" for commands, ", style="dim")
        welcome.append("exit", style="bold red")
        welcome.append(" to quit.\n", style="dim")
        
        self.console.print(Panel(welcome, border_style="blue"))
    
    def _print_response(self, text: str) -> None:
        """Print assistant response."""
        if not text:
            return
        
        # Check if it looks like markdown
        if any(c in text for c in ['```', '**', '##', '- ', '* ']):
            self.console.print(f"\n[bold green]{self.name}[/bold green]:")
            self.console.print(Markdown(text))
        else:
            self.console.print(f"\n[bold green]{self.name}[/bold green]: {text}")
    
    async def _show_help(self) -> None:
        """Show help message."""
        help_text = """
**Available Commands:**

| Command | Description |
|---------|-------------|
| `/help` | Show this help message |
| `/clear` | Clear the screen |
| `/status` | Show system status |
| `/plugins` | List loaded plugins |
| `/exit` | Exit the CLI |

**Example Queries:**
- "What's my CPU usage?"
- "Set a timer for 5 minutes"
- "Search for Python tutorials"
- "Open Firefox"
- "Find files named report"
"""
        self.console.print(Markdown(help_text))
    
    async def _clear_screen(self) -> None:
        """Clear the screen."""
        self.console.clear()
        self._print_welcome()
    
    async def _show_status(self) -> None:
        """Show system status."""
        try:
            import psutil
            
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            status = f"""
**System Status:**
- CPU: {cpu}%
- Memory: {mem.percent}% ({mem.used // (1024**3)}/{mem.total // (1024**3)} GB)
- Disk: {disk.percent}% ({disk.used // (1024**3)}/{disk.total // (1024**3)} GB)
"""
            self.console.print(Markdown(status))
        except Exception as e:
            self.console.print(f"[red]Error getting status: {e}[/red]")
    
    async def _list_plugins(self) -> None:
        """List loaded plugins."""
        # This would need access to plugin manager
        self.console.print("[dim]Plugin listing requires engine access.[/dim]")
    
    async def _exit(self) -> None:
        """Exit the CLI."""
        self.console.print(f"\n[dim]Goodbye from {self.name}![/dim]\n")
        self._running = False
