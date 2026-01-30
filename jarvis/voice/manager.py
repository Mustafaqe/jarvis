"""
JARVIS Voice Manager

Coordinates wake word detection, speech-to-text, and text-to-speech
for the complete voice interface.
"""

import asyncio

from loguru import logger

from jarvis.core.events import EventBus, EventType
from jarvis.voice.audio import AudioManager
from jarvis.voice.wake_word import create_wake_word_detector
from jarvis.voice.stt import create_stt_engine
from jarvis.voice.tts import create_tts_engine


class VoiceManager:
    """
    Manages the complete voice interface pipeline.
    
    Pipeline:
    1. Wait for wake word
    2. Record user speech
    3. Transcribe to text (STT)
    4. Emit event for processing
    5. Speak response (TTS)
    """
    
    def __init__(self, config, event_bus: EventBus):
        """
        Initialize voice manager.
        
        Args:
            config: Configuration object
            event_bus: Event bus for communication
        """
        self.config = config
        self.event_bus = event_bus
        
        # Voice components
        self.audio = AudioManager(config)
        self.wake_word = None
        self.stt = None
        self.tts = None
        
        # State
        self._initialized = False
        self._listening = False
        self._speaking = False
        
        # Settings
        self.continuous_mode = config.get("voice.continuous_mode", True)
        self.confirmation_sound = config.get("voice.confirmation_sound", True)
    
    async def initialize(self) -> None:
        """Initialize all voice components."""
        if self._initialized:
            return
        
        logger.info("Initializing voice system...")
        
        # Initialize audio
        self.audio.initialize()
        
        # Initialize wake word detector
        self.wake_word = create_wake_word_detector(self.config)
        self.wake_word.initialize()
        
        # Initialize STT
        self.stt = create_stt_engine(self.config)
        
        # Initialize TTS
        self.tts = create_tts_engine(self.config)
        
        # Subscribe to response events
        self.event_bus.subscribe(EventType.ASSISTANT_RESPONSE, self._on_response)
        
        self._initialized = True
        logger.info("Voice system initialized successfully")
    
    async def listen(self) -> None:
        """
        Main listening loop.
        
        Waits for wake word, then records and processes user speech.
        """
        if not self._initialized:
            await self.initialize()
        
        self._listening = True
        
        logger.info("👂 Listening for wake word...")
        
        while self._listening:
            try:
                # Wait for wake word
                detected = await self._wait_for_wake_word()
                
                if not detected:
                    continue
                
                # Wake word detected!
                await self.event_bus.emit(
                    EventType.WAKE_WORD_DETECTED,
                    source="voice"
                )
                
                # Play confirmation beep
                if self.confirmation_sound:
                    await self._play_confirmation()
                
                # Record user speech
                logger.info("🎤 Listening for command...")
                await self.event_bus.emit(EventType.SPEECH_START, source="voice")
                
                audio_data = await self.audio.record_audio_async(
                    duration=10,  # Max 10 seconds
                    stop_on_silence=True,
                    silence_threshold=500,
                    silence_duration=1.5,
                )
                
                await self.event_bus.emit(EventType.SPEECH_END, source="voice")
                
                if not audio_data or len(audio_data) < 1000:
                    logger.debug("No speech detected")
                    continue
                
                # Transcribe
                text = await self.stt.transcribe(audio_data)
                
                if not text:
                    logger.debug("Empty transcription")
                    continue
                
                await self.event_bus.emit(
                    EventType.TRANSCRIPTION_COMPLETE,
                    {"text": text},
                    source="voice"
                )
                
                # Emit user input event for processing
                await self.event_bus.emit(
                    EventType.USER_INPUT,
                    {"text": text, "source": "voice"},
                    source="voice"
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Voice loop error: {e}")
                await asyncio.sleep(1)
    
    async def _wait_for_wake_word(self) -> bool:
        """
        Wait for wake word detection.
        
        Returns:
            True if wake word detected
        """
        # Stream audio and check for wake word
        chunk_count = 0
        chunks_to_process = 16000 // self.audio.chunk_size * 2  # 2 seconds of audio
        
        audio_buffer = b''
        
        for chunk in self.audio.stream_audio():
            if not self._listening:
                return False
            
            audio_buffer += chunk
            chunk_count += 1
            
            # Check periodically
            if chunk_count >= chunks_to_process:
                # Check for wake word
                if self.wake_word.process(audio_buffer):
                    return True
                
                # Keep last second of audio for overlap
                keep_bytes = self.audio.sample_rate * 2  # 1 second of 16-bit audio
                if len(audio_buffer) > keep_bytes:
                    audio_buffer = audio_buffer[-keep_bytes:]
                
                chunk_count = 0
            
            # Small yield to prevent blocking
            await asyncio.sleep(0)
        
        return False
    
    async def _play_confirmation(self) -> None:
        """Play a confirmation sound when wake word is detected."""
        try:
            # Generate a simple beep
            import struct
            import math
            
            sample_rate = 16000
            duration = 0.15  # seconds
            frequency = 880  # Hz
            
            samples = int(sample_rate * duration)
            data = []
            
            for i in range(samples):
                # Fade in/out to prevent clicks
                t = i / sample_rate
                envelope = min(1.0, min(t * 20, (duration - t) * 20))
                value = int(16000 * envelope * math.sin(2 * math.pi * frequency * t))
                data.append(struct.pack('<h', value))
            
            audio_data = b''.join(data)
            await self.audio.play_audio_async(audio_data)
            
        except Exception as e:
            logger.debug(f"Could not play confirmation: {e}")
    
    async def speak(self, text: str) -> None:
        """
        Speak text through TTS.
        
        Args:
            text: Text to speak
        """
        if not self.tts:
            logger.warning("TTS not initialized")
            return
        
        if not text:
            return
        
        self._speaking = True
        
        try:
            await self.event_bus.emit(
                EventType.TTS_START,
                {"text": text},
                source="voice"
            )
            
            await self.tts.speak(text)
            
            await self.event_bus.emit(
                EventType.TTS_COMPLETE,
                {"text": text},
                source="voice"
            )
            
        except Exception as e:
            logger.error(f"TTS error: {e}")
        finally:
            self._speaking = False
    
    async def _on_response(self, event) -> None:
        """Handle assistant response events."""
        text = event.data.get("text", "")
        if text and event.source != "voice":
            await self.speak(text)
    
    def stop_listening(self) -> None:
        """Stop the listening loop."""
        self._listening = False
    
    async def shutdown(self) -> None:
        """Cleanup voice resources."""
        logger.info("Shutting down voice system...")
        
        self._listening = False
        
        if self.wake_word:
            self.wake_word.shutdown()
        
        if self.stt:
            self.stt.shutdown()
        
        if self.tts:
            self.tts.shutdown()
        
        if self.audio:
            self.audio.shutdown()
        
        self._initialized = False
        logger.info("Voice system shutdown complete")
