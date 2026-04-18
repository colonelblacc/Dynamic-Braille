"""
OCR pipeline:
    frame -> page detection -> perspective warp -> enhance -> tesseract
Also provides page-number extraction from the bottom strip.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np
import pytesseract

import config

log = logging.getLogger(__name__)


@dataclass
class OcrResult:
    text: str
    page_number: Optional[int] = None
    confidence: float = 0.0
    blocks: List[str] = field(default_factory=list)
    warped_image: Optional[np.ndarray] = None


# ---------- 1. Page detection + perspective warp ----------

def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 corners as TL, TR, BR, BL."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]       # top-left has smallest x+y
    rect[2] = pts[np.argmax(s)]       # bottom-right has largest x+y
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]       # top-right
    rect[3] = pts[np.argmax(d)]       # bottom-left
    return rect


def find_page_contour(frame: np.ndarray) -> Optional[np.ndarray]:
    """Return the 4-corner page contour, or None if not found."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Adaptive threshold works well when the desk mat is much darker than the page
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


# ---------- 2. Enhancement for OCR ----------

def enhance_for_ocr(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    # CLAHE improves contrast on unevenly lit pages
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    # Mild denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    # Adaptive threshold to a clean binary image
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )


# ---------- 3. Tesseract wrappers ----------

def _run_tesseract(img: np.ndarray, psm: int, whitelist: str = "") -> str:
    cfg = f"--oem 3 --psm {psm} -l {config.TESSERACT_LANG}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(img, config=cfg).strip()


def extract_text(warped_gray: np.ndarray) -> str:
    return _run_tesseract(warped_gray, config.TESSERACT_PSM_BLOCK)


def extract_page_number(warped_gray: np.ndarray) -> Optional[int]:
    """Crop bottom strip, OCR digits only, return int or None."""
    h, w = warped_gray.shape[:2]
    # bottom 12% of the page
    strip = warped_gray[int(h * 0.88):, :]
    raw = _run_tesseract(strip, config.TESSERACT_PSM_SPARSE, whitelist="0123456789")
    nums = re.findall(r"\d{1,4}", raw)
    if not nums:
        # try top 10% as a fallback (some books put page numbers at the top)
        strip = warped_gray[: int(h * 0.10), :]
        raw = _run_tesseract(strip, config.TESSERACT_PSM_SPARSE,
                             whitelist="0123456789")
        nums = re.findall(r"\d{1,4}", raw)
    if not nums:
        return None
    # pick the shortest reasonable number (page numbers rarely > 4 digits)
    candidate = min(nums, key=len)
    return int(candidate)


# ---------- 4. Public entry point ----------

def process_frame(frame: np.ndarray) -> OcrResult:
    """Full pipeline: frame -> OcrResult."""
    corners = find_page_contour(frame)
    if corners is None:
        log.warning("No page contour found; using full frame.")
        warped = frame.copy()
    else:
        warped = warp_page(frame, corners)
    enhanced = enhance_for_ocr(warped)
    text = extract_text(enhanced)
    page = extract_page_number(enhanced)
    # crude confidence: length of text / expected length
    conf = min(1.0, len(text) / 1500.0)
    result = OcrResult(text=text, page_number=page,
                       confidence=conf, warped_image=warped)
    log.info("OCR: %d chars, page=%s, conf=%.2f",
             len(text), page, conf)
    return result