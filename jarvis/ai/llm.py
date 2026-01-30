"""
JARVIS LLM Integration

Provides unified interface to different LLM providers:
- Anthropic Claude (cloud)
- OpenAI GPT (cloud)
- Ollama (local)
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

from loguru import logger


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a response from the LLM."""
        pass
    
    @abstractmethod
    async def generate_with_context(
        self,
        messages: list[dict],
        system_prompt: str | None = None
    ) -> str:
        """Generate response with conversation context."""
        pass


class AnthropicProvider(LLMProvider):
    """Claude API provider."""
    
    def __init__(self, config):
        """Initialize Anthropic provider."""
        self.config = config
        self.model = config.get("ai.llm.model", "claude-3-5-sonnet-20241022")
        self.max_tokens = config.get("ai.llm.max_tokens", 1024)
        self.temperature = config.get("ai.llm.temperature", 0.7)
        self._client = None
    
    async def _get_client(self):
        """Get or create Anthropic client."""
        if self._client is None:
            from anthropic import AsyncAnthropic
            api_key = self.config.get("ai.llm.anthropic_api_key")
            if not api_key:
                raise ValueError("Anthropic API key not configured")
            self._client = AsyncAnthropic(api_key=api_key)
        return self._client
    
    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate response from Claude."""
        try:
            client = await self._get_client()
            
            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt or self._default_system_prompt(),
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise
    
    async def generate_with_context(
        self,
        messages: list[dict],
        system_prompt: str | None = None
    ) -> str:
        """Generate response with conversation context."""
        try:
            client = await self._get_client()
            
            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt or self._default_system_prompt(),
                messages=messages
            )
            
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise
    
    def _default_system_prompt(self) -> str:
        """Get default system prompt."""
        return """You are JARVIS, an intelligent AI assistant running on Linux. 
You help the user with tasks including:
- System control and monitoring
- File management
- Scheduling and reminders
- Information retrieval
- General questions

Be concise but helpful. When asked to perform actions, describe what you'll do.
For voice interactions, keep responses brief and natural-sounding.
Current date/time: """ + datetime.now().strftime("%Y-%m-%d %H:%M")


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""
    
    def __init__(self, config):
        """Initialize Ollama provider."""
        self.config = config
        self.model = config.get("ai.llm.ollama_model", "llama3.2")
        self.host = config.get("ai.llm.ollama_host", "http://localhost:11434")
        self.temperature = config.get("ai.llm.temperature", 0.7)
    
    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate response from Ollama."""
        try:
            import ollama
            
            client = ollama.AsyncClient(host=self.host)
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = await client.chat(
                model=self.model,
                messages=messages,
                options={"temperature": self.temperature}
            )
            
            return response['message']['content']
            
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise
    
    async def generate_with_context(
        self,
        messages: list[dict],
        system_prompt: str | None = None
    ) -> str:
        """Generate response with conversation context."""
        try:
            import ollama
            
            client = ollama.AsyncClient(host=self.host)
            
            all_messages = []
            if system_prompt:
                all_messages.append({"role": "system", "content": system_prompt})
            all_messages.extend(messages)
            
            response = await client.chat(
                model=self.model,
                messages=all_messages,
                options={"temperature": self.temperature}
            )
            
            return response['message']['content']
            
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise


