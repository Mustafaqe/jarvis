# JARVIS AI Assistant

> AI-Powered Voice Assistant for Linux

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

JARVIS is a comprehensive AI assistant for Linux featuring:
- 🎤 **Voice Interaction** - Wake word detection, speech-to-text, text-to-speech
- 🤖 **AI Integration** - Claude API and Ollama (local LLM) support
- ⚡ **System Control** - Monitor CPU, memory, disk; launch apps
- 🔌 **Plugin System** - Extensible architecture for new capabilities
- 🌐 **Web Dashboard** - Modern web interface for remote control

## Quick Start

```bash
# Clone and install
cd jarvis-opus
chmod +x install.sh
./install.sh

# Configure API keys
nano .env  # Add your keys

# Run
source venv/bin/activate
python main.py --mode cli
```

## Modes

| Mode | Command | Description |
|------|---------|-------------|
| CLI | `python main.py --mode cli` | Text-based terminal interface |
| Voice | `python main.py --mode voice` | Voice-activated assistant |
| Web | `python main.py --mode web` | Web dashboard at localhost:8000 |

## Example Commands

```
"Hey Jarvis, what's my CPU usage?"
"Open Firefox"
"Set a timer for 5 minutes"
"Search for Python tutorials"
"Find files named report"
"What time is it?"
```

## Configuration

### API Keys

Create a `.env` file:
```bash
ANTHROPIC_API_KEY=your-key-here      # For Claude LLM
JARVIS_PORCUPINE_ACCESS_KEY=key      # For wake word (optional)
```

### Custom Settings

Edit `config/user.yaml` to override defaults:
```yaml
ai:
  llm:
    provider: "ollama"  # Use local LLM
    ollama_model: "llama3.2"

voice:
  tts:
    engine: "espeak"
    rate: 150
```

## Architecture

```
jarvis-opus/
├── main.py              # Entry point
├── jarvis/
│   ├── core/            # Engine, events, config, security
│   ├── voice/           # Wake word, STT, TTS, audio
│   ├── ai/              # LLM integration, intent detection
│   ├── plugins/         # System control, files, timer, etc.
│   └── interface/       # CLI and web interfaces
├── config/              # YAML configuration
└── data/                # Logs, database, models
```

## Plugins

| Plugin | Capabilities |
|--------|--------------|
| System Control | CPU/memory/disk monitoring, app launcher |
| File Manager | Search, list, open files |
| Timer | Timers, reminders, alarms |
| Shell | Safe command execution |
| Web Search | DuckDuckGo search |

## Docker

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f jarvis
```

## Requirements

- Python 3.10+
- Linux (Ubuntu, Arch, Fedora)
- Microphone (for voice mode)
- Optional: Ollama for local LLM

## License

MIT License - see LICENSE file.
