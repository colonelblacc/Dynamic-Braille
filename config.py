import os
 
# ---------- Camera ----------
CAMERA_RESOLUTION = (2304, 1296)   # Pi Camera 3 native-ish, good for OCR
CAMERA_WARMUP_SEC = 1.0            # AE/AWB settle time before first capture
CAPTURE_DIR = "/tmp/brailledesk"   # where captured frames are saved
os.makedirs(CAPTURE_DIR, exist_ok=True)
 
# ---------- OCR ----------
TESSERACT_LANG = "eng"
TESSERACT_PSM_BLOCK = 6            # assume a block of uniform text
TESSERACT_PSM_SPARSE = 11          # sparse text (page numbers etc.)
OCR_WARP_SIZE = (1600, 2200)       # target resolution after perspective warp
MIN_PAGE_AREA_RATIO = 0.25         # page contour must cover >=25% of frame
 
# ---------- Gemma (Ollama) ----------
OLLAMA_URL = "http://localhost:11434"
GEMMA_MODEL = "gemma2:2b"          # change to "gemma3:1b" for the 4GB Pi
GEMMA_TIMEOUT = 30                 # seconds
GEMMA_TEMPERATURE = 0.2            # low temp = deterministic cleanup
 
# ---------- Arduino / Braille ----------
SERIAL_PORT = "/dev/ttyACM0"       # Uno shows up here; Nano often /dev/ttyUSB0
SERIAL_BAUD = 9600
SERIAL_TIMEOUT = 2.0
BRAILLE_SETTLE_MS = 400            # wait after sending a packet for servos to move
 
# ---------- Logging ----------
LOG_LEVEL = "INFO"
 