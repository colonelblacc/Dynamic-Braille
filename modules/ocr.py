"""
Bilingual OCR pipeline (merged from main + branch1):

    frame
      → perspective warp  (main: handles camera-angle distortion)
      → deskew + preprocess  (branch1: corrects text skew)
      → enhance (CLAHE + denoise)
      → PaddleOCR English  [primary, real confidence scores]
           ├─ conf > OCR_HIGH_CONF  → accept English result
           ├─ conf < OCR_LOW_CONF   → hard-switch to Tesseract Malayalam
           └─ conf in between       → run both, pick higher-confidence winner
      → page-number extraction (main: dedicated strip OCR, top/bottom fallback)
      → OcrResult

Config toggles (config.py):
    PADDLE_ENABLED     – False → skip PaddleOCR, use Tesseract English only
    MALAYALAM_ENABLED  – False → skip Malayalam fallback
    TESSDATA_DIR       – path to local tessdata folder (for bundled .traineddata)
    OCR_HIGH_CONF      – default 0.80
    OCR_LOW_CONF       – default 0.60
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pytesseract

import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy PaddleOCR loader — only imported when PADDLE_ENABLED is True
# so the app still starts without paddlepaddle installed.
# ---------------------------------------------------------------------------

_paddle_engine = None

def _get_paddle():
    global _paddle_engine
    if _paddle_engine is None:
        try:
            from paddleocr import PaddleOCR
            _paddle_engine = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                use_gpu=config.PADDLE_USE_GPU,
                show_log=False,
            )
            log.info("PaddleOCR engine loaded.")
        except ImportError:
            log.warning("paddleocr not installed — falling back to Tesseract only.")
            _paddle_engine = None
    return _paddle_engine


# ---------------------------------------------------------------------------
# OcrResult
# ---------------------------------------------------------------------------

@dataclass
class OcrResult:
    text: str
    page_number: Optional[int] = None
    confidence: float = 0.0
    engine: str = "tesseract"          # which engine produced the final text
    blocks: List[str] = field(default_factory=list)
    warped_image: Optional[np.ndarray] = None


# ---------------------------------------------------------------------------
# 1. Perspective warp  (from main — corrects camera-angle distortion)
# ---------------------------------------------------------------------------

def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 corners as TL, TR, BR, BL."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect


def find_page_contour(frame: np.ndarray) -> Optional[np.ndarray]:
    """Return the 4-corner page contour, or None if not found."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 15
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    frame_area = frame.shape[0] * frame.shape[1]
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for c in contours[:5]:
        if cv2.contourArea(c) < config.MIN_PAGE_AREA_RATIO * frame_area:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2)
    return None


def warp_page(frame: np.ndarray, corners: np.ndarray,
              out_size=None) -> np.ndarray:
    out_w, out_h = out_size or config.OCR_WARP_SIZE
    src = _order_corners(corners.astype("float32"))
    dst = np.array([[0, 0], [out_w - 1, 0],
                    [out_w - 1, out_h - 1], [0, out_h - 1]],
                   dtype="float32")
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(frame, M, (out_w, out_h))


# ---------------------------------------------------------------------------
# 2. Deskew  (from branch1 — corrects text-line skew within the page)
# ---------------------------------------------------------------------------