class LLMManager:
    """
    Manages LLM interactions with context and memory.
    
    Features:
    - Provider abstraction (Claude, Ollama)
    - Conversation context management
    - Intent classification
    """
    
    SYSTEM_PROMPT = """You are JARVIS, an intelligent AI assistant for Linux systems.

Your capabilities include:
- System monitoring (CPU, memory, disk usage)
- File operations (search, list, read)
- Application launching
- Timer/reminder setting
- Web searches
- Answering questions

Instructions:
1. Be concise - keep responses under 2-3 sentences for voice
2. When performing actions, briefly confirm what you're doing
3. For ambiguous requests, ask for clarification
4. If you can't do something, suggest alternatives
5. Use natural, conversational language

Current time: {time}

Previous context:
{context}
"""
    
    def __init__(self, config):
        """Initialize LLM manager."""
        self.config = config
        self.provider: LLMProvider | None = None
        
        # Conversation history
        self.messages: list[dict] = []
        self.max_history = config.get("ai.context.max_history", 20)
        
        # Intent patterns
        self.intent_patterns = {
            "system_info": ["cpu", "memory", "ram", "disk", "usage", "status", "system"],
            "file_operation": ["file", "folder", "directory", "open", "find", "search", "create", "delete"],
            "timer": ["timer", "alarm", "remind", "reminder", "schedule", "minutes", "hours"],
            "application": ["open", "launch", "start", "run", "close", "application", "app"],
            "web_search": ["search", "google", "look up", "find online", "what is"],
            "shell_command": ["run command", "execute", "terminal", "shell"],
            "exit": ["goodbye", "bye", "exit", "quit", "stop"],
        }
    
    async def initialize(self) -> None:
        """Initialize the LLM provider."""
        provider_name = self.config.get("ai.llm.provider", "anthropic")
        
        if provider_name == "anthropic":
            api_key = self.config.get("ai.llm.anthropic_api_key")
            if api_key:
                self.provider = AnthropicProvider(self.config)
                logger.info("Using Anthropic Claude")
            else:
                logger.warning("Anthropic API key not set, trying Ollama")
                provider_name = "ollama"
        
        if provider_name == "ollama":
            self.provider = OllamaProvider(self.config)
            logger.info(f"Using Ollama with model: {self.config.get('ai.llm.ollama_model')}")
        
        if not self.provider:
            logger.warning("No LLM provider available - using pattern matching only")
    
    async def process(self, text: str) -> str:
        """
        Process user input and generate response.
        
        Args:
            text: User input text
            
        Returns:
            Assistant response
        """
        # Detect intent
        intent = self._detect_intent(text)
        logger.debug(f"Detected intent: {intent}")
        
        # Add to conversation history
        self.messages.append({"role": "user", "content": text})
        
        # Trim history if needed
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
        
        # Generate response
        if self.provider:
            try:
                system_prompt = self._build_system_prompt()
                response = await self.provider.generate_with_context(
                    self.messages,
                    system_prompt
                )
            except Exception as e:
                logger.error(f"LLM error: {e}")
                response = self._fallback_response(text, intent)
        else:
            response = self._fallback_response(text, intent)
        
        # Add response to history
        self.messages.append({"role": "assistant", "content": response})
        
        return response
    
    def _detect_intent(self, text: str) -> str:
        """Detect user intent from text."""
        text_lower = text.lower()
        
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    return intent
        
        return "general"
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with context."""
        context_summary = ""
        if len(self.messages) > 2:
            # Summarize recent context
            recent = self.messages[-4:-1]
            context_parts = [
                f"- {m['role']}: {m['content'][:100]}..."
                for m in recent if m['content']
            ]
            context_summary = "\n".join(context_parts)
        
        return self.SYSTEM_PROMPT.format(
            time=datetime.now().strftime("%Y-%m-%d %H:%M"),
            context=context_summary or "No previous context"
        )
    
    def _fallback_response(self, text: str, intent: str) -> str:
        """Generate fallback response without LLM."""
        text_lower = text.lower()
        
        if intent == "system_info":
            return self._get_system_info()
        
        if intent == "exit":
            return "Goodbye! Have a great day!"
        
        if "hello" in text_lower or "hi" in text_lower:
            return "Hello! I'm JARVIS, your AI assistant. How can I help you today?"
        
        if "time" in text_lower:
            return f"The current time is {datetime.now().strftime('%I:%M %p')}"
        
        if "date" in text_lower:
            return f"Today is {datetime.now().strftime('%A, %B %d, %Y')}"
        
        if "weather" in text_lower:
            return "I don't have access to weather data yet. This feature is coming soon!"
        
        return "I heard you, but I need an LLM connection to fully understand that request. Try asking about system status, time, or date."
    
    def _get_system_info(self) -> str:
        """Get system information."""
        try:
            import psutil
            
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return (
                f"System status: CPU at {cpu}%, "
                f"memory {mem.percent}% used, "
                f"disk {disk.percent}% used."
            )
        except Exception:
            return "Unable to retrieve system information."
    
    def clear_context(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        logger.debug("Conversation context cleared")
    
    async def shutdown(self) -> None:
        """Cleanup resources."""
        self.messages.clear()
        self.provider = None
        logger.debug("LLM manager shutdown complete")
