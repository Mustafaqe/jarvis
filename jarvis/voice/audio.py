"""
JARVIS Audio I/O Management

Handles microphone input, speaker output, and audio stream management.
"""

import asyncio
import wave
from pathlib import Path
from typing import Generator

import pyaudio
from loguru import logger


class AudioManager:
    """
    Manages audio input/output streams.
    
    Provides:
    - Microphone input with device selection
    - Audio recording and playback
    - Stream management
    """
    
    def __init__(self, config):
        """
        Initialize audio manager.
        
        Args:
            config: Configuration object
        """
        self.config = config
        
        # Audio settings
        self.sample_rate = config.get("voice.audio.sample_rate", 16000)
        self.channels = config.get("voice.audio.channels", 1)
        self.chunk_size = config.get("voice.audio.chunk_size", 1024)
        self.format = pyaudio.paInt16
        
        # Device selection
        self.input_device = config.get("voice.audio.input_device")
        self.output_device = config.get("voice.audio.output_device")
        
        self._pyaudio: pyaudio.PyAudio | None = None
        self._input_stream: pyaudio.Stream | None = None
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize PyAudio and select devices."""
        if self._initialized:
            return
        
        self._pyaudio = pyaudio.PyAudio()
        
        # Auto-detect best input device
        if self.input_device is None:
            self.input_device = self._find_best_input_device()
        
        self._initialized = True
        logger.info(f"Audio initialized - Input device: {self.input_device}")
    
    def _find_best_input_device(self) -> int | None:
        """Find the best available input device, preferring USB microphones."""
        if not self._pyaudio:
            return None
        
        usb_device = None
        default_device = None
        
        for i in range(self._pyaudio.get_device_count()):
            info = self._pyaudio.get_device_info_by_index(i)
            
            if info['maxInputChannels'] > 0:
                name = info['name'].lower()
                
                # Prefer USB microphones
                if 'usb' in name:
                    usb_device = i
                    logger.debug(f"Found USB microphone: {info['name']}")
                
                # Track default device
                if default_device is None:
                    default_device = i
        
        selected = usb_device if usb_device is not None else default_device
        
        if selected is not None:
            info = self._pyaudio.get_device_info_by_index(selected)
            logger.info(f"Selected input device: {info['name']}")
        
        return selected
    
    def list_devices(self) -> list[dict]:
        """List all audio devices."""
        if not self._pyaudio:
            self.initialize()
        
        devices = []
        for i in range(self._pyaudio.get_device_count()):
            info = self._pyaudio.get_device_info_by_index(i)
            devices.append({
                'index': i,
                'name': info['name'],
                'input_channels': info['maxInputChannels'],
                'output_channels': info['maxOutputChannels'],
                'sample_rate': int(info['defaultSampleRate']),
            })
        
        return devices
    
    def open_input_stream(self) -> pyaudio.Stream:
        """Open an input stream for recording."""
        if not self._initialized:
            self.initialize()
        
        stream = self._pyaudio.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.input_device,
            frames_per_buffer=self.chunk_size,
        )
        
        return stream
    
    def record_audio(
        self,
        duration: float | None = None,
        stop_on_silence: bool = True,
        silence_threshold: int = 500,
        silence_duration: float = 1.5,
    ) -> bytes:
        """
        Record audio from microphone.
        
        Args:
            duration: Max recording duration in seconds (None for unlimited)
            stop_on_silence: Stop recording after silence detected
            silence_threshold: Audio level threshold for silence
            silence_duration: Duration of silence before stopping
            
        Returns:
            Recorded audio data as bytes
        """
        stream = self.open_input_stream()
        frames = []
        
        silent_chunks = 0
        chunks_per_second = self.sample_rate / self.chunk_size
        max_silent_chunks = int(silence_duration * chunks_per_second)
        max_chunks = int(duration * chunks_per_second) if duration else float('inf')
        
        try:
            chunk_count = 0
            while chunk_count < max_chunks:
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                frames.append(data)
                chunk_count += 1
                
                # Check for silence
                if stop_on_silence:
                    audio_level = self._get_audio_level(data)
                    
                    if audio_level < silence_threshold:
                        silent_chunks += 1
                        if silent_chunks >= max_silent_chunks and len(frames) > chunks_per_second:
                            logger.debug("Silence detected, stopping recording")
                            break
                    else:
                        silent_chunks = 0
        finally:
            stream.stop_stream()
            stream.close()
        
        return b''.join(frames)
    
    def _get_audio_level(self, data: bytes) -> int:
        """Calculate audio level from raw data."""
        import struct
        
        count = len(data) // 2
        format_str = f"{count}h"
        shorts = struct.unpack(format_str, data)
        
        # RMS calculation
        sum_squares = sum(s ** 2 for s in shorts)
        rms = (sum_squares / count) ** 0.5
        
        return int(rms)
    
    async def record_audio_async(
        self,
        duration: float | None = None,
        stop_on_silence: bool = True,
        silence_threshold: int = 500,
        silence_duration: float = 1.5,
    ) -> bytes:
        """Async wrapper for record_audio."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.record_audio(
                duration, stop_on_silence, silence_threshold, silence_duration
            )
        )
    
    def stream_audio(self) -> Generator[bytes, None, None]:
        """Stream audio chunks from microphone."""
        stream = self.open_input_stream()
        
        try:
            while True:
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                yield data
        finally:
            stream.stop_stream()
            stream.close()
    
    def save_audio(self, audio_data: bytes, path: str | Path) -> Path:
        """
        Save audio data to a WAV file.
        
        Args:
            audio_data: Raw audio bytes
            path: Output file path
            
        Returns:
            Path to saved file
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with wave.open(str(path), 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self._pyaudio.get_sample_size(self.format))
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data)
        
        logger.debug(f"Saved audio to {path}")
        return path
    
    def play_audio(self, audio_data: bytes) -> None:
        """Play audio data through speakers."""
        if not self._initialized:
            self.initialize()
        
        stream = self._pyaudio.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            output=True,
            output_device_index=self.output_device,
        )
        
        try:
            stream.write(audio_data)
        finally:
            stream.stop_stream()
            stream.close()
    
    async def play_audio_async(self, audio_data: bytes) -> None:
        """Async wrapper for play_audio."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.play_audio, audio_data)
    
    def shutdown(self) -> None:
        """Cleanup audio resources."""
        if self._input_stream:
            self._input_stream.stop_stream()
            self._input_stream.close()
            self._input_stream = None
        
        if self._pyaudio:
            self._pyaudio.terminate()
            self._pyaudio = None
        
        self._initialized = False
        logger.debug("Audio manager shutdown complete")
