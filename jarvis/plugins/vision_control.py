"""
JARVIS Vision Control Plugin

Provides commands for screen capture, OCR, and image analysis.
"""

import asyncio
from typing import Any

from loguru import logger

from jarvis.plugins.base import Plugin, PluginInfo


class VisionControlPlugin(Plugin):
    """
    Plugin for vision-related commands.
    
    Capabilities:
    - Capture and analyze screen content
    - Read text from screen using OCR
    - Answer questions about what's visible
    - Detect errors and notifications
    """
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="Vision Control",
            description="Screen capture, OCR, and image analysis",
            version="1.0.0",
            author="JARVIS",
            enabled=True,
            commands=[
                "screenshot",
                "capture",
                "read screen",
                "what's on screen",
                "analyze screen",
                "read error",
                "find text",
            ],
            intents=[
                "screen",
                "display",
                "see",
                "look",
                "show",
                "visible",
                "monitor",
            ]
        )
    
    async def initialize(self) -> None:
        """Initialize vision components."""
        await super().initialize()
        
        self._screen_capture = None
        self._ocr = None
        self._analyzer = None
        self._window_monitor = None
        
        # Lazy load components
        self._initialized_vision = False
    
    def _ensure_vision_initialized(self) -> None:
        """Lazy initialize vision components."""
        if self._initialized_vision:
            return
        
        try:
            from jarvis.vision.screen_capture import ScreenCapture
            from jarvis.vision.ocr import OCREngine
            from jarvis.vision.image_analysis import ImageAnalyzer
            from jarvis.vision.window_monitor import WindowMonitor
            
            self._screen_capture = ScreenCapture(self.config)
            self._ocr = OCREngine(self.config)
            self._analyzer = ImageAnalyzer(self.config)
            self._window_monitor = WindowMonitor(self.config)
            
            self._initialized_vision = True
            logger.info("Vision components initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize vision: {e}")
    
    async def execute(self, command: str, params: dict[str, Any]) -> str:
        """Execute vision commands."""
        command_lower = command.lower()
        
        # Parse command
        if any(phrase in command_lower for phrase in [
            "what's on screen", "what is on screen", "what do you see",
            "look at screen", "see my screen", "analyze screen"
        ]):
            return await self._analyze_screen()
        
        elif any(phrase in command_lower for phrase in [
            "read screen", "read text", "ocr", "extract text"
        ]):
            return await self._read_screen_text()
        
        elif any(phrase in command_lower for phrase in [
            "read error", "what error", "explain error", "error message"
        ]):
            return await self._read_error()
        
        elif any(phrase in command_lower for phrase in [
            "screenshot", "capture screen", "take screenshot"
        ]):
            return await self._take_screenshot()
        
        elif any(phrase in command_lower for phrase in [
            "active window", "current window", "what window"
        ]):
            return await self._get_active_window()
        
        elif any(phrase in command_lower for phrase in [
            "list windows", "open windows", "what windows"
        ]):
            return await self._list_windows()
        
        elif "find text" in command_lower or "find on screen" in command_lower:
            # Extract the text to find
            for phrase in ["find text", "find on screen"]:
                if phrase in command_lower:
                    target = command_lower.split(phrase)[-1].strip()
                    target = target.strip('"').strip("'")
                    if target:
                        return await self._find_text(target)
            return "Please specify what text to find."
        
        elif any(phrase in command_lower for phrase in [
            "describe", "what is this", "analyze"
        ]):
            return await self._analyze_screen()
        
        else:
            # Default: analyze screen
            return await self._analyze_screen()
    
    async def _analyze_screen(self) -> str:
        """Capture and analyze the current screen."""
        self._ensure_vision_initialized()
        
        if not self._analyzer:
            return "Vision system not available. Please check dependencies."
        
        try:
            # Capture screen
            capture = await self._screen_capture.capture_screen_async(1)  # Primary monitor
            
            if not capture.image:
                return "Failed to capture screen."
            
            # Analyze with Claude Vision
            result = await self._analyzer.read_screen(capture.image)
            
            return f"Here's what I see on your screen:\n\n{result}"
            
        except Exception as e:
            logger.error(f"Screen analysis failed: {e}")
            return f"Failed to analyze screen: {e}"
    
    async def _read_screen_text(self) -> str:
        """Read text from screen using OCR."""
        self._ensure_vision_initialized()
        
        if not self._ocr:
            return "OCR not available. Install tesseract or easyocr."
        
        try:
            # Capture screen
            capture = await self._screen_capture.capture_screen_async(1)
            
            if not capture.image:
                return "Failed to capture screen."
            
            # Extract text
            result = await self._ocr.extract_text_async(capture.image)
            
            if not result.strip():
                return "No text detected on screen."
            
            # Truncate if too long
            if len(result) > 2000:
                result = result[:2000] + "\n\n[Text truncated...]"
            
            return f"Text detected on screen:\n\n{result}"
            
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return f"Failed to read screen text: {e}"
    
    async def _read_error(self) -> str:
        """Read and explain error messages on screen."""
        self._ensure_vision_initialized()
        
        if not self._analyzer:
            return "Vision system not available."
        
        try:
            capture = await self._screen_capture.capture_screen_async(1)
            
            if not capture.image:
                return "Failed to capture screen."
            
            result = await self._analyzer.read_error(capture.image)
            
            return result
            
        except Exception as e:
            logger.error(f"Error reading failed: {e}")
            return f"Failed to analyze error: {e}"
    
    async def _take_screenshot(self) -> str:
        """Take and save a screenshot."""
        self._ensure_vision_initialized()
        
        if not self._screen_capture:
            return "Screen capture not available."
        
        try:
            import time
            from pathlib import Path
            
            capture = await self._screen_capture.capture_screen_async(1)
            
            if not capture.image:
                return "Failed to capture screen."
            
            # Save to data directory
            data_dir = Path(self.config.get("core.data_dir", "data"))
            screenshots_dir = data_dir / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            capture.save(filepath)
            
            return f"Screenshot saved to: {filepath}"
            
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return f"Failed to take screenshot: {e}"
    
    async def _get_active_window(self) -> str:
        """Get information about the active window."""
        self._ensure_vision_initialized()
        
        if not self._window_monitor:
            return "Window monitor not available."
        
        try:
            window = await self._window_monitor.get_active_window_async()
            
            if not window:
                return "Could not determine active window."
            
            return (
                f"Active window:\n"
                f"- Title: {window.title}\n"
                f"- Application: {window.class_name or 'Unknown'}\n"
                f"- Size: {window.width}x{window.height}\n"
                f"- Position: ({window.x}, {window.y})"
            )
            
        except Exception as e:
            logger.error(f"Failed to get active window: {e}")
            return f"Failed to get active window: {e}"
    
    async def _list_windows(self) -> str:
        """List all open windows."""
        self._ensure_vision_initialized()
        
        if not self._window_monitor:
            return "Window monitor not available."
        
        try:
            windows = await self._window_monitor.list_windows_async()
            
            if not windows:
                return "No windows found or window listing not available."
            
            lines = ["Open windows:"]
            for i, w in enumerate(windows[:15], 1):  # Limit to 15
                active = " (active)" if w.is_active else ""
                lines.append(f"{i}. {w.title[:50]}{active}")
            
            if len(windows) > 15:
                lines.append(f"... and {len(windows) - 15} more windows")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Failed to list windows: {e}")
            return f"Failed to list windows: {e}"
    
    async def _find_text(self, target: str) -> str:
        """Find specific text on screen."""
        self._ensure_vision_initialized()
        
        if not self._analyzer:
            return "Vision system not available."
        
        try:
            capture = await self._screen_capture.capture_screen_async(1)
            
            if not capture.image:
                return "Failed to capture screen."
            
            result = await self._analyzer.find_text(capture.image, target)
            
            return result
            
        except Exception as e:
            logger.error(f"Find text failed: {e}")
            return f"Failed to find text: {e}"
    
    async def shutdown(self) -> None:
        """Cleanup vision resources."""
        if self._screen_capture:
            self._screen_capture.shutdown()
        if self._ocr:
            self._ocr.shutdown()
        if self._analyzer:
            self._analyzer.shutdown()
        if self._window_monitor:
            self._window_monitor.shutdown()
        
        await super().shutdown()
