"""
JARVIS System Tray

Provides system tray icon with quick actions and notifications.
"""

import sys
import threading
from typing import Optional, Callable, List
from dataclasses import dataclass

from loguru import logger

# Try to import PyQt6, fallback to PyQt5
try:
    from PyQt6.QtWidgets import (
        QApplication, QSystemTrayIcon, QMenu
    )
    from PyQt6.QtCore import Qt, QObject, pyqtSignal
    from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
    PYQT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtWidgets import (
            QApplication, QSystemTrayIcon, QMenu, QAction
        )
        from PyQt5.QtCore import Qt, QObject, pyqtSignal
        from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
        PYQT_AVAILABLE = True
    except ImportError:
        PYQT_AVAILABLE = False
        logger.warning("PyQt not available for system tray")


@dataclass
class TrayMenuItem:
    """Menu item configuration."""
    label: str
    callback: Optional[Callable] = None
    separator: bool = False
    submenu: Optional[List["TrayMenuItem"]] = None


if PYQT_AVAILABLE:
    
    class TraySignals(QObject):
        """Signals for thread-safe tray updates."""
        show_notification = pyqtSignal(str, str, str)  # title, body, icon
        set_status = pyqtSignal(str)
        quit_app = pyqtSignal()
    
    
    class JarvisTrayIcon(QSystemTrayIcon):
        """JARVIS system tray icon."""
        
        def __init__(self, config, callbacks: dict = None):
            super().__init__()
            
            self.config = config
            self.callbacks = callbacks or {}
            
            self._create_icon()
            self._create_menu()
            self._connect_signals()
        
        def _create_icon(self):
            """Create the tray icon."""
            # Create a simple JARVIS-style icon
            size = 64
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Draw blue circle background
            painter.setBrush(QColor("#0066CC"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(4, 4, size - 8, size - 8)
            
            # Draw inner circle
            painter.setBrush(QColor("#00D4FF"))
            painter.drawEllipse(12, 12, size - 24, size - 24)
            
            # Draw center dot
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(size // 2 - 6, size // 2 - 6, 12, 12)
            
            painter.end()
            
            self.setIcon(QIcon(pixmap))
            self.setToolTip("JARVIS AI Assistant")
        
        def _create_menu(self):
            """Create the context menu."""
            menu = QMenu()
            
            # Status (non-clickable)
            self.status_action = menu.addAction("Status: Active")
            self.status_action.setEnabled(False)
            
            menu.addSeparator()
            
            # Quick actions
            menu.addAction("🎤 Start Voice Mode", self._on_voice_mode)
            menu.addAction("📝 Open Dashboard", self._on_open_dashboard)
            menu.addAction("⚙️ Settings", self._on_settings)
            
            menu.addSeparator()
            
            # Vision actions
            vision_menu = menu.addMenu("👁️ Vision")
            vision_menu.addAction("Screenshot", self._on_screenshot)
            vision_menu.addAction("Analyze Screen", self._on_analyze_screen)
            
            menu.addSeparator()
            
            # Exit
            menu.addAction("❌ Exit", self._on_exit)
            
            self.setContextMenu(menu)
        
        def _connect_signals(self):
            """Connect click signals."""
            self.activated.connect(self._on_activated)
        
        def _on_activated(self, reason):
            """Handle tray icon activation."""
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
                self._on_open_dashboard()
        
        def _on_voice_mode(self):
            """Start voice mode."""
            callback = self.callbacks.get("voice_mode")
            if callback:
                callback()
        
        def _on_open_dashboard(self):
            """Open web dashboard."""
            callback = self.callbacks.get("open_dashboard")
            if callback:
                callback()
            else:
                import webbrowser
                port = self.config.get("web.port", 8000)
                webbrowser.open(f"http://localhost:{port}")
        
        def _on_settings(self):
            """Open settings."""
            callback = self.callbacks.get("settings")
            if callback:
                callback()
        
        def _on_screenshot(self):
            """Take screenshot."""
            callback = self.callbacks.get("screenshot")
            if callback:
                callback()
        
        def _on_analyze_screen(self):
            """Analyze screen."""
            callback = self.callbacks.get("analyze_screen")
            if callback:
                callback()
        
        def _on_exit(self):
            """Exit application."""
            callback = self.callbacks.get("exit")
            if callback:
                callback()
            else:
                QApplication.quit()
        
        def set_status(self, status: str):
            """Update status text."""
            self.status_action.setText(f"Status: {status}")
        
        def show_notification(self, title: str, body: str, icon_type: str = "info"):
            """Show a notification."""
            icon_map = {
                "info": QSystemTrayIcon.MessageIcon.Information,
                "warning": QSystemTrayIcon.MessageIcon.Warning,
                "error": QSystemTrayIcon.MessageIcon.Critical,
            }
            icon = icon_map.get(icon_type, QSystemTrayIcon.MessageIcon.Information)
            self.showMessage(title, body, icon, 5000)  # 5 second timeout


class JarvisTray:
    """
    JARVIS system tray manager.
    
    Provides:
    - System tray icon
    - Quick action menu
    - Desktop notifications
    """
    
    def __init__(self, config, callbacks: dict = None):
        """
        Initialize tray manager.
        
        Args:
            config: Configuration object
            callbacks: Dict of callback functions for menu actions
        """
        self.config = config
        self.callbacks = callbacks or {}
        self.enabled = config.get("ui.tray.enabled", True) and PYQT_AVAILABLE
        
        self._app = None
        self._tray = None
        self._signals = None
        self._thread = None
        self._started = False
    
    def start(self) -> bool:
        """
        Start the system tray in a background thread.
        
        Returns:
            True if started successfully
        """
        if not self.enabled:
            logger.warning("System tray disabled or PyQt not available")
            return False
        
        if self._started:
            return True
        
        try:
            self._thread = threading.Thread(target=self._run_qt, daemon=True)
            self._thread.start()
            self._started = True
            logger.info("JARVIS system tray started")
            return True
        except Exception as e:
            logger.error(f"Failed to start system tray: {e}")
            return False
    
    def _run_qt(self):
        """Run Qt event loop in thread."""
        try:
            # Check if QApplication already exists
            self._app = QApplication.instance()
            if not self._app:
                self._app = QApplication([])
            
            self._signals = TraySignals()
            self._tray = JarvisTrayIcon(self.config, self.callbacks)
            
            # Connect signals
            self._signals.show_notification.connect(
                lambda t, b, i: self._tray.show_notification(t, b, i)
            )
            self._signals.set_status.connect(self._tray.set_status)
            self._signals.quit_app.connect(self._app.quit)
            
            self._tray.show()
            self._app.exec()
            
        except Exception as e:
            logger.error(f"System tray error: {e}")
    
    def show_notification(
        self, 
        title: str, 
        body: str, 
        icon_type: str = "info"
    ) -> None:
        """
        Show a desktop notification.
        
        Args:
            title: Notification title
            body: Notification body
            icon_type: Icon type (info, warning, error)
        """
        if self._signals:
            self._signals.show_notification.emit(title, body, icon_type)
    
    def set_status(self, status: str) -> None:
        """
        Update tray status text.
        
        Args:
            status: Status text
        """
        if self._signals:
            self._signals.set_status.emit(status)
    
    def shutdown(self) -> None:
        """Shutdown the system tray."""
        if self._signals:
            self._signals.quit_app.emit()
        self._started = False