def deskew(img: np.ndarray) -> np.ndarray:
    """
    Detect text skew angle via bounding-box of bright pixels and
    rotate the image to straighten it.
    Works on a grayscale or BGR image; always returns grayscale.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h),
                             flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
    return rotated


# ---------------------------------------------------------------------------
# 3. Enhancement  (from main — CLAHE + denoise + adaptive threshold)
# ---------------------------------------------------------------------------

def enhance_for_ocr(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )


# ---------------------------------------------------------------------------
# 4a. PaddleOCR — English primary engine  (from branch1)
#     Returns (text, page_number, avg_confidence)
#     Real per-word probabilities, so confidence is meaningful.
# ---------------------------------------------------------------------------

def _extract_paddle(img: np.ndarray) -> Tuple[str, Optional[str], float]:
    """Run PaddleOCR on a preprocessed (grayscale or BGR) image."""
    engine = _get_paddle()
    if engine is None:
        return "", None, 0.0

    result = engine.ocr(img, cls=True)
    extracted, page_number, confidences = "", None, []

    if result and result[0]:
        lines = result[0]
        # Sort top-to-bottom by Y-coordinate of first bounding-box point
        lines.sort(key=lambda x: x[0][0][1])

        for i, line in enumerate(lines):
            snippet = line[1][0].strip()
            score = float(line[1][1])

            # Page-number heuristic (edge position + all-digit content)
            is_digit = snippet.isdigit() or snippet.lower().replace("page", "").strip().isdigit()
            is_edge = (i <= 1) or (i >= len(lines) - 2)
            if is_digit and is_edge and page_number is None:
                page_number = "".join(filter(str.isdigit, snippet))
                continue

            extracted += snippet + " "
            confidences.append(score)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return extracted.strip(), page_number, avg_conf


# ---------------------------------------------------------------------------
# 4b. Tesseract Malayalam fallback  (from branch1)
#     Returns (text, None, avg_confidence)
#     Confidence is normalised to [0, 1] from Tesseract's 0-100 scale.
# ---------------------------------------------------------------------------

def _extract_malayalam(img: np.ndarray) -> Tuple[str, None, float]:
    """Run Tesseract Malayalam on a preprocessed image."""
    tess_cfg = "--oem 3 --psm 6 -l mal"
    if config.TESSDATA_DIR:
        tess_cfg += f" --tessdata-dir {config.TESSDATA_DIR}"

    try:
        data = pytesseract.image_to_data(
            img, config=tess_cfg,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as e:
        log.warning("Tesseract Malayalam failed (%s).", e)
        return "", None, 0.0

    parts, scores = [], []
    for i in range(len(data["text"])):
        conf = float(data["conf"][i])
        word = data["text"][i].strip()
        if conf > 0 and word:
            parts.append(word)
            scores.append(conf / 100.0)

    avg_conf = sum(scores) / len(scores) if scores else 0.0
    return " ".join(parts), None, avg_conf


# ---------------------------------------------------------------------------
# 4c. Tesseract English (original main path — used when PADDLE_ENABLED=False)
# ---------------------------------------------------------------------------

def _run_tesseract(img: np.ndarray, psm: int, whitelist: str = "") -> str:
    cfg = f"--oem 3 --psm {psm} -l {config.TESSERACT_LANG}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(img, config=cfg).strip()


# ---------------------------------------------------------------------------
# 5. Page-number extraction  (from main — dedicated strip + top/bottom fallback)
# ---------------------------------------------------------------------------

def extract_page_number(warped_gray: np.ndarray) -> Optional[int]:
    """Crop the bottom strip, OCR digits only, return int or None."""
    h, w = warped_gray.shape[:2]
    strip = warped_gray[int(h * 0.88):, :]
    raw = _run_tesseract(strip, config.TESSERACT_PSM_SPARSE,
                         whitelist="0123456789")
    nums = re.findall(r"\d{1,4}", raw)
    if not nums:
        strip = warped_gray[: int(h * 0.10), :]
        raw = _run_tesseract(strip, config.TESSERACT_PSM_SPARSE,
                             whitelist="0123456789")
        nums = re.findall(r"\d{1,4}", raw)
    if not nums:
        return None
    return int(min(nums, key=len))


# ---------------------------------------------------------------------------
# 6. Dynamic bilingual engine selection  (branch1 logic, adapted)
# ---------------------------------------------------------------------------

def _select_engine(img: np.ndarray) -> Tuple[str, float, str]:
    """
    Run the engine-selection logic and return (text, confidence, engine_name).

    Decision tree:
        PaddleOCR (English)
            ├─ conf > OCR_HIGH_CONF  ──────────► accept English
            ├─ conf in [LOW, HIGH]   ──────────► run Malayalam, pick winner
            └─ conf < OCR_LOW_CONF   ──────────► use Malayalam directly

    Falls back to Tesseract English if PaddleOCR is unavailable.
    """
    if not config.PADDLE_ENABLED or _get_paddle() is None:
        # Straight Tesseract English (original main behaviour)
        text = _run_tesseract(img, config.TESSERACT_PSM_BLOCK)
        conf = min(1.0, len(text) / 1500.0)   # length-based heuristic
        return text, conf, "tesseract-eng"

    text_en, _, conf_en = _extract_paddle(img)
    log.debug("PaddleOCR conf=%.2f  (%d chars)", conf_en, len(text_en))

    # High confidence — accept immediately
    if conf_en >= config.OCR_HIGH_CONF:
        log.info("OCR engine: PaddleOCR-English  (conf=%.2f ≥ %.2f)",
                 conf_en, config.OCR_HIGH_CONF)
        return text_en, conf_en, "paddle-eng"

    # Low confidence — skip PaddleOCR, go straight to Malayalam
    if conf_en < config.OCR_LOW_CONF and config.MALAYALAM_ENABLED:
        log.info("OCR engine: Tesseract-Malayalam  (paddle conf=%.2f < %.2f)",
                 conf_en, config.OCR_LOW_CONF)
        text_ml, _, conf_ml = _extract_malayalam(img)
        return text_ml, conf_ml, "tesseract-mal"

    # Medium confidence — run both, pick winner
    if config.MALAYALAM_ENABLED:
        text_ml, _, conf_ml = _extract_malayalam(img)
        log.info(
            "OCR medium zone — PaddleOCR=%.2f  Tesseract-Mal=%.2f",
            conf_en, conf_ml,
        )
        if conf_ml > conf_en:
            log.info("Winner: Tesseract-Malayalam")
            return text_ml, conf_ml, "tesseract-mal"
        log.info("Winner: PaddleOCR-English")
        return text_en, conf_en, "paddle-eng"

    # Malayalam disabled — stay with PaddleOCR even in medium zone
    return text_en, conf_en, "paddle-eng"


# ---------------------------------------------------------------------------
# 7. Public entry point
# ---------------------------------------------------------------------------

def process_frame(frame: np.ndarray) -> OcrResult:
    """
    Full bilingual pipeline: camera frame → OcrResult.

    Steps
    -----
    1. Perspective warp (straighten page from camera angle)
    2. Deskew (correct text-line tilt within page)
    3. CLAHE enhance (contrast + denoise)
    4. Engine selection (PaddleOCR → Malayalam → Tesseract-English)
    5. Page-number extraction (Tesseract digit strip)
    """
    # Step 1 — perspective warp
    corners = find_page_contour(frame)
    if corners is None:
        log.warning("No page contour found; using full frame.")
        warped = frame.copy()
    else:
        warped = warp_page(frame, corners)

    # Step 2 — deskew (returns grayscale)
    deskewed = deskew(warped)

    # Step 3 — CLAHE enhance
    enhanced = enhance_for_ocr(deskewed)

    # Step 4 — bilingual engine selection
    text, conf, engine = _select_engine(enhanced)

    # Step 5 — page number (dedicated Tesseract digit strip)
    page = extract_page_number(enhanced)

    # If PaddleOCR detected a page number inline, use it as fallback
    if page is None and engine.startswith("paddle"):
        _, paddle_page, _ = _extract_paddle(enhanced)
        if paddle_page is not None:
            try:
                page = int(paddle_page)
            except ValueError:
                pass

    result = OcrResult(
        text=text,
        page_number=page,
        confidence=conf,
        engine=engine,
        warped_image=warped,
    )
    log.info(
        "OCR done: engine=%s  chars=%d  page=%s  conf=%.2f",
        engine, len(text), page, conf,
    )
    return result