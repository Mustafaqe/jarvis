"""
JARVIS Server - Central AI Brain

The main server that coordinates all JARVIS clients, manages AI processing,
and provides the web dashboard. Runs on the central server or Raspberry Pi.
"""

import asyncio
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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


class ClientState(Enum):
    """State of a connected client."""
    CONNECTING = "connecting"
    AUTHENTICATED = "authenticated"
    ACTIVE = "active"
    IDLE = "idle"
    DISCONNECTED = "disconnected"


@dataclass
class ConnectedClient:
    """Represents a connected JARVIS client."""
    client_id: str
    hostname: str
    ip_address: str
    os_type: str
    os_version: str
    capabilities: list[str]
    state: ClientState = ClientState.CONNECTING
    session_token: Optional[str] = None
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    last_status: Optional[dict] = None
    pending_commands: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "client_id": self.client_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "os_type": self.os_type,
            "os_version": self.os_version,
            "capabilities": self.capabilities,
            "state": self.state.value,
            "connected_at": self.connected_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "last_status": self.last_status,
        }


@dataclass
class PendingCommand:
    """A command waiting to be executed."""
    command_id: str
    command_type: str
    payload: dict
    target_client: str
    priority: int = 0
    timeout_seconds: int = 60
    require_confirmation: bool = False
    queued_at: datetime = field(default_factory=datetime.now)
    callback: Optional[Callable] = None


class ClientManager:
    """Manages all connected JARVIS clients."""
    
    def __init__(self):
        self.clients: dict[str, ConnectedClient] = {}
        self.sessions: dict[str, str] = {}  # session_token -> client_id
        self._lock = asyncio.Lock()
        self._heartbeat_timeout = 30  # seconds
        
    async def register_client(self, client_info: dict) -> tuple[bool, str, str]:
        """
        Register a new client.
        
        Returns:
            (success, session_token, error_message)
        """
        async with self._lock:
            client_id = client_info.get("client_id")
            
            if not client_id:
                return False, "", "client_id is required"
            
            # Generate session token
            session_token = secrets.token_urlsafe(32)
            
            # Create client record
            client = ConnectedClient(
                client_id=client_id,
                hostname=client_info.get("hostname", "unknown"),
                ip_address=client_info.get("ip_address", "unknown"),
                os_type=client_info.get("os_type", "linux"),
                os_version=client_info.get("os_version", ""),
                capabilities=client_info.get("capabilities", []),
                session_token=session_token,
                state=ClientState.AUTHENTICATED,
            )
            
            self.clients[client_id] = client
            self.sessions[session_token] = client_id
            
            logger.info(f"Client registered: {client.hostname} ({client_id[:8]}...)")
            return True, session_token, ""
    
    async def validate_session(self, session_token: str) -> Optional[ConnectedClient]:
        """Validate a session token and return the client."""
        client_id = self.sessions.get(session_token)
        if client_id:
            return self.clients.get(client_id)
        return None
    
    async def update_heartbeat(self, client_id: str, status: dict = None) -> bool:
        """Update client heartbeat timestamp."""
        async with self._lock:
            client = self.clients.get(client_id)
            if client:
                client.last_heartbeat = datetime.now()
                client.state = ClientState.ACTIVE
                if status:
                    client.last_status = status
                return True
            return False
    
    async def get_pending_commands(self, client_id: str) -> list[dict]:
        """Get pending commands for a client."""
        async with self._lock:
            client = self.clients.get(client_id)
            if client and client.pending_commands:
                commands = client.pending_commands.copy()
                client.pending_commands.clear()
                return commands
            return []
    
    async def queue_command(self, client_id: str, command: PendingCommand) -> bool:
        """Queue a command for a client."""
        async with self._lock:
            client = self.clients.get(client_id)
            if client:
                client.pending_commands.append({
                    "command_id": command.command_id,
                    "command_type": command.command_type,
                    "payload": command.payload,
                    "priority": command.priority,
                    "timeout_seconds": command.timeout_seconds,
                    "require_confirmation": command.require_confirmation,
                })
                return True
            return False
    
    async def disconnect_client(self, client_id: str, reason: str = "") -> bool:
        """Disconnect a client."""
        async with self._lock:
            client = self.clients.get(client_id)
            if client:
                client.state = ClientState.DISCONNECTED
                if client.session_token in self.sessions:
                    del self.sessions[client.session_token]
                logger.info(f"Client disconnected: {client.hostname} - {reason}")
                return True
            return False
    
    async def cleanup_stale_clients(self):
        """Remove clients that haven't sent heartbeat recently."""
        async with self._lock:
            now = datetime.now()
            stale_clients = []
            
            for client_id, client in self.clients.items():
                if client.state != ClientState.DISCONNECTED:
                    time_since_heartbeat = (now - client.last_heartbeat).total_seconds()
                    if time_since_heartbeat > self._heartbeat_timeout:
                        stale_clients.append(client_id)
            
            for client_id in stale_clients:
                client = self.clients[client_id]
                client.state = ClientState.DISCONNECTED
                if client.session_token in self.sessions:
                    del self.sessions[client.session_token]
                logger.warning(f"Client timed out: {client.hostname}")
    
    def get_active_clients(self) -> list[ConnectedClient]:
        """Get all active clients."""
        return [c for c in self.clients.values() 
                if c.state in (ClientState.ACTIVE, ClientState.AUTHENTICATED, ClientState.IDLE)]
    
    def get_client_by_hostname(self, hostname: str) -> Optional[ConnectedClient]:
        """Find client by hostname."""
        for client in self.clients.values():
            if client.hostname.lower() == hostname.lower():
                return client
        return None


