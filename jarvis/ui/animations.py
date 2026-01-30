"""
JARVIS Animations

Visual effects and animations for the JARVIS interface.
"""

from dataclasses import dataclass
from typing import Optional, Callable
import asyncio
import math

from loguru import logger


@dataclass
class AnimationConfig:
    """Animation configuration."""
    duration_ms: int = 300
    easing: str = "ease_out"  # linear, ease_in, ease_out, ease_in_out
    fps: int = 60


class JarvisAnimations:
    """
    Animation utilities for JARVIS visual effects.
    
    Features:
    - Typewriter text effect
    - Fade in/out
    - Pulse glow
    - Waveform animation
    - Particle effects (conceptual)
    """
    
    # Easing functions
    @staticmethod
    def linear(t: float) -> float:
        """Linear interpolation."""
        return t
    
    @staticmethod
    def ease_in(t: float) -> float:
        """Ease in (quad)."""
        return t * t
    
    @staticmethod
    def ease_out(t: float) -> float:
        """Ease out (quad)."""
        return 1 - (1 - t) * (1 - t)
    
    @staticmethod
    def ease_in_out(t: float) -> float:
        """Ease in-out (quad)."""
        if t < 0.5:
            return 2 * t * t
        return 1 - pow(-2 * t + 2, 2) / 2
    
    @staticmethod
    def elastic(t: float) -> float:
        """Elastic bounce effect."""
        if t == 0 or t == 1:
            return t
        return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
    
    def __init__(self, config=None):
        """Initialize animation manager."""
        self.config = config
        self._running_animations = {}
    
    def get_easing_func(self, name: str) -> Callable:
        """Get easing function by name."""
        easings = {
            "linear": self.linear,
            "ease_in": self.ease_in,
            "ease_out": self.ease_out,
            "ease_in_out": self.ease_in_out,
            "elastic": self.elastic,
        }
        return easings.get(name, self.linear)
    
    async def animate_value(
        self,
        start: float,
        end: float,
        duration_ms: int,
        callback: Callable[[float], None],
        easing: str = "ease_out"
    ) -> None:
        """
        Animate a value from start to end.
        
        Args:
            start: Starting value
            end: Ending value
            duration_ms: Duration in milliseconds
            callback: Function called with current value each frame
            easing: Easing function name
        """
        easing_func = self.get_easing_func(easing)
        frames = max(1, duration_ms // 16)  # ~60fps
        
        for i in range(frames + 1):
            t = i / frames
            eased_t = easing_func(t)
            value = start + (end - start) * eased_t
            callback(value)
            await asyncio.sleep(0.016)  # ~60fps
    
    async def typewriter_effect(
        self,
        text: str,
        callback: Callable[[str], None],
        interval_ms: int = 30,
        cursor: str = "▌"
    ) -> None:
        """
        Typewriter text animation.
        
        Args:
            text: Full text to display
            callback: Function called with current displayed text
            interval_ms: Milliseconds between characters
            cursor: Cursor character to show at end
        """
        for i in range(len(text) + 1):
            current_text = text[:i]
            # Add blinking cursor
            if i < len(text):
                callback(current_text + cursor)
            else:
                callback(current_text)
            await asyncio.sleep(interval_ms / 1000)
        
        # Blink cursor a few times at the end
        for _ in range(3):
            callback(text + cursor)
            await asyncio.sleep(0.3)
            callback(text)
            await asyncio.sleep(0.3)
    
    async def fade_in(
        self,
        callback: Callable[[float], None],
        duration_ms: int = 300
    ) -> None:
        """
        Fade in animation (0.0 to 1.0).
        
        Args:
            callback: Function called with opacity value
            duration_ms: Duration in milliseconds
        """
        await self.animate_value(0.0, 1.0, duration_ms, callback, "ease_out")
    
    async def fade_out(
        self,
        callback: Callable[[float], None],
        duration_ms: int = 300
    ) -> None:
        """
        Fade out animation (1.0 to 0.0).
        
        Args:
            callback: Function called with opacity value
            duration_ms: Duration in milliseconds
        """
        await self.animate_value(1.0, 0.0, duration_ms, callback, "ease_in")
    
    async def pulse(
        self,
        callback: Callable[[float], None],
        min_value: float = 0.5,
        max_value: float = 1.0,
        duration_ms: int = 1000,
        count: int = 3
    ) -> None:
        """
        Pulsing animation.
        
        Args:
            callback: Function called with current value
            min_value: Minimum pulse value
            max_value: Maximum pulse value
            duration_ms: Duration of one pulse cycle
            count: Number of pulses (0 for infinite)
        """
        half_duration = duration_ms // 2
        iterations = 0
        
        while count == 0 or iterations < count:
            await self.animate_value(min_value, max_value, half_duration, callback, "ease_in_out")
            await self.animate_value(max_value, min_value, half_duration, callback, "ease_in_out")
            iterations += 1
    
    def generate_waveform(self, audio_levels: list, width: int, height: int) -> list:
        """
        Generate waveform points from audio levels.
        
        Args:
            audio_levels: List of audio levels (0.0 - 1.0)
            width: Width of waveform area
            height: Height of waveform area
            
        Returns:
            List of (x, y) points for the waveform
        """
        if not audio_levels:
            return []
        
        points = []
        bar_width = width / len(audio_levels)
        center_y = height / 2
        
        for i, level in enumerate(audio_levels):
            x = i * bar_width + bar_width / 2
            amplitude = level * center_y * 0.9
            
            # Top and bottom of bar
            points.append({
                "x": x,
                "top": center_y - amplitude,
                "bottom": center_y + amplitude,
                "level": level,
            })
        
        return points
    
    def generate_particle_positions(
        self,
        count: int,
        center_x: float,
        center_y: float,
        frame: int,
        max_radius: float = 100
    ) -> list:
        """
        Generate particle positions for a burst effect.
        
        Args:
            count: Number of particles
            center_x: Burst center X
            center_y: Burst center Y
            frame: Current animation frame (0-60)
            max_radius: Maximum spread radius
            
        Returns:
            List of particle positions and properties
        """
        particles = []
        progress = frame / 60.0  # Normalize to 0-1
        
        for i in range(count):
            angle = (2 * math.pi * i) / count
            radius = max_radius * self.ease_out(progress)
            
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            
            # Fade out
            opacity = 1.0 - progress
            size = 5 * (1.0 - progress * 0.5)
            
            particles.append({
                "x": x,
                "y": y,
                "opacity": opacity,
                "size": size,
            })
        
        return particles
    
    def interpolate_color(
        self,
        color1: tuple,
        color2: tuple,
        t: float
    ) -> tuple:
        """
        Interpolate between two RGB colors.
        
        Args:
            color1: Starting color (r, g, b) 0-255
            color2: Ending color (r, g, b) 0-255
            t: Interpolation factor (0-1)
            
        Returns:
            Interpolated color (r, g, b)
        """
        r = int(color1[0] + (color2[0] - color1[0]) * t)
        g = int(color1[1] + (color2[1] - color1[1]) * t)
        b = int(color1[2] + (color2[2] - color1[2]) * t)
        return (r, g, b)
    
    def hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def rgb_to_hex(self, rgb: tuple) -> str:
        """Convert RGB tuple to hex color."""
        return "#{:02x}{:02x}{:02x}".format(*rgb)


# Terminal-based animations for CLI mode
class TerminalAnimations:
    """Animations for terminal/CLI output."""
    
    SPINNERS = {
        "dots": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "line": ["-", "\\", "|", "/"],
        "arc": ["◜", "◠", "◝", "◞", "◡", "◟"],
        "circle": ["◐", "◓", "◑", "◒"],
        "pulse": ["█", "▓", "▒", "░", "▒", "▓"],
    }
    
    @classmethod 
    async def spinner(
        cls,
        callback: Callable[[str], None],
        style: str = "dots",
        duration: float = 0
    ) -> None:
        """
        Show animated spinner.
        
        Args:
            callback: Function to update display
            style: Spinner style name
            duration: Duration in seconds (0 for until cancelled)
        """
        frames = cls.SPINNERS.get(style, cls.SPINNERS["dots"])
        frame_time = 0.1
        elapsed = 0
        i = 0
        
        while duration == 0 or elapsed < duration:
            callback(frames[i % len(frames)])
            await asyncio.sleep(frame_time)
            elapsed += frame_time
            i += 1
    
    @classmethod
    async def progress_bar(
        cls,
        callback: Callable[[str], None],
        total: int,
        current: int,
        width: int = 30
    ) -> None:
        """
        Show progress bar.
        
        Args:
            callback: Function to update display
            total: Total value
            current: Current value
            width: Bar width in characters
        """
        progress = current / total if total > 0 else 0
        filled = int(width * progress)
        empty = width - filled
        
        bar = "█" * filled + "░" * empty
        percentage = int(progress * 100)
        
        callback(f"[{bar}] {percentage}%")
