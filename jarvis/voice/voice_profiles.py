"""
JARVIS Voice Profiles

Provides predefined voice profiles and custom voice management.
Each profile defines voice characteristics, personality, and speech patterns.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import json

from loguru import logger


class VoiceGender(Enum):
    """Voice gender options."""
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


class VoiceAccent(Enum):
    """Voice accent options."""
    BRITISH = "british"
    AMERICAN = "american"
    AUSTRALIAN = "australian"
    INDIAN = "indian"
    NEUTRAL = "neutral"


@dataclass
class VoiceProfile:
    """
    Voice profile configuration.
    
    Defines all characteristics of a voice including technical settings
    and personality traits.
    """
    id: str
    name: str
    description: str
    
    # Voice characteristics
    gender: VoiceGender = VoiceGender.NEUTRAL
    accent: VoiceAccent = VoiceAccent.NEUTRAL
    age: str = "adult"  # child, young, adult, elderly
    
    # TTS engine settings
    engine: str = "coqui"  # coqui, elevenlabs
    voice_id: Optional[str] = None  # Engine-specific voice ID
    model: Optional[str] = None  # Model name for Coqui
    
    # Speech parameters
    speed: float = 1.0  # 0.5 - 2.0
    pitch: float = 1.0  # 0.5 - 2.0
    
    # Personality (affects response generation)
    personality: str = "professional"  # professional, friendly, formal, casual
    address_user_as: str = "Sir"  # How to address the user
    
    # Emotion defaults
    default_emotion: str = "neutral"
    
    # Voice cloning reference (if cloned)
    reference_audio: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "gender": self.gender.value,
            "accent": self.accent.value,
            "age": self.age,
            "engine": self.engine,
            "voice_id": self.voice_id,
            "model": self.model,
            "speed": self.speed,
            "pitch": self.pitch,
            "personality": self.personality,
            "address_user_as": self.address_user_as,
            "default_emotion": self.default_emotion,
            "reference_audio": self.reference_audio,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "VoiceProfile":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            gender=VoiceGender(data.get("gender", "neutral")),
            accent=VoiceAccent(data.get("accent", "neutral")),
            age=data.get("age", "adult"),
            engine=data.get("engine", "coqui"),
            voice_id=data.get("voice_id"),
            model=data.get("model"),
            speed=data.get("speed", 1.0),
            pitch=data.get("pitch", 1.0),
            personality=data.get("personality", "professional"),
            address_user_as=data.get("address_user_as", "Sir"),
            default_emotion=data.get("default_emotion", "neutral"),
            reference_audio=data.get("reference_audio"),
        )


# Predefined voice profiles
BUILTIN_PROFILES = {
    "jarvis_classic": VoiceProfile(
        id="jarvis_classic",
        name="JARVIS Classic",
        description="Professional British butler, like the original JARVIS",
        gender=VoiceGender.MALE,
        accent=VoiceAccent.BRITISH,
        engine="coqui",
        model="tts_models/en/vctk/vits",
        voice_id="p273",  # VCTK male British speaker
        personality="professional",
        address_user_as="Sir",
        default_emotion="neutral",
    ),
    
    "friday": VoiceProfile(
        id="friday",
        name="F.R.I.D.A.Y.",
        description="Friendly female assistant with Irish accent",
        gender=VoiceGender.FEMALE,
        accent=VoiceAccent.BRITISH,  # Closest to Irish
        engine="coqui",
        model="tts_models/en/vctk/vits",
        voice_id="p234",  # VCTK female speaker
        personality="friendly",
        address_user_as="Boss",
        default_emotion="happy",
    ),
    
    "professional_american": VoiceProfile(
        id="professional_american",
        name="Professional American",
        description="Clear American professional voice",
        gender=VoiceGender.FEMALE,
        accent=VoiceAccent.AMERICAN,
        engine="coqui",
        model="tts_models/en/ljspeech/vits",
        personality="professional",
        address_user_as="",
        default_emotion="neutral",
    ),
    
    "casual_assistant": VoiceProfile(
        id="casual_assistant",
        name="Casual Assistant",
        description="Friendly and casual voice for everyday use",
        gender=VoiceGender.NEUTRAL,
        accent=VoiceAccent.AMERICAN,
        engine="coqui",
        model="tts_models/en/vctk/vits",
        voice_id="p225",  # Neutral voice
        speed=1.05,
        personality="casual",
        address_user_as="",
        default_emotion="happy",
    ),
    
    # ElevenLabs profiles (require API key)
    "elevenlabs_rachel": VoiceProfile(
        id="elevenlabs_rachel",
        name="Rachel (ElevenLabs)",
        description="Natural American female voice (ElevenLabs)",
        gender=VoiceGender.FEMALE,
        accent=VoiceAccent.AMERICAN,
        engine="elevenlabs",
        voice_id="21m00Tcm4TlvDq8ikWAM",  # Rachel
        personality="professional",
        address_user_as="",
        default_emotion="neutral",
    ),
    
    "elevenlabs_adam": VoiceProfile(
        id="elevenlabs_adam",
        name="Adam (ElevenLabs)",
        description="Deep American male voice (ElevenLabs)",
        gender=VoiceGender.MALE,
        accent=VoiceAccent.AMERICAN,
        engine="elevenlabs",
        voice_id="pNInz6obpgDQGcFmaJgB",  # Adam
        personality="professional",
        address_user_as="",
        default_emotion="neutral",
    ),
    
    "elevenlabs_british": VoiceProfile(
        id="elevenlabs_british",
        name="Daniel (ElevenLabs)",
        description="British male voice (ElevenLabs)",
        gender=VoiceGender.MALE,
        accent=VoiceAccent.BRITISH,
        engine="elevenlabs",
        voice_id="onwK4e9ZLuTAKqWW03F9",  # Daniel
        personality="professional",
        address_user_as="Sir",
        default_emotion="neutral",
    ),
}


class VoiceProfileManager:
    """
    Manages voice profiles including built-in and custom profiles.
    """
    
    def __init__(self, config, profiles_dir: Optional[Path] = None):
        """
        Initialize profile manager.
        
        Args:
            config: Configuration object
            profiles_dir: Directory for custom profiles
        """
        self.config = config
        self.profiles_dir = profiles_dir or Path(
            config.get("core.data_dir", "data")
        ) / "profiles"
        
        self._profiles: dict[str, VoiceProfile] = {}
        self._current_profile: Optional[VoiceProfile] = None
        
        # Load built-in profiles
        self._profiles.update(BUILTIN_PROFILES)
        
        # Load custom profiles
        self._load_custom_profiles()
        
        # Set default profile
        default_id = config.get("voice.tts.voice_profile", "jarvis_classic")
        if default_id in self._profiles:
            self._current_profile = self._profiles[default_id]
        else:
            self._current_profile = BUILTIN_PROFILES["jarvis_classic"]
    
    def _load_custom_profiles(self) -> None:
        """Load custom profiles from disk."""
        if not self.profiles_dir.exists():
            return
        
        for profile_file in self.profiles_dir.glob("*.json"):
            try:
                with open(profile_file, "r") as f:
                    data = json.load(f)
                profile = VoiceProfile.from_dict(data)
                self._profiles[profile.id] = profile
                logger.debug(f"Loaded custom profile: {profile.name}")
            except Exception as e:
                logger.warning(f"Failed to load profile {profile_file}: {e}")
    
    def get_profile(self, profile_id: str) -> Optional[VoiceProfile]:
        """Get profile by ID."""
        return self._profiles.get(profile_id)
    
    def get_current_profile(self) -> VoiceProfile:
        """Get current active profile."""
        return self._current_profile
    
    def set_current_profile(self, profile_id: str) -> bool:
        """
        Set current active profile.
        
        Args:
            profile_id: Profile ID to activate
            
        Returns:
            True if profile was activated
        """
        profile = self._profiles.get(profile_id)
        if profile:
            self._current_profile = profile
            logger.info(f"Voice profile changed to: {profile.name}")
            return True
        
        logger.warning(f"Profile not found: {profile_id}")
        return False
    
    def list_profiles(self) -> list[VoiceProfile]:
        """List all available profiles."""
        return list(self._profiles.values())
    
    def list_profiles_by_engine(self, engine: str) -> list[VoiceProfile]:
        """List profiles for a specific engine."""
        return [p for p in self._profiles.values() if p.engine == engine]
    
    def create_profile(self, profile: VoiceProfile) -> bool:
        """
        Create a new custom profile.
        
        Args:
            profile: Profile to create
            
        Returns:
            True if created successfully
        """
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        
        profile_path = self.profiles_dir / f"{profile.id}.json"
        
        try:
            with open(profile_path, "w") as f:
                json.dump(profile.to_dict(), f, indent=2)
            
            self._profiles[profile.id] = profile
            logger.info(f"Created voice profile: {profile.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create profile: {e}")
            return False
    
    def delete_profile(self, profile_id: str) -> bool:
        """
        Delete a custom profile.
        
        Args:
            profile_id: Profile ID to delete
            
        Returns:
            True if deleted successfully
        """
        # Cannot delete built-in profiles
        if profile_id in BUILTIN_PROFILES:
            logger.warning("Cannot delete built-in profile")
            return False
        
        profile_path = self.profiles_dir / f"{profile_id}.json"
        
        try:
            if profile_path.exists():
                profile_path.unlink()
            
            if profile_id in self._profiles:
                del self._profiles[profile_id]
            
            # Reset current if deleted
            if self._current_profile and self._current_profile.id == profile_id:
                self._current_profile = BUILTIN_PROFILES["jarvis_classic"]
            
            logger.info(f"Deleted profile: {profile_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete profile: {e}")
            return False
    
    async def create_cloned_profile(
        self,
        name: str,
        description: str,
        audio_path: str,
        engine: str = "coqui"
    ) -> Optional[VoiceProfile]:
        """
        Create a profile from voice cloning.
        
        Args:
            name: Profile name
            description: Profile description
            audio_path: Path to reference audio
            engine: TTS engine to use (coqui xtts or elevenlabs)
            
        Returns:
            Created profile or None
        """
        profile_id = f"cloned_{name.lower().replace(' ', '_')}"
        
        profile = VoiceProfile(
            id=profile_id,
            name=name,
            description=description,
            engine=engine,
            model="tts_models/multilingual/multi-dataset/xtts_v2" if engine == "coqui" else None,
            reference_audio=audio_path,
            personality="custom",
            address_user_as="",
        )
        
        if self.create_profile(profile):
            return profile
        return None
    
    def get_address_for_user(self) -> str:
        """Get how JARVIS should address the user based on current profile."""
        if self._current_profile and self._current_profile.address_user_as:
            return self._current_profile.address_user_as
        return ""
    
    def get_personality(self) -> str:
        """Get current voice personality."""
        if self._current_profile:
            return self._current_profile.personality
        return "professional"
