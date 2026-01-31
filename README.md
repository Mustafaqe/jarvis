# 🤖 JARVIS - AI-Powered Assistant for Linux

<div align="center">

![JARVIS Banner](https://img.shields.io/badge/JARVIS-AI%20Assistant-blue?style=for-the-badge&logo=robot)
[![Python](https://img.shields.io/badge/Python-3.11+-green?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?style=flat-square&logo=docker)](docker-compose.yml)

**A fully local, voice-controlled AI assistant with distributed multi-PC control capabilities.**

[Quick Start](#-quick-start) •
[Features](#-features) •
[Installation](#-installation) •
[Usage](#-usage) •
[Distributed Mode](#-distributed-mode) •
[Configuration](#-configuration)

</div>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎤 **Voice Control** | Wake word detection, speech-to-text, natural TTS |
| 🧠 **Local AI** | Ollama integration - 100% offline, no cloud |
| 🖥️ **Multi-PC Control** | Control multiple computers from a central server |
| 🔒 **Secure** | mTLS encryption, certificate-based authentication |
| 🏠 **Smart Home** | MQTT & Home Assistant integration |
| 🔌 **Plugin System** | Extensible with custom plugins |
| 🌐 **Web Dashboard** | Real-time monitoring and control |
| 🤖 **Autonomous Tasks** | Multi-step task planning and execution |

---

## 🚀 Quick Start

### One-Line Install

```bash
git clone https://github.com/Mustafaqe/jarvis.git && cd jarvis && ./setup.sh
```

### Manual Install (5 minutes)

```bash
# 1. Clone the repo
git clone https://github.com/Mustafaqe/jarvis.git
cd jarvis

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start Ollama (in another terminal)
ollama serve
ollama pull llama3.2

# 5. Run JARVIS
python main.py --mode voice
```

### Docker (Recommended)

```bash
docker-compose up -d
```

---

## 📦 Installation

### Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.11+ | 3.12+ |
| RAM | 4GB | 8GB+ |
| Disk | 5GB | 10GB+ |
| GPU | Optional | NVIDIA (for faster AI) |

### System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv \
    portaudio19-dev espeak-ng tesseract-ocr
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip portaudio espeak-ng tesseract
```

**Fedora:**
```bash
sudo dnf install -y python3 python3-pip portaudio-devel espeak-ng tesseract
```

### Python Dependencies

```bash
pip install -r requirements.txt
```

### Ollama Setup (Local AI)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.2        # Fast, good quality
# OR
ollama pull mistral         # Alternative
# OR  
ollama pull qwen2.5:1.5b    # Lightweight for low RAM
```

---

## 🎮 Usage

### Operating Modes

| Mode | Command | Description |
|------|---------|-------------|
| **Voice** | `python main.py --mode voice` | Wake word + voice control |
| **CLI** | `python main.py --mode cli` | Text-based interaction |
| **Web** | `python main.py --mode web` | Web dashboard at :8000 |
| **Server** | `python main.py --mode server` | Distributed server |
| **Client** | `python main.py --mode client` | Connect to server |

### Voice Commands

```
"Hey Jarvis"              → Wake word
"Open Firefox"            → Launch applications
"What time is it?"        → Get information
"Turn on the lights"      → Control smart home
"Run system update"       → Execute commands
"Take a screenshot"       → Capture screen
"Goodbye"                 → Exit
```

### Web Dashboard

Start with web mode and visit `http://localhost:8000`:

```bash
python main.py --mode web
```

---

## 🌐 Distributed Mode

Control multiple PCs from a central server!

### Architecture

```
┌───────────────────────────────────────────┐
│            JARVIS Server                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────────┐  │
│  │   AI    │ │  Task   │ │   Context   │  │
│  │ (Ollama)│ │ Planner │ │ Aggregator  │  │
│  └────┬────┘ └────┬────┘ └──────┬──────┘  │
│       └───────────┴─────────────┘         │
│              gRPC :50051                   │
│              Web  :8000                    │
└─────────────────────┬─────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
   │ Client  │   │ Client  │   │ Client  │
   │  PC #1  │   │  PC #2  │   │  PC #N  │
   └─────────┘   └─────────┘   └─────────┘
```

### Server Setup

```bash
# On your main server/Raspberry Pi
python main.py --mode server
```

### Client Setup

```bash
# On each PC you want to control
python main.py --mode client --server-host 192.168.1.100
```

### With Security (mTLS)

```bash
# 1. Generate certificates on server
python -c "
from jarvis.security.pki import CertificateAuthority
ca = CertificateAuthority('certs')
ca.initialize()
ca.generate_server_cert(hostname='jarvis-server', ip_addresses=['192.168.1.100'])
ca.generate_client_cert(client_id='my-pc')
"

# 2. Copy client certs to each PC
scp -r certs/clients/my-pc/ user@client-pc:~/jarvis/certs/

# 3. Enable TLS in config/user.yaml
```

---

## ⚙️ Configuration

Create `config/user.yaml` to customize:

```yaml
# Core settings
core:
  name: "Jarvis"
  personality: "helpful and professional"

# Voice settings
voice:
  wake_word: "jarvis"
  
  stt:
    engine: "whisper"          # whisper, google, vosk
    model: "base"              # tiny, base, small, medium
  
  tts:
    engine: "piper"            # piper, espeak, elevenlabs
    voice: "en_US-lessac-medium"

# AI settings
ai:
  llm:
    provider: "ollama"         # ollama, openai, anthropic
    ollama_model: "llama3.2"
    ollama_host: "http://localhost:11434"

# Distributed settings (optional)
network:
  mode: "standalone"           # standalone, server, client
  server_host: "0.0.0.0"
  server_port: 50051
  
  tls:
    enabled: false
    cert_path: "certs/server.crt"
    key_path: "certs/server.key"
    ca_path: "certs/ca.crt"

# Smart home (optional)
iot:
  mqtt:
    enabled: false
    host: "localhost"
    port: 1883
  homeassistant:
    enabled: false
    url: "http://homeassistant.local:8123"
    token: "${HASS_TOKEN}"
```

---

## 🐳 Docker

### Full Stack

```bash
# Start everything (JARVIS + Ollama + MQTT)
docker-compose up -d

# View logs
docker-compose logs -f jarvis-server

# Stop
docker-compose down
```

### Build Images

```bash
# Server image
docker build -f Dockerfile.server -t jarvis-server .

# Client image
docker build -f Dockerfile.client -t jarvis-client .
```

---

## 🔌 Plugins

Built-in plugins:

| Plugin | Description |
|--------|-------------|
| `shell` | Execute shell commands |
| `system_control` | Apps, volume, brightness |
| `web_search` | Search the web |
| `file_manager` | File operations |
| `weather` | Weather information |

### Create a Plugin

```python
# jarvis/plugins/my_plugin.py
from jarvis.plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    name = "my_plugin"
    
    def get_commands(self):
        return {
            "do_something": self.do_something,
        }
    
    async def do_something(self, args):
        return "Done!"
```

---

## 🛠️ Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Format code
black jarvis/
isort jarvis/

# Type check
mypy jarvis/
```

---

## 📁 Project Structure

```
jarvis/
├── main.py                 # Entry point
├── setup.sh               # Interactive setup
├── docker-compose.yml     # Docker stack
├── config/
│   └── default.yaml       # Default configuration
├── jarvis/
│   ├── core/              # Core engine, config, events
│   ├── ai/                # LLM, planner, pattern learning
│   ├── voice/             # STT, TTS, wake word
│   ├── network/           # gRPC server/client, discovery
│   ├── security/          # PKI, certificates
│   ├── plugins/           # Command plugins
│   ├── vision/            # Screen capture, OCR
│   └── interface/         # Web dashboard
└── docs/                  # Documentation
```

---

## 🔧 Troubleshooting

<details>
<summary><b>Microphone not detected</b></summary>

```bash
# List audio devices
python -c "import pyaudio; p = pyaudio.PyAudio(); [print(p.get_device_info_by_index(i)) for i in range(p.get_device_count())]"

# Set device in config
voice:
  input_device: 1
```
</details>

<details>
<summary><b>Ollama connection failed</b></summary>

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Check model is pulled
ollama list
```
</details>

<details>
<summary><b>TTS not working</b></summary>

```bash
# Install espeak
sudo apt install espeak-ng

# Or use piper
pip install piper-tts
```
</details>

<details>
<summary><b>Permission denied for commands</b></summary>

Check `config/user.yaml` security settings:
```yaml
security:
  require_confirmation: true
  allowed_commands: ["ls", "cat", "echo"]
```
</details>

---

## 📜 License

MIT License - see [LICENSE](LICENSE)

---

## 🙏 Acknowledgments

- [Ollama](https://ollama.com) - Local LLM
- [Whisper](https://github.com/openai/whisper) - Speech recognition
- [Piper](https://github.com/rhasspy/piper) - Text-to-speech
- [FastAPI](https://fastapi.tiangolo.com) - Web framework

---

<div align="center">

**Made with ❤️ for the open-source community**

[⬆ Back to Top](#-jarvis---ai-powered-assistant-for-linux)

</div>
