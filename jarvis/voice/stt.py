"""
JARVIS Speech-to-Text

Converts spoken audio to text using Whisper API or Vosk (offline).
"""

import asyncio
import tempfile
import wave
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger


class STTEngine(ABC):
    """Abstract base class for speech-to-text engines."""
    
    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """
        Transcribe audio to text.
        
        Args:
            audio_data: Raw audio bytes (16-bit, 16kHz, mono)
            
        Returns:
            Transcribed text
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup resources."""
        pass


class WhisperSTT(STTEngine):
    """Speech-to-text using OpenAI Whisper API."""
    
    def __init__(self, config):
        """
        Initialize Whisper STT.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.model = config.get("voice.stt.whisper_model", "whisper-1")
        self.language = config.get("voice.stt.language", "en")
        self._client = None
    
    async def _get_client(self):
        """Get or create OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            api_key = self.config.get("ai.llm.openai_api_key")
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client
    
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio using Whisper API."""
        try:
            client = await self._get_client()
            
            # Save audio to temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
                
                with wave.open(f, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(audio_data)
            
            # Transcribe
            with open(temp_path, 'rb') as audio_file:
                transcript = await client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    language=self.language,
                )
            
            # Cleanup
            Path(temp_path).unlink(missing_ok=True)
            
            text = transcript.text.strip()
            logger.info(f"Whisper transcription: {text}")
            return text
            
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return ""
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        self._client = None


class VoskSTT(STTEngine):
    """Offline speech-to-text using Vosk."""
    
    def __init__(self, config):
        """
        Initialize Vosk STT.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.model_path = config.get(
            "voice.stt.vosk_model_path",
            "models/vosk-model-small-en-us"
        )
        self._model = None
        self._recognizer = None
    
    def _ensure_model(self) -> None:
        """Ensure Vosk model is loaded."""
        if self._model is not None:
            return
        
        try:
            from vosk import Model, KaldiRecognizer
            
            model_path = Path(self.model_path)
            
            if not model_path.exists():
                logger.warning(f"Vosk model not found at {model_path}")
                logger.info("Download a model from https://alphacephei.com/vosk/models")
                raise FileNotFoundError(f"Vosk model not found: {model_path}")
            
            self._model = Model(str(model_path))
            self._recognizer = KaldiRecognizer(self._model, 16000)
            
            logger.info(f"Vosk model loaded: {model_path}")
            
        except ImportError:
            raise ImportError("vosk package required for VoskSTT")
    
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio using Vosk."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_data)
    
    def _transcribe_sync(self, audio_data: bytes) -> str:
        """Synchronous transcription."""
        try:
            import json
            self._ensure_model()
            
            # Process audio
            self._recognizer.AcceptWaveform(audio_data)
            result = json.loads(self._recognizer.FinalResult())
            
            text = result.get('text', '').strip()
            logger.info(f"Vosk transcription: {text}")
            return text
            
        except Exception as e:
            logger.error(f"Vosk transcription error: {e}")
            return ""
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        self._model = None
        self._recognizer = None


class GoogleSTT(STTEngine):
    """Speech-to-text using Google Speech Recognition (free, online)."""
    
    def __init__(self, config):
        """Initialize Google STT."""
        self.config = config
        self.language = config.get("voice.stt.language", "en-US")
    
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe using Google Speech Recognition."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_data)
    
    def _transcribe_sync(self, audio_data: bytes) -> str:
        """Synchronous transcription."""
        try:
            import speech_recognition as sr
            
            recognizer = sr.Recognizer()
            audio = sr.AudioData(audio_data, sample_rate=16000, sample_width=2)
            
            text = recognizer.recognize_google(audio, language=self.language)
            logger.info(f"Google STT transcription: {text}")
            return text
            
        except Exception as e:
            logger.error(f"Google STT error: {e}")
            return ""
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        pass


def create_stt_engine(config) -> STTEngine:
    """
    Factory function to create appropriate STT engine.
    
    Args:
        config: Configuration object
        
    Returns:
        STTEngine instance
    """
    engine = config.get("voice.stt.engine", "google")
    
    if engine == "whisper":
        api_key = config.get("ai.llm.openai_api_key")
        if api_key:
            return WhisperSTT(config)
        else:
            logger.warning("OpenAI API key not set, falling back to Google STT")
            return GoogleSTT(config)
    
    if engine == "vosk":
        return VoskSTT(config)
    
    # Default to Google (free, online)
    return GoogleSTT(config)
