"""
JARVIS IoT Integration

Provides integration with IoT devices through MQTT, Home Assistant,
and generic REST APIs.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any

from loguru import logger

try:
    import paho.mqtt.client as mqtt
    from paho.mqtt.client import Client as MQTTClient
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.debug("Paho MQTT not available. Install with: pip install paho-mqtt")

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class DeviceCategory(Enum):
    """Categories of IoT devices."""
    LIGHT = "light"
    SWITCH = "switch"
    SENSOR = "sensor"
    THERMOSTAT = "thermostat"
    LOCK = "lock"
    CAMERA = "camera"
    SPEAKER = "speaker"
    TV = "tv"
    FAN = "fan"
    COVER = "cover"  # Blinds, curtains
    CLIMATE = "climate"
    VACUUM = "vacuum"
    OTHER = "other"


@dataclass
class IoTDevice:
    """Represents an IoT device."""
    device_id: str
    name: str
    category: DeviceCategory = DeviceCategory.OTHER
    manufacturer: str = ""
    model: str = ""
    protocol: str = ""  # mqtt, rest, homeassistant, etc.
    is_online: bool = True
    state: dict = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    last_update: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "category": self.category.value,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "protocol": self.protocol,
            "is_online": self.is_online,
            "state": self.state,
            "capabilities": self.capabilities,
            "last_update": self.last_update.isoformat(),
        }


class MQTTHandler:
    """Handles MQTT communication with IoT devices."""
    
    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        username: str = None,
        password: str = None,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        
        self._client: Optional[MQTTClient] = None
        self._connected = False
        self._subscriptions: dict[str, list[Callable]] = {}
        self._message_handlers: list[Callable] = []
    
    def on_message(self, handler: Callable):
        """Register handler for all messages."""
        self._message_handlers.append(handler)
    
    def connect(self) -> bool:
        """Connect to MQTT broker."""
        if not MQTT_AVAILABLE:
            logger.error("MQTT not available")
            return False
        
        try:
            self._client = mqtt.Client()
            
            if self.username and self.password:
                self._client.username_pw_set(self.username, self.password)
            
            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.on_disconnect = self._on_disconnect
            
            self._client.connect(self.broker_host, self.broker_port, 60)
            self._client.loop_start()
            
            return True
            
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
            self._connected = False
    
    def subscribe(self, topic: str, handler: Callable = None):
        """Subscribe to a topic."""
        if not self._client:
            return
        
        self._client.subscribe(topic)
        
        if handler:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(handler)
    
    def publish(self, topic: str, payload: Any, retain: bool = False) -> bool:
        """Publish a message."""
        if not self._client or not self._connected:
            return False
        
        try:
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            elif not isinstance(payload, str):
                payload = str(payload)
            
            self._client.publish(topic, payload, retain=retain)
            return True
            
        except Exception as e:
            logger.error(f"MQTT publish failed: {e}")
            return False
    
    def _on_connect(self, client, userdata, flags, rc):
        """Handle connection."""
        if rc == 0:
            self._connected = True
            logger.info("Connected to MQTT broker")
            
            # Resubscribe to topics
            for topic in self._subscriptions:
                self._client.subscribe(topic)
        else:
            logger.error(f"MQTT connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Handle disconnection."""
        self._connected = False
        logger.warning("Disconnected from MQTT broker")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming message."""
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        
        # Try to parse JSON
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            pass
        
        # Call topic-specific handlers
        for pattern, handlers in self._subscriptions.items():
            if self._topic_matches(topic, pattern):
                for handler in handlers:
                    try:
                        handler(topic, payload)
                    except Exception as e:
                        logger.error(f"MQTT handler error: {e}")
        
        # Call general handlers
        for handler in self._message_handlers:
            try:
                handler(topic, payload)
            except Exception as e:
                logger.error(f"MQTT message handler error: {e}")
    
    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """Check if topic matches pattern (with wildcards)."""
        if pattern == topic:
            return True
        
        pattern_parts = pattern.split("/")
        topic_parts = topic.split("/")
        
        for i, p in enumerate(pattern_parts):
            if p == "#":
                return True
            if i >= len(topic_parts):
                return False
            if p != "+" and p != topic_parts[i]:
                return False
        
        return len(pattern_parts) == len(topic_parts)


class HomeAssistantClient:
    """Client for Home Assistant REST API."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        access_token: str = "",
        use_ssl: bool = False,
    ):
        self.host = host
        self.port = port
        self.access_token = access_token
        self.base_url = f"{'https' if use_ssl else 'http'}://{host}:{port}/api"
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def connect(self) -> bool:
        """Initialize connection."""
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp not available")
            return False
        
        try:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                }
            )
            
            # Test connection
            async with self._session.get(f"{self.base_url}/") as response:
                if response.status == 200:
                    logger.info("Connected to Home Assistant")
                    return True
                else:
                    logger.error(f"Home Assistant connection failed: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Home Assistant connection error: {e}")
            return False
    
    async def disconnect(self):
        """Close connection."""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def get_states(self) -> list[dict]:
        """Get all entity states."""
        if not self._session:
            return []
        
        try:
            async with self._session.get(f"{self.base_url}/states") as response:
                if response.status == 200:
                    return await response.json()
                return []
        except Exception as e:
            logger.error(f"Failed to get states: {e}")
            return []
    
    async def get_state(self, entity_id: str) -> Optional[dict]:
        """Get state of a specific entity."""
        if not self._session:
            return None
        
        try:
            async with self._session.get(f"{self.base_url}/states/{entity_id}") as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            logger.error(f"Failed to get state: {e}")
            return None
    
    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str = None,
        data: dict = None,
    ) -> bool:
        """Call a Home Assistant service."""
        if not self._session:
            return False
        
        try:
            payload = data or {}
            if entity_id:
                payload["entity_id"] = entity_id
            
            async with self._session.post(
                f"{self.base_url}/services/{domain}/{service}",
                json=payload,
            ) as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"Service call failed: {e}")
            return False
    
    async def turn_on(self, entity_id: str, **kwargs) -> bool:
        """Turn on an entity."""
        domain = entity_id.split(".")[0]
        return await self.call_service(domain, "turn_on", entity_id, kwargs)
    
    async def turn_off(self, entity_id: str) -> bool:
        """Turn off an entity."""
        domain = entity_id.split(".")[0]
        return await self.call_service(domain, "turn_off", entity_id)
    
    async def toggle(self, entity_id: str) -> bool:
        """Toggle an entity."""
        domain = entity_id.split(".")[0]
        return await self.call_service(domain, "toggle", entity_id)