class CommandRouter:
    """Routes commands to appropriate clients."""
    
    def __init__(self, client_manager: ClientManager):
        self.client_manager = client_manager
        self.command_results: dict[str, Any] = {}
        self.result_callbacks: dict[str, Callable] = {}
        self._lock = asyncio.Lock()
    
    async def send_command(
        self,
        target: str,  # client_id, hostname, or "all"
        command_type: str,
        payload: dict,
        priority: int = 0,
        timeout: int = 60,
        require_confirmation: bool = False,
        callback: Optional[Callable] = None,
    ) -> str:
        """
        Send a command to a client or all clients.
        
        Returns:
            command_id
        """
        command_id = str(uuid.uuid4())
        
        command = PendingCommand(
            command_id=command_id,
            command_type=command_type,
            payload=payload,
            target_client=target,
            priority=priority,
            timeout_seconds=timeout,
            require_confirmation=require_confirmation,
            callback=callback,
        )
        
        if callback:
            self.result_callbacks[command_id] = callback
        
        # Determine target clients
        if target == "all":
            clients = self.client_manager.get_active_clients()
            for client in clients:
                await self.client_manager.queue_command(client.client_id, command)
        else:
            # Try by client_id first, then hostname
            client = self.client_manager.clients.get(target)
            if not client:
                client = self.client_manager.get_client_by_hostname(target)
            
            if client:
                await self.client_manager.queue_command(client.client_id, command)
            else:
                logger.warning(f"Target client not found: {target}")
        
        logger.debug(f"Command queued: {command_type} -> {target}")
        return command_id
    
    async def handle_result(self, command_id: str, result: dict) -> None:
        """Handle command execution result from client."""
        async with self._lock:
            self.command_results[command_id] = result
            
            if command_id in self.result_callbacks:
                callback = self.result_callbacks.pop(command_id)
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
                except Exception as e:
                    logger.error(f"Error in command callback: {e}")


