"""
JARVIS Timer Plugin

Provides timer, alarm, and reminder functionality:
- Set timers
- Set reminders
- List active timers
- Cancel timers
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from loguru import logger

from jarvis.core.events import EventBus, EventType
from jarvis.plugins.base import Plugin, PluginInfo


@dataclass
class Timer:
    """Represents an active timer."""
    id: str
    name: str
    duration_seconds: int
    end_time: datetime
    message: str = ""
    completed: bool = False
    task: asyncio.Task | None = field(default=None, repr=False)


class TimerPlugin(Plugin):
    """Timer and reminder management plugin."""
    
    def __init__(self, config, event_bus: EventBus):
        super().__init__(config, event_bus)
        self.timers: dict[str, Timer] = {}
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="Timer",
            description="Set timers, alarms, and reminders",
            version="1.0.0",
            commands=[
                "set timer", "set alarm", "remind me",
                "list timers", "cancel timer", "stop timer",
            ],
            intents=[
                "timer", "alarm", "remind", "reminder",
                "minutes", "hours", "seconds", "later",
                "schedule", "notify",
            ],
        )
    
    async def execute(self, command: str, params: dict[str, Any]) -> str:
        """Execute timer command."""
        command_lower = command.lower()
        
        # Set timer/reminder
        if any(w in command_lower for w in ["set", "start", "remind"]):
            return await self._set_timer(command, params)
        
        # List timers
        if "list" in command_lower:
            return self._list_timers()
        
        # Cancel timer
        if any(w in command_lower for w in ["cancel", "stop", "delete", "remove"]):
            return await self._cancel_timer(command, params)
        
        return "I can set timers. Try 'set timer for 5 minutes' or 'remind me in 30 minutes to check email'."
    
    async def _set_timer(self, command: str, params: dict) -> str:
        """Set a new timer."""
        # Parse duration
        duration_seconds = self._parse_duration(command)
        
        if duration_seconds is None:
            return "Please specify a duration, like '5 minutes' or '1 hour'."
        
        # Extract message/name
        message = self._extract_reminder_message(command)
        
        # Create timer
        timer_id = str(uuid4())[:8]
        end_time = datetime.now() + timedelta(seconds=duration_seconds)
        
        timer = Timer(
            id=timer_id,
            name=message or f"Timer {timer_id}",
            duration_seconds=duration_seconds,
            end_time=end_time,
            message=message,
        )
        
        # Start the timer task
        timer.task = asyncio.create_task(self._timer_task(timer))
        self.timers[timer_id] = timer
        
        # Format response
        duration_str = self._format_duration(duration_seconds)
        
        if message:
            return f"I'll remind you {message} in {duration_str}."
        else:
            return f"Timer set for {duration_str}."
    
    def _parse_duration(self, command: str) -> int | None:
        """Parse duration from command text."""
        import re
        
        command_lower = command.lower()
        total_seconds = 0
        found = False
        
        # Pattern for "X hours/minutes/seconds"
        patterns = [
            (r'(\d+)\s*hours?', 3600),
            (r'(\d+)\s*hour', 3600),
            (r'(\d+)\s*minutes?', 60),
            (r'(\d+)\s*mins?', 60),
            (r'(\d+)\s*seconds?', 1),
            (r'(\d+)\s*secs?', 1),
        ]
        
        for pattern, multiplier in patterns:
            match = re.search(pattern, command_lower)
            if match:
                value = int(match.group(1))
                total_seconds += value * multiplier
                found = True
        
        # Handle "half an hour" etc
        if "half an hour" in command_lower or "half hour" in command_lower:
            total_seconds += 1800
            found = True
        
        return total_seconds if found else None
    
    def _extract_reminder_message(self, command: str) -> str:
        """Extract the reminder message from command."""
        command_lower = command.lower()
        
        # Look for "to [message]" pattern
        indicators = ["to ", "that ", "about "]
        
        for indicator in indicators:
            idx = command_lower.rfind(indicator)
            if idx > 0:
                # Check if it's after the time specification
                time_words = ["minute", "hour", "second"]
                time_idx = max(
                    command_lower.rfind(tw) for tw in time_words
                )
                
                if idx > time_idx > 0:
                    message = command[idx + len(indicator):].strip()
                    # Remove trailing punctuation
                    message = message.rstrip('.,!?')
                    if message:
                        return message
        
        return ""
    
    async def _timer_task(self, timer: Timer) -> None:
        """Async task that waits and triggers when timer completes."""
        try:
            await asyncio.sleep(timer.duration_seconds)
            
            timer.completed = True
            
            # Emit timer complete event
            if timer.message:
                notification = f"Reminder: {timer.message}"
            else:
                notification = f"Timer '{timer.name}' has completed!"
            
            await self.event_bus.emit(
                EventType.ASSISTANT_RESPONSE,
                {"text": notification, "source": "timer"},
                source="timer_plugin"
            )
            
            logger.info(f"Timer completed: {timer.name}")
            
            # Clean up
            if timer.id in self.timers:
                del self.timers[timer.id]
                
        except asyncio.CancelledError:
            logger.debug(f"Timer cancelled: {timer.name}")
    
    def _list_timers(self) -> str:
        """List all active timers."""
        active = [t for t in self.timers.values() if not t.completed]
        
        if not active:
            return "No active timers."
        
        response = f"Active timers ({len(active)}):\n"
        
        for timer in active:
            remaining = timer.end_time - datetime.now()
            remaining_str = self._format_duration(int(remaining.total_seconds()))
            response += f"• {timer.name}: {remaining_str} remaining\n"
        
        return response.strip()
    
    async def _cancel_timer(self, command: str, params: dict) -> str:
        """Cancel an active timer."""
        if not self.timers:
            return "No active timers to cancel."
        
        # If only one timer, cancel it
        if len(self.timers) == 1:
            timer = list(self.timers.values())[0]
            if timer.task:
                timer.task.cancel()
            del self.timers[timer.id]
            return f"Cancelled timer: {timer.name}"
        
        # Try to find specific timer by name
        command_lower = command.lower()
        
        for timer in self.timers.values():
            if timer.name.lower() in command_lower:
                if timer.task:
                    timer.task.cancel()
                del self.timers[timer.id]
                return f"Cancelled timer: {timer.name}"
        
        # Cancel all if requested
        if "all" in command_lower:
            count = len(self.timers)
            for timer in self.timers.values():
                if timer.task:
                    timer.task.cancel()
            self.timers.clear()
            return f"Cancelled all {count} timers."
        
        return f"Multiple timers active. Specify which to cancel or say 'cancel all timers': {self._list_timers()}"
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration for display."""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining = seconds % 60
            if remaining:
                return f"{minutes} minutes {remaining} seconds"
            return f"{minutes} minutes"
        else:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            if remaining_minutes:
                return f"{hours} hours {remaining_minutes} minutes"
            return f"{hours} hours"
    
    async def shutdown(self) -> None:
        """Cancel all timers on shutdown."""
        for timer in self.timers.values():
            if timer.task:
                timer.task.cancel()
        self.timers.clear()
        await super().shutdown()
