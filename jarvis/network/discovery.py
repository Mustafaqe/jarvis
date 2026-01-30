"""
JARVIS Network Discovery

Scans and monitors the local network for devices, including
automatic JARVIS client discovery using mDNS/Zeroconf.
"""

import asyncio
import ipaddress
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable

from loguru import logger

try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    from zeroconf.asyncio import AsyncZeroconf, AsyncServiceBrowser
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False
    logger.debug("Zeroconf not available. Install with: pip install zeroconf")


class DeviceType(Enum):
    """Types of network devices."""
    UNKNOWN = "unknown"
    PC = "pc"
    LAPTOP = "laptop"
    SERVER = "server"
    RASPBERRY_PI = "raspberry_pi"
    PHONE = "phone"
    TABLET = "tablet"
    ROUTER = "router"
    IOT = "iot"
    PRINTER = "printer"
    TV = "tv"
    JARVIS_CLIENT = "jarvis_client"


@dataclass
class NetworkDevice:
    """Represents a device on the network."""
    mac_address: str
    ip_address: str
    hostname: str = ""
    device_type: DeviceType = DeviceType.UNKNOWN
    vendor: str = ""
    is_online: bool = True
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    open_ports: list[int] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    is_jarvis_client: bool = False
    jarvis_client_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "mac_address": self.mac_address,
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "device_type": self.device_type.value,
            "vendor": self.vendor,
            "is_online": self.is_online,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "open_ports": self.open_ports,
            "services": self.services,
            "is_jarvis_client": self.is_jarvis_client,
        }