class JarvisServer:
    """
    Main JARVIS Server.
    
    Handles:
    - Client connections and authentication
    - Command routing to clients
    - AI processing coordination
    - Web dashboard API
    """
    
    def __init__(self, config):
        self.config = config
        self.client_manager = ClientManager()
        self.command_router = CommandRouter(self.client_manager)
        
        # Server settings
        self.host = config.get("network.server_host", "0.0.0.0")
        self.port = config.get("network.server_port", 50051)
        self.auth_tokens = set(config.get("network.auth_tokens", []))
        
        # Event handlers
        self._on_client_connected: list[Callable] = []
        self._on_client_disconnected: list[Callable] = []
        self._on_command_result: list[Callable] = []
        
        # State
        self._running = False
        self._grpc_server = None
        self._cleanup_task = None
        
    def on_client_connected(self, handler: Callable):
        """Register handler for client connection events."""
        self._on_client_connected.append(handler)
        
    def on_client_disconnected(self, handler: Callable):
        """Register handler for client disconnection events."""
        self._on_client_disconnected.append(handler)
        
    def on_command_result(self, handler: Callable):
        """Register handler for command results."""
        self._on_command_result.append(handler)
    
    async def start(self):
        """Start the JARVIS server."""
        if not GRPC_AVAILABLE:
            logger.error("gRPC not available. Cannot start server.")
            return False
        
        logger.info(f"Starting JARVIS server on {self.host}:{self.port}")
        
        self._running = True
        
        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # Start gRPC server
        self._grpc_server = grpc_aio.server()
        
        # Add service implementation
        # Note: Actual protobuf service would be registered here after generation
        # For now, we'll use a simple handler pattern
        
        listen_addr = f"{self.host}:{self.port}"
        
        # Add secure port with TLS if configured
        tls_config = self.config.get("network.tls", {})
        if tls_config.get("enabled", False):
            cert_path = Path(tls_config.get("cert_path", "certs/server.crt"))
            key_path = Path(tls_config.get("key_path", "certs/server.key"))
            ca_path = Path(tls_config.get("ca_path", "certs/ca.crt"))
            
            if cert_path.exists() and key_path.exists():
                with open(key_path, "rb") as f:
                    private_key = f.read()
                with open(cert_path, "rb") as f:
                    certificate_chain = f.read()
                
                # For mTLS, also load CA cert
                root_certificates = None
                if ca_path.exists():
                    with open(ca_path, "rb") as f:
                        root_certificates = f.read()
                
                credentials = grpc.ssl_server_credentials(
                    [(private_key, certificate_chain)],
                    root_certificates=root_certificates,
                    require_client_auth=tls_config.get("require_client_cert", False),
                )
                self._grpc_server.add_secure_port(listen_addr, credentials)
                logger.info(f"TLS enabled with mTLS: {tls_config.get('require_client_cert', False)}")
            else:
                logger.warning("TLS certificates not found, falling back to insecure")
                self._grpc_server.add_insecure_port(listen_addr)
        else:
            self._grpc_server.add_insecure_port(listen_addr)
        
        await self._grpc_server.start()
        logger.info(f"✅ JARVIS server listening on {listen_addr}")
        
        return True
    
    async def stop(self):
        """Stop the JARVIS server."""
        logger.info("Stopping JARVIS server...")
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self._grpc_server:
            await self._grpc_server.stop(grace=5)
        
        # Disconnect all clients
        for client_id in list(self.client_manager.clients.keys()):
            await self.client_manager.disconnect_client(client_id, "Server shutdown")
        
        logger.info("JARVIS server stopped")
    
    async def _cleanup_loop(self):
        """Background task to clean up stale clients."""
        while self._running:
            try:
                await asyncio.sleep(10)
                await self.client_manager.cleanup_stale_clients()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    # =========================================================================
    # API Methods (called by web dashboard or AI engine)
    # =========================================================================
    
    async def get_clients(self) -> list[dict]:
        """Get all connected clients as dicts."""
        return [c.to_dict() for c in self.client_manager.get_active_clients()]
    
    async def send_command_to_client(
        self,
        target: str,
        command_type: str,
        payload: dict,
    ) -> str:
        """Send a command to a client. Returns command_id."""
        return await self.command_router.send_command(
            target=target,
            command_type=command_type,
            payload=payload,
        )
    
    async def broadcast_message(self, message: str) -> None:
        """Broadcast a message to all clients."""
        await self.command_router.send_command(
            target="all",
            command_type="message",
            payload={"text": message},
        )
    
    async def capture_screen(self, client_id: str, monitor: int = 1) -> Optional[bytes]:
        """Request screen capture from a client."""
        command_id = await self.command_router.send_command(
            target=client_id,
            command_type="screen_capture",
            payload={"monitor": monitor, "quality": 80},
            timeout=10,
        )
        
        # Wait for result (simplified - real impl would use proper async waiting)
        for _ in range(100):  # 10 second timeout
            await asyncio.sleep(0.1)
            if command_id in self.command_router.command_results:
                result = self.command_router.command_results.pop(command_id)
                return result.get("image_data")
        
        return None
    
    async def execute_on_client(
        self,
        client_id: str,
        command: str,
        shell: bool = True,
    ) -> Optional[dict]:
        """Execute a command on a specific client."""
        command_id = await self.command_router.send_command(
            target=client_id,
            command_type="shell" if shell else "execute",
            payload={"command": command},
            timeout=30,
        )
        
        # Wait for result
        for _ in range(300):  # 30 second timeout
            await asyncio.sleep(0.1)
            if command_id in self.command_router.command_results:
                return self.command_router.command_results.pop(command_id)
        
        return None
    
    async def speak_on_client(self, client_id: str, text: str) -> bool:
        """Make a client speak text via TTS."""
        await self.command_router.send_command(
            target=client_id,
            command_type="speak",
            payload={"text": text},
        )
        return True
    
    # =========================================================================
    # gRPC Service Handlers (called by gRPC service implementation)
    # =========================================================================
    
    async def handle_authenticate(self, request: dict) -> dict:
        """Handle client authentication request."""
        auth_token = request.get("auth_token", "")
        
        # Validate auth token if tokens are configured
        if self.auth_tokens and auth_token not in self.auth_tokens:
            return {
                "success": False,
                "error_message": "Invalid authentication token",
            }
        
        success, session_token, error = await self.client_manager.register_client(
            request.get("client_info", {})
        )
        
        if success:
            # Notify handlers
            for handler in self._on_client_connected:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(request.get("client_info", {}))
                    else:
                        handler(request.get("client_info", {}))
                except Exception as e:
                    logger.error(f"Client connected handler error: {e}")
        
        return {
            "success": success,
            "session_token": session_token,
            "error_message": error,
            "heartbeat_interval": 10,
        }
    
    async def handle_heartbeat(self, request: dict) -> dict:
        """Handle client heartbeat."""
        session_token = request.get("session_token", "")
        client = await self.client_manager.validate_session(session_token)
        
        if not client:
            return {"success": False, "pending_commands": []}
        
        await self.client_manager.update_heartbeat(
            client.client_id,
            request.get("status", {}),
        )
        
        pending = await self.client_manager.get_pending_commands(client.client_id)
        
        return {
            "success": True,
            "pending_commands": pending,
        }
    
    async def handle_command_result(self, request: dict) -> dict:
        """Handle command execution result from client."""
        command_id = request.get("command_id", "")
        
        await self.command_router.handle_result(command_id, request)
        
        # Notify handlers
        for handler in self._on_command_result:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(request)
                else:
                    handler(request)
            except Exception as e:
                logger.error(f"Command result handler error: {e}")
        
        return {"received": True}


# =============================================================================
# Async Server Runner
# =============================================================================

async def run_server(config) -> None:
    """Run the JARVIS server as standalone."""
    server = JarvisServer(config)
    
    try:
        await server.start()
        
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    # Quick test
    from jarvis.core.config import Config
    
    config = Config()
    asyncio.run(run_server(config))
