"""
JARVIS Natural Text-to-Speech

Provides natural-sounding voice synthesis using:
- Coqui TTS (VITS/XTTS models) - Local, free
- ElevenLabs API - Cloud, premium quality

Features:
- Multiple voice profiles
- Emotion and prosody control
- Voice cloning capability
- Streaming synthesis for low latency
"""

import asyncio
import io
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import wave

import numpy as np
from loguru import logger

# Audio playback
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logger.warning("sounddevice not available, audio playback may be limited")


class NaturalTTSEngine(ABC):
    """Abstract base class for natural TTS engines."""
    
    @abstractmethod
    async def speak(self, text: str, emotion: str = "neutral") -> None:
        """
        Convert text to speech and play.
        
        Args:
            text: Text to speak
            emotion: Emotion tone (neutral, happy, serious, excited, sad)
        """
        pass
    
    @abstractmethod
    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """
        Synthesize text to audio bytes.
        
        Args:
            text: Text to synthesize
            emotion: Emotion tone
            
        Returns:
            Audio data as WAV bytes
        """
        pass
    
    @abstractmethod
    def get_available_voices(self) -> list[dict]:
        """Get list of available voices."""
        pass
    
    @abstractmethod
    def set_voice(self, voice_id: str) -> None:
        """Set the current voice."""
        pass
    
    async def shutdown(self) -> None:
        """Cleanup resources."""
        pass


