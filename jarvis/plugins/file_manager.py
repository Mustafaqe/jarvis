"""
JARVIS File Manager Plugin

Provides file system operations:
- Search for files
- List directory contents
- Open files
- Get file information
"""

import asyncio
import mimetypes
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from jarvis.plugins.base import Plugin, PluginInfo


class FileManagerPlugin(Plugin):
    """File system management plugin."""
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="File Manager",
            description="Search, browse, and manage files",
            version="1.0.0",
            commands=[
                "find file", "search file", "list files", "open file",
                "file info", "recent files", "modified files",
            ],
            intents=[
                "file", "folder", "directory", "find", "search",
                "list", "open", "modified", "recent", "document",
            ],
        )
    
    async def execute(self, command: str, params: dict[str, Any]) -> str:
        """Execute file management command."""
        command_lower = command.lower()
        
        # Search for files
        if any(w in command_lower for w in ["find", "search", "where"]):
            return await self._search_files(command, params)
        
        # List directory
        if "list" in command_lower:
            return await self._list_directory(command, params)
        
        # Open file
        if "open" in command_lower:
            return await self._open_file(command, params)
        
        # File info
        if "info" in command_lower:
            return await self._get_file_info(command, params)
        
        # Recent/modified files
        if any(w in command_lower for w in ["recent", "modified", "today"]):
            return await self._get_recent_files(command, params)
        
        return "I can help with files. Try 'find [filename]', 'list files in [directory]', or 'open [file]'."
    
    async def _search_files(self, command: str, params: dict) -> str:
        """Search for files by name."""
        # Extract search term
        search_term = self._extract_search_term(command)
        
        if not search_term:
            return "Please specify what file you're looking for."
        
        # Search in home directory
        home = Path.home()
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, self._search_sync, str(home), search_term
        )
        
        if not results:
            return f"No files found matching '{search_term}'."
        
        if len(results) == 1:
            return f"Found: {results[0]}"
        
        # Limit results
        shown = results[:5]
        response = f"Found {len(results)} files matching '{search_term}':\n"
        response += "\n".join(f"• {f}" for f in shown)
        
        if len(results) > 5:
            response += f"\n... and {len(results) - 5} more."
        
        return response
    
    def _search_sync(self, start_dir: str, pattern: str, max_results: int = 20) -> list[str]:
        """Synchronous file search using find command."""
        try:
            result = subprocess.run(
                ['find', start_dir, '-name', f'*{pattern}*', '-type', 'f'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            files = result.stdout.strip().split('\n')
            return [f for f in files if f][:max_results]
            
        except Exception as e:
            logger.error(f"File search error: {e}")
            return []
    
    def _extract_search_term(self, command: str) -> str:
        """Extract search term from command."""
        words = command.lower().split()
        
        skip_words = ['find', 'search', 'for', 'file', 'files', 'named', 'called', 'where', 'is']
        
        for i, word in enumerate(words):
            if word in skip_words:
                continue
            # Return remaining words as search term
            remaining = words[i:]
            return ' '.join(w for w in remaining if w not in skip_words)
        
        return ""
    
    async def _list_directory(self, command: str, params: dict) -> str:
        """List contents of a directory."""
        # Extract directory path
        path = self._extract_path(command)
        
        if not path:
            path = Path.home()
        else:
            path = Path(path).expanduser()
        
        if not path.exists():
            return f"Directory not found: {path}"
        
        if not path.is_dir():
            return f"{path} is not a directory."
        
        try:
            items = list(path.iterdir())
            
            dirs = sorted([i for i in items if i.is_dir()])
            files = sorted([i for i in items if i.is_file()])
            
            response = f"Contents of {path}:\n"
            
            if dirs:
                response += f"\nFolders ({len(dirs)}):\n"
                for d in dirs[:10]:
                    response += f"📁 {d.name}\n"
                if len(dirs) > 10:
                    response += f"  ... and {len(dirs) - 10} more folders\n"
            
            if files:
                response += f"\nFiles ({len(files)}):\n"
                for f in files[:10]:
                    size = self._format_size(f.stat().st_size)
                    response += f"📄 {f.name} ({size})\n"
                if len(files) > 10:
                    response += f"  ... and {len(files) - 10} more files\n"
            
            return response.strip()
            
        except PermissionError:
            return f"Permission denied: {path}"
        except Exception as e:
            return f"Error listing directory: {e}"
    
    def _extract_path(self, command: str) -> str | None:
        """Extract file/directory path from command."""
        # Look for path indicators
        words = command.split()
        
        for i, word in enumerate(words):
            if word.lower() in ['in', 'at', 'of', 'from']:
                if i + 1 < len(words):
                    path = ' '.join(words[i + 1:])
                    # Remove trailing punctuation
                    path = path.rstrip('.,?!')
                    return path
            
            # Check if word looks like a path
            if '/' in word or word.startswith('~'):
                return word
        
        return None
    
    async def _open_file(self, command: str, params: dict) -> str:
        """Open a file with the default application."""
        path = self._extract_path(command)
        
        if not path:
            return "Please specify which file to open."
        
        file_path = Path(path).expanduser()
        
        if not file_path.exists():
            # Try searching for it
            search_result = self._search_sync(str(Path.home()), path, max_results=1)
            if search_result:
                file_path = Path(search_result[0])
            else:
                return f"File not found: {path}"
        
        try:
            subprocess.Popen(
                ['xdg-open', str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return f"Opening {file_path.name}"
        except Exception as e:
            return f"Failed to open file: {e}"
    
    async def _get_file_info(self, command: str, params: dict) -> str:
        """Get information about a file."""
        path = self._extract_path(command)
        
        if not path:
            return "Please specify which file."
        
        file_path = Path(path).expanduser()
        
        if not file_path.exists():
            return f"File not found: {path}"
        
        stat = file_path.stat()
        
        info = f"File: {file_path.name}\n"
        info += f"Path: {file_path.absolute()}\n"
        info += f"Size: {self._format_size(stat.st_size)}\n"
        info += f"Modified: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')}\n"
        
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            info += f"Type: {mime_type}\n"
        
        return info
    
    async def _get_recent_files(self, command: str, params: dict) -> str:
        """Get recently modified files."""
        home = Path.home()
        
        # Use find to get recently modified files
        try:
            result = subprocess.run(
                ['find', str(home), '-type', 'f', '-mtime', '-1', '-not', '-path', '*/.*'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            files = result.stdout.strip().split('\n')
            files = [f for f in files if f][:10]
            
            if not files:
                return "No files were modified in the last 24 hours."
            
            response = "Recently modified files:\n"
            for f in files:
                path = Path(f)
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                response += f"• {path.name} ({mtime.strftime('%H:%M')})\n"
            
            return response.strip()
            
        except Exception as e:
            return f"Error finding recent files: {e}"
    
    def _format_size(self, size: int) -> str:
        """Format file size for display."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
