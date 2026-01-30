"""
JARVIS Security Layer

Provides command validation, safety checks, and confirmation for
potentially dangerous operations.
"""

import re
import shlex
from dataclasses import dataclass
from enum import Enum, auto

from loguru import logger


class RiskLevel(Enum):
    """Risk levels for commands."""
    SAFE = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()
    BLOCKED = auto()


@dataclass
class SecurityCheck:
    """Result of a security check."""
    allowed: bool
    risk_level: RiskLevel
    reason: str
    requires_confirmation: bool = False


class SecurityManager:
    """
    Manages security checks and command validation.
    
    Provides:
    - Command whitelisting/blacklisting
    - Risk assessment
    - Confirmation requirements for dangerous operations
    """
    
    # Patterns that indicate dangerous operations
    DANGEROUS_PATTERNS = [
        (r"rm\s+(-rf?|--recursive)\s+/", RiskLevel.CRITICAL, "Recursive delete from root"),
        (r"rm\s+(-rf?|--recursive)\s+~", RiskLevel.HIGH, "Recursive delete from home"),
        (r"rm\s+(-rf?|--recursive)", RiskLevel.MEDIUM, "Recursive delete"),
        (r"dd\s+if=", RiskLevel.CRITICAL, "Direct disk write"),
        (r"mkfs\.", RiskLevel.CRITICAL, "Filesystem format"),
        (r":\(\)\s*\{.*\}.*;:", RiskLevel.CRITICAL, "Fork bomb pattern"),
        (r"chmod\s+777", RiskLevel.MEDIUM, "World-writable permissions"),
        (r"chmod\s+-R", RiskLevel.MEDIUM, "Recursive permission change"),
        (r"chown\s+-R", RiskLevel.MEDIUM, "Recursive owner change"),
        (r"sudo\s+rm", RiskLevel.HIGH, "Sudo delete"),
        (r">\s*/dev/sd", RiskLevel.CRITICAL, "Direct device write"),
        (r"curl.*\|\s*(bash|sh)", RiskLevel.HIGH, "Piped script execution"),
        (r"wget.*\|\s*(bash|sh)", RiskLevel.HIGH, "Piped script execution"),
        (r"shutdown|reboot|poweroff", RiskLevel.MEDIUM, "System power control"),
        (r"systemctl\s+(stop|disable)", RiskLevel.MEDIUM, "Service control"),
        (r"/etc/passwd|/etc/shadow", RiskLevel.HIGH, "Sensitive file access"),
        (r"iptables|ufw|firewall", RiskLevel.MEDIUM, "Firewall modification"),
    ]
    
    # Commands that are always blocked
    BLOCKED_COMMANDS = [
        "rm -rf /",
        "rm -rf /*",
        "dd if=/dev/zero of=/dev/sda",
        ":(){:|:&};:",
        "mv ~ /dev/null",
        "chmod -R 777 /",
    ]
    
    # Safe command prefixes (read-only operations)
    SAFE_PREFIXES = [
        "ls", "cat", "head", "tail", "less", "more",
        "grep", "find", "locate", "which", "whereis",
        "pwd", "whoami", "hostname", "date", "cal",
        "df", "du", "free", "top", "htop", "ps",
        "echo", "printf", "env", "printenv",
        "uname", "lsb_release", "uptime",
        "ip addr", "ifconfig", "netstat",
    ]
    
    def __init__(self, config):
        """
        Initialize security manager.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self._load_config()
    
    def _load_config(self):
        """Load security configuration."""
        self.require_confirmation = self.config.get(
            "security.require_confirmation",
            ["delete", "remove", "shutdown", "reboot"]
        )
        
        self.blocked_commands = self.config.get(
            "security.blocked_commands",
            self.BLOCKED_COMMANDS
        )
        
        self.sandbox_enabled = self.config.get(
            "security.sandbox_enabled",
            True
        )
    
    def check_command(self, command: str) -> SecurityCheck:
        """
        Check if a command is safe to execute.
        
        Args:
            command: The shell command to check
            
        Returns:
            SecurityCheck with result and risk assessment
        """
        # Normalize command
        command = command.strip()
        command_lower = command.lower()
        
        # Check blocked commands
        for blocked in self.blocked_commands:
            if blocked.lower() in command_lower:
                logger.warning(f"Blocked command detected: {command}")
                return SecurityCheck(
                    allowed=False,
                    risk_level=RiskLevel.BLOCKED,
                    reason=f"Command contains blocked pattern: {blocked}"
                )
        
        # Check dangerous patterns
        for pattern, risk, reason in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                requires_confirm = risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)
                
                if risk == RiskLevel.CRITICAL:
                    logger.warning(f"Critical risk command blocked: {command}")
                    return SecurityCheck(
                        allowed=False,
                        risk_level=risk,
                        reason=reason
                    )
                
                return SecurityCheck(
                    allowed=True,
                    risk_level=risk,
                    reason=reason,
                    requires_confirmation=requires_confirm
                )
        
        # Check if command requires confirmation keywords
        for keyword in self.require_confirmation:
            if keyword.lower() in command_lower:
                return SecurityCheck(
                    allowed=True,
                    risk_level=RiskLevel.MEDIUM,
                    reason=f"Command contains '{keyword}' - confirmation required",
                    requires_confirmation=True
                )
        
        # Check safe prefixes
        for prefix in self.SAFE_PREFIXES:
            if command_lower.startswith(prefix):
                return SecurityCheck(
                    allowed=True,
                    risk_level=RiskLevel.SAFE,
                    reason="Read-only command"
                )
        
        # Default to low risk with confirmation
        return SecurityCheck(
            allowed=True,
            risk_level=RiskLevel.LOW,
            reason="Unknown command - proceeding with caution",
            requires_confirmation=False
        )
    
    def check_file_operation(self, operation: str, path: str) -> SecurityCheck:
        """
        Check if a file operation is safe.
        
        Args:
            operation: Type of operation (read, write, delete, etc.)
            path: File path
            
        Returns:
            SecurityCheck with result
        """
        # Protected paths
        protected_paths = [
            "/etc", "/usr", "/bin", "/sbin", "/lib",
            "/boot", "/dev", "/proc", "/sys", "/root",
        ]
        
        # Check for protected paths
        for protected in protected_paths:
            if path.startswith(protected):
                if operation in ("delete", "write", "modify"):
                    return SecurityCheck(
                        allowed=False,
                        risk_level=RiskLevel.HIGH,
                        reason=f"Cannot {operation} files in protected path: {protected}"
                    )
        
        # Delete operations need confirmation
        if operation == "delete":
            return SecurityCheck(
                allowed=True,
                risk_level=RiskLevel.MEDIUM,
                reason="Delete operation requires confirmation",
                requires_confirmation=True
            )
        
        return SecurityCheck(
            allowed=True,
            risk_level=RiskLevel.SAFE,
            reason="File operation allowed"
        )
    
    def sanitize_command(self, command: str) -> str:
        """
        Sanitize a command for safe execution.
        
        Args:
            command: Raw command string
            
        Returns:
            Sanitized command
        """
        # Remove shell special characters that could be dangerous
        dangerous_chars = [";", "&&", "||", "|", "`", "$(", "${"]
        
        result = command
        for char in dangerous_chars:
            if char in result:
                # Only remove if not properly quoted
                try:
                    shlex.split(result)
                except ValueError:
                    result = result.replace(char, "")
        
        return result.strip()
    
    def validate_api_key(self, key: str, service: str) -> bool:
        """
        Validate API key format.
        
        Args:
            key: API key to validate
            service: Service name (anthropic, openai, etc.)
            
        Returns:
            True if valid format
        """
        if not key or len(key) < 20:
            return False
        
        patterns = {
            "anthropic": r"^sk-ant-",
            "openai": r"^sk-",
            "porcupine": r"^[A-Za-z0-9+/=]+$",
        }
        
        pattern = patterns.get(service)
        if pattern:
            return bool(re.match(pattern, key))
        
        return True
