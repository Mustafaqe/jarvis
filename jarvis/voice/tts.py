"""
JARVIS Text-to-Speech

Converts text responses to natural spoken audio.
"""

import asyncio
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger


class TTSEngine(ABC):
    """Abstract base class for text-to-speech engines."""
    
    @abstractmethod
    async def speak(self, text: str) -> None:
        """
        Convert text to speech and play.
        
        Args:
            text: Text to speak
        """
        pass
    
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        Convert text to audio bytes.
        
        Args:
            text: Text to synthesize
            
        Returns:
            Audio data as bytes
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup resources."""
        pass


class Pyttsx3TTS(TTSEngine):
    """Text-to-speech using pyttsx3 (offline, cross-platform)."""
    
    def __init__(self, config):
        """
        Initialize pyttsx3 TTS.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.voice = config.get("voice.tts.voice")
        self.rate = config.get("voice.tts.rate", 175)
        self.volume = config.get("voice.tts.volume", 0.9)
        
        self._engine = None
        self._lock = asyncio.Lock()
    
    def _get_engine(self):
        """Get or create pyttsx3 engine."""
        if self._engine is None:
            import pyttsx3
            
            self._engine = pyttsx3.init()
            
            # Set properties
            self._engine.setProperty('rate', self.rate)
            self._engine.setProperty('volume', self.volume)
            
            # Set voice if specified
            if self.voice:
                voices = self._engine.getProperty('voices')
                for v in voices:
                    if self.voice.lower() in v.name.lower():
                        self._engine.setProperty('voice', v.id)
                        break
            
            logger.debug("pyttsx3 engine initialized")
        
        return self._engine
    
    async def speak(self, text: str) -> None:
        """Speak text using pyttsx3."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._speak_sync, text)
    
    def _speak_sync(self, text: str) -> None:
        """Synchronous speech."""
        try:
            engine = self._get_engine()
            engine.say(text)
            engine.runAndWait()
            logger.debug(f"Spoke: {text[:50]}...")
        except Exception as e:
            logger.error(f"pyttsx3 error: {e}")
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio bytes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text)
    
    def _synthesize_sync(self, text: str) -> bytes:
        """Synchronous synthesis to file then read."""
        try:
            engine = self._get_engine()
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
            
            engine.save_to_file(text, temp_path)
            engine.runAndWait()
            
            # Read the file
            with open(temp_path, 'rb') as f:
                audio_data = f.read()
            
            Path(temp_path).unlink(missing_ok=True)
            return audio_data
            
        except Exception as e:
            logger.error(f"pyttsx3 synthesis error: {e}")
            return b''
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        if self._engine:
            self._engine.stop()
            self._engine = None


class GTTS_TTS(TTSEngine):
    """Text-to-speech using Google TTS (online)."""
    
    def __init__(self, config):
        """Initialize gTTS."""
        self.config = config
        self.language = config.get("voice.stt.language", "en")[:2]  # Just language code
    
    async def speak(self, text: str) -> None:
        """Speak text using gTTS + pygame for playback."""
        audio_data = await self.synthesize(text)
        if audio_data:
            await self._play_audio(audio_data)
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio bytes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text)
    
    def _synthesize_sync(self, text: str) -> bytes:
        """Synchronous synthesis."""
        try:
            from gtts import gTTS
            from io import BytesIO
            
            tts = gTTS(text=text, lang=self.language, slow=False)
            
            buffer = BytesIO()
            tts.write_to_fp(buffer)
            buffer.seek(0)
            
            return buffer.read()
            
        except Exception as e:
            logger.error(f"gTTS synthesis error: {e}")
            return b''
    
    async def _play_audio(self, audio_data: bytes) -> None:
        """Play audio data."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._play_sync, audio_data)
    
    def _play_sync(self, audio_data: bytes) -> None:
        """Synchronous audio playback."""
        try:
            import tempfile
            import subprocess
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(audio_data)
                temp_path = f.name
            
            # Try different players
            for player in ['mpv', 'ffplay', 'aplay', 'paplay']:
                try:
                    subprocess.run(
                        [player, '-nodisp' if player in ['mpv', 'ffplay'] else '', temp_path],
                        capture_output=True,
                        timeout=30
                    )
                    break
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            
            Path(temp_path).unlink(missing_ok=True)
            
        except Exception as e:
            logger.error(f"Audio playback error: {e}")
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        pass


