#!/usr/bin/env bash
# One-shot setup for BrailleDesk on a fresh Raspberry Pi OS (Bookworm, 64-bit).
# Run on the Pi with: bash setup.sh

set -e

echo "==> Updating apt packages"
sudo apt-get update
sudo apt-get install -y \
  python3-pip python3-venv \
  tesseract-ocr libtesseract-dev \
  python3-picamera2 \
  libatlas-base-dev \
  curl

echo "==> Installing Python deps"
pip install --break-system-packages -r requirements.txt

echo "==> Installing Ollama"
if ! command -v ollama &> /dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "==> Configuring Ollama to unload models quickly (save RAM on 4GB Pi)"
sudo mkdir -p /etc/systemd/system/ollama.service.d
echo -e "[Service]\nEnvironment=\"OLLAMA_KEEP_ALIVE=30s\"" | \
  sudo tee /etc/systemd/system/ollama.service.d/keepalive.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama || true

echo "==> Pulling Gemma (this will take a few minutes)"
ollama pull gemma2:2b

echo "==> Adding user to dialout group (for /dev/ttyUSB*)"
sudo usermod -a -G dialout $USER

echo ""
echo "Setup complete. Log out and back in so the dialout group takes effect."
echo "Then: python tests/test_camera.py"