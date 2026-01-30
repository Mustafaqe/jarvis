"""
JARVIS Pattern Learner

Learns from user behavior patterns to anticipate needs and suggest
proactive actions.
"""

import asyncio
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

from loguru import logger


@dataclass
class Pattern:
    """A learned behavioral pattern."""
    pattern_id: str
    pattern_type: str  # time_based, sequence, activity, location
    trigger: dict  # What triggers this pattern
    action: dict  # What action to suggest/take
    confidence: float = 0.5  # 0-1, how confident in this pattern
    occurrences: int = 1  # Times this pattern occurred
    last_triggered: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "trigger": self.trigger,
            "action": self.action,
            "confidence": self.confidence,
            "occurrences": self.occurrences,
        }


@dataclass
class CommandSequence:
    """A sequence of commands."""
    commands: list[str]
    timestamps: list[datetime]
    client_id: Optional[str] = None
    
    def matches_start(self, sequence: list[str], threshold: int = 3) -> bool:
        """Check if given sequence matches the start of this sequence."""
        if len(sequence) < 2 or len(self.commands) < len(sequence):
            return False
        return self.commands[:len(sequence)] == sequence


class PatternLearner:
    """
    Learns behavioral patterns from user activity.
    
    Pattern Types:
    - Time-based: User does X at a certain time
    - Sequence: User does A then B then C
    - Activity: When doing X, user often needs Y
    - Conditional: Under conditions X, user does Y
    """
    
    def __init__(self, config: dict = None, db_path: str = None):
        self.config = config or {}
        self.db_path = db_path or "data/patterns.db"
        
        # In-memory pattern storage
        self.patterns: dict[str, Pattern] = {}
        
        # Tracking current activity
        self._command_history: list[dict] = []
        self._activity_history: list[dict] = []
        self._time_patterns: dict[str, list[dict]] = defaultdict(list)  # hour -> actions
        
        # Learning settings
        self._min_occurrences = self.config.get("min_occurrences", 3)
        self._sequence_window = self.config.get("sequence_window_seconds", 300)  # 5 min
        self._confidence_threshold = self.config.get("confidence_threshold", 0.6)
        
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self):
        """Initialize the pattern learner."""
        if self._initialized:
            return
        
        # Create database
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        
        await self._init_database()
        await self._load_patterns()
        
        self._initialized = True
        logger.info(f"Pattern learner initialized with {len(self.patterns)} patterns")
    
    async def _init_database(self):
        """Initialize SQLite database."""
        def init():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    pattern_id TEXT PRIMARY KEY,
                    pattern_type TEXT,
                    trigger_json TEXT,
                    action_json TEXT,
                    confidence REAL,
                    occurrences INTEGER,
                    last_triggered TEXT,
                    created_at TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS command_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    command TEXT,
                    client_id TEXT,
                    hour INTEGER,
                    day_of_week INTEGER
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    activity TEXT,
                    client_id TEXT,
                    duration_seconds INTEGER
                )
            """)
            
            conn.commit()
            conn.close()
        
        await asyncio.get_event_loop().run_in_executor(None, init)
    
    async def _load_patterns(self):
        """Load patterns from database."""
        def load():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM patterns")
            rows = cursor.fetchall()
            
            conn.close()
            return rows
        
        rows = await asyncio.get_event_loop().run_in_executor(None, load)
        
        for row in rows:
            pattern = Pattern(
                pattern_id=row[0],
                pattern_type=row[1],
                trigger=json.loads(row[2]),
                action=json.loads(row[3]),
                confidence=row[4],
                occurrences=row[5],
                last_triggered=datetime.fromisoformat(row[6]) if row[6] else None,
                created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
            )
            self.patterns[pattern.pattern_id] = pattern
    
    async def _save_pattern(self, pattern: Pattern):
        """Save a pattern to database."""
        def save():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO patterns 
                (pattern_id, pattern_type, trigger_json, action_json, confidence, 
                 occurrences, last_triggered, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pattern.pattern_id,
                pattern.pattern_type,
                json.dumps(pattern.trigger),
                json.dumps(pattern.action),
                pattern.confidence,
                pattern.occurrences,
                pattern.last_triggered.isoformat() if pattern.last_triggered else None,
                pattern.created_at.isoformat(),
            ))
            
            conn.commit()
            conn.close()
        
        await asyncio.get_event_loop().run_in_executor(None, save)
    
    async def record_command(
        self,
        command: str,
        client_id: str = None,
        context: dict = None,
    ):
        """Record a command execution for pattern learning."""
        now = datetime.now()
        
        async with self._lock:
            # Add to history
            self._command_history.append({
                "command": command,
                "client_id": client_id,
                "timestamp": now,
                "hour": now.hour,
                "day_of_week": now.weekday(),
                "context": context or {},
            })
            
            # Keep history bounded
            if len(self._command_history) > 1000:
                self._command_history = self._command_history[-500:]
            
            # Record in database
            await self._log_command(command, client_id, now)
            
            # Learn from this command
            await self._learn_time_pattern(command, now)
            await self._learn_sequence_pattern()
    
    async def record_activity(
        self,
        activity: str,
        client_id: str = None,
        duration_seconds: int = 0,
    ):
        """Record a detected activity."""
        now = datetime.now()
        
        async with self._lock:
            self._activity_history.append({
                "activity": activity,
                "client_id": client_id,
                "timestamp": now,
                "duration": duration_seconds,
            })
            
            # Keep history bounded
            if len(self._activity_history) > 500:
                self._activity_history = self._activity_history[-250:]
    
    async def _log_command(self, command: str, client_id: str, timestamp: datetime):
        """Log command to database."""
        def log():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO command_log (timestamp, command, client_id, hour, day_of_week)
                VALUES (?, ?, ?, ?, ?)
            """, (
                timestamp.isoformat(),
                command,
                client_id,
                timestamp.hour,
                timestamp.weekday(),
            ))
            
            conn.commit()
            conn.close()
        
        await asyncio.get_event_loop().run_in_executor(None, log)
    
    async def _learn_time_pattern(self, command: str, timestamp: datetime):
        """Learn time-based patterns."""
        hour = timestamp.hour
        day = timestamp.weekday()
        
        # Track commands by hour
        key = f"{hour}:{day}"
        self._time_patterns[key].append({
            "command": command,
            "timestamp": timestamp,
        })
        
        # Check if this is a recurring pattern
        if len(self._time_patterns[key]) >= self._min_occurrences:
            # Find most common command at this time
            from collections import Counter
            commands = [e["command"] for e in self._time_patterns[key]]
            most_common = Counter(commands).most_common(1)
            
            if most_common:
                cmd, count = most_common[0]
                if count >= self._min_occurrences:
                    # Create or update pattern
                    pattern_id = f"time_{hour}_{day}_{cmd[:20]}"
                    
                    if pattern_id not in self.patterns:
                        pattern = Pattern(
                            pattern_id=pattern_id,
                            pattern_type="time_based",
                            trigger={"hour": hour, "day_of_week": day},
                            action={"command": cmd, "type": "suggest"},
                            confidence=min(0.9, count / 10),
                            occurrences=count,
                        )
                        self.patterns[pattern_id] = pattern
                        await self._save_pattern(pattern)
                        logger.info(f"Learned time pattern: {cmd} at {hour}:00 on day {day}")
                    else:
                        # Update existing
                        pattern = self.patterns[pattern_id]
                        pattern.occurrences = count
                        pattern.confidence = min(0.9, count / 10)
                        await self._save_pattern(pattern)
    
    async def _learn_sequence_pattern(self):
        """Learn command sequence patterns."""
        if len(self._command_history) < 3:
            return
        
        # Get recent commands within time window
        now = datetime.now()
        window_start = now - timedelta(seconds=self._sequence_window)
        
        recent = [
            c["command"] for c in self._command_history
            if c["timestamp"] > window_start
        ]
        
        if len(recent) < 2:
            return
        
        # Look for repeating sequences (simplified)
        # In production, would use more sophisticated sequence mining
        for i in range(len(recent) - 1):
            seq = (recent[i], recent[i + 1])
            pattern_id = f"seq_{hash(seq) % 1000000}"
            
            if pattern_id in self.patterns:
                pattern = self.patterns[pattern_id]
                pattern.occurrences += 1
                pattern.confidence = min(0.9, pattern.occurrences / 10)
                
                if pattern.occurrences >= self._min_occurrences:
                    await self._save_pattern(pattern)
            else:
                pattern = Pattern(
                    pattern_id=pattern_id,
                    pattern_type="sequence",
                    trigger={"after_command": seq[0]},
                    action={"suggest_command": seq[1], "type": "suggest"},
                    confidence=0.3,
                    occurrences=1,
                )
                self.patterns[pattern_id] = pattern
    
    async def get_suggestions(
        self,
        current_context: dict = None,
        recent_command: str = None,
    ) -> list[dict]:
        """
        Get proactive suggestions based on learned patterns.
        
        Args:
            current_context: Current system/activity context
            recent_command: Most recent command (for sequence suggestions)
        
        Returns:
            List of suggestions with confidence scores
        """
        suggestions = []
        now = datetime.now()
        hour = now.hour
        day = now.weekday()
        
        async with self._lock:
            for pattern in self.patterns.values():
                if pattern.confidence < self._confidence_threshold:
                    continue
                
                matches = False
                
                if pattern.pattern_type == "time_based":
                    trigger_hour = pattern.trigger.get("hour")
                    trigger_day = pattern.trigger.get("day_of_week")
                    
                    # Match within an hour window
                    if trigger_hour is not None:
                        if abs(hour - trigger_hour) <= 1:
                            if trigger_day is None or trigger_day == day:
                                matches = True
                
                elif pattern.pattern_type == "sequence":
                    if recent_command:
                        after_cmd = pattern.trigger.get("after_command", "")
                        if after_cmd and after_cmd in recent_command:
                            matches = True
                
                elif pattern.pattern_type == "activity":
                    if current_context:
                        trigger_activity = pattern.trigger.get("activity")
                        if trigger_activity == current_context.get("current_activity"):
                            matches = True
                
                if matches:
                    suggestions.append({
                        "pattern_id": pattern.pattern_id,
                        "type": pattern.pattern_type,
                        "action": pattern.action,
                        "confidence": pattern.confidence,
                        "occurrences": pattern.occurrences,
                    })
        
        # Sort by confidence
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        
        return suggestions[:5]  # Top 5 suggestions
    
    async def provide_feedback(
        self,
        pattern_id: str,
        accepted: bool,
    ):
        """
        Provide feedback on a suggestion.
        
        Args:
            pattern_id: ID of the pattern
            accepted: Whether the user accepted the suggestion
        """
        async with self._lock:
            if pattern_id in self.patterns:
                pattern = self.patterns[pattern_id]
                
                # Adjust confidence based on feedback
                if accepted:
                    pattern.confidence = min(1.0, pattern.confidence + 0.1)
                    pattern.occurrences += 1
                    pattern.last_triggered = datetime.now()
                else:
                    pattern.confidence = max(0.1, pattern.confidence - 0.15)
                
                await self._save_pattern(pattern)
    
    async def get_patterns(self) -> list[Pattern]:
        """Get all learned patterns."""
        return list(self.patterns.values())
    
    async def get_high_confidence_patterns(self) -> list[Pattern]:
        """Get patterns with high confidence."""
        return [
            p for p in self.patterns.values()
            if p.confidence >= self._confidence_threshold
        ]
    
    async def delete_pattern(self, pattern_id: str):
        """Delete a pattern."""
        async with self._lock:
            if pattern_id in self.patterns:
                del self.patterns[pattern_id]
                
                def delete():
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM patterns WHERE pattern_id = ?", (pattern_id,))
                    conn.commit()
                    conn.close()
                
                await asyncio.get_event_loop().run_in_executor(None, delete)
    
    async def clear_all(self):
        """Clear all learned patterns."""
        async with self._lock:
            self.patterns.clear()
            self._command_history.clear()
            self._activity_history.clear()
            self._time_patterns.clear()
            
            def clear():
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM patterns")
                cursor.execute("DELETE FROM command_log")
                cursor.execute("DELETE FROM activity_log")
                conn.commit()
                conn.close()
            
            await asyncio.get_event_loop().run_in_executor(None, clear)
            
            logger.info("Cleared all learned patterns")
