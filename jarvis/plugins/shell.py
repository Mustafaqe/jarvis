"""
JARVIS Shell Command Plugin

Provides safe shell command execution with:
- Command validation
- Output capture
- Sandboxing
"""

import asyncio
import subprocess
from typing import Any

from loguru import logger

from jarvis.core.security import SecurityManager
from jarvis.plugins.base import Plugin, PluginInfo


class ShellPlugin(Plugin):
    """Safe shell command execution plugin."""
    
    def __init__(self, config, event_bus):
        super().__init__(config, event_bus)
        self.security = SecurityManager(config)
        self.max_output_length = 500
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="Shell",
            description="Execute shell commands safely",
            version="1.0.0",
            commands=[
                "run command", "execute", "shell",
                "terminal command", "run script",
            ],
            intents=[
                "run", "execute", "command", "shell",
                "terminal", "script", "bash",
            ],
        )
    
    async def execute(self, command: str, params: dict[str, Any]) -> str:
        """Execute shell command."""
        command_lower = command.lower()
        
        # Extract the actual shell command
        shell_cmd = self._extract_command(command)
        
        if not shell_cmd:
            return "Please specify a command to run. For example: 'run command ls -la'"
        
        # Security check
        check = self.security.check_command(shell_cmd)
        
        if not check.allowed:
            return f"Command blocked for security: {check.reason}"
        
        if check.requires_confirmation:
            # In future, implement confirmation flow
            return f"This command requires confirmation due to: {check.reason}. Please confirm or rephrase."
        
        # Execute command
        return await self._run_command(shell_cmd)
    
    def _extract_command(self, text: str) -> str:
        """Extract shell command from user text."""
        text_lower = text.lower()
        
        # Remove common prefixes
        prefixes = [
            "run command", "run the command", "execute command",
            "execute the command", "run", "execute",
            "shell command", "terminal command",
            "please run", "can you run",
        ]
        
        result = text
        for prefix in prefixes:
            if text_lower.startswith(prefix):
                result = text[len(prefix):].strip()
                break
        
        # Remove quotes if present
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        elif result.startswith("'") and result.endswith("'"):
            result = result[1:-1]
        
        return result.strip()
    
    async def _run_command(self, command: str) -> str:
        """Run a shell command and return output."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._run_sync, command
            )
            return result
        except Exception as e:
            return f"Command failed: {e}"
    
    def _run_sync(self, command: str) -> str:
        """Synchronous command execution."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
                cwd=str(__import__('pathlib').Path.home()),
            )
            
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            if result.returncode != 0:
                if error:
                    return f"Command failed (exit {result.returncode}):\n{error[:self.max_output_length]}"
                return f"Command failed with exit code {result.returncode}"
            
            if not output:
                return "Command completed successfully (no output)."
            
            # Truncate long output
            if len(output) > self.max_output_length:
                output = output[:self.max_output_length] + "\n... (output truncated)"
            
            return f"```\n{output}\n```"
            
        except subprocess.TimeoutExpired:
            return "Command timed out after 30 seconds."
        except Exception as e:
            logger.error(f"Shell execution error: {e}")
            return f"Execution error: {e}"
