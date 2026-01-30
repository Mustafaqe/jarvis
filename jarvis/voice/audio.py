"""
JARVIS Audio I/O Management

Handles microphone input, speaker output, and audio stream management.
Uses sounddevice library for better compatibility with modern systems.
"""

import asyncio
import queue
import threading
import wave
from pathlib import Path
from typing import Generator

import numpy as np
import sounddevice as sd
from loguru import logger


class AudioManager:
    """
    Manages audio input/output streams using sounddevice.
    
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
        
        # Device selection
        self.input_device = config.get("voice.audio.input_device")
        self.output_device = config.get("voice.audio.output_device")
        
        # Track the device's native sample rate (may differ from target)
        self.device_sample_rate = self.sample_rate
        self.needs_resampling = False
        
        self._audio_queue: queue.Queue | None = None
        self._stream_lock = threading.Lock()
        self._initialized = False
        self._stop_streaming = False
    
    def initialize(self) -> None:
        """Initialize audio system and select devices."""
        if self._initialized:
            return
        
        # Auto-detect best input device
        if self.input_device is None:
            self.input_device = self._find_best_input_device()
        
        self._initialized = True
        logger.info(f"Audio initialized - Input device: {self.input_device}")
    
    def _find_best_input_device(self) -> int | None:
        """Find the best available input device, preferring USB microphones."""
        usb_device = None
        default_device = None
        
        try:
            devices = sd.query_devices()
            
            for i, info in enumerate(devices):
                try:
                    if info['max_input_channels'] > 0:
                        name = info['name'].lower()
                        
                        # Prefer USB microphones
                        if 'usb' in name:
                            usb_device = i
                            logger.debug(f"Found USB microphone: {info['name']}")
                        
                        # Track default device
                        if default_device is None:
                            default_device = i
                except Exception as e:
                    logger.debug(f"Could not get info for device {i}: {e}")
            
            selected = usb_device if usb_device is not None else default_device
            
            if selected is not None:
                info = sd.query_devices(selected)
                logger.info(f"Selected input device: {info['name']}")
                
                # Check the device's native sample rate
                device_rate = int(info['default_samplerate'])
                
                # Test if device supports our target rate
                if self._test_sample_rate(selected, self.sample_rate):
                    logger.info(f"Device supports target sample rate: {self.sample_rate} Hz")
                    self.device_sample_rate = self.sample_rate
                    self.needs_resampling = False
                elif self._test_sample_rate(selected, device_rate):
                    logger.info(f"Device uses native rate {device_rate} Hz, will resample to {self.sample_rate} Hz")
                    self.device_sample_rate = device_rate
                    self.needs_resampling = True
                else:
                    # Try common sample rates
                    for rate in [48000, 44100, 32000, 22050]:
                        if self._test_sample_rate(selected, rate):
                            logger.info(f"Device supports {rate} Hz, will resample to {self.sample_rate} Hz")
                            self.device_sample_rate = rate
                            self.needs_resampling = True
                            break
            
            return selected
            
        except Exception as e:
            logger.error(f"Error finding input device: {e}")
            return None
    
    def _test_sample_rate(self, device_index: int, sample_rate: int) -> bool:
        """Test if a device supports a specific sample rate."""
        try:
            sd.check_input_settings(
                device=device_index,
                channels=self.channels,
                dtype='int16',
                samplerate=sample_rate
            )
            return True
        except sd.PortAudioError:
            return False
        except Exception as e:
            logger.debug(f"Sample rate test error: {e}")
            return False
    
    def list_devices(self) -> list[dict]:
        """List all audio devices."""
        devices = []
        try:
            device_list = sd.query_devices()
            for i, info in enumerate(device_list):
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'input_channels': info['max_input_channels'],
                    'output_channels': info['max_output_channels'],
                    'sample_rate': int(info['default_samplerate']),
                })
        except Exception as e:
            logger.error(f"Error listing devices: {e}")
        
        return devices
    
    def _resample_audio(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        Resample audio data from one sample rate to another.
        
        Args:
            audio_data: Raw audio bytes (16-bit signed)
            from_rate: Original sample rate
            to_rate: Target sample rate
            
        Returns:
            Resampled audio bytes
        """
        if from_rate == to_rate:
            return audio_data
        
        # Convert bytes to numpy array
        samples = np.frombuffer(audio_data, dtype=np.int16)
        
        if len(samples) == 0:
            return audio_data
        
        # Calculate new length
        duration = len(samples) / from_rate
        new_length = int(duration * to_rate)
        
        if new_length == 0:
            return audio_data
        
        # Resample using numpy interpolation
        indices = np.linspace(0, len(samples) - 1, new_length)
        resampled = np.interp(indices, np.arange(len(samples)), samples.astype(np.float64))
        
        # Convert back to int16 bytes
        return resampled.astype(np.int16).tobytes()
    
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
        if not self._initialized:
            self.initialize()
        
        frames = []
        silent_chunks = 0
        chunks_per_second = self.device_sample_rate / self.chunk_size
        max_silent_chunks = int(silence_duration * chunks_per_second)
        max_duration = duration if duration else 30  # Max 30 seconds if not specified
        
        try:
            # Record using sounddevice
            recording = sd.rec(
                int(max_duration * self.device_sample_rate),
                samplerate=self.device_sample_rate,
                channels=self.channels,
                dtype='int16',
                device=self.input_device
            )
            
            # Wait for recording with silence detection
            chunk_samples = self.chunk_size
            recorded_samples = 0
            
            while recorded_samples < len(recording):
                # Wait a bit for data
                sd.sleep(int(1000 * chunk_samples / self.device_sample_rate))
                
                # Check recorded portion
                end_idx = min(recorded_samples + chunk_samples, len(recording))
                chunk = recording[recorded_samples:end_idx]
                
                if len(chunk) == 0:
                    break
                
                frames.append(chunk.tobytes())
                recorded_samples = end_idx
                
                # Check for silence
                if stop_on_silence:
                    rms = np.sqrt(np.mean(chunk.astype(np.float64) ** 2))
                    
                    if rms < silence_threshold:
                        silent_chunks += 1
                        if silent_chunks >= max_silent_chunks and len(frames) > chunks_per_second:
                            logger.debug("Silence detected, stopping recording")
                            break
                    else:
                        silent_chunks = 0
            
            sd.stop()
            
        except Exception as e:
            logger.error(f"Recording error: {e}")
            return b''
        
        audio_data = b''.join(frames)
        
        # Resample if needed
        if self.needs_resampling:
            audio_data = self._resample_audio(audio_data, self.device_sample_rate, self.sample_rate)
        
        return audio_data
    
    def _get_audio_level(self, data: bytes) -> int:
        """Calculate audio level from raw data."""
        if len(data) < 2:
            return 0
        
        samples = np.frombuffer(data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
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
        if not self._initialized:
            self.initialize()
        
        self._stop_streaming = False
        self._audio_queue = queue.Queue()
        
        def audio_callback(indata, frames, time, status):
            """Callback for audio stream."""
            if status:
                logger.debug(f"Stream status: {status}")
            
            # Convert to bytes and put in queue
            audio_bytes = indata.copy().tobytes()
            self._audio_queue.put(audio_bytes)
        
        try:
            with sd.InputStream(
                device=self.input_device,
                channels=self.channels,
                samplerate=self.device_sample_rate,
                blocksize=self.chunk_size,
                dtype='int16',
                callback=audio_callback
            ):
                while not self._stop_streaming:
                    try:
                        data = self._audio_queue.get(timeout=1.0)
                        
                        # Resample if needed
                        if self.needs_resampling:
                            data = self._resample_audio(data, self.device_sample_rate, self.sample_rate)
                        
                        yield data
                    except queue.Empty:
                        continue
                        
        except Exception as e:
            logger.error(f"Stream audio error: {e}")
            raise
    
    def stop_streaming(self) -> None:
        """Stop the audio streaming."""
        self._stop_streaming = True
    
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
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data)
        
        logger.debug(f"Saved audio to {path}")
        return path
    
    def play_audio(self, audio_data: bytes) -> None:
        """Play audio data through speakers."""
        if not self._initialized:
            self.initialize()
        
        try:
            # Convert bytes to numpy array
            samples = np.frombuffer(audio_data, dtype=np.int16)
            
            # Play audio
            sd.play(samples, samplerate=self.sample_rate, device=self.output_device)
            sd.wait()
            
        except Exception as e:
            logger.error(f"Playback error: {e}")
    
    async def play_audio_async(self, audio_data: bytes) -> None:
        """Async wrapper for play_audio."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.play_audio, audio_data)
    
    def shutdown(self) -> None:
        """Cleanup audio resources."""
        self._stop_streaming = True
        
        try:
            sd.stop()
        except Exception:
            pass
        
        self._initialized = False
        logger.debug("Audio manager shutdown complete")
