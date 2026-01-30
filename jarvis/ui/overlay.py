"""
JARVIS Transparent Overlay

Creates a transparent, click-through overlay for displaying JARVIS responses
with Iron Man-style visual effects.
"""

import asyncio
import sys
import threading
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum

from loguru import logger

# Try to import PyQt6, fallback to PyQt5
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, 
        QVBoxLayout, QHBoxLayout, QFrame, QGraphicsOpacityEffect
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QPropertyAnimation, QEasingCurve, 
        pyqtSignal, QObject, QThread, QPoint, QSize
    )
    from PyQt6.QtGui import (
        QFont, QColor, QPainter, QPen, QBrush, 
        QLinearGradient, QScreen, QPainterPath
    )
    PYQT_AVAILABLE = True
    PYQT_VERSION = 6
except ImportError:
    try:
        from PyQt5.QtWidgets import (
            QApplication, QMainWindow, QWidget, QLabel,
            QVBoxLayout, QHBoxLayout, QFrame, QGraphicsOpacityEffect
        )
        from PyQt5.QtCore import (
            Qt, QTimer, QPropertyAnimation, QEasingCurve,
            pyqtSignal, QObject, QThread, QPoint, QSize
        )
        from PyQt5.QtGui import (
            QFont, QColor, QPainter, QPen, QBrush,
            QLinearGradient, QScreen, QPainterPath
        )
        PYQT_AVAILABLE = True
        PYQT_VERSION = 5
    except ImportError:
        PYQT_AVAILABLE = False
        PYQT_VERSION = 0
        logger.warning("PyQt not available. Install with: pip install PyQt6")