class NetworkDiscovery:
    """
    Discovers and monitors devices on the local network.
    
    Features:
    - ARP scan for device discovery
    - mDNS/Zeroconf for service discovery
    - Automatic JARVIS client detection
    - Port scanning for service identification
    """
    
    JARVIS_SERVICE_TYPE = "_jarvis._tcp.local."
    
    # Common ports to check for service identification
    COMMON_PORTS = {
        22: "ssh",
        80: "http",
        443: "https",
        445: "smb",
        548: "afp",
        631: "ipp",
        3389: "rdp",
        5000: "upnp",
        5353: "mdns",
        8080: "http-alt",
        8443: "https-alt",
        9100: "printer",
        50051: "jarvis",  # Our gRPC port
    }
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.devices: dict[str, NetworkDevice] = {}  # mac -> device
        self._lock = asyncio.Lock()
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self._zeroconf: Optional[AsyncZeroconf] = None
        self._service_browser: Optional[AsyncServiceBrowser] = None
        
        # Event handlers
        self._on_device_found: list[Callable] = []
        self._on_device_lost: list[Callable] = []
        self._on_jarvis_client_found: list[Callable] = []
        
        # Configuration
        self._scan_interval = self.config.get("scan_interval", 300)  # 5 minutes
        self._network_range = self.config.get("network_range")  # Auto-detect if None
    
    def on_device_found(self, handler: Callable):
        """Register handler for new device discovery."""
        self._on_device_found.append(handler)
    
    def on_device_lost(self, handler: Callable):
        """Register handler for device going offline."""
        self._on_device_lost.append(handler)
    
    def on_jarvis_client_found(self, handler: Callable):
        """Register handler for JARVIS client discovery."""
        self._on_jarvis_client_found.append(handler)
    
    async def start(self):
        """Start network discovery."""
        self._running = True
        logger.info("Starting network discovery...")
        
        # Start mDNS/Zeroconf if available
        if ZEROCONF_AVAILABLE:
            await self._start_zeroconf()
        
        # Start periodic scanning
        self._scan_task = asyncio.create_task(self._scan_loop())
        
        # Initial scan
        await self.scan_network()
        
        logger.info("Network discovery active")
    
    async def stop(self):
        """Stop network discovery."""
        self._running = False
        
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        
        if self._service_browser:
            await self._service_browser.async_cancel()
        
        if self._zeroconf:
            await self._zeroconf.async_close()
        
        logger.info("Network discovery stopped")
    
    async def _start_zeroconf(self):
        """Initialize Zeroconf for mDNS discovery."""
        try:
            self._zeroconf = AsyncZeroconf()
            
            # Create service listener
            listener = JarvisServiceListener(self._on_jarvis_service_found)
            
            # Browse for JARVIS clients
            self._service_browser = AsyncServiceBrowser(
                self._zeroconf.zeroconf,
                [self.JARVIS_SERVICE_TYPE],
                listener,
            )
            
            logger.info("Zeroconf mDNS discovery started")
            
        except Exception as e:
            logger.error(f"Failed to start Zeroconf: {e}")
    
    async def _on_jarvis_service_found(self, name: str, address: str, port: int, properties: dict):
        """Handle discovered JARVIS client via mDNS."""
        client_id = properties.get(b"client_id", b"").decode()
        hostname = properties.get(b"hostname", name.encode()).decode()
        
        logger.info(f"Discovered JARVIS client via mDNS: {hostname} at {address}:{port}")
        
        # Notify handlers
        for handler in self._on_jarvis_client_found:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler({
                        "client_id": client_id,
                        "hostname": hostname,
                        "ip_address": address,
                        "port": port,
                    })
                else:
                    handler({
                        "client_id": client_id,
                        "hostname": hostname,
                        "ip_address": address,
                        "port": port,
                    })
            except Exception as e:
                logger.error(f"Jarvis client handler error: {e}")
    
    async def _scan_loop(self):
        """Periodic network scanning."""
        while self._running:
            try:
                await asyncio.sleep(self._scan_interval)
                await self.scan_network()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scan loop error: {e}")
    
    async def scan_network(self, full_scan: bool = False) -> list[NetworkDevice]:
        """
        Scan the network for devices.
        
        Args:
            full_scan: If True, perform port scanning (slower)
        
        Returns:
            List of discovered devices
        """
        logger.debug("Scanning network...")
        
        # Get network range
        network = self._network_range or await self._detect_network_range()
        
        if not network:
            logger.warning("Could not determine network range")
            return []
        
        # Use ARP scan
        discovered = await self._arp_scan(network)
        
        # Update device list
        async with self._lock:
            now = datetime.now()
            current_macs = set()
            
            for device in discovered:
                current_macs.add(device.mac_address)
                
                if device.mac_address in self.devices:
                    # Update existing device
                    existing = self.devices[device.mac_address]
                    existing.ip_address = device.ip_address
                    existing.hostname = device.hostname or existing.hostname
                    existing.is_online = True
                    existing.last_seen = now
                else:
                    # New device
                    self.devices[device.mac_address] = device
                    
                    # Notify handlers
                    for handler in self._on_device_found:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(device)
                            else:
                                handler(device)
                        except Exception as e:
                            logger.error(f"Device found handler error: {e}")
            
            # Mark offline devices
            for mac, device in self.devices.items():
                if mac not in current_macs and device.is_online:
                    device.is_online = False
                    
                    for handler in self._on_device_lost:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(device)
                            else:
                                handler(device)
                        except Exception as e:
                            logger.error(f"Device lost handler error: {e}")
        
        # Optional port scanning
        if full_scan:
            for device in discovered:
                asyncio.create_task(self._scan_ports(device))
        
        logger.debug(f"Network scan complete: {len(discovered)} devices found")
        return discovered
    
    async def _detect_network_range(self) -> Optional[str]:
        """Auto-detect the local network range."""
        try:
            # Get default gateway
            result = await asyncio.create_subprocess_exec(
                "ip", "route", "show", "default",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await result.communicate()
            
            # Parse output: "default via 192.168.1.1 dev eth0"
            parts = stdout.decode().split()
            if "via" in parts:
                gateway_idx = parts.index("via") + 1
                gateway = parts[gateway_idx]
                
                # Assume /24 network
                network = ipaddress.IPv4Network(f"{gateway}/24", strict=False)
                return str(network)
            
        except Exception as e:
            logger.debug(f"Failed to detect network range: {e}")
        
        return None
    
    async def _arp_scan(self, network: str) -> list[NetworkDevice]:
        """Perform ARP scan of the network."""
        devices = []
        
        try:
            # Use arp-scan if available (requires root)
            result = await asyncio.create_subprocess_exec(
                "arp-scan", "--localnet", "--quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await result.communicate()
            
            for line in stdout.decode().splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    ip = parts[0].strip()
                    mac = parts[1].strip()
                    vendor = parts[2].strip() if len(parts) > 2 else ""
                    
                    hostname = await self._resolve_hostname(ip)
                    device_type = self._guess_device_type(hostname, vendor)
                    
                    devices.append(NetworkDevice(
                        mac_address=mac,
                        ip_address=ip,
                        hostname=hostname,
                        vendor=vendor,
                        device_type=device_type,
                    ))
            
        except FileNotFoundError:
            # Fallback to parsing ARP cache
            devices = await self._read_arp_cache()
        
        except Exception as e:
            logger.debug(f"ARP scan error: {e}")
            devices = await self._read_arp_cache()
        
        return devices
    
    async def _read_arp_cache(self) -> list[NetworkDevice]:
        """Read the system ARP cache."""
        devices = []
        
        try:
            result = await asyncio.create_subprocess_exec(
                "ip", "neigh", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await result.communicate()
            
            for line in stdout.decode().splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[3] == "lladdr":
                    ip = parts[0]
                    mac = parts[4]
                    state = parts[-1] if len(parts) > 5 else "REACHABLE"
                    
                    if state not in ("FAILED", "INCOMPLETE"):
                        hostname = await self._resolve_hostname(ip)
                        
                        devices.append(NetworkDevice(
                            mac_address=mac,
                            ip_address=ip,
                            hostname=hostname,
                        ))
            
        except Exception as e:
            logger.debug(f"ARP cache read error: {e}")
        
        return devices
    
    async def _resolve_hostname(self, ip: str) -> str:
        """Resolve hostname for an IP address."""
        try:
            result = socket.gethostbyaddr(ip)
            return result[0]
        except Exception:
            return ""
    
    async def _scan_ports(self, device: NetworkDevice):
        """Scan common ports on a device."""
        open_ports = []
        
        for port, service in self.COMMON_PORTS.items():
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(device.ip_address, port),
                    timeout=0.5,
                )
                writer.close()
                await writer.wait_closed()
                
                open_ports.append(port)
                device.services.append(service)
                
                # Check if it's a JARVIS client
                if port == 50051:
                    device.is_jarvis_client = True
                    device.device_type = DeviceType.JARVIS_CLIENT
                    
            except Exception:
                pass
        
        device.open_ports = open_ports
    
    def _guess_device_type(self, hostname: str, vendor: str) -> DeviceType:
        """Guess device type based on hostname and vendor."""
        hostname_lower = hostname.lower()
        vendor_lower = vendor.lower()
        
        # Check hostname patterns
        if "raspberrypi" in hostname_lower or "raspberry" in hostname_lower:
            return DeviceType.RASPBERRY_PI
        elif "iphone" in hostname_lower or "android" in hostname_lower:
            return DeviceType.PHONE
        elif "ipad" in hostname_lower:
            return DeviceType.TABLET
        elif "tv" in hostname_lower or "roku" in hostname_lower or "chromecast" in hostname_lower:
            return DeviceType.TV
        elif "printer" in hostname_lower or "brother" in vendor_lower or "hp" in vendor_lower:
            return DeviceType.PRINTER
        
        # Check vendor patterns
        if "intel" in vendor_lower or "dell" in vendor_lower or "hp" in vendor_lower:
            return DeviceType.PC
        elif "apple" in vendor_lower:
            return DeviceType.LAPTOP  # Could be phone too
        elif "raspberrypi" in vendor_lower or "raspberry pi" in vendor_lower:
            return DeviceType.RASPBERRY_PI
        elif "amazon" in vendor_lower or "google" in vendor_lower or "nest" in vendor_lower:
            return DeviceType.IOT
        
        return DeviceType.UNKNOWN
    
    def get_devices(self) -> list[NetworkDevice]:
        """Get all known devices."""
        return list(self.devices.values())
    
    def get_online_devices(self) -> list[NetworkDevice]:
        """Get currently online devices."""
        return [d for d in self.devices.values() if d.is_online]
    
    def get_jarvis_clients(self) -> list[NetworkDevice]:
        """Get discovered JARVIS clients."""
        return [d for d in self.devices.values() if d.is_jarvis_client]
    
    def get_device_by_ip(self, ip: str) -> Optional[NetworkDevice]:
        """Find device by IP address."""
        for device in self.devices.values():
            if device.ip_address == ip:
                return device
        return None


class JarvisServiceListener:
    """Listener for JARVIS mDNS services."""
    
    def __init__(self, callback: Callable):
        self.callback = callback
    
    def add_service(self, zc: Zeroconf, type_: str, name: str):
        """Handle new service."""
        asyncio.create_task(self._handle_service(zc, type_, name))
    
    def remove_service(self, zc: Zeroconf, type_: str, name: str):
        """Handle removed service."""
        pass
    
    def update_service(self, zc: Zeroconf, type_: str, name: str):
        """Handle updated service."""
        asyncio.create_task(self._handle_service(zc, type_, name))
    
    async def _handle_service(self, zc: Zeroconf, type_: str, name: str):
        """Process discovered service."""
        try:
            info = zc.get_service_info(type_, name)
            if info:
                addresses = info.parsed_addresses()
                if addresses:
                    await self.callback(
                        name=name,
                        address=addresses[0],
                        port=info.port,
                        properties=info.properties,
                    )
        except Exception as e:
            logger.error(f"Service handler error: {e}")


# =============================================================================
# Convenience function
# =============================================================================

async def discover_jarvis_clients(timeout: int = 10) -> list[dict]:
    """Quick scan for JARVIS clients on the network."""
    discovery = NetworkDiscovery()
    found_clients = []
    
    def on_found(client_info):
        found_clients.append(client_info)
    
    discovery.on_jarvis_client_found(on_found)
    
    await discovery.start()
    await asyncio.sleep(timeout)
    await discovery.stop()
    
    return found_clients