class EspeakTTS(TTSEngine):
    """Text-to-speech using espeak (offline, Linux)."""
    
    def __init__(self, config):
        """Initialize espeak TTS."""
        self.config = config
        self.voice = config.get("voice.tts.voice", "en")
        self.rate = config.get("voice.tts.rate", 175)
    
    async def speak(self, text: str) -> None:
        """Speak text using espeak."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._speak_sync, text)
    
    def _speak_sync(self, text: str) -> None:
        """Synchronous speech."""
        try:
            import subprocess
            
            subprocess.run(
                ['espeak', '-v', self.voice, '-s', str(self.rate), text],
                capture_output=True,
                timeout=30
            )
            
        except FileNotFoundError:
            logger.error("espeak not installed. Install with: sudo apt install espeak")
        except Exception as e:
            logger.error(f"espeak error: {e}")
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio bytes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text)
    
    def _synthesize_sync(self, text: str) -> bytes:
        """Synchronous synthesis."""
        try:
            import subprocess
            import tempfile
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
            
            subprocess.run(
                ['espeak', '-v', self.voice, '-s', str(self.rate), '-w', temp_path, text],
                capture_output=True,
                timeout=30
            )
            
            with open(temp_path, 'rb') as f:
                audio_data = f.read()
            
            Path(temp_path).unlink(missing_ok=True)
            return audio_data
            
        except Exception as e:
            logger.error(f"espeak synthesis error: {e}")
            return b''
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        pass


class PiperTTS(TTSEngine):
    """Text-to-speech using Piper (fast, high-quality, offline neural TTS)."""
    
    def __init__(self, config):
        """Initialize Piper TTS."""
        self.config = config
        
        # Find piper binary
        base_path = Path(__file__).parent.parent.parent / "models" / "piper"
        self.piper_path = base_path / "piper" / "piper"
        self.model_path = base_path / config.get("voice.tts.piper_model", "en_GB-alan-low.onnx")
        
        if not self.piper_path.exists():
            raise FileNotFoundError(f"Piper binary not found at {self.piper_path}")
        if not self.model_path.exists():
            raise FileNotFoundError(f"Piper model not found at {self.model_path}")
        
        logger.info(f"Using Piper TTS with model: {self.model_path.name}")
    
    async def speak(self, text: str) -> None:
        """Speak text using Piper."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._speak_sync, text)
    
    def _speak_sync(self, text: str) -> None:
        """Synchronous speech."""
        try:
            import subprocess
            
            # Generate audio with piper and pipe to aplay
            piper_env = {
                "LD_LIBRARY_PATH": str(self.piper_path.parent),
            }
            piper_env.update(__import__('os').environ)
            
            # Run piper and play directly
            piper_proc = subprocess.Popen(
                [str(self.piper_path), "--model", str(self.model_path), "--output-raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=piper_env,
            )
            
            aplay_proc = subprocess.Popen(
                ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
                stdin=piper_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            piper_proc.stdin.write(text.encode())
            piper_proc.stdin.close()
            aplay_proc.wait(timeout=30)
            piper_proc.wait(timeout=5)
            
            logger.debug(f"Piper spoke: {text[:50]}...")
            
        except FileNotFoundError as e:
            logger.error(f"Piper not found: {e}")
        except Exception as e:
            logger.error(f"Piper TTS error: {e}")
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio bytes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text)
    
    def _synthesize_sync(self, text: str) -> bytes:
        """Synchronous synthesis."""
        try:
            import subprocess
            
            piper_env = {
                "LD_LIBRARY_PATH": str(self.piper_path.parent),
            }
            piper_env.update(__import__('os').environ)
            
            result = subprocess.run(
                [str(self.piper_path), "--model", str(self.model_path), "--output-raw"],
                input=text.encode(),
                capture_output=True,
                timeout=30,
                env=piper_env,
            )
            
            return result.stdout
            
        except Exception as e:
            logger.error(f"Piper synthesis error: {e}")
            return b''
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        pass


def create_tts_engine(config) -> TTSEngine:
    """
    Factory function to create appropriate TTS engine.
    
    Supports:
    - piper: High-quality neural TTS, offline (recommended)
    - espeak: Offline, Linux (lightweight fallback)
    - pyttsx3: Offline, cross-platform
    - coqui: Natural voice with VITS/XTTS models (Python <3.12 only)
    - elevenlabs: Premium voice quality (requires API key)
    - gtts: Google TTS online
    
    Args:
        config: Configuration object
        
    Returns:
        TTSEngine instance
    """
    engine = config.get("voice.tts.engine", "piper")
    
    # High-quality offline (recommended)
    if engine == "piper":
        try:
            return PiperTTS(config)
        except FileNotFoundError as e:
            logger.warning(f"Piper not available: {e}, falling back to espeak")
            return EspeakTTS(config)
    
    # Basic offline engines
    elif engine == "espeak":
        return EspeakTTS(config)
    
    elif engine == "pyttsx3":
        return Pyttsx3TTS(config)
    
    # Natural TTS engines
    elif engine == "coqui":
        try:
            from jarvis.voice.natural_tts import CoquiTTS
            return CoquiTTS(config)
        except ImportError as e:
            logger.warning(f"Coqui TTS not available: {e}, falling back to espeak")
            return EspeakTTS(config)
    
    elif engine == "elevenlabs":
        try:
            from jarvis.voice.natural_tts import ElevenLabsTTS
            return ElevenLabsTTS(config)
        except ImportError as e:
            logger.warning(f"ElevenLabs not available: {e}, falling back to espeak")
            return EspeakTTS(config)
    
    # Online engine
    elif engine == "gtts":
        return GTTS_TTS(config)
    
    # Default to Piper with fallback to espeak
    try:
        return PiperTTS(config)
    except FileNotFoundError:
        logger.warning(f"Unknown TTS engine '{engine}', using espeak")
        return EspeakTTS(config)
