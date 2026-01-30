#!/bin/bash
# JARVIS AI Assistant - Installation Script
# Supports Ubuntu/Debian and Arch Linux

set -e

echo "╔══════════════════════════════════════════╗"
echo "║     JARVIS AI Assistant Installer        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for root
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}Warning: Running as root is not recommended.${NC}"
    echo "Consider running as a normal user."
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Detect package manager
if command -v apt &> /dev/null; then
    PKG_MANAGER="apt"
    INSTALL_CMD="sudo apt install -y"
elif command -v pacman &> /dev/null; then
    PKG_MANAGER="pacman"
    INSTALL_CMD="sudo pacman -S --noconfirm"
elif command -v dnf &> /dev/null; then
    PKG_MANAGER="dnf"
    INSTALL_CMD="sudo dnf install -y"
else
    echo -e "${RED}Error: No supported package manager found.${NC}"
    echo "Please install dependencies manually."
    exit 1
fi

echo -e "${GREEN}Detected package manager: ${PKG_MANAGER}${NC}"

# Install system dependencies
echo ""
echo "📦 Installing system dependencies..."

if [ "$PKG_MANAGER" = "apt" ]; then
    sudo apt update
    $INSTALL_CMD \
        python3 python3-pip python3-venv \
        portaudio19-dev python3-pyaudio \
        espeak ffmpeg \
        libsndfile1
elif [ "$PKG_MANAGER" = "pacman" ]; then
    $INSTALL_CMD \
        python python-pip python-virtualenv \
        portaudio \
        espeak-ng ffmpeg \
        libsndfile
elif [ "$PKG_MANAGER" = "dnf" ]; then
    $INSTALL_CMD \
        python3 python3-pip python3-virtualenv \
        portaudio-devel \
        espeak ffmpeg \
        libsndfile
fi

# Create virtual environment
echo ""
echo "🐍 Setting up Python virtual environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}Virtual environment created.${NC}"
else
    echo "Virtual environment already exists."
fi

# Activate venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip wheel setuptools

# Install Python dependencies
echo ""
echo "📚 Installing Python dependencies..."
pip install -r requirements.txt

# Create data directories
echo ""
echo "📁 Creating data directories..."
mkdir -p data/logs
mkdir -p data/models
mkdir -p config

# Create user config if not exists
if [ ! -f "config/user.yaml" ]; then
    echo "# User configuration - overrides default.yaml" > config/user.yaml
    echo "# Uncomment and modify as needed" >> config/user.yaml
    echo "" >> config/user.yaml
    echo "# voice:" >> config/user.yaml
    echo "#   wake_word:" >> config/user.yaml
    echo "#     porcupine_access_key: \"your-key-here\"" >> config/user.yaml
fi

# Create .env file for API keys
if [ ! -f ".env" ]; then
    echo "# JARVIS API Keys" > .env
    echo "# Get Anthropic key from: https://console.anthropic.com/" >> .env
    echo "ANTHROPIC_API_KEY=" >> .env
    echo "" >> .env
    echo "# Get Porcupine key from: https://console.picovoice.ai/" >> .env
    echo "JARVIS_PORCUPINE_ACCESS_KEY=" >> .env
    echo "" >> .env
    echo "# Optional: OpenAI for Whisper" >> .env
    echo "OPENAI_API_KEY=" >> .env
fi

# Check for Ollama
echo ""
echo "🤖 Checking for Ollama..."
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}Ollama is installed.${NC}"
    
    # Check if running
    if pgrep -x "ollama" > /dev/null; then
        echo "Ollama is running."
    else
        echo -e "${YELLOW}Starting Ollama...${NC}"
        ollama serve &
        sleep 2
    fi
    
    # Check if model exists
    if ! ollama list | grep -q "llama3.2"; then
        echo "Pulling llama3.2 model..."
        ollama pull llama3.2
    fi
else
    echo -e "${YELLOW}Ollama not installed.${NC}"
    echo "For local LLM support, install Ollama from: https://ollama.ai/"
    echo "Then run: ollama pull llama3.2"
fi

# Summary
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         Installation Complete!           ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "1. Configure API keys in .env file:"
echo "   - ANTHROPIC_API_KEY (or use Ollama for local LLM)"
echo "   - JARVIS_PORCUPINE_ACCESS_KEY (for wake word)"
echo ""
echo "2. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "3. Run JARVIS:"
echo "   python main.py --mode cli    # CLI mode"
echo "   python main.py --mode voice  # Voice mode"
echo "   python main.py --mode web    # Web dashboard"
echo ""
echo -e "${GREEN}Enjoy JARVIS!${NC} 🤖"
