"""
JARVIS Configuration Management

Handles loading, merging, and accessing configuration from YAML files
and environment variables.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


class Config:
    """
    Configuration manager for JARVIS.
    
    Loads configuration from:
    1. Default config (config/default.yaml)
    2. User config (config/user.yaml) - overrides defaults
    3. Environment variables (JARVIS_*) - highest priority
    """
    
    DEFAULT_CONFIG = {
        # Core settings
        "core": {
            "name": "Jarvis",
            "wake_words": ["jarvis", "hey jarvis"],
            "language": "en-US",
            "data_dir": "data",
        },
        
        # Voice settings
        "voice": {
            "enabled": True,
            "wake_word": {
                "engine": "porcupine",  # porcupine, openwakeword
                "sensitivity": 0.5,
                "porcupine_access_key": "",
            },
            "stt": {
                "engine": "whisper",  # whisper, vosk
                "whisper_model": "base",
                "vosk_model_path": "models/vosk-model-small-en-us",
                "language": "en",
            },
            "tts": {
                "engine": "pyttsx3",  # pyttsx3, gtts, coqui
                "voice": None,  # System default
                "rate": 175,
                "volume": 0.9,
            },
            "audio": {
                "sample_rate": 16000,
                "channels": 1,
                "chunk_size": 1024,
                "input_device": None,  # Auto-detect
                "output_device": None,
            },
        },
        
        # AI settings
        "ai": {
            "llm": {
                "provider": "anthropic",  # anthropic, ollama, openai
                "model": "claude-3-5-sonnet-20241022",
                "ollama_model": "llama3.2",
                "ollama_host": "http://localhost:11434",
                "temperature": 0.7,
                "max_tokens": 1024,
            },
            "context": {
                "max_history": 20,
                "max_tokens": 4096,
            },
            "memory": {
                "enabled": True,
                "database": "data/memory.db",
            },
        },
        
        # Security settings
        "security": {
            "require_confirmation": [
                "delete",
                "remove",
                "shutdown",
                "reboot",
                "format",
                "rm -rf",
            ],
            "blocked_commands": [
                "rm -rf /",
                "dd if=",
                "mkfs",
                ":(){:|:&};:",
            ],
            "sandbox_enabled": True,
        },
        
        # Plugin settings
        "plugins": {
            "enabled": True,
            "directory": "jarvis/plugins",
            "autoload": [
                "system_control",
                "file_manager",
                "timer",
                "shell",
                "web_search",
            ],
        },
        
        # Web interface
        "web": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 8000,
            "cors_origins": ["*"],
        },
        
        # Logging
        "logging": {
            "level": "INFO",
            "file": "data/logs/jarvis.log",
            "rotation": "10 MB",
            "retention": "7 days",
            "format": "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        },
    }
    
    def __init__(self, config_path: str | Path | None = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Optional path to custom config file
        """
        self._config: dict[str, Any] = {}
        self._load_config(config_path)
    
    def _load_config(self, config_path: str | Path | None = None):
        """Load and merge configuration from all sources."""
        # Start with defaults
        self._config = self._deep_copy(self.DEFAULT_CONFIG)
        
        # Find project root
        project_root = Path(__file__).parent.parent.parent
        
        # Load default config if exists
        default_path = project_root / "config" / "default.yaml"
        if default_path.exists():
            self._merge_yaml(default_path)
        
        # Load user config if exists
        user_path = project_root / "config" / "user.yaml"
        if user_path.exists():
            self._merge_yaml(user_path)
        
        # Load custom config if provided
        if config_path:
            self._merge_yaml(Path(config_path))
        
        # Override with environment variables
        self._load_env_vars()
        
        logger.debug("Configuration loaded successfully")
    
    def _merge_yaml(self, path: Path):
        """Merge YAML file into configuration."""
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
                if data:
                    self._deep_merge(self._config, data)
                    logger.debug(f"Merged config from {path}")
        except Exception as e:
            logger.warning(f"Failed to load config from {path}: {e}")
    
    def _load_env_vars(self):
        """Load configuration from environment variables."""
        env_mappings = {
            "JARVIS_ANTHROPIC_API_KEY": "ai.llm.anthropic_api_key",
            "JARVIS_OPENAI_API_KEY": "ai.llm.openai_api_key",
            "JARVIS_PORCUPINE_ACCESS_KEY": "voice.wake_word.porcupine_access_key",
            "JARVIS_OLLAMA_HOST": "ai.llm.ollama_host",
            "JARVIS_LOG_LEVEL": "logging.level",
            "JARVIS_WEB_PORT": "web.port",
            "ANTHROPIC_API_KEY": "ai.llm.anthropic_api_key",
            "OPENAI_API_KEY": "ai.llm.openai_api_key",
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                self.set(config_path, value)
                logger.debug(f"Loaded {config_path} from environment")
    
    def _deep_copy(self, obj: Any) -> Any:
        """Create a deep copy of a nested dict/list structure."""
        if isinstance(obj, dict):
            return {k: self._deep_copy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._deep_copy(item) for item in obj]
        return obj
    
    def _deep_merge(self, base: dict, override: dict):
        """Deep merge override into base dict."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        Get a configuration value by dot-notation path.
        
        Args:
            path: Dot-separated path (e.g., "voice.stt.engine")
            default: Default value if path not found
            
        Returns:
            Configuration value or default
        """
        keys = path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, path: str, value: Any):
        """
        Set a configuration value by dot-notation path.
        
        Args:
            path: Dot-separated path (e.g., "voice.stt.engine")
            value: Value to set
        """
        keys = path.split('.')
        config = self._config
        
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        config[keys[-1]] = value
    
    def as_dict(self) -> dict[str, Any]:
        """Return full configuration as dictionary."""
        return self._deep_copy(self._config)
    
    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access: config['key']."""
        return self.get(key)
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists in config."""
        return self.get(key) is not None
