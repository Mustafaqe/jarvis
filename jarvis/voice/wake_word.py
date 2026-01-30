"""
JARVIS Wake Word Detection

Detects wake words like "Hey Jarvis" to activate the assistant.
Supports Porcupine (commercial) and OpenWakeWord (open source).
"""

import asyncio
import struct
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger


class WakeWordDetector(ABC):
    """Abstract base class for wake word detectors."""
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the wake word detector."""
        pass
    
    @abstractmethod
    def process(self, audio_data: bytes) -> bool:
        """
        Process audio data and check for wake word.
        
        Args:
            audio_data: Raw audio bytes (16-bit, 16kHz, mono)
            
        Returns:
            True if wake word detected
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup resources."""
        pass


class PorcupineDetector(WakeWordDetector):
    """Wake word detection using Picovoice Porcupine."""
    
    def __init__(self, config):
        """
        Initialize Porcupine detector.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.access_key = config.get("voice.wake_word.porcupine_access_key", "")
        self.sensitivity = config.get("voice.wake_word.sensitivity", 0.5)
        self.keywords = config.get("core.wake_words", ["jarvis"])
        
        self._porcupine = None
        self._frame_length = 512
    
    def initialize(self) -> None:
        """Initialize Porcupine engine."""
        if not self.access_key:
            raise ValueError(
                "Porcupine access key required. "
                "Get one at https://console.picovoice.ai/ "
                "and set JARVIS_PORCUPINE_ACCESS_KEY environment variable."
            )
        
        try:
            import pvporcupine
            
            # Map keywords to built-in ones or custom paths
            keywords = []
            for kw in self.keywords:
                if kw.lower() == "jarvis":
                    keywords.append("jarvis")
                elif Path(kw).exists():
                    keywords.append(kw)
            
            if not keywords:
                keywords = ["jarvis"]
            
            self._porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=keywords,
                sensitivities=[self.sensitivity] * len(keywords),
            )
            
            self._frame_length = self._porcupine.frame_length
            
            logger.info(f"Porcupine initialized with keywords: {keywords}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Porcupine: {e}")
            raise
    
    def process(self, audio_data: bytes) -> bool:
        """Process audio and check for wake word."""
        if not self._porcupine:
            return False
        
        # Convert bytes to int16 array
        num_samples = len(audio_data) // 2
        pcm = struct.unpack(f'{num_samples}h', audio_data)
        
        # Process in frames
        for i in range(0, len(pcm) - self._frame_length, self._frame_length):
            frame = pcm[i:i + self._frame_length]
            
            if len(frame) == self._frame_length:
                keyword_index = self._porcupine.process(frame)
                
                if keyword_index >= 0:
                    keyword = self.keywords[keyword_index] if keyword_index < len(self.keywords) else "wake word"
                    logger.info(f"Wake word detected: {keyword}")
                    return True
        
        return False
    
    def shutdown(self) -> None:
        """Cleanup Porcupine resources."""
        if self._porcupine:
            self._porcupine.delete()
            self._porcupine = None
            logger.debug("Porcupine shutdown complete")


class SimpleWakeWordDetector(WakeWordDetector):
    """
    Simple wake word detection using speech recognition.
    
    This is a fallback when Porcupine is not available.
    Less accurate but works offline without API keys.
    """
    
    def __init__(self, config):
        """Initialize simple detector."""
        self.config = config
        self.wake_words = [w.lower() for w in config.get("core.wake_words", ["jarvis"])]
        self._recognizer = None
    
    def initialize(self) -> None:
        """Initialize speech recognizer."""
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            logger.info(f"Simple wake word detector initialized: {self.wake_words}")
        except ImportError:
            raise ImportError("speech_recognition required for SimpleWakeWordDetector")
    
    def process(self, audio_data: bytes) -> bool:
        """Process audio looking for wake word."""
        if not self._recognizer:
            return False
        
        try:
            import speech_recognition as sr
            
            # Create audio data object
            audio = sr.AudioData(audio_data, sample_rate=16000, sample_width=2)
            
            # Try to recognize
            try:
                text = self._recognizer.recognize_google(audio).lower()
                
                for wake_word in self.wake_words:
                    if wake_word in text:
                        logger.info(f"Wake word detected in: {text}")
                        return True
                        
            except sr.UnknownValueError:
                pass  # No speech detected
            except sr.RequestError as e:
                logger.warning(f"Speech recognition error: {e}")
                
        except Exception as e:
            logger.error(f"Wake word detection error: {e}")
        
        return False
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        self._recognizer = None
        logger.debug("Simple wake word detector shutdown")


def create_wake_word_detector(config) -> WakeWordDetector:
    """
    Factory function to create appropriate wake word detector.
    
    Args:
        config: Configuration object
        
    Returns:
        WakeWordDetector instance
    """
    engine = config.get("voice.wake_word.engine", "porcupine")
    
    if engine == "porcupine":
        access_key = config.get("voice.wake_word.porcupine_access_key", "")
        if access_key:
            return PorcupineDetector(config)
        else:
            logger.warning("Porcupine access key not set, falling back to simple detector")
            return SimpleWakeWordDetector(config)
    
    # Default to simple detector
    return SimpleWakeWordDetector(config)
