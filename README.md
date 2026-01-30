# JARVIS AI Assistant

> **Distributed AI-Powered Voice Assistant for Linux**

![Version](https://img.shields.io/badge/version-0.2.0-blue)
![Python](https://img.shields.io/badge/python-3.14+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Status](https://img.shields.io/badge/status-beta-yellow)

JARVIS is a production-grade, distributed AI assistant designed for local privacy and total system control. It operates as a central "brain" server that orchestrates multiple client PCs, enabling seamless voice interaction, screen analysis, and automation across your entire home network.

## Key Features

*   **🧠 Distributed Architecture**: Central AI server controlling multiple lightweight clients.
*   **🔒 Local & Private**: 100% local operation with Ollama (LLM) and local STT/TTS. No cloud dependencies.
*   **🛡️ Secure Communication**: gRPC with mTLS (Mutual TLS) encryption and authentication.
*   **👁️ Computer Vision**: Real-time screen analysis and context awareness.
*   **🤖 Autonomous Agents**: Multi-step task planning, pattern learning, and proactive suggestions.
*   **🗣️ Voice Interaction**: Fast, natural voice control with wake word detection.
*   **🔌 IoT Integration**: Built-in MQTT broker and Home Assistant support.
*   **🐳 Easy Deployment**: Docker-based stack with systemd integration.

## Quick Start

### 1. Installation

Clone the repository and run the setup script:

```bash
git clone https://github.com/sukeesh/Jarvis.git
cd Jarvis/jarvis-opus
chmod +x setup.sh
./setup.sh
```

The interactive setup script will guide you through:
*   Choosing **Server** or **Client** mode
*   Installing system dependencies
*   Generating certificates (PKI)
*   Configuring the system
*   Setting up systemd services

### 2. Manual Run

**Server Mode:**
```bash
source venv/bin/activate
python main.py --mode server
```

**Client Mode:**
```bash
source venv/bin/activate
python main.py --mode client --server-host <SERVER_IP>
```

### 3. Docker Deployment

Deploy the full stack (Server + Ollama + MQTT):

```bash
docker-compose up -d
```

## Architecture

JARVIS uses a modular, event-driven architecture:

```
┌──────────────┐      mTLS/gRPC       ┌──────────────┐
│  JARVIS      │ ◄──────────────────► │  JARVIS      │
│  Server      │                      │  Client      │
│  (AI Brain)  │ ◄──────────────────► │  (Endpoint)  │
└──────┬───────┘      WebSocket       └──────────────┘
       │
       ▼
┌──────────────┐
│  Web         │
│  Dashboard   │
└──────────────┘
```

*   **Core**: Event bus, configuration, security manager.
*   **Network**: gRPC server/client, mTLS, discovery (Zeroconf), IoT (MQTT).
*   **AI**: Task planner, context aggregator, pattern learner, LLM integration.
*   **Voice**: Wake word (Porcupine), STT (Faster-Whisper), TTS (Piper/Espeak).
*   **Vision**: Screen capture, OCR, object detection.

## Documentation

*   [Distributed Architecture Guide](docs/distributed.md)
*   [API Reference](docs/api.md) (Coming Soon)
*   [Plugin Development](docs/plugins.md) (Coming Soon)

## Configuration

Configuration is managed via `config/user.yaml`.

**Example Server Config:**
```yaml
network:
  mode: "server"
  discovery:
    enabled: true
  tls:
    enabled: true
    require_client_cert: true

ai:
  llm:
    provider: "ollama"
    model: "llama3.2"
```

**Example Client Config:**
```yaml
network:
  mode: "client"
  server_host: "192.168.1.100"
  client:
    id: "living-room-pc"
```

## Requirements

*   **OS**: Linux (Ubuntu, Fedora, Arch)
*   **Python**: 3.12+
*   **Hardware**: 
    *   Server: 16GB+ RAM recommended for local LLMs.
    *   Client: Lightweight, runs on any PC or Raspberry Pi 4+.

## License

MIT License - see [LICENSE](LICENSE) file.
