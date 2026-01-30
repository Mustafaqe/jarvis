"""
JARVIS Context Aggregator

Collects and aggregates context from all connected clients, IoT devices,
and system state to provide the AI with comprehensive situational awareness.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Any

from loguru import logger


@dataclass
class ClientContext:
    """Context from a single client."""
    client_id: str
    hostname: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # System state
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    is_idle: bool = False
    idle_seconds: int = 0
    
    # User activity
    active_window: str = ""
    active_app: str = ""
    recent_apps: list[str] = field(default_factory=list)
    
    # Screen context (from OCR/vision)
    screen_text: str = ""
    detected_activity: str = ""
    
    # Clipboard (if allowed)
    clipboard_text: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "client_id": self.client_id,
            "hostname": self.hostname,
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "disk_percent": self.disk_percent,
            "is_idle": self.is_idle,
            "idle_seconds": self.idle_seconds,
            "active_window": self.active_window,
            "active_app": self.active_app,
            "recent_apps": self.recent_apps,
            "detected_activity": self.detected_activity,
        }


@dataclass
class IoTContext:
    """Context from IoT devices."""
    device_id: str
    device_name: str
    category: str
    state: dict = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "category": self.category,
            "state": self.state,
            "last_update": self.last_update.isoformat(),
        }


@dataclass
class EnvironmentContext:
    """Environmental context."""
    time_of_day: str = ""  # morning, afternoon, evening, night
    day_of_week: str = ""
    is_workday: bool = True
    weather: Optional[dict] = None
    location: Optional[dict] = None


@dataclass
class GlobalContext:
    """Aggregated context from all sources."""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Connected clients
    clients: list[ClientContext] = field(default_factory=list)
    active_client_count: int = 0
    
    # IoT devices
    iot_devices: list[IoTContext] = field(default_factory=list)
    
    # Environment
    environment: EnvironmentContext = field(default_factory=EnvironmentContext)
    
    # Recent activity
    recent_commands: list[dict] = field(default_factory=list)
    recent_conversations: list[dict] = field(default_factory=list)
    
    # Detected patterns
    current_activity: str = ""  # What the user seems to be doing
    predicted_needs: list[str] = field(default_factory=list)  # What they might need
    
    def to_dict(self) -> dict:
        """Convert to dictionary for AI consumption."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "clients": [c.to_dict() for c in self.clients],
            "active_client_count": self.active_client_count,
            "iot_devices": [d.to_dict() for d in self.iot_devices],
            "environment": {
                "time_of_day": self.environment.time_of_day,
                "day_of_week": self.environment.day_of_week,
                "is_workday": self.environment.is_workday,
            },
            "current_activity": self.current_activity,
            "predicted_needs": self.predicted_needs,
        }
    
    def to_prompt(self) -> str:
        """Generate a natural language context summary for AI."""
        parts = []
        
        # Time context
        now = datetime.now()
        parts.append(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} ({self.environment.time_of_day})")
        parts.append(f"Day: {self.environment.day_of_week}")
        
        # Client context
        if self.clients:
            parts.append(f"\nConnected clients: {len(self.clients)}")
            for client in self.clients:
                status = "idle" if client.is_idle else "active"
                parts.append(f"  - {client.hostname}: {status}, using {client.active_app or 'unknown'}")
                if client.active_window:
                    parts.append(f"    Window: {client.active_window[:50]}")
        
        # IoT context
        if self.iot_devices:
            parts.append(f"\nIoT devices: {len(self.iot_devices)}")
            for device in self.iot_devices[:5]:  # Limit to top 5
                state_str = device.state.get("state", "unknown")
                parts.append(f"  - {device.device_name}: {state_str}")
        
        # Activity
        if self.current_activity:
            parts.append(f"\nDetected activity: {self.current_activity}")
        
        if self.predicted_needs:
            parts.append(f"Predicted needs: {', '.join(self.predicted_needs[:3])}")
        
        return "\n".join(parts)


