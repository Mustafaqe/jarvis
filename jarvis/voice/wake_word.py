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


class VoskWakeWordDetector(WakeWordDetector):
    """
    Wake word detection using Vosk offline speech recognition.
    
    This is a safer alternative to SimpleWakeWordDetector that works offline
    and doesn't have the threading issues that cause memory corruption.
    """
    
    def __init__(self, config):
        """Initialize Vosk detector."""
        self.config = config
        self.wake_words = [w.lower() for w in config.get("core.wake_words", ["jarvis"])]
        self.model_path = config.get(
            "voice.stt.vosk_model_path",
            "models/vosk-model-small-en-us"
        )
        self._model = None
        self._recognizer = None
    
    def initialize(self) -> None:
        """Initialize Vosk model for wake word detection."""
        try:
            from vosk import Model, KaldiRecognizer, SetLogLevel
            
            # Suppress Vosk logs
            SetLogLevel(-1)
            
            model_path = Path(self.model_path)
            
            if not model_path.exists():
                logger.warning(f"Vosk model not found at {model_path}, falling back to audio-level detection")
                self._model = None
                return
            
            self._model = Model(str(model_path))
            self._recognizer = KaldiRecognizer(self._model, 16000)
            
            logger.info(f"Vosk wake word detector initialized: {self.wake_words}")
            
        except ImportError:
            logger.warning("vosk package not installed, falling back to audio-level detection")
            self._model = None
        except Exception as e:
            logger.warning(f"Vosk initialization failed: {e}, falling back to audio-level detection")
            self._model = None
    
    def process(self, audio_data: bytes) -> bool:
        """Process audio looking for wake word using Vosk."""
        # If Vosk not available, use simple audio level detection
        if not self._recognizer:
            return self._simple_audio_detect(audio_data)
        
        try:
            import json
            
            # Process with Vosk
            if self._recognizer.AcceptWaveform(audio_data):
                result = json.loads(self._recognizer.Result())
                text = result.get('text', '').lower()
                
                for wake_word in self.wake_words:
                    if wake_word in text:
                        logger.info(f"Wake word detected in: {text}")
                        return True
            else:
                # Check partial results too
                partial = json.loads(self._recognizer.PartialResult())
                text = partial.get('partial', '').lower()
                
                for wake_word in self.wake_words:
                    if wake_word in text:
                        logger.info(f"Wake word detected in partial: {text}")
                        # Reset recognizer after detection
                        self._recognizer.Reset()
                        return True
                        
        except Exception as e:
            logger.debug(f"Vosk wake word detection error: {e}")
        
        return False
    
    def _simple_audio_detect(self, audio_data: bytes) -> bool:
        """
        Simple audio level detection as last resort.
        
        This just detects when there's significant audio activity,
        treating any loud enough sound as a potential wake word.
        Not recommended but works as a fallback.
        """
        import struct
        
        if len(audio_data) < 2:
            return False
        
        # Calculate RMS
        count = len(audio_data) // 2
        shorts = struct.unpack(f'{count}h', audio_data)
        rms = (sum(s ** 2 for s in shorts) / count) ** 0.5
        
        # High threshold to avoid false positives
        threshold = 2000
        
        if rms > threshold:
            logger.info(f"Audio activity detected (RMS: {rms:.0f})")
            return True
        
        return False
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        self._model = None
        self._recognizer = None
        logger.debug("Vosk wake word detector shutdown")


class SimpleWakeWordDetector(WakeWordDetector):
    """
    Simple wake word detection based on audio level.
    
    This is a basic fallback that just detects when someone speaks.
    For proper wake word detection, use Porcupine or VoskWakeWordDetector.
    """
    
    def __init__(self, config):
        """Initialize simple detector."""
        self.config = config
        self.wake_words = [w.lower() for w in config.get("core.wake_words", ["jarvis"])]
        self._active = False
        self._speech_threshold = 1500  # RMS threshold for speech
        self._speech_frames = 0
        self._min_speech_frames = 3  # Minimum frames of speech before triggering
    
    def initialize(self) -> None:
        """Initialize simple detector."""
        self._active = True
        logger.info(f"Simple wake word detector initialized (audio-level based): {self.wake_words}")
        logger.warning("Audio-level detection is active. Say anything loudly to trigger. For better accuracy, set up Porcupine or Vosk.")
    
    def process(self, audio_data: bytes) -> bool:
        """Process audio looking for sustained speech activity."""
        if not self._active:
            return False
        
        import struct
        
        if len(audio_data) < 2:
            return False
        
        # Calculate RMS
        count = len(audio_data) // 2
        shorts = struct.unpack(f'{count}h', audio_data)
        rms = (sum(s ** 2 for s in shorts) / count) ** 0.5
        
        if rms > self._speech_threshold:
            self._speech_frames += 1
            if self._speech_frames >= self._min_speech_frames:
                logger.info(f"Speech activity detected (triggering wake word)")
                self._speech_frames = 0
                return True
        else:
            self._speech_frames = 0
        
        return False
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        self._active = False
        logger.debug("Simple wake word detector shutdown")


def create_wake_word_detector(config) -> WakeWordDetector:
    """
    Factory function to create appropriate wake word detector.
    
    Priority: Porcupine > Vosk > Simple (audio-level)
    
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
            logger.warning("Porcupine access key not set, falling back to Vosk detector")
            return VoskWakeWordDetector(config)
    
    if engine == "vosk":
        return VoskWakeWordDetector(config)
    
    # Default to Vosk (safer than simple, works offline)
    return VoskWakeWordDetector(config)