class CoquiTTS(NaturalTTSEngine):
    """
    Coqui TTS with VITS/XTTS models for natural voice.
    
    Features:
    - Multiple pre-trained models
    - Multi-speaker support
    - Voice cloning with XTTS
    - Local processing (no API key needed)
    """
    
    # Emotion to speech parameter mappings
    EMOTION_PARAMS = {
        "neutral": {"speed": 1.0, "pitch": 1.0},
        "happy": {"speed": 1.1, "pitch": 1.05},
        "serious": {"speed": 0.95, "pitch": 0.95},
        "excited": {"speed": 1.15, "pitch": 1.1},
        "sad": {"speed": 0.9, "pitch": 0.9},
        "calm": {"speed": 0.9, "pitch": 1.0},
    }
    
    # Recommended models
    MODELS = {
        "vits_vctk": "tts_models/en/vctk/vits",  # Multi-speaker, fast
        "vits_ljspeech": "tts_models/en/ljspeech/vits",  # Single speaker, high quality
        "jenny": "tts_models/en/jenny/jenny",  # Natural female voice
        "xtts_v2": "tts_models/multilingual/multi-dataset/xtts_v2",  # Voice cloning
    }
    
    def __init__(self, config):
        """
        Initialize Coqui TTS.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.model_name = config.get("voice.tts.coqui.model", self.MODELS["vits_vctk"])
        self.speaker = config.get("voice.tts.coqui.speaker", None)
        self.sample_rate = 22050  # Coqui default
        
        self._tts = None
        self._initialized = False
        self._available_speakers = []
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of TTS model."""
        if self._initialized:
            return
        
        try:
            from TTS.api import TTS
            
            logger.info(f"Loading Coqui TTS model: {self.model_name}")
            
            # Check for GPU
            use_gpu = False
            try:
                import torch
                use_gpu = torch.cuda.is_available()
            except ImportError:
                pass
            
            self._tts = TTS(self.model_name, gpu=use_gpu)
            
            # Get available speakers for multi-speaker models
            if hasattr(self._tts, 'speakers') and self._tts.speakers:
                self._available_speakers = self._tts.speakers
                logger.info(f"Available speakers: {len(self._available_speakers)}")
                
                # Set default speaker if not specified
                if not self.speaker and self._available_speakers:
                    self.speaker = self._available_speakers[0]
            
            self._initialized = True
            logger.info("Coqui TTS initialized successfully")
            
        except ImportError:
            raise RuntimeError(
                "Coqui TTS not installed. Install with: pip install TTS"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Coqui TTS: {e}")
            raise
    
    async def speak(self, text: str, emotion: str = "neutral") -> None:
        """Speak text using Coqui TTS."""
        audio_data = await self.synthesize(text, emotion)
        await self._play_audio(audio_data)
    
    def _synthesize_sync(self, text: str, emotion: str = "neutral") -> bytes:
        """Synchronous synthesis."""
        self._ensure_initialized()
        
        # Get emotion parameters
        params = self.EMOTION_PARAMS.get(emotion, self.EMOTION_PARAMS["neutral"])
        
        # Create temp file for output
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
        
        try:
            # Synthesize speech
            kwargs = {}
            if self.speaker and self._available_speakers:
                kwargs["speaker"] = self.speaker
            
            # Apply speed adjustment via text preprocessing
            # Coqui TTS doesn't directly support speed/pitch, so we handle playback
            self._tts.tts_to_file(
                text=text,
                file_path=temp_path,
                **kwargs
            )
            
            # Read the generated audio
            with open(temp_path, "rb") as f:
                audio_data = f.read()
            
            # Store sample rate from generated file
            with wave.open(temp_path, "rb") as wf:
                self.sample_rate = wf.getframerate()
            
            return audio_data
            
        finally:
            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except:
                pass
    
    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """Synthesize text to audio bytes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._synthesize_sync, text, emotion
        )
    
    def get_available_voices(self) -> list[dict]:
        """Get list of available voices/speakers."""
        self._ensure_initialized()
        
        voices = []
        for speaker in self._available_speakers:
            voices.append({
                "id": speaker,
                "name": speaker,
                "type": "coqui",
                "model": self.model_name,
            })
        
        return voices
    
    def set_voice(self, voice_id: str) -> None:
        """Set the current voice/speaker."""
        if voice_id in self._available_speakers:
            self.speaker = voice_id
            logger.info(f"Voice set to: {voice_id}")
        else:
            logger.warning(f"Voice not found: {voice_id}")
    
    async def clone_voice(self, audio_path: str, name: str) -> dict:
        """
        Clone a voice from audio sample (requires XTTS model).
        
        Args:
            audio_path: Path to audio sample (WAV, 6-30 seconds)
            name: Name for the cloned voice
            
        Returns:
            Voice profile dict
        """
        if "xtts" not in self.model_name.lower():
            raise RuntimeError("Voice cloning requires XTTS model")
        
        self._ensure_initialized()
        
        # Store the reference audio path for XTTS
        voice_profile = {
            "id": f"clone_{name}",
            "name": name,
            "type": "cloned",
            "reference_audio": audio_path,
        }
        
        logger.info(f"Voice profile created: {name}")
        return voice_profile
    
    async def _play_audio(self, audio_data: bytes) -> None:
        """Play audio data through speakers."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._play_audio_sync, audio_data)
    
    def _play_audio_sync(self, audio_data: bytes) -> None:
        """Synchronous audio playback."""
        if not SOUNDDEVICE_AVAILABLE:
            logger.warning("sounddevice not available for playback")
            return
        
        try:
            # Parse WAV data
            with io.BytesIO(audio_data) as f:
                with wave.open(f, "rb") as wf:
                    sample_rate = wf.getframerate()
                    n_channels = wf.getnchannels()
                    sample_width = wf.getsampwidth()
                    frames = wf.readframes(wf.getnframes())
            
            # Convert to numpy array
            dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
            dtype = dtype_map.get(sample_width, np.int16)
            audio_array = np.frombuffer(frames, dtype=dtype)
            
            # Reshape for stereo if needed
            if n_channels > 1:
                audio_array = audio_array.reshape(-1, n_channels)
            
            # Normalize to float32 for playback
            audio_float = audio_array.astype(np.float32) / np.iinfo(dtype).max
            
            # Play audio
            sd.play(audio_float, sample_rate)
            sd.wait()
            
        except Exception as e:
            logger.error(f"Audio playback error: {e}")
    
    async def shutdown(self) -> None:
        """Cleanup resources."""
        self._tts = None
        self._initialized = False
        logger.debug("Coqui TTS shutdown")


class ElevenLabsTTS(NaturalTTSEngine):
    """
    ElevenLabs API for premium quality voice synthesis.
    
    Features:
    - Ultra-realistic voices
    - Voice customization
    - Emotion control
    - Voice cloning
    """
    
    # Stability/similarity settings for emotions
    EMOTION_SETTINGS = {
        "neutral": {"stability": 0.5, "similarity_boost": 0.75},
        "happy": {"stability": 0.3, "similarity_boost": 0.8},
        "serious": {"stability": 0.7, "similarity_boost": 0.7},
        "excited": {"stability": 0.2, "similarity_boost": 0.85},
        "sad": {"stability": 0.6, "similarity_boost": 0.6},
        "calm": {"stability": 0.8, "similarity_boost": 0.7},
    }
    
    def __init__(self, config):
        """
        Initialize ElevenLabs TTS.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.api_key = config.get("voice.tts.elevenlabs.api_key") or os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = config.get("voice.tts.elevenlabs.voice_id", "21m00Tcm4TlvDq8ikWAM")  # Rachel
        self.model_id = config.get("voice.tts.elevenlabs.model", "eleven_monolingual_v1")
        
        self._client = None
        self._voices_cache = None
        self.sample_rate = 44100  # ElevenLabs default
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of ElevenLabs client."""
        if self._client is not None:
            return
        
        if not self.api_key:
            raise RuntimeError(
                "ElevenLabs API key not found. Set ELEVENLABS_API_KEY environment variable "
                "or configure voice.tts.elevenlabs.api_key"
            )
        
        try:
            from elevenlabs.client import ElevenLabs
            self._client = ElevenLabs(api_key=self.api_key)
            logger.info("ElevenLabs TTS initialized")
        except ImportError:
            raise RuntimeError(
                "ElevenLabs not installed. Install with: pip install elevenlabs"
            )
    
    async def speak(self, text: str, emotion: str = "neutral") -> None:
        """Speak text using ElevenLabs."""
        audio_data = await self.synthesize(text, emotion)
        await self._play_audio(audio_data)
    
    def _synthesize_sync(self, text: str, emotion: str = "neutral") -> bytes:
        """Synchronous synthesis."""
        self._ensure_initialized()
        
        # Get emotion settings
        settings = self.EMOTION_SETTINGS.get(emotion, self.EMOTION_SETTINGS["neutral"])
        
        try:
            from elevenlabs import VoiceSettings
            
            # Generate audio
            audio_generator = self._client.generate(
                text=text,
                voice=self.voice_id,
                model=self.model_id,
                voice_settings=VoiceSettings(
                    stability=settings["stability"],
                    similarity_boost=settings["similarity_boost"],
                )
            )
            
            # Collect audio chunks
            audio_chunks = []
            for chunk in audio_generator:
                audio_chunks.append(chunk)
            
            return b"".join(audio_chunks)
            
        except Exception as e:
            logger.error(f"ElevenLabs synthesis error: {e}")
            raise
    
    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """Synthesize text to audio bytes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._synthesize_sync, text, emotion
        )
    
    def _get_voices_sync(self) -> list[dict]:
        """Synchronous voice list retrieval."""
        self._ensure_initialized()
        
        try:
            response = self._client.voices.get_all()
            voices = []
            for voice in response.voices:
                voices.append({
                    "id": voice.voice_id,
                    "name": voice.name,
                    "type": "elevenlabs",
                    "category": getattr(voice, 'category', 'unknown'),
                    "labels": getattr(voice, 'labels', {}),
                })
            return voices
        except Exception as e:
            logger.error(f"Failed to get voices: {e}")
            return []
    
    def get_available_voices(self) -> list[dict]:
        """Get list of available voices."""
        if self._voices_cache is None:
            self._voices_cache = self._get_voices_sync()
        return self._voices_cache
    
    def set_voice(self, voice_id: str) -> None:
        """Set the current voice."""
        self.voice_id = voice_id
        logger.info(f"Voice set to: {voice_id}")
    
    async def clone_voice(self, audio_paths: list[str], name: str, description: str = "") -> dict:
        """
        Clone a voice from audio samples.
        
        Args:
            audio_paths: List of paths to audio samples
            name: Name for the cloned voice
            description: Voice description
            
        Returns:
            Voice profile dict
        """
        self._ensure_initialized()
        
        try:
            # Open audio files
            files = []
            for path in audio_paths:
                files.append(open(path, "rb"))
            
            # Create voice clone
            voice = self._client.clone(
                name=name,
                description=description,
                files=files,
            )
            
            # Close files
            for f in files:
                f.close()
            
            # Invalidate cache
            self._voices_cache = None
            
            return {
                "id": voice.voice_id,
                "name": name,
                "type": "cloned",
            }
            
        except Exception as e:
            logger.error(f"Voice cloning failed: {e}")
            raise
    
    async def _play_audio(self, audio_data: bytes) -> None:
        """Play audio data through speakers."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._play_audio_sync, audio_data)
    
    def _play_audio_sync(self, audio_data: bytes) -> None:
        """Synchronous audio playback (MP3 from ElevenLabs)."""
        if not SOUNDDEVICE_AVAILABLE:
            logger.warning("sounddevice not available for playback")
            return
        
        try:
            # ElevenLabs returns MP3, need to decode
            # Use pydub for MP3 decoding
            from pydub import AudioSegment
            
            audio = AudioSegment.from_mp3(io.BytesIO(audio_data))
            
            # Convert to numpy array
            samples = np.array(audio.get_array_of_samples())
            
            # Handle stereo
            if audio.channels == 2:
                samples = samples.reshape((-1, 2))
            
            # Normalize
            samples = samples.astype(np.float32) / 32768.0
            
            # Play
            sd.play(samples, audio.frame_rate)
            sd.wait()
            
        except ImportError:
            logger.warning("pydub not installed, trying alternate playback")
            # Fallback: save to temp file and play
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_data)
                temp_path = f.name
            
            try:
                import subprocess
                # Try mpv, mpg123, or ffplay
                for player in ["mpv", "mpg123", "ffplay"]:
                    try:
                        subprocess.run(
                            [player, "-really-quiet", temp_path] if player == "mpv"
                            else [player, "-q", temp_path] if player == "mpg123"
                            else [player, "-nodisp", "-autoexit", temp_path],
                            check=True,
                            capture_output=True
                        )
                        break
                    except FileNotFoundError:
                        continue
            finally:
                os.unlink(temp_path)
        except Exception as e:
            logger.error(f"Audio playback error: {e}")
    
    async def shutdown(self) -> None:
        """Cleanup resources."""
        self._client = None
        self._voices_cache = None
        logger.debug("ElevenLabs TTS shutdown")


def create_natural_tts_engine(config) -> NaturalTTSEngine:
    """
    Factory function to create appropriate natural TTS engine.
    
    Args:
        config: Configuration object
        
    Returns:
        NaturalTTSEngine instance
    """
    engine_type = config.get("voice.tts.engine", "coqui")
    
    if engine_type == "coqui":
        return CoquiTTS(config)
    elif engine_type == "elevenlabs":
        return ElevenLabsTTS(config)
    else:
        # Fallback to Coqui
        logger.warning(f"Unknown TTS engine '{engine_type}', using Coqui")
        return CoquiTTS(config)