class ContextAggregator:
    """
    Aggregates context from all sources for AI consumption.
    
    Sources:
    - Connected JARVIS clients (system stats, active windows, screens)
    - IoT devices (states, recent changes)
    - Environment (time, weather, location)
    - History (recent commands, conversations)
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        
        # Context storage
        self._client_contexts: dict[str, ClientContext] = {}
        self._iot_contexts: dict[str, IoTContext] = {}
        self._recent_commands: list[dict] = []
        self._recent_conversations: list[dict] = []
        
        # Cache
        self._cached_context: Optional[GlobalContext] = None
        self._cache_ttl = self.config.get("cache_ttl", 5)  # seconds
        self._last_cache_update: Optional[datetime] = None
        
        # Configuration
        self._max_recent_commands = self.config.get("max_recent_commands", 20)
        self._max_recent_conversations = self.config.get("max_recent_conversations", 10)
        
        self._lock = asyncio.Lock()
    
    async def update_client_context(self, client_id: str, data: dict):
        """Update context for a client."""
        async with self._lock:
            ctx = self._client_contexts.get(client_id)
            
            if not ctx:
                ctx = ClientContext(
                    client_id=client_id,
                    hostname=data.get("hostname", "unknown"),
                )
                self._client_contexts[client_id] = ctx
            
            # Update fields
            ctx.timestamp = datetime.now()
            ctx.cpu_percent = data.get("cpu_percent", ctx.cpu_percent)
            ctx.memory_percent = data.get("memory_percent", ctx.memory_percent)
            ctx.disk_percent = data.get("disk_percent", ctx.disk_percent)
            ctx.is_idle = data.get("is_idle", ctx.is_idle)
            ctx.idle_seconds = data.get("idle_seconds", ctx.idle_seconds)
            ctx.active_window = data.get("active_window", ctx.active_window)
            ctx.active_app = data.get("active_app", ctx.active_app)
            ctx.recent_apps = data.get("recent_apps", ctx.recent_apps)
            ctx.screen_text = data.get("screen_text", ctx.screen_text)
            ctx.detected_activity = data.get("detected_activity", ctx.detected_activity)
            
            # Invalidate cache
            self._cached_context = None
    
    async def update_iot_context(self, device_id: str, data: dict):
        """Update context for an IoT device."""
        async with self._lock:
            ctx = IoTContext(
                device_id=device_id,
                device_name=data.get("name", device_id),
                category=data.get("category", "other"),
                state=data.get("state", {}),
                last_update=datetime.now(),
            )
            self._iot_contexts[device_id] = ctx
            
            # Invalidate cache
            self._cached_context = None
    
    async def record_command(self, command: dict):
        """Record a command in history."""
        async with self._lock:
            self._recent_commands.insert(0, {
                **command,
                "timestamp": datetime.now().isoformat(),
            })
            
            # Trim to max size
            if len(self._recent_commands) > self._max_recent_commands:
                self._recent_commands = self._recent_commands[:self._max_recent_commands]
    
    async def record_conversation(self, user_input: str, response: str):
        """Record a conversation turn."""
        async with self._lock:
            self._recent_conversations.insert(0, {
                "user": user_input,
                "assistant": response,
                "timestamp": datetime.now().isoformat(),
            })
            
            if len(self._recent_conversations) > self._max_recent_conversations:
                self._recent_conversations = self._recent_conversations[:self._max_recent_conversations]
    
    async def get_context(self, force_refresh: bool = False) -> GlobalContext:
        """
        Get the current aggregated context.
        
        Uses caching to avoid expensive recomputation.
        """
        async with self._lock:
            # Check cache
            if not force_refresh and self._cached_context:
                if self._last_cache_update:
                    age = (datetime.now() - self._last_cache_update).total_seconds()
                    if age < self._cache_ttl:
                        return self._cached_context
            
            # Build fresh context
            context = GlobalContext(
                timestamp=datetime.now(),
                clients=list(self._client_contexts.values()),
                active_client_count=sum(
                    1 for c in self._client_contexts.values() 
                    if not c.is_idle and (datetime.now() - c.timestamp).seconds < 60
                ),
                iot_devices=list(self._iot_contexts.values()),
                environment=self._get_environment_context(),
                recent_commands=self._recent_commands[:5],
                recent_conversations=self._recent_conversations[:3],
            )
            
            # Detect current activity
            context.current_activity = self._detect_activity(context)
            
            # Predict needs
            context.predicted_needs = self._predict_needs(context)
            
            # Update cache
            self._cached_context = context
            self._last_cache_update = datetime.now()
            
            return context
    
    def _get_environment_context(self) -> EnvironmentContext:
        """Get current environment context."""
        now = datetime.now()
        
        # Determine time of day
        hour = now.hour
        if 5 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 17:
            time_of_day = "afternoon"
        elif 17 <= hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"
        
        # Day of week
        day = now.strftime("%A")
        is_workday = now.weekday() < 5
        
        return EnvironmentContext(
            time_of_day=time_of_day,
            day_of_week=day,
            is_workday=is_workday,
        )
    
    def _detect_activity(self, context: GlobalContext) -> str:
        """Detect what the user is currently doing."""
        activities = []
        
        for client in context.clients:
            if client.is_idle:
                continue
            
            app = client.active_app.lower() if client.active_app else ""
            window = client.active_window.lower() if client.active_window else ""
            
            # Detect common activities
            if any(x in app for x in ["code", "vscode", "intellij", "pycharm", "vim", "nvim"]):
                activities.append("coding")
            elif any(x in app for x in ["firefox", "chrome", "chromium", "brave"]):
                if any(x in window for x in ["youtube", "netflix", "twitch"]):
                    activities.append("watching_video")
                elif any(x in window for x in ["github", "stackoverflow", "docs"]):
                    activities.append("researching")
                else:
                    activities.append("browsing")
            elif any(x in app for x in ["slack", "discord", "teams", "telegram"]):
                activities.append("communicating")
            elif any(x in app for x in ["thunderbird", "outlook", "gmail"]):
                activities.append("checking_email")
            elif any(x in app for x in ["spotify", "rhythmbox", "vlc"]):
                activities.append("listening_music")
            elif any(x in app for x in ["terminal", "konsole", "gnome-terminal"]):
                activities.append("using_terminal")
        
        if not activities:
            if all(c.is_idle for c in context.clients):
                return "idle"
            return "unknown"
        
        # Return most common activity
        from collections import Counter
        return Counter(activities).most_common(1)[0][0]
    
    def _predict_needs(self, context: GlobalContext) -> list[str]:
        """Predict what the user might need based on context."""
        predictions = []
        
        # Time-based predictions
        if context.environment.time_of_day == "morning":
            predictions.append("daily_briefing")
        elif context.environment.time_of_day == "evening":
            predictions.append("day_summary")
        
        # Activity-based predictions
        if context.current_activity == "coding":
            predictions.append("documentation_lookup")
            predictions.append("code_assistance")
        elif context.current_activity == "researching":
            predictions.append("search_assistance")
        elif context.current_activity == "browsing":
            predictions.append("bookmark_suggestion")
        
        # System-based predictions
        for client in context.clients:
            if client.cpu_percent > 80:
                predictions.append("performance_check")
            if client.disk_percent > 90:
                predictions.append("disk_cleanup")
        
        return list(set(predictions))[:5]
    
    async def get_context_for_ai(self) -> str:
        """Get context formatted for AI consumption."""
        context = await self.get_context()
        return context.to_prompt()
    
    async def get_context_dict(self) -> dict:
        """Get context as a dictionary."""
        context = await self.get_context()
        return context.to_dict()
    
    def remove_client(self, client_id: str):
        """Remove a client from context."""
        if client_id in self._client_contexts:
            del self._client_contexts[client_id]
            self._cached_context = None
    
    def clear(self):
        """Clear all context."""
        self._client_contexts.clear()
        self._iot_contexts.clear()
        self._recent_commands.clear()
        self._recent_conversations.clear()
        self._cached_context = None
