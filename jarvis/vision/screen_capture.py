"""
JARVIS Screen Capture

Captures screen content using the mss library for fast, cross-platform screenshots.
Supports full screen, specific monitors, windows, and regions.
"""

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import base64

from loguru import logger

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    logger.warning("mss not installed. Install with: pip install mss")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL not installed. Install with: pip install Pillow")


@dataclass
class CaptureResult:
    """Result of a screen capture operation."""
    image: Optional["Image.Image"]
    width: int
    height: int
    monitor: int
    timestamp: float
    
    def to_bytes(self, format: str = "PNG") -> bytes:
        """Convert image to bytes."""
        if self.image is None:
            return b""
        buffer = io.BytesIO()
        self.image.save(buffer, format=format)
        return buffer.getvalue()
    
    def to_base64(self, format: str = "PNG") -> str:
        """Convert image to base64 string."""
        data = self.to_bytes(format)
        return base64.b64encode(data).decode("utf-8")
    
    def save(self, path: str | Path, format: str = "PNG") -> bool:
        """Save image to file."""
        if self.image is None:
            return False
        try:
            self.image.save(str(path), format=format)
            return True
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            return False


class ScreenCapture:
    """
    Screen capture using mss library.
    
    Features:
    - Fast screen capture
    - Multi-monitor support
    - Region capture
    - Window capture (Linux X11)
    """
    
    def __init__(self, config):
        """
        Initialize screen capture.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self._sct = None
    
    def _get_sct(self) -> "mss.mss":
        """Get or create mss instance."""
        if not MSS_AVAILABLE:
            raise RuntimeError("mss library not available. Install with: pip install mss")
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct
    
    def get_monitors(self) -> list[dict]:
        """
        Get list of available monitors.
        
        Returns:
            List of monitor info dicts with left, top, width, height
        """
        sct = self._get_sct()
        monitors = []
        for i, mon in enumerate(sct.monitors):
            monitors.append({
                "index": i,
                "left": mon["left"],
                "top": mon["top"],
                "width": mon["width"],
                "height": mon["height"],
            })
        return monitors
    
    def capture_screen(self, monitor: int = 0) -> CaptureResult:
        """
        Capture a full screen.
        
        Args:
            monitor: Monitor index (0 = all monitors combined, 1+ = specific monitor)
            
        Returns:
            CaptureResult with the captured image
        """
        import time
        
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available. Install with: pip install Pillow")
        
        sct = self._get_sct()
        
        try:
            if monitor < len(sct.monitors):
                mon = sct.monitors[monitor]
            else:
                mon = sct.monitors[0]  # Fallback to all monitors
            
            # Capture the screen
            sct_img = sct.grab(mon)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            return CaptureResult(
                image=img,
                width=sct_img.width,
                height=sct_img.height,
                monitor=monitor,
                timestamp=time.time(),
            )
            
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return CaptureResult(
                image=None,
                width=0,
                height=0,
                monitor=monitor,
                timestamp=time.time(),
            )
    
    async def capture_screen_async(self, monitor: int = 0) -> CaptureResult:
        """Async wrapper for capture_screen."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.capture_screen, monitor)
    
    def capture_region(
        self,
        left: int,
        top: int,
        width: int,
        height: int
    ) -> CaptureResult:
        """
        Capture a specific region of the screen.
        
        Args:
            left: X coordinate of top-left corner
            top: Y coordinate of top-left corner
            width: Width of region
            height: Height of region
            
        Returns:
            CaptureResult with the captured image
        """
        import time
        
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available")
        
        sct = self._get_sct()
        
        try:
            region = {
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
            
            sct_img = sct.grab(region)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            return CaptureResult(
                image=img,
                width=width,
                height=height,
                monitor=0,
                timestamp=time.time(),
            )
            
        except Exception as e:
            logger.error(f"Region capture failed: {e}")
            return CaptureResult(
                image=None,
                width=0,
                height=0,
                monitor=0,
                timestamp=time.time(),
            )
    
    async def capture_region_async(
        self,
        left: int,
        top: int,
        width: int,
        height: int
    ) -> CaptureResult:
        """Async wrapper for capture_region."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.capture_region, left, top, width, height
        )
    
    def capture_window(self, window_title: str) -> Optional[CaptureResult]:
        """
        Capture a specific window by title (Linux X11 only).
        
        Args:
            window_title: Title of window to capture (partial match)
            
        Returns:
            CaptureResult or None if window not found
        """
        import time
        
        try:
            import subprocess
            
            # Use wmctrl to find window geometry
            result = subprocess.run(
                ["wmctrl", "-l", "-G"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.warning("wmctrl not available, cannot capture by window title")
                return None
            
            # Parse output and find matching window
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                
                parts = line.split(None, 8)
                if len(parts) < 8:
                    continue
                
                title = parts[-1] if len(parts) > 8 else ""
                
                if window_title.lower() in title.lower():
                    # Found it - get geometry
                    x = int(parts[2])
                    y = int(parts[3])
                    width = int(parts[4])
                    height = int(parts[5])
                    
                    # Capture the region
                    return self.capture_region(x, y, width, height)
            
            logger.warning(f"Window not found: {window_title}")
            return None
            
        except FileNotFoundError:
            logger.warning("wmctrl not installed. Install with: sudo apt install wmctrl")
            return None
        except Exception as e:
            logger.error(f"Window capture failed: {e}")
            return None
    
    async def capture_window_async(self, window_title: str) -> Optional[CaptureResult]:
        """Async wrapper for capture_window."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.capture_window, window_title)
    
    def capture_active_window(self) -> Optional[CaptureResult]:
        """
        Capture the currently active/focused window (Linux X11).
        
        Returns:
            CaptureResult or None if failed
        """
        import time
        
        try:
            import subprocess
            
            # Get active window ID
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowgeometry", "--shell"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.warning("xdotool failed, cannot capture active window")
                return None
            
            # Parse geometry
            geometry = {}
            for line in result.stdout.strip().split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    geometry[key] = int(value)
            
            x = geometry.get("X", 0)
            y = geometry.get("Y", 0)
            width = geometry.get("WIDTH", 800)
            height = geometry.get("HEIGHT", 600)
            
            return self.capture_region(x, y, width, height)
            
        except FileNotFoundError:
            logger.warning("xdotool not installed. Install with: sudo apt install xdotool")
            return None
        except Exception as e:
            logger.error(f"Active window capture failed: {e}")
            return None
    
    async def capture_active_window_async(self) -> Optional[CaptureResult]:
        """Async wrapper for capture_active_window."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.capture_active_window)
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        if self._sct:
            self._sct.close()
            self._sct = None
