"""
JARVIS Client - Lightweight PC Agent

Runs on each PC to connect to the JARVIS server, execute commands,
stream screen captures, and forward voice input.
"""

import asyncio
import json
import platform
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any

from loguru import logger

try:
    import grpc
    from grpc import aio as grpc_aio
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    logger.warning("gRPC not installed. Install with: pip install grpcio grpcio-tools")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class ConnectionState(Enum):
    """Client connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class ClientConfig:
    """Configuration for JARVIS client."""
    client_id: str
    server_host: str
    server_port: int = 50051
    auth_token: str = ""
    heartbeat_interval: int = 10
    auto_reconnect: bool = True
    reconnect_delay: int = 5
    tls_enabled: bool = False
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    ca_path: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "ClientConfig":
        """Create config from dictionary."""
        return cls(
            client_id=data.get("client_id", str(uuid.uuid4())),
            server_host=data.get("server_host", "localhost"),
            server_port=data.get("server_port", 50051),
            auth_token=data.get("auth_token", ""),
            heartbeat_interval=data.get("heartbeat_interval", 10),
            auto_reconnect=data.get("auto_reconnect", True),
            reconnect_delay=data.get("reconnect_delay", 5),
            tls_enabled=data.get("tls_enabled", False),
            cert_path=data.get("cert_path"),
            key_path=data.get("key_path"),
            ca_path=data.get("ca_path"),
        )


class CommandExecutor:
    """Executes commands received from the server."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.allowed_commands = self.config.get("allowed_commands", [])
        self.blocked_commands = self.config.get("blocked_commands", [
            "rm -rf /",
            "dd if=/dev/zero",
            ":(){:|:&};:",
            "mkfs",
            "chmod -R 777 /",
        ])
        
        # Command handlers
        self._handlers: dict[str, Callable] = {
            "shell": self._execute_shell,
            "execute": self._execute_shell,
            "app": self._execute_app,
            "speak": self._execute_speak,
            "screen_capture": self._execute_screen_capture,
            "file_read": self._execute_file_read,
            "file_write": self._execute_file_write,
            "system": self._execute_system,
            "message": self._execute_message,
        }
    
    def register_handler(self, command_type: str, handler: Callable):
        """Register a custom command handler."""
        self._handlers[command_type] = handler
    
    async def execute(self, command_type: str, payload: dict) -> dict:
        """Execute a command and return the result."""
        start_time = time.time()
        
        handler = self._handlers.get(command_type)
        if not handler:
            return {
                "success": False,
                "error": f"Unknown command type: {command_type}",
            }
        
        try:
            result = await handler(payload)
            result["duration_ms"] = int((time.time() - start_time) * 1000)
            return result
        except Exception as e:
            logger.exception(f"Command execution error: {e}")
            return {
                "success": False,
                "error": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }
    
    async def _execute_shell(self, payload: dict) -> dict:
        """Execute a shell command."""
        command = payload.get("command", "")
        
        # Security check
        for blocked in self.blocked_commands:
            if blocked in command:
                return {
                    "success": False,
                    "error": f"Blocked command pattern: {blocked}",
                }
        
        timeout = payload.get("timeout", 30)
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "success": False,
                    "error": "Command timed out",
                    "exit_code": -1,
                }
            
            return {
                "success": process.returncode == 0,
                "output": stdout.decode("utf-8", errors="replace"),
                "error": stderr.decode("utf-8", errors="replace") if process.returncode != 0 else "",
                "exit_code": process.returncode,
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def _execute_app(self, payload: dict) -> dict:
        """Launch an application."""
        app_name = payload.get("app", "")
        args = payload.get("args", [])
        
        try:
            # Use subprocess for launching apps
            if platform.system() == "Linux":
                # Try common launchers
                for launcher in ["gtk-launch", "xdg-open"]:
                    try:
                        subprocess.Popen([launcher, app_name] + args,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
                        return {"success": True, "output": f"Launched {app_name}"}
                    except FileNotFoundError:
                        continue
                
                # Direct execution
                subprocess.Popen([app_name] + args,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                return {"success": True, "output": f"Launched {app_name}"}
            else:
                subprocess.Popen([app_name] + args)
                return {"success": True, "output": f"Launched {app_name}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_speak(self, payload: dict) -> dict:
        """Speak text using TTS."""
        text = payload.get("text", "")
        
        try:
            # Try different TTS methods
            if platform.system() == "Linux":
                # Try espeak first
                process = await asyncio.create_subprocess_exec(
                    "espeak", text,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.wait()
                return {"success": True, "output": "Spoke text"}
            else:
                return {"success": False, "error": "TTS not available"}
                
        except FileNotFoundError:
            # Try piper-tts or other alternatives
            return {"success": False, "error": "No TTS engine found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_screen_capture(self, payload: dict) -> dict:
        """Capture the screen."""
        monitor = payload.get("monitor", 1)
        quality = payload.get("quality", 80)
        
        try:
            # Try to use the vision module
            from jarvis.vision.screen_capture import capture_screen
            
            image_data = await asyncio.get_event_loop().run_in_executor(
                None, capture_screen, monitor, quality
            )
            
            if image_data:
                return {
                    "success": True,
                    "image_data": image_data,
                    "format": "jpeg",
                }
            else:
                return {"success": False, "error": "Capture failed"}
                
        except ImportError:
            # Fallback to basic screenshot
            try:
                import mss
                import io
                from PIL import Image
                
                with mss.mss() as sct:
                    mon = sct.monitors[monitor] if monitor < len(sct.monitors) else sct.monitors[1]
                    img = sct.grab(mon)
                    
                    # Convert to PIL and compress
                    pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                    buffer = io.BytesIO()
                    pil_img.save(buffer, format="JPEG", quality=quality)
                    
                    return {
                        "success": True,
                        "image_data": buffer.getvalue(),
                        "format": "jpeg",
                        "width": img.width,
                        "height": img.height,
                    }
                    
            except Exception as e:
                return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_file_read(self, payload: dict) -> dict:
        """Read a file."""
        path = payload.get("path", "")
        
        try:
            file_path = Path(path).expanduser().resolve()
            
            if not file_path.exists():
                return {"success": False, "error": "File not found"}
            
            # Limit file size
            max_size = payload.get("max_size", 1024 * 1024)  # 1MB default
            if file_path.stat().st_size > max_size:
                return {"success": False, "error": "File too large"}
            
            content = file_path.read_text(errors="replace")
            return {"success": True, "output": content}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_file_write(self, payload: dict) -> dict:
        """Write to a file."""
        path = payload.get("path", "")
        content = payload.get("content", "")
        
        try:
            file_path = Path(path).expanduser().resolve()
            
            # Security: don't allow writing to system directories
            forbidden = ["/etc", "/bin", "/sbin", "/usr", "/boot", "/root"]
            if any(str(file_path).startswith(f) for f in forbidden):
                return {"success": False, "error": "Cannot write to system directories"}
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            
            return {"success": True, "output": f"Wrote to {path}"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_system(self, payload: dict) -> dict:
        """Execute system operations."""
        operation = payload.get("operation", "")
        
        if operation == "status":
            return await self._get_system_status()
        elif operation == "shutdown":
            return {"success": False, "error": "Shutdown requires confirmation"}
        elif operation == "reboot":
            return {"success": False, "error": "Reboot requires confirmation"}
        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}
    
    async def _get_system_status(self) -> dict:
        """Get system status information."""
        if not PSUTIL_AVAILABLE:
            return {"success": False, "error": "psutil not available"}
        
        try:
            return {
                "success": True,
                "output": json.dumps({
                    "cpu_percent": psutil.cpu_percent(interval=0.1),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_percent": psutil.disk_usage("/").percent,
                    "boot_time": psutil.boot_time(),
                    "processes": len(psutil.pids()),
                }),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_message(self, payload: dict) -> dict:
        """Handle a message from server."""
        text = payload.get("text", "")
        logger.info(f"Message from server: {text}")
        return {"success": True, "output": "Message received"}


class ScreenStreamer:
    """Streams screen captures to the server."""
    
    def __init__(self, fps: int = 5, quality: int = 60):
        self.fps = fps
        self.quality = quality
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_frame: list[Callable] = []
    
    def on_frame(self, handler: Callable):
        """Register handler for new frames."""
        self._on_frame.append(handler)
    
    async def start(self, monitor: int = 1):
        """Start streaming."""
        self._running = True
        self._task = asyncio.create_task(self._stream_loop(monitor))
    
    async def stop(self):
        """Stop streaming."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _stream_loop(self, monitor: int):
        """Main streaming loop."""
        interval = 1.0 / self.fps
        executor = CommandExecutor()
        
        while self._running:
            try:
                start = time.time()
                
                result = await executor._execute_screen_capture({
                    "monitor": monitor,
                    "quality": self.quality,
                })
                
                if result.get("success"):
                    for handler in self._on_frame:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(result.get("image_data"))
                            else:
                                handler(result.get("image_data"))
                        except Exception as e:
                            logger.error(f"Frame handler error: {e}")
                
                # Maintain FPS
                elapsed = time.time() - start
                if elapsed < interval:
                    await asyncio.sleep(interval - elapsed)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Screen stream error: {e}")
                await asyncio.sleep(1)


class JarvisClient:
    """
    JARVIS Client - connects to server and executes commands.
    
    Runs on each PC that should be controlled by JARVIS.
    """
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self.state = ConnectionState.DISCONNECTED
        
        # Components
        self.executor = CommandExecutor()
        self.screen_streamer = ScreenStreamer()
        
        # Connection state
        self._session_token: Optional[str] = None
        self._channel: Optional[Any] = None
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._command_task: Optional[asyncio.Task] = None
        
        # Event handlers
        self._on_connected: list[Callable] = []
        self._on_disconnected: list[Callable] = []
        self._on_command: list[Callable] = []
        
        # Client info
        self._client_info = self._build_client_info()
    
    def _build_client_info(self) -> dict:
        """Build client information."""
        capabilities = ["shell", "app", "file", "screen"]
        
        if PSUTIL_AVAILABLE:
            capabilities.append("system")
        
        return {
            "client_id": self.config.client_id,
            "hostname": socket.gethostname(),
            "os_type": platform.system().lower(),
            "os_version": platform.release(),
            "capabilities": capabilities,
            "ip_address": self._get_local_ip(),
        }
    
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def on_connected(self, handler: Callable):
        """Register handler for connection events."""
        self._on_connected.append(handler)
    
    def on_disconnected(self, handler: Callable):
        """Register handler for disconnection events."""
        self._on_disconnected.append(handler)
    
    def on_command(self, handler: Callable):
        """Register handler for incoming commands."""
        self._on_command.append(handler)
    
    async def connect(self) -> bool:
        """Connect to the JARVIS server."""
        if not GRPC_AVAILABLE:
            logger.error("gRPC not available. Cannot connect.")
            return False
        
        self.state = ConnectionState.CONNECTING
        logger.info(f"Connecting to JARVIS server at {self.config.server_host}:{self.config.server_port}")
        
        try:
            # Create channel
            target = f"{self.config.server_host}:{self.config.server_port}"
            
            if self.config.tls_enabled:
                # Load TLS credentials
                credentials = self._load_tls_credentials()
                if credentials:
                    self._channel = grpc_aio.secure_channel(target, credentials)
                else:
                    logger.warning("TLS credentials not available, using insecure channel")
                    self._channel = grpc_aio.insecure_channel(target)
            else:
                self._channel = grpc_aio.insecure_channel(target)
            
            # Authenticate
            self.state = ConnectionState.AUTHENTICATING
            auth_result = await self._authenticate()
            
            if auth_result:
                self.state = ConnectionState.CONNECTED
                self._running = True
                
                # Start background tasks
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
                # Notify handlers
                for handler in self._on_connected:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler()
                        else:
                            handler()
                    except Exception as e:
                        logger.error(f"Connected handler error: {e}")
                
                logger.info("✅ Connected to JARVIS server")
                return True
            else:
                self.state = ConnectionState.DISCONNECTED
                return False
                
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.state = ConnectionState.DISCONNECTED
            return False
    
    def _load_tls_credentials(self):
        """Load TLS credentials for secure connection."""
        try:
            root_certs = None
            private_key = None
            cert_chain = None
            
            if self.config.ca_path:
                ca_path = Path(self.config.ca_path)
                if ca_path.exists():
                    root_certs = ca_path.read_bytes()
            
            if self.config.cert_path and self.config.key_path:
                cert_path = Path(self.config.cert_path)
                key_path = Path(self.config.key_path)
                if cert_path.exists() and key_path.exists():
                    private_key = key_path.read_bytes()
                    cert_chain = cert_path.read_bytes()
            
            return grpc.ssl_channel_credentials(
                root_certificates=root_certs,
                private_key=private_key,
                certificate_chain=cert_chain,
            )
        except Exception as e:
            logger.error(f"Failed to load TLS credentials: {e}")
            return None
    
    async def _authenticate(self) -> bool:
        """Authenticate with the server."""
        # Note: In real implementation, this would use the generated gRPC stub
        # For now, we'll use a simplified HTTP-based approach as fallback
        
        try:
            # Simulate authentication request
            # In real impl: stub = JarvisServiceStub(self._channel)
            #               response = await stub.Authenticate(request)
            
            # For development, assume success
            self._session_token = "dev-session-token"
            return True
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    async def disconnect(self, reason: str = ""):
        """Disconnect from the server."""
        logger.info(f"Disconnecting: {reason}")
        
        self._running = False
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close channel
        if self._channel:
            await self._channel.close()
            self._channel = None
        
        self.state = ConnectionState.DISCONNECTED
        self._session_token = None
        
        # Notify handlers
        for handler in self._on_disconnected:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(reason)
                else:
                    handler(reason)
            except Exception as e:
                logger.error(f"Disconnected handler error: {e}")
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to server."""
        while self._running:
            try:
                # Get current status
                status = await self._get_status()
                
                # Send heartbeat
                # In real impl: response = await stub.SendHeartbeat(request)
                
                # Process pending commands from heartbeat response
                # pending_commands = response.pending_commands
                # for cmd in pending_commands:
                #     await self._process_command(cmd)
                
                await asyncio.sleep(self.config.heartbeat_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                
                if self.config.auto_reconnect:
                    self.state = ConnectionState.RECONNECTING
                    await asyncio.sleep(self.config.reconnect_delay)
                    await self._try_reconnect()
    
    async def _get_status(self) -> dict:
        """Get current system status."""
        if not PSUTIL_AVAILABLE:
            return {}
        
        try:
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage("/").percent,
                "is_idle": False,  # TODO: Implement idle detection
            }
        except Exception:
            return {}
    
    async def _try_reconnect(self):
        """Attempt to reconnect to the server."""
        logger.info("Attempting to reconnect...")
        
        try:
            if await self.connect():
                logger.info("Reconnected successfully")
            else:
                logger.warning("Reconnection failed, will retry")
        except Exception as e:
            logger.error(f"Reconnection error: {e}")
    
    async def _process_command(self, command: dict):
        """Process a command from the server."""
        command_id = command.get("command_id", "")
        command_type = command.get("command_type", "")
        payload = command.get("payload", {})
        
        logger.debug(f"Processing command: {command_type} ({command_id[:8]}...)")
        
        # Notify handlers
        for handler in self._on_command:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(command)
                else:
                    handler(command)
            except Exception as e:
                logger.error(f"Command handler error: {e}")
        
        # Execute command
        result = await self.executor.execute(command_type, payload)
        result["command_id"] = command_id
        
        # Report result back to server
        # In real impl: await stub.ReportResult(result)
        
        logger.debug(f"Command completed: {command_type} - {'success' if result.get('success') else 'failed'}")
    
    async def run(self):
        """Run the client until disconnected."""
        if not await self.connect():
            return
        
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect("Client stopped")


# =============================================================================
# Async Client Runner
# =============================================================================

async def run_client(config: dict) -> None:
    """Run the JARVIS client as standalone."""
    client_config = ClientConfig.from_dict(config)
    client = JarvisClient(client_config)
    
    try:
        await client.run()
    except asyncio.CancelledError:
        pass
    finally:
        await client.disconnect("Shutdown")


if __name__ == "__main__":
    import sys
    
    # Simple CLI for testing
    config = {
        "client_id": str(uuid.uuid4()),
        "server_host": sys.argv[1] if len(sys.argv) > 1 else "localhost",
        "server_port": int(sys.argv[2]) if len(sys.argv) > 2 else 50051,
    }
    
    asyncio.run(run_client(config))
