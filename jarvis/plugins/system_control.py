"""
JARVIS System Control Plugin

Provides system monitoring and control capabilities:
- CPU, memory, disk usage
- Process management
- Application launching
- System information
"""

import asyncio
import subprocess
from typing import Any

import psutil
from loguru import logger

from jarvis.plugins.base import Plugin, PluginInfo


class SystemControlPlugin(Plugin):
    """System monitoring and control plugin."""
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="System Control",
            description="Monitor and control system resources",
            version="1.0.0",
            commands=[
                "cpu usage", "memory usage", "disk usage", "system status",
                "list processes", "kill process", "open application",
                "battery status", "network status",
            ],
            intents=[
                "cpu", "memory", "ram", "disk", "storage",
                "system", "status", "process", "battery", "network",
                "open", "launch", "start", "run", "close", "kill",
            ],
        )
    
    async def execute(self, command: str, params: dict[str, Any]) -> str:
        """Execute system control command."""
        command_lower = command.lower()
        
        # CPU usage
        if any(w in command_lower for w in ["cpu", "processor"]):
            return await self._get_cpu_info()
        
        # Memory usage
        if any(w in command_lower for w in ["memory", "ram"]):
            return await self._get_memory_info()
        
        # Disk usage
        if any(w in command_lower for w in ["disk", "storage", "space"]):
            return await self._get_disk_info()
        
        # Battery status
        if "battery" in command_lower:
            return await self._get_battery_info()
        
        # Network status
        if "network" in command_lower:
            return await self._get_network_info()
        
        # Full system status
        if any(w in command_lower for w in ["status", "system info"]):
            return await self._get_system_status()
        
        # Process list
        if "process" in command_lower and "list" in command_lower:
            return await self._list_processes()
        
        # Kill process
        if "kill" in command_lower:
            return await self._kill_process(command, params)
        
        # Open application
        if any(w in command_lower for w in ["open", "launch", "start", "run"]):
            return await self._open_application(command, params)
        
        # Close application
        if "close" in command_lower:
            return await self._close_application(command, params)
        
        return "I can help with system monitoring. Try asking about CPU, memory, disk usage, or opening applications."
    
    async def _get_cpu_info(self) -> str:
        """Get CPU usage information."""
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        
        freq_str = f" at {cpu_freq.current:.0f} MHz" if cpu_freq else ""
        
        return f"CPU usage is {cpu_percent}% across {cpu_count} cores{freq_str}."
    
    async def _get_memory_info(self) -> str:
        """Get memory usage information."""
        mem = psutil.virtual_memory()
        
        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        
        return (
            f"Memory usage: {mem.percent}% "
            f"({used_gb:.1f} GB used of {total_gb:.1f} GB total). "
            f"{available_gb:.1f} GB available."
        )
    
    async def _get_disk_info(self) -> str:
        """Get disk usage information."""
        disk = psutil.disk_usage('/')
        
        used_gb = disk.used / (1024 ** 3)
        total_gb = disk.total / (1024 ** 3)
        free_gb = disk.free / (1024 ** 3)
        
        return (
            f"Disk usage: {disk.percent}% "
            f"({used_gb:.0f} GB used of {total_gb:.0f} GB total). "
            f"{free_gb:.0f} GB free."
        )
    
    async def _get_battery_info(self) -> str:
        """Get battery status."""
        battery = psutil.sensors_battery()
        
        if not battery:
            return "No battery detected. This might be a desktop system."
        
        status = "charging" if battery.power_plugged else "on battery"
        time_left = ""
        
        if battery.secsleft > 0 and not battery.power_plugged:
            hours = battery.secsleft // 3600
            minutes = (battery.secsleft % 3600) // 60
            time_left = f" About {hours} hours {minutes} minutes remaining."
        
        return f"Battery at {battery.percent}%, {status}.{time_left}"
    
    async def _get_network_info(self) -> str:
        """Get network information."""
        interfaces = psutil.net_if_addrs()
        stats = psutil.net_io_counters()
        
        # Find active interface
        active = None
        for name, addrs in interfaces.items():
            if name != 'lo':  # Skip loopback
                for addr in addrs:
                    if addr.family.name == 'AF_INET':
                        active = (name, addr.address)
                        break
                if active:
                    break
        
        if not active:
            return "No active network connection detected."
        
        sent_mb = stats.bytes_sent / (1024 ** 2)
        recv_mb = stats.bytes_recv / (1024 ** 2)
        
        return (
            f"Connected via {active[0]} with IP {active[1]}. "
            f"Data: {sent_mb:.1f} MB sent, {recv_mb:.1f} MB received."
        )
    
    async def _get_system_status(self) -> str:
        """Get overall system status."""
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Get uptime
        import time
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        uptime_hours = int(uptime_seconds // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        
        return (
            f"System status: CPU {cpu}%, Memory {mem.percent}%, Disk {disk.percent}%. "
            f"Uptime: {uptime_hours} hours {uptime_minutes} minutes."
        )
    
    async def _list_processes(self, limit: int = 5) -> str:
        """List top processes by CPU usage."""
        processes = []
        
        for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] is not None:
                    processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort by CPU usage
        processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
        
        if not processes:
            return "Unable to list processes."
        
        top = processes[:limit]
        lines = [f"{p['name']}: CPU {p['cpu_percent']:.1f}%, RAM {p['memory_percent']:.1f}%" 
                 for p in top]
        
        return "Top processes: " + "; ".join(lines)
    
    async def _kill_process(self, command: str, params: dict) -> str:
        """Kill a process by name."""
        # Extract process name from command
        words = command.lower().split()
        
        try:
            kill_idx = words.index("kill")
            if kill_idx + 1 < len(words):
                proc_name = words[kill_idx + 1]
            else:
                return "Please specify which process to kill."
        except ValueError:
            return "Please specify which process to kill."
        
        killed = 0
        for proc in psutil.process_iter(['name']):
            try:
                if proc_name.lower() in proc.info['name'].lower():
                    proc.terminate()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if killed:
            return f"Terminated {killed} process(es) matching '{proc_name}'."
        return f"No process found matching '{proc_name}'."
    
    async def _open_application(self, command: str, params: dict) -> str:
        """Open an application."""
        # Common application mappings
        app_commands = {
            "firefox": "firefox",
            "browser": "firefox",
            "chrome": "google-chrome",
            "terminal": "gnome-terminal",
            "files": "nautilus",
            "file manager": "nautilus",
            "calculator": "gnome-calculator",
            "settings": "gnome-control-center",
            "text editor": "gedit",
            "code": "code",
            "vscode": "code",
            "spotify": "spotify",
            "discord": "discord",
            "slack": "slack",
        }
        
        command_lower = command.lower()
        
        # Find which app to open
        app_to_open = None
        for app_name, app_cmd in app_commands.items():
            if app_name in command_lower:
                app_to_open = app_cmd
                break
        
        if not app_to_open:
            # Try to extract app name
            for word in ["open", "launch", "start", "run"]:
                if word in command_lower:
                    parts = command_lower.split(word)
                    if len(parts) > 1:
                        app_to_open = parts[1].strip().split()[0]
                    break
        
        if not app_to_open:
            return "Please specify which application to open."
        
        try:
            subprocess.Popen(
                [app_to_open],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return f"Opening {app_to_open}."
        except FileNotFoundError:
            return f"Application '{app_to_open}' not found."
        except Exception as e:
            return f"Failed to open {app_to_open}: {e}"
    
    async def _close_application(self, command: str, params: dict) -> str:
        """Close an application."""
        words = command.lower().split()
        
        try:
            close_idx = words.index("close")
            if close_idx + 1 < len(words):
                app_name = words[close_idx + 1]
            else:
                return "Please specify which application to close."
        except ValueError:
            return "Please specify which application to close."
        
        closed = 0
        for proc in psutil.process_iter(['name']):
            try:
                if app_name.lower() in proc.info['name'].lower():
                    proc.terminate()
                    closed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if closed:
            return f"Closed {closed} instance(s) of {app_name}."
        return f"No running application found matching '{app_name}'."
