import os

# ---------- Camera ----------
CAMERA_RESOLUTION = (2304, 1296)   # Pi Camera 3 native; good for OCR
CAMERA_WARMUP_SEC = 1.0
CAPTURE_DIR = "/tmp/brailledesk"
os.makedirs(CAPTURE_DIR, exist_ok=True)

# ---------- OCR ----------
TESSERACT_LANG = "eng"
TESSERACT_PSM_BLOCK = 6            # uniform block of text
TESSERACT_PSM_SPARSE = 11          # sparse text (page numbers)
OCR_WARP_SIZE = (1600, 2200)
MIN_PAGE_AREA_RATIO = 0.25

# ---------- Bilingual OCR (PaddleOCR + Malayalam fallback) ----------
PADDLE_ENABLED = True              # set False to skip PaddleOCR (English-only, lighter)
PADDLE_USE_GPU = False             # set True if CUDA is available
MALAYALAM_ENABLED = True           # set False to disable Tesseract Malayalam fallback
TESSDATA_DIR = ""                  # path to tessdata dir; "" = system default
# Confidence thresholds for dynamic engine switching
OCR_HIGH_CONF = 0.80               # above this → accept PaddleOCR result directly
OCR_LOW_CONF  = 0.60               # below this → hard-switch to Malayalam Tesseract

# ---------- Gemma (Ollama — local) ----------
OLLAMA_URL = "http://localhost:11434"
GEMMA_MODEL = "gemma2:2b"          # use "gemma3:1b" on 4GB Pi
GEMMA_TIMEOUT = 30
GEMMA_TEMPERATURE = 0.2

# ---------- Gemini (cloud) ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-1.5-flash"  # fast + cheap; switch to "gemini-1.5-pro" for depth

# ---------- Arduino / Braille ----------
SERIAL_PORT = "/dev/ttyACM0"       # Uno: ttyACM0  |  Nano: ttyUSB0
SERIAL_BAUD = 9600
SERIAL_TIMEOUT = 2.0
BRAILLE_SETTLE_MS = 400

# ---------- TTS ----------
TTS_RATE = 150                     # words per minute (espeak default ~175)

# ---------- Voice / Microphone ----------
MIC_DEVICE_INDEX = None            # None = system default
MIC_ENERGY_THRESHOLD = 300        # SpeechRecognition energy gate
VOSK_MODEL_PATH = ""               # set to path of vosk model dir for offline ASR

# ---------- Physical Buttons (BCM pin numbers) ----------
# Map BCM GPIO pin -> action string.  Edit for your wiring.
BUTTON_PINS: dict = {
    17: "SCAN",
    27: "READ",
    22: "NEXT_WORD",
    23: "NEXT_LINE",
    24: "REPEAT",
    25: "BRAILLE",
    5:  "EXPLAIN",
    6:  "STOP",
}

# ---------- Logging ----------
LOG_LEVEL = "INFO"
