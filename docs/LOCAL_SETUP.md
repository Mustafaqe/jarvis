# JARVIS - Local Setup Walkthrough

Complete guide to running JARVIS on your Linux system.

---

## Step 1: Install System Dependencies

The install script handles this automatically, but here's what it installs:

```bash
# For Arch Linux (detected on your system)
sudo pacman -S python python-pip python-virtualenv portaudio espeak-ng ffmpeg libsndfile
```

---

## Step 2: Create Virtual Environment

```bash
cd /home/mustafa/Jarvis/jarvis-opus

# Create and activate venv
python -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
```

---

## Step 3: Configure API Keys

Create your `.env` file:

```bash
cp .env.example .env
nano .env
```

Add your keys:
```bash
# Option A: Use Claude (cloud LLM)
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Option B: Use Ollama (local LLM) - no key needed!
# Just install Ollama: https://ollama.ai
# Then run: ollama pull llama3.2
```

For **voice mode**, optionally add:
```bash
JARVIS_PORCUPINE_ACCESS_KEY=xxxxx  # Get free key at picovoice.ai
```

---

## Step 4: Run JARVIS

### CLI Mode (Text Input) - Easiest to Start
```bash
source venv/bin/activate
python main.py --mode cli
```

### Voice Mode (Wake Word + Speech)
```bash
source venv/bin/activate
python main.py --mode voice
```
Then say **"Hey Jarvis"** followed by your command.

### Web Dashboard
```bash
source venv/bin/activate
python main.py --mode web
```
Open browser: **http://localhost:8000**

---

## Step 5: Try These Commands

| Command | What It Does |
|---------|--------------|
| "What's my CPU usage?" | Shows system stats |
| "Set a timer for 5 minutes" | Creates a timer |
| "Open Firefox" | Launches application |
| "Find files named report" | Searches home directory |
| "What time is it?" | Shows current time |

---

## Troubleshooting

### No LLM Response?
```bash
# Check if Ollama is running
ollama serve &
ollama pull llama3.2
```

### Voice Not Working?
```bash
# Test microphone
arecord -l  # List audio devices

# Test TTS
espeak "Hello from Jarvis"
```

### Missing Dependencies?
```bash
pip install pyaudio pyttsx3 SpeechRecognition
```

---

## Quick Test (After Install)

```bash
cd /home/mustafa/Jarvis/jarvis-opus
source venv/bin/activate
python main.py --mode cli --debug
```

Type: `hello` - You should get a response!