class JarvisState(Enum):
    """JARVIS visual state."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


@dataclass
class OverlayTheme:
    """Theme configuration for overlay."""
    primary_color: str = "#00D4FF"  # Cyan blue
    secondary_color: str = "#0066CC"  # Darker blue
    background_color: str = "#1A1A2E"  # Dark background
    text_color: str = "#FFFFFF"
    accent_color: str = "#00FF88"  # Green accent
    font_family: str = "Roboto"
    font_size: int = 14


# Predefined themes
THEMES = {
    "jarvis": OverlayTheme(
        primary_color="#00D4FF",
        secondary_color="#0066CC",
        background_color="#0A0A1A",
        text_color="#FFFFFF",
        accent_color="#00FF88",
    ),
    "friday": OverlayTheme(
        primary_color="#FF6B6B",
        secondary_color="#CC3366",
        background_color="#1A0A0A",
        text_color="#FFFFFF",
        accent_color="#FFD93D",
    ),
    "minimal": OverlayTheme(
        primary_color="#FFFFFF",
        secondary_color="#CCCCCC",
        background_color="#000000",
        text_color="#FFFFFF",
        accent_color="#00FF00",
    ),
    "dark": OverlayTheme(
        primary_color="#6C5CE7",
        secondary_color="#A29BFE",
        background_color="#2D3436",
        text_color="#FFFFFF",
        accent_color="#00CEC9",
    ),
}


if PYQT_AVAILABLE:
    
    class OverlaySignals(QObject):
        """Signals for thread-safe overlay updates."""
        show_response = pyqtSignal(str)
        show_notification = pyqtSignal(str, str)
        set_state = pyqtSignal(str)
        hide_overlay = pyqtSignal()
        update_waveform = pyqtSignal(list)
    
    
    class GlowLabel(QLabel):
        """Label with glow effect."""
        
        def __init__(self, text="", parent=None, color="#00D4FF"):
            super().__init__(text, parent)
            self.glow_color = QColor(color)
            self.glow_radius = 10
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Draw glow
            for i in range(self.glow_radius, 0, -2):
                alpha = int(50 * (1 - i / self.glow_radius))
                glow = QColor(self.glow_color)
                glow.setAlpha(alpha)
                painter.setPen(QPen(glow, i * 2))
                painter.drawText(self.rect(), self.alignment(), self.text())
            
            # Draw text
            painter.setPen(QPen(QColor(self.glow_color), 1))
            painter.drawText(self.rect(), self.alignment(), self.text())
    
    
    class WaveformWidget(QWidget):
        """Audio waveform visualization."""
        
        def __init__(self, parent=None, color="#00D4FF"):
            super().__init__(parent)
            self.color = QColor(color)
            self.levels = [0.0] * 20
            self.setMinimumHeight(30)
        
        def update_levels(self, levels: list):
            """Update waveform levels."""
            self.levels = levels[-20:] if len(levels) > 20 else levels
            while len(self.levels) < 20:
                self.levels.append(0.0)
            self.update()
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            bar_width = self.width() // len(self.levels)
            spacing = 2
            
            for i, level in enumerate(self.levels):
                bar_height = max(2, int(level * self.height()))
                x = i * bar_width + spacing
                y = (self.height() - bar_height) // 2
                
                # Gradient color based on level
                alpha = int(100 + 155 * level)
                color = QColor(self.color)
                color.setAlpha(alpha)
                
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(
                    x, y, bar_width - spacing * 2, bar_height, 2, 2
                )
    
    
    class StatusIndicator(QWidget):
        """Animated status indicator (listening, processing, etc)."""
        
        def __init__(self, parent=None, color="#00D4FF"):
            super().__init__(parent)
            self.color = QColor(color)
            self.state = JarvisState.IDLE
            self.animation_frame = 0
            self.setFixedSize(100, 100)
            
            # Animation timer
            self.timer = QTimer()
            self.timer.timeout.connect(self._animate)
            self.timer.start(50)
        
        def set_state(self, state: JarvisState):
            """Set the current state."""
            self.state = state
            self.update()
        
        def _animate(self):
            """Update animation frame."""
            self.animation_frame = (self.animation_frame + 1) % 60
            self.update()
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            center = self.rect().center()
            
            if self.state == JarvisState.IDLE:
                # Small static dot
                painter.setBrush(QBrush(self.color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(center, 5, 5)
                
            elif self.state == JarvisState.LISTENING:
                # Pulsing circles
                import math
                for i in range(3):
                    offset = (self.animation_frame + i * 20) % 60
                    radius = 10 + offset // 2
                    alpha = int(255 * (1 - offset / 60))
                    color = QColor(self.color)
                    color.setAlpha(alpha)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(color, 2))
                    painter.drawEllipse(center, radius, radius)
                
            elif self.state == JarvisState.PROCESSING:
                # Spinning arc
                import math
                start_angle = self.animation_frame * 12 * 16
                span_angle = 90 * 16
                painter.setPen(QPen(self.color, 3))
                painter.drawArc(
                    center.x() - 15, center.y() - 15, 30, 30,
                    start_angle, span_angle
                )
                
            elif self.state == JarvisState.SPEAKING:
                # Waveform-like pattern
                import math
                painter.setPen(QPen(self.color, 2))
                for i in range(-3, 4):
                    height = 10 + 8 * math.sin((self.animation_frame + i * 5) * 0.2)
                    x = center.x() + i * 8
                    painter.drawLine(x, center.y() - int(height), x, center.y() + int(height))
    
    
    class JarvisOverlayWindow(QMainWindow):
        """Main transparent overlay window."""
        
        def __init__(self, theme: OverlayTheme = None, position: str = "top-right"):
            super().__init__()
            
            self.theme = theme or THEMES["jarvis"]
            self.position = position
            self.current_state = JarvisState.IDLE
            
            self._setup_window()
            self._setup_ui()
            self._setup_animations()
        
        def _setup_window(self):
            """Configure window properties."""
            # Frameless, translucent, always on top
            flags = (
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            
            # Make click-through on X11
            if sys.platform == "linux":
                try:
                    self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                except:
                    pass
            
            # Set size and position
            self.setFixedWidth(400)
            self.setMinimumHeight(100)
            self.setMaximumHeight(500)
            
            self._update_position()
        
        def _update_position(self):
            """Position the overlay on screen."""
            screen = QApplication.primaryScreen()
            if screen:
                geometry = screen.availableGeometry()
                
                if self.position == "top-right":
                    x = geometry.right() - self.width() - 20
                    y = geometry.top() + 20
                elif self.position == "top-left":
                    x = geometry.left() + 20
                    y = geometry.top() + 20
                elif self.position == "bottom-right":
                    x = geometry.right() - self.width() - 20
                    y = geometry.bottom() - self.height() - 20
                elif self.position == "bottom-left":
                    x = geometry.left() + 20
                    y = geometry.bottom() - self.height() - 20
                else:  # center
                    x = (geometry.width() - self.width()) // 2
                    y = geometry.top() + 100
                
                self.move(x, y)
        
        def _setup_ui(self):
            """Setup the UI components."""
            # Central widget
            central = QWidget()
            self.setCentralWidget(central)
            
            # Main layout
            layout = QVBoxLayout(central)
            layout.setContentsMargins(15, 15, 15, 15)
            layout.setSpacing(10)
            
            # Container with background
            self.container = QFrame()
            self.container.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(10, 10, 26, 230);
                    border-radius: 15px;
                    border: 1px solid {self.theme.primary_color};
                }}
            """)
            
            container_layout = QVBoxLayout(self.container)
            container_layout.setContentsMargins(15, 15, 15, 15)
            container_layout.setSpacing(10)
            
            # Header with status
            header = QHBoxLayout()
            
            # JARVIS title
            title = QLabel("JARVIS")
            title.setStyleSheet(f"""
                QLabel {{
                    color: {self.theme.primary_color};
                    font-family: {self.theme.font_family};
                    font-size: 18px;
                    font-weight: bold;
                }}
            """)
            header.addWidget(title)
            
            header.addStretch()
            
            # Status indicator
            self.status_indicator = StatusIndicator(color=self.theme.primary_color)
            self.status_indicator.setFixedSize(40, 40)
            header.addWidget(self.status_indicator)
            
            container_layout.addLayout(header)
            
            # Response text
            self.response_label = QLabel("")
            self.response_label.setWordWrap(True)
            self.response_label.setStyleSheet(f"""
                QLabel {{
                    color: {self.theme.text_color};
                    font-family: {self.theme.font_family};
                    font-size: {self.theme.font_size}px;
                    padding: 5px;
                }}
            """)
            container_layout.addWidget(self.response_label)
            
            # Waveform
            self.waveform = WaveformWidget(color=self.theme.primary_color)
            self.waveform.setVisible(False)
            container_layout.addWidget(self.waveform)
            
            # Status text
            self.status_label = QLabel("Ready")
            self.status_label.setStyleSheet(f"""
                QLabel {{
                    color: {self.theme.secondary_color};
                    font-family: {self.theme.font_family};
                    font-size: 11px;
                }}
            """)
            container_layout.addWidget(self.status_label)
            
            layout.addWidget(self.container)
        
        def _setup_animations(self):
            """Setup animations."""
            # Fade effect
            self.opacity_effect = QGraphicsOpacityEffect()
            self.container.setGraphicsEffect(self.opacity_effect)
            
            # Fade animation
            self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
            self.fade_anim.setDuration(300)
            self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            
            # Text animation timer
            self.text_timer = QTimer()
            self.text_timer.timeout.connect(self._animate_text)
            self.full_text = ""
            self.current_text_index = 0
        
        def show_response(self, text: str):
            """Show response with typewriter animation."""
            self.full_text = text
            self.current_text_index = 0
            self.response_label.setText("")
            
            # Start typewriter animation
            self.text_timer.start(20)  # 20ms per character
            
            # Show window with fade
            self.opacity_effect.setOpacity(0)
            self.show()
            self.fade_anim.setStartValue(0)
            self.fade_anim.setEndValue(1)
            self.fade_anim.start()
        
        def _animate_text(self):
            """Typewriter text animation."""
            if self.current_text_index < len(self.full_text):
                self.current_text_index += 1
                self.response_label.setText(self.full_text[:self.current_text_index])
            else:
                self.text_timer.stop()
        
        def set_state(self, state: JarvisState):
            """Set JARVIS state."""
            self.current_state = state
            self.status_indicator.set_state(state)
            
            state_text = {
                JarvisState.IDLE: "Ready",
                JarvisState.LISTENING: "Listening...",
                JarvisState.PROCESSING: "Processing...",
                JarvisState.SPEAKING: "Speaking...",
            }
            self.status_label.setText(state_text.get(state, ""))
            
            # Show waveform when listening/speaking
            self.waveform.setVisible(state in [JarvisState.LISTENING, JarvisState.SPEAKING])
        
        def update_waveform(self, levels: list):
            """Update waveform visualization."""
            self.waveform.update_levels(levels)
        
        def hide_overlay(self):
            """Hide with fade out."""
            self.fade_anim.setStartValue(1)
            self.fade_anim.setEndValue(0)
            self.fade_anim.finished.connect(self.hide)
            self.fade_anim.start()


