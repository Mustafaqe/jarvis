# JARVIS Distributed System

This document describes the distributed architecture of JARVIS that enables controlling multiple PCs from a central server.

## Quick Start

### Server Setup

```bash
# 1. Run the setup script
chmod +x setup.sh
./setup.sh

# 2. Or manually:
source venv/bin/activate
pip install grpcio grpcio-tools cryptography paho-mqtt zeroconf aiohttp

# 3. Start the server
python main.py --mode server

# 4. Or use Docker
docker-compose up -d jarvis-server ollama
```

### Client Setup

```bash
# On each client PC:
./setup.sh

# Or manually:
python main.py --mode client --server-host <SERVER_IP>
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        JARVIS Server                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │ AI Core  │ │ Task     │ │ Pattern  │ │ Context Aggregator   │ │
│  │ (Ollama) │ │ Planner  │ │ Learner  │ │                      │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────┬───────────┘ │
│       │            │            │                  │             │
│  ┌────┴────────────┴────────────┴──────────────────┴───────────┐ │
│  │                     gRPC Server (mTLS)                       │ │
│  │                     Port 50051                               │ │
│  └──────────────────────────────┬──────────────────────────────┘ │
│                                 │                                │
│  ┌──────────────────────────────┴──────────────────────────────┐ │
│  │              Web Dashboard (FastAPI)                         │ │
│  │              Port 8000                                       │ │
│  └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
    │  Client   │  │  Client   │  │  Client   │
    │  PC #1    │  │  PC #2    │  │  PC #N    │
    └───────────┘  └───────────┘  └───────────┘
```

## Components

### Network Module (`jarvis/network/`)

| File | Description |
|------|-------------|
| `server.py` | gRPC server with TLS/mTLS, client management, command routing |
| `client.py` | gRPC client with auto-reconnect, screen streaming, command execution |
| `discovery.py` | Network scanning (ARP) and mDNS (Zeroconf) for device discovery |
| `iot.py` | MQTT and Home Assistant integration for IoT control |
| `protocol.proto` | gRPC protocol definitions |

### AI Module (`jarvis/ai/`)

| File | Description |
|------|-------------|
| `planner.py` | Multi-step task planning and execution |
| `context_aggregator.py` | Aggregates state from all clients for AI awareness |
| `pattern_learner.py` | Learns user behavior patterns for proactive suggestions |

### Security Module (`jarvis/security/`)

| File | Description |
|------|-------------|
| `pki.py` | Certificate Authority for mTLS |

## Security

### mTLS (Mutual TLS)

Generate certificates:

```bash
# Initialize CA
python -c "from jarvis.security.pki import CertificateAuthority; \
           ca = CertificateAuthority('certs'); \
           ca.initialize()"

# Generate server cert
python -c "from jarvis.security.pki import CertificateAuthority; \
           ca = CertificateAuthority('certs'); \
           ca.initialize(); \
           ca.generate_server_cert(hostname='jarvis-server', ip_addresses=['192.168.1.100'])"

# Generate client cert
python -c "from jarvis.security.pki import CertificateAuthority; \
           ca = CertificateAuthority('certs'); \
           ca.initialize(); \
           ca.generate_client_cert(client_id='my-pc')"
```

Copy client certs to each PC:
```bash
scp -r certs/clients/<client-id>/ user@client-pc:/path/to/jarvis/certs/
```

## Configuration

Add to `config/user.yaml`:

```yaml
network:
  mode: "server"  # or "client"
  server_host: "0.0.0.0"  # server: bind address, client: server IP
  server_port: 50051
  
  tls:
    enabled: true
    cert_path: "certs/server.crt"
    key_path: "certs/server.key"
    ca_path: "certs/ca.crt"
    require_client_cert: true  # mTLS
  
  discovery:
    enabled: true
    method: "zeroconf"  # or "arp"
  
  iot:
    mqtt:
      enabled: true
      host: "localhost"
      port: 1883
    homeassistant:
      enabled: false
      url: "http://homeassistant.local:8123"
      token: "${HASS_TOKEN}"

autonomous:
  task_planning: true
  pattern_learning: true
  proactive_suggestions: true
```

## Docker

```bash
# Full stack
docker-compose up -d

# Just server + Ollama
docker-compose up -d jarvis-server ollama

# View logs
docker-compose logs -f jarvis-server

# Stop
docker-compose down
```

## Systemd

Created by `setup.sh`, or manually:

```ini
# /etc/systemd/system/jarvis-server.service
[Unit]
Description=JARVIS AI Assistant (Server)
After=network.target

[Service]
Type=simple
User=myuser
WorkingDirectory=/path/to/jarvis
ExecStart=/path/to/jarvis/venv/bin/python main.py --mode server
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable jarvis-server
sudo systemctl start jarvis-server
sudo journalctl -u jarvis-server -f
```

## API (gRPC)

The gRPC protocol supports:

- **Authentication**: Token-based with session management
- **Commands**: Execute shell commands on clients
- **Screen Capture**: Stream client screens in real-time
- **File Transfer**: Upload/download files between server and clients
- **Voice**: Bidirectional voice streaming
- **IoT**: Control smart home devices through clients

See `jarvis/network/protocol.proto` for full API definition.
