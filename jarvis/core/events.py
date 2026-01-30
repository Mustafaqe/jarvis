"""
JARVIS Event System

Provides an event-driven architecture for component communication using
async queues and pub/sub patterns.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Coroutine
from uuid import uuid4

from loguru import logger


class EventType(Enum):
    """Types of events in the JARVIS system."""
    
    # Voice events
    WAKE_WORD_DETECTED = auto()
    SPEECH_START = auto()
    SPEECH_END = auto()
    TRANSCRIPTION_COMPLETE = auto()
    TTS_START = auto()
    TTS_COMPLETE = auto()
    
    # AI events
    INTENT_CLASSIFIED = auto()
    LLM_RESPONSE = auto()
    CONTEXT_UPDATED = auto()
    
    # Command events
    COMMAND_RECEIVED = auto()
    COMMAND_EXECUTING = auto()
    COMMAND_COMPLETE = auto()
    COMMAND_ERROR = auto()
    
    # Plugin events
    PLUGIN_LOADED = auto()
    PLUGIN_UNLOADED = auto()
    PLUGIN_ERROR = auto()
    
    # System events
    SYSTEM_READY = auto()
    SYSTEM_SHUTDOWN = auto()
    SYSTEM_ERROR = auto()
    
    # User interaction
    USER_INPUT = auto()
    ASSISTANT_RESPONSE = auto()
    CONFIRMATION_REQUIRED = auto()
    CONFIRMATION_RECEIVED = auto()


@dataclass
class Event:
    """
    Event data container.
    
    Attributes:
        type: The type of event
        data: Event payload data
        source: Component that generated the event
        timestamp: When the event was created
        id: Unique event identifier
    """
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: str(uuid4()))
    
    def __str__(self) -> str:
        return f"Event({self.type.name}, source={self.source}, id={self.id[:8]})"


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Central event bus for component communication.
    
    Provides pub/sub functionality with async support for decoupled
    component communication.
    """
    
    def __init__(self):
        """Initialize the event bus."""
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None
        
    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Subscribe a handler to an event type.
        
        Args:
            event_type: Type of event to listen for
            handler: Async function to call when event occurs
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        
        self._handlers[event_type].append(handler)
        logger.debug(f"Subscribed handler to {event_type.name}")
    
    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Unsubscribe a handler from an event type.
        
        Args:
            event_type: Type of event
            handler: Handler to remove
        """
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug(f"Unsubscribed handler from {event_type.name}")
    
    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.
        
        Args:
            event: Event to publish
        """
        await self._queue.put(event)
        logger.debug(f"Published {event}")
    
    async def emit(
        self,
        event_type: EventType,
        data: dict[str, Any] | None = None,
        source: str = "system"
    ) -> Event:
        """
        Convenience method to create and publish an event.
        
        Args:
            event_type: Type of event
            data: Optional event data
            source: Source component name
            
        Returns:
            The created event
        """
        event = Event(type=event_type, data=data or {}, source=source)
        await self.publish(event)
        return event
    
    async def _process_events(self) -> None:
        """Main event processing loop."""
        while self._running:
            try:
                # Wait for event with timeout to allow checking running flag
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                
                # Get handlers for this event type
                handlers = self._handlers.get(event.type, [])
                
                if not handlers:
                    logger.debug(f"No handlers for {event.type.name}")
                    continue
                
                # Call all handlers concurrently
                tasks = [
                    asyncio.create_task(self._safe_call(handler, event))
                    for handler in handlers
                ]
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
            except Exception as e:
                logger.error(f"Error processing event: {e}")
    
    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        """Safely call an event handler with error handling."""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Handler error for {event.type.name}: {e}")
    
    async def start(self) -> None:
        """Start the event processing loop."""
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")
    
    async def stop(self) -> None:
        """Stop the event processing loop."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Event bus stopped")
    
    def clear(self) -> None:
        """Clear all event handlers."""
        self._handlers.clear()
        logger.debug("Event handlers cleared")


# Global event bus instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