class JarvisOverlay:
    """
    JARVIS visual overlay manager.
    
    Manages the transparent overlay UI in a separate thread to not block
    the main JARVIS event loop.
    """
    
    def __init__(self, config):
        """
        Initialize overlay manager.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.enabled = config.get("ui.overlay.enabled", True) and PYQT_AVAILABLE
        
        theme_name = config.get("ui.overlay.theme", "jarvis")
        self.theme = THEMES.get(theme_name, THEMES["jarvis"])
        self.position = config.get("ui.overlay.position", "top-right")
        
        self._app = None
        self._window = None
        self._thread = None
        self._signals = None
        self._started = False
    
    def start(self) -> bool:
        """
        Start the overlay in a background thread.
        
        Returns:
            True if started successfully
        """
        if not self.enabled:
            logger.warning("Overlay disabled or PyQt not available")
            return False
        
        if self._started:
            return True
        
        try:
            self._thread = threading.Thread(target=self._run_qt, daemon=True)
            self._thread.start()
            self._started = True
            logger.info("JARVIS overlay started")
            return True
        except Exception as e:
            logger.error(f"Failed to start overlay: {e}")
            return False
    
    def _run_qt(self):
        """Run Qt event loop in thread."""
        try:
            self._app = QApplication([])
            self._signals = OverlaySignals()
            self._window = JarvisOverlayWindow(self.theme, self.position)
            
            # Connect signals
            self._signals.show_response.connect(self._window.show_response)
            self._signals.set_state.connect(
                lambda s: self._window.set_state(JarvisState(s))
            )
            self._signals.hide_overlay.connect(self._window.hide_overlay)
            self._signals.update_waveform.connect(self._window.update_waveform)
            
            self._app.exec()
        except Exception as e:
            logger.error(f"Overlay error: {e}")
    
    def show_response(self, text: str) -> None:
        """
        Show a response on the overlay.
        
        Args:
            text: Response text to display
        """
        if self._signals:
            self._signals.show_response.emit(text)
    
    def set_state(self, state: str) -> None:
        """
        Set JARVIS state.
        
        Args:
            state: State name (idle, listening, processing, speaking)
        """
        if self._signals:
            self._signals.set_state.emit(state)
    
    def hide(self) -> None:
        """Hide the overlay."""
        if self._signals:
            self._signals.hide_overlay.emit()
    
    def update_waveform(self, levels: list) -> None:
        """
        Update waveform visualization.
        
        Args:
            levels: List of audio levels (0.0 - 1.0)
        """
        if self._signals:
            self._signals.update_waveform.emit(levels)
    
    def shutdown(self) -> None:
        """Shutdown the overlay."""
        if self._app:
            self._app.quit()
        self._started = False
