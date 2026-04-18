#!/usr/bin/env bash
# One-shot setup for DynaBraille on a fresh Raspberry Pi OS (Bookworm, 64-bit).
# Run on the Pi with: bash setup.sh

set -e

echo "==> Updating apt packages"
sudo apt-get update
sudo apt-get install -y \
  python3-pip python3-venv \
  tesseract-ocr libtesseract-dev \
  python3-picamera2 \
  libatlas-base-dev \
  curl \
  espeak espeak-ng \
  portaudio19-dev python3-pyaudio \
  ffmpeg \
  libespeak-dev

echo "==> Installing Python deps"
pip install --break-system-packages -r requirements.txt

echo "==> Installing Ollama"
if ! command -v ollama &> /dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "==> Configuring Ollama keep-alive (save RAM on 4GB Pi)"
sudo mkdir -p /etc/systemd/system/ollama.service.d
echo -e "[Service]\nEnvironment=\"OLLAMA_KEEP_ALIVE=30s\"" | \
  sudo tee /etc/systemd/system/ollama.service.d/keepalive.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama || true

echo "==> Pulling Gemma (this takes a few minutes)"
ollama pull gemma2:2b

echo "==> Adding user to dialout group (for /dev/ttyUSB* and /dev/ttyACM*)"
sudo usermod -a -G dialout "$USER"

echo "==> Adding user to audio group (for microphone access)"
sudo usermod -a -G audio "$USER"

echo ""
echo "==========================================================="
echo " Setup complete!"
echo " 1. Set your Gemini key:  export GEMINI_API_KEY='your_key'"
echo "    (Add this line to ~/.bashrc for persistence)"
echo ""
echo " 2. Log out and back in so group changes take effect."
echo ""
echo " 3. Test each module:"
echo "    python tests/test_camera.py"
echo "    python tests/test_ocr.py"
echo "    ollama serve  # in a separate terminal"
echo "    python tests/test_gemma.py"
echo "    python tests/test_arduino.py"
echo ""
echo " 4. Run the full app:"
echo "    python main.py"
echo "    python main.py --no-voice     # keyboard-only fallback"
echo "    python main.py --no-braille --no-gemma  # laptop demo mode"
echo "==========================================================="
