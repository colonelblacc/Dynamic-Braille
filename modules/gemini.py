"""
Gemini API client for advanced AI tasks (explanation, Q&A, image description,
page navigation guidance).  Requires GEMINI_API_KEY in config or environment.
"""
import logging
import os
from typing import Optional

import numpy as np

import config

log = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None,
                 model: Optional[str] = None):
        key = api_key or config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        self._model_name = model or config.GEMINI_MODEL
        self._model = None
        if key:
            self._init(key)
        else:
            log.warning("GEMINI_API_KEY not set — Gemini features disabled.")

    def _init(self, key: str):
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            self._model = genai.GenerativeModel(self._model_name)
            log.info("Gemini ready (model=%s)", self._model_name)
        except ImportError:
            log.warning("google-generativeai not installed — Gemini disabled.")
        except Exception as e:
            log.error("Gemini init failed: %s", e)

    def is_available(self) -> bool:
        return self._model is not None

    # ---------- high-level tasks ----------

    def explain_text(self, text: str,
                     level: str = "middle school") -> str:
        """Simplify a textbook passage for a blind student."""
        prompt = (
            f"You are a patient tutor helping a blind student understand a textbook. "
            f"Explain the following passage in clear, simple language at {level} level. "
            f"Keep it under 80 words and speak directly to the student.\n\n"
            f"Passage:\n{text}\n\nExplanation:"
        )
        return self._generate(prompt)

    def answer_question(self, question: str, context: str) -> str:
        """Answer a question based on the currently scanned page text."""
        prompt = (
            f"You are helping a blind student reading a textbook. "
            f"Answer the question using only the page text below. "
            f"Be brief (under 60 words).\n\n"
            f"Page text:\n{context}\n\n"
            f"Question: {question}\nAnswer:"
        )
        return self._generate(prompt)

    def guide_navigation(self, current_page: Optional[int],
                         target_page: int) -> str:
        """Return a spoken page-turning instruction."""
        if current_page is None:
            return (
                f"I cannot read the current page number. "
                f"Please find page {target_page} manually."
            )
        if current_page == target_page:
            return f"You are already on page {target_page}."
        diff = target_page - current_page
        direction = "forward" if diff > 0 else "backward"
        n = abs(diff)
        word = "page" if n == 1 else "pages"
        return (
            f"You are on page {current_page}. "
            f"Turn {n} {word} {direction} to reach page {target_page}."
        )

    def describe_image(self, frame: np.ndarray) -> str:
        """Describe a diagram or figure visible in the camera frame."""
        if not self.is_available():
            return "Image description is not available right now."
        try:
            import cv2
            import google.generativeai as genai
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            img_part = {
                "mime_type": "image/jpeg",
                "data": buf.tobytes(),
            }
            response = self._model.generate_content(
                [
                    (
                        "Describe what is shown in this image for a blind student. "
                        "Focus on any diagrams, figures, charts, or illustrations. "
                        "Be concise — under 60 words."
                    ),
                    img_part,
                ]
            )
            return response.text.strip()
        except Exception as e:
            log.error("Gemini describe_image failed: %s", e)
            return "Could not describe the image."

    def summarize_page(self, text: str) -> str:
        """Return a short spoken summary of the full page."""
        prompt = (
            f"Summarize the following textbook page for a blind student in 3 sentences. "
            f"Focus on the main topic and key points. Speak directly.\n\n"
            f"{text}\n\nSummary:"
        )
        return self._generate(prompt)

    # ---------- internal ----------

    def _generate(self, prompt: str, max_retries: int = 1) -> str:
        if not self.is_available():
            return ""
        for attempt in range(max_retries + 1):
            try:
                response = self._model.generate_content(prompt)
                return response.text.strip()
            except Exception as e:
                log.error("Gemini generate failed (attempt %d): %s", attempt + 1, e)
        return ""
