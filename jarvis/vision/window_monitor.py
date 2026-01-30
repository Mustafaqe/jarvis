"""
JARVIS Window Monitor

Monitors active windows, tracks focus changes, and detects notifications.
Linux X11/Wayland support with fallbacks.
"""

import asyncio
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, Callable, List
from enum import Enum

from loguru import logger


class WindowSystem(Enum):
    """Window system type."""
    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"


@dataclass
class WindowInfo:
    """Information about a window."""
    id: str
    title: str
    class_name: str
    pid: int
    x: int
    y: int
    width: int
    height: int
    is_active: bool
    desktop: int
    
    @property
    def geometry(self) -> tuple:
        """Get (x, y, width, height) tuple."""
        return (self.x, self.y, self.width, self.height)


@dataclass
class Notification:
    """A detected notification."""
    app: str
    title: str
    body: str
    timestamp: float
    urgency: str  # low, normal, critical


class WindowMonitor:
    """
    Monitor windows and track focus changes.
    
    Features:
    - Get active window info
    - List all windows
    - Watch for focus changes
    - Track window history
    """
    
    def __init__(self, config):
        """
        Initialize window monitor.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self._window_system = self._detect_window_system()
        self._callbacks: List[Callable] = []
        self._watching = False
        self._watch_task = None
        self._last_active_window: Optional[WindowInfo] = None
        self._window_history: List[WindowInfo] = []
        self._max_history = 20
    
    def _detect_window_system(self) -> WindowSystem:
        """Detect the window system in use."""
        import os
        
        # Check for Wayland
        if os.environ.get("WAYLAND_DISPLAY"):
            return WindowSystem.WAYLAND
        
        # Check for X11
        if os.environ.get("DISPLAY"):
            return WindowSystem.X11
        
        return WindowSystem.UNKNOWN
    
    def get_active_window(self) -> Optional[WindowInfo]:
        """
        Get the currently active/focused window.
        
        Returns:
            WindowInfo or None if cannot determine
        """
        if self._window_system == WindowSystem.X11:
            return self._get_active_window_x11()
        elif self._window_system == WindowSystem.WAYLAND:
            return self._get_active_window_wayland()
        else:
            logger.warning("Unknown window system, cannot get active window")
            return None
    
    def _get_active_window_x11(self) -> Optional[WindowInfo]:
        """Get active window using X11 tools."""
        try:
            # Get active window ID
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            window_id = result.stdout.strip()
            
            # Get window name
            name_result = subprocess.run(
                ["xdotool", "getwindowname", window_id],
                capture_output=True,
                text=True,
                timeout=5
            )
            title = name_result.stdout.strip() if name_result.returncode == 0 else ""
            
            # Get window geometry
            geom_result = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", window_id],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            geometry = {}
            if geom_result.returncode == 0:
                for line in geom_result.stdout.strip().split("\n"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        geometry[key] = value
            
            # Get window class
            class_result = subprocess.run(
                ["xprop", "-id", window_id, "WM_CLASS"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            class_name = ""
            if class_result.returncode == 0 and "=" in class_result.stdout:
                class_name = class_result.stdout.split("=")[-1].strip().strip('"')
            
            # Get PID
            pid_result = subprocess.run(
                ["xdotool", "getwindowpid", window_id],
                capture_output=True,
                text=True,
                timeout=5
            )
            pid = int(pid_result.stdout.strip()) if pid_result.returncode == 0 else 0
            
            return WindowInfo(
                id=window_id,
                title=title,
                class_name=class_name,
                pid=pid,
                x=int(geometry.get("X", 0)),
                y=int(geometry.get("Y", 0)),
                width=int(geometry.get("WIDTH", 0)),
                height=int(geometry.get("HEIGHT", 0)),
                is_active=True,
                desktop=int(geometry.get("SCREEN", 0))
            )
            
        except FileNotFoundError:
            logger.warning("xdotool not installed. Install with: sudo apt install xdotool")
            return None
        except Exception as e:
            logger.error(f"Failed to get active window: {e}")
            return None
    
    def _get_active_window_wayland(self) -> Optional[WindowInfo]:
        """Get active window on Wayland (limited support)."""
        # Wayland has stricter security, so we have limited options
        # Try using wlrctl if available (for wlroots compositors)
        try:
            # Try gdbus for GNOME
            result = subprocess.run(
                [
                    "gdbus", "call", "--session",
                    "--dest", "org.gnome.Shell",
                    "--object-path", "/org/gnome/Shell",
                    "--method", "org.gnome.Shell.Eval",
                    "global.display.focus_window.get_title()"
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Parse the output
                output = result.stdout.strip()
                if "'" in output:
                    title = output.split("'")[1]
                    return WindowInfo(
                        id="unknown",
                        title=title,
                        class_name="",
                        pid=0,
                        x=0,
                        y=0,
                        width=0,
                        height=0,
                        is_active=True,
                        desktop=0
                    )
            
            return None
            
        except Exception as e:
            logger.debug(f"Wayland window detection failed: {e}")
            return None
    
    async def get_active_window_async(self) -> Optional[WindowInfo]:
        """Async wrapper for get_active_window."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_active_window)
    
    def list_windows(self) -> List[WindowInfo]:
        """
        List all open windows.
        
        Returns:
            List of WindowInfo objects
        """
        if self._window_system != WindowSystem.X11:
            logger.warning("Window listing only available on X11")
            return []
        
        try:
            result = subprocess.run(
                ["wmctrl", "-l", "-G", "-p"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []
            
            windows = []
            active_window = self.get_active_window()
            active_id = active_window.id if active_window else ""
            
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                
                parts = line.split(None, 8)
                if len(parts) < 8:
                    continue
                
                window_id = parts[0]
                desktop = int(parts[1])
                pid = int(parts[2])
                x = int(parts[3])
                y = int(parts[4])
                width = int(parts[5])
                height = int(parts[6])
                title = parts[7] if len(parts) > 7 else ""
                
                windows.append(WindowInfo(
                    id=window_id,
                    title=title,
                    class_name="",
                    pid=pid,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    is_active=(window_id == active_id),
                    desktop=desktop
                ))
            
            return windows
            
        except FileNotFoundError:
            logger.warning("wmctrl not installed. Install with: sudo apt install wmctrl")
            return []
        except Exception as e:
            logger.error(f"Failed to list windows: {e}")
            return []
    
    async def list_windows_async(self) -> List[WindowInfo]:
        """Async wrapper for list_windows."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.list_windows)
    
    def find_window(self, title: str) -> Optional[WindowInfo]:
        """
        Find a window by title (partial match).
        
        Args:
            title: Window title to search for
            
        Returns:
            WindowInfo or None
        """
        windows = self.list_windows()
        title_lower = title.lower()
        
        for window in windows:
            if title_lower in window.title.lower():
                return window
        
        return None
    
    def start_watching(self, callback: Callable[[WindowInfo, WindowInfo], None]) -> None:
        """
        Start watching for window focus changes.
        
        Args:
            callback: Function called with (old_window, new_window) on change
        """
        self._callbacks.append(callback)
        
        if not self._watching:
            self._watching = True
            self._watch_task = asyncio.create_task(self._watch_loop())
    
    def stop_watching(self) -> None:
        """Stop watching for window changes."""
        self._watching = False
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None
        self._callbacks.clear()
    
    async def _watch_loop(self) -> None:
        """Main watch loop."""
        while self._watching:
            try:
                current = await self.get_active_window_async()
                
                if current and (
                    not self._last_active_window or
                    current.id != self._last_active_window.id
                ):
                    old = self._last_active_window
                    self._last_active_window = current
                    
                    # Add to history
                    self._window_history.append(current)
                    if len(self._window_history) > self._max_history:
                        self._window_history.pop(0)
                    
                    # Notify callbacks
                    for callback in self._callbacks:
                        try:
                            callback(old, current)
                        except Exception as e:
                            logger.error(f"Watch callback error: {e}")
                
                await asyncio.sleep(0.5)  # Poll every 500ms
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watch loop error: {e}")
                await asyncio.sleep(1)
    
    def get_window_history(self) -> List[WindowInfo]:
        """Get recent window focus history."""
        return list(self._window_history)
    
    def get_recent_apps(self) -> List[str]:
        """Get list of recently used applications."""
        seen = set()
        apps = []
        
        for window in reversed(self._window_history):
            app = window.class_name or window.title.split(" - ")[-1]
            if app and app not in seen:
                seen.add(app)
                apps.append(app)
        
        return apps[:10]  # Last 10 unique apps
    
    def detect_notifications(self) -> List[Notification]:
        """
        Detect notifications using dbus (Linux).
        
        Note: This requires monitoring dbus which needs special setup.
        This is a simplified version that checks for notification-related windows.
        
        Returns:
            List of detected notifications
        """
        # This is a simplified approach - for full notification monitoring,
        # you would need to subscribe to org.freedesktop.Notifications on dbus
        notifications = []
        
        windows = self.list_windows()
        notification_keywords = ["notification", "notify", "alert", "popup"]
        
        for window in windows:
            title_lower = window.title.lower()
            class_lower = window.class_name.lower()
            
            if any(kw in title_lower or kw in class_lower for kw in notification_keywords):
                notifications.append(Notification(
                    app=window.class_name or "Unknown",
                    title=window.title,
                    body="",
                    timestamp=time.time(),
                    urgency="normal"
                ))
        
        return notifications
    
    def focus_window(self, window: WindowInfo) -> bool:
        """
        Focus/activate a specific window.
        
        Args:
            window: Window to focus
            
        Returns:
            True if successful
        """
        if self._window_system != WindowSystem.X11:
            logger.warning("Window focusing only available on X11")
            return False
        
        try:
            result = subprocess.run(
                ["wmctrl", "-i", "-a", window.id],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to focus window: {e}")
            return False
    
    def close_window(self, window: WindowInfo) -> bool:
        """
        Close a specific window.
        
        Args:
            window: Window to close
            
        Returns:
            True if successful
        """
        if self._window_system != WindowSystem.X11:
            logger.warning("Window closing only available on X11")
            return False
        
        try:
            result = subprocess.run(
                ["wmctrl", "-i", "-c", window.id],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to close window: {e}")
            return False
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        self.stop_watching()