class IoTManager:
    """
    Manages all IoT devices across different protocols.
    
    Supports:
    - MQTT devices
    - Home Assistant integration
    - Generic REST devices
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.devices: dict[str, IoTDevice] = {}
        
        # Protocol handlers
        self._mqtt: Optional[MQTTHandler] = None
        self._homeassistant: Optional[HomeAssistantClient] = None
        
        # Event handlers
        self._on_state_change: list[Callable] = []
        self._on_device_added: list[Callable] = []
        
        self._running = False
        self._lock = asyncio.Lock()
    
    def on_state_change(self, handler: Callable):
        """Register handler for device state changes."""
        self._on_state_change.append(handler)
    
    def on_device_added(self, handler: Callable):
        """Register handler for new devices."""
        self._on_device_added.append(handler)
    
    async def start(self):
        """Start IoT manager."""
        self._running = True
        
        # Initialize MQTT
        mqtt_config = self.config.get("mqtt", {})
        if mqtt_config.get("enabled", False):
            self._mqtt = MQTTHandler(
                broker_host=mqtt_config.get("host", "localhost"),
                broker_port=mqtt_config.get("port", 1883),
                username=mqtt_config.get("username"),
                password=mqtt_config.get("password"),
            )
            
            if self._mqtt.connect():
                # Subscribe to common topics
                self._mqtt.subscribe("zigbee2mqtt/#", self._handle_zigbee2mqtt)
                self._mqtt.subscribe("tasmota/#", self._handle_tasmota)
                self._mqtt.subscribe("jarvis/iot/#", self._handle_jarvis_iot)
        
        # Initialize Home Assistant
        ha_config = self.config.get("homeassistant", {})
        if ha_config.get("enabled", False):
            self._homeassistant = HomeAssistantClient(
                host=ha_config.get("host", "localhost"),
                port=ha_config.get("port", 8123),
                access_token=ha_config.get("access_token", ""),
                use_ssl=ha_config.get("use_ssl", False),
            )
            
            if await self._homeassistant.connect():
                # Discover devices
                await self._discover_ha_devices()
        
        logger.info("IoT manager started")
    
    async def stop(self):
        """Stop IoT manager."""
        self._running = False
        
        if self._mqtt:
            self._mqtt.disconnect()
        
        if self._homeassistant:
            await self._homeassistant.disconnect()
        
        logger.info("IoT manager stopped")
    
    async def _discover_ha_devices(self):
        """Discover devices from Home Assistant."""
        if not self._homeassistant:
            return
        
        states = await self._homeassistant.get_states()
        
        for state in states:
            entity_id = state.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            
            # Map Home Assistant domains to our categories
            category_map = {
                "light": DeviceCategory.LIGHT,
                "switch": DeviceCategory.SWITCH,
                "sensor": DeviceCategory.SENSOR,
                "binary_sensor": DeviceCategory.SENSOR,
                "climate": DeviceCategory.CLIMATE,
                "lock": DeviceCategory.LOCK,
                "camera": DeviceCategory.CAMERA,
                "media_player": DeviceCategory.SPEAKER,
                "fan": DeviceCategory.FAN,
                "cover": DeviceCategory.COVER,
                "vacuum": DeviceCategory.VACUUM,
            }
            
            if domain in category_map:
                device = IoTDevice(
                    device_id=entity_id,
                    name=state.get("attributes", {}).get("friendly_name", entity_id),
                    category=category_map.get(domain, DeviceCategory.OTHER),
                    protocol="homeassistant",
                    state={"state": state.get("state"), **state.get("attributes", {})},
                )
                
                await self._add_device(device)
    
    def _handle_zigbee2mqtt(self, topic: str, payload: Any):
        """Handle Zigbee2MQTT messages."""
        parts = topic.split("/")
        if len(parts) >= 2:
            device_name = parts[1]
            
            if isinstance(payload, dict):
                asyncio.create_task(self._update_device_state(
                    f"zigbee2mqtt.{device_name}",
                    payload,
                ))
    
    def _handle_tasmota(self, topic: str, payload: Any):
        """Handle Tasmota device messages."""
        parts = topic.split("/")
        if len(parts) >= 2:
            device_name = parts[1]
            
            asyncio.create_task(self._update_device_state(
                f"tasmota.{device_name}",
                {"state": payload} if isinstance(payload, str) else payload,
            ))
    
    def _handle_jarvis_iot(self, topic: str, payload: Any):
        """Handle messages on jarvis/iot topic."""
        parts = topic.split("/")
        if len(parts) >= 3:
            device_id = parts[2]
            
            if isinstance(payload, dict):
                asyncio.create_task(self._update_device_state(device_id, payload))
    
    async def _add_device(self, device: IoTDevice):
        """Add a new device."""
        async with self._lock:
            self.devices[device.device_id] = device
        
        for handler in self._on_device_added:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(device)
                else:
                    handler(device)
            except Exception as e:
                logger.error(f"Device added handler error: {e}")
    
    async def _update_device_state(self, device_id: str, state: dict):
        """Update device state."""
        async with self._lock:
            if device_id in self.devices:
                device = self.devices[device_id]
                device.state.update(state)
                device.last_update = datetime.now()
                
                for handler in self._on_state_change:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(device)
                        else:
                            handler(device)
                    except Exception as e:
                        logger.error(f"State change handler error: {e}")
    
    # =========================================================================
    # Control Methods
    # =========================================================================
    
    async def control(
        self,
        device_id: str,
        action: str,
        parameters: dict = None,
    ) -> bool:
        """
        Control an IoT device.
        
        Args:
            device_id: Device identifier
            action: Action to perform (on, off, toggle, set, etc.)
            parameters: Action parameters
        """
        if device_id not in self.devices:
            logger.warning(f"Device not found: {device_id}")
            return False
        
        device = self.devices[device_id]
        
        if device.protocol == "homeassistant":
            return await self._control_ha_device(device, action, parameters)
        elif device.protocol == "mqtt":
            return await self._control_mqtt_device(device, action, parameters)
        else:
            logger.warning(f"Unknown protocol: {device.protocol}")
            return False
    
    async def _control_ha_device(
        self,
        device: IoTDevice,
        action: str,
        parameters: dict = None,
    ) -> bool:
        """Control a Home Assistant device."""
        if not self._homeassistant:
            return False
        
        if action == "on":
            return await self._homeassistant.turn_on(device.device_id, **(parameters or {}))
        elif action == "off":
            return await self._homeassistant.turn_off(device.device_id)
        elif action == "toggle":
            return await self._homeassistant.toggle(device.device_id)
        else:
            # Generic service call
            domain = device.device_id.split(".")[0]
            return await self._homeassistant.call_service(
                domain, action, device.device_id, parameters
            )
    
    async def _control_mqtt_device(
        self,
        device: IoTDevice,
        action: str,
        parameters: dict = None,
    ) -> bool:
        """Control an MQTT device."""
        if not self._mqtt:
            return False
        
        # Build topic based on device type
        if device.device_id.startswith("zigbee2mqtt."):
            device_name = device.device_id.replace("zigbee2mqtt.", "")
            topic = f"zigbee2mqtt/{device_name}/set"
            
            payload = parameters or {}
            if action == "on":
                payload["state"] = "ON"
            elif action == "off":
                payload["state"] = "OFF"
            elif action == "toggle":
                payload["state"] = "TOGGLE"
            
            return self._mqtt.publish(topic, payload)
            
        elif device.device_id.startswith("tasmota."):
            device_name = device.device_id.replace("tasmota.", "")
            
            if action in ("on", "off", "toggle"):
                topic = f"cmnd/{device_name}/POWER"
                payload = action.upper()
            else:
                topic = f"cmnd/{device_name}/{action}"
                payload = json.dumps(parameters) if parameters else ""
            
            return self._mqtt.publish(topic, payload)
        
        else:
            # Generic MQTT device
            topic = f"jarvis/iot/{device.device_id}/set"
            return self._mqtt.publish(topic, {"action": action, **(parameters or {})})
    
    def get_devices(self) -> list[IoTDevice]:
        """Get all devices."""
        return list(self.devices.values())
    
    def get_devices_by_category(self, category: DeviceCategory) -> list[IoTDevice]:
        """Get devices by category."""
        return [d for d in self.devices.values() if d.category == category]
    
    def get_device(self, device_id: str) -> Optional[IoTDevice]:
        """Get a specific device."""
        return self.devices.get(device_id)
    
    async def turn_on(self, device_id: str, **kwargs) -> bool:
        """Convenience method to turn on a device."""
        return await self.control(device_id, "on", kwargs if kwargs else None)
    
    async def turn_off(self, device_id: str) -> bool:
        """Convenience method to turn off a device."""
        return await self.control(device_id, "off")
    
    async def toggle(self, device_id: str) -> bool:
        """Convenience method to toggle a device."""
        return await self.control(device_id, "toggle")
