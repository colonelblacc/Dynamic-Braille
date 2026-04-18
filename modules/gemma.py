"""
Gemma via Ollama HTTP API.
Ollama runs locally on the Pi (default port 11434).
We hit /api/generate with a tight prompt and low temperature.

Tasks:
    - clean_ocr: fix obvious OCR junk, keep meaning intact.
    - simplify_for_braille: shorten long paragraphs for the Braille cell.
    - parse_intent: fallback intent parser for free-form utterances.
"""
import json
import logging
from typing import Optional

import requests

import config

log = logging.getLogger(__name__)


class GemmaClient:
    def __init__(self, base_url: Optional[str] = None,
                 model: Optional[str] = None):
        self.base_url = base_url or config.OLLAMA_URL
        self.model = model or config.GEMMA_MODEL

    # ---------- low-level ----------

    def _generate(self, prompt: str, system: Optional[str] = None,
                  temperature: Optional[float] = None,
                  max_tokens: int = 400) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": (temperature
                                if temperature is not None
                                else config.GEMMA_TEMPERATURE),
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system
        try:
            r = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=config.GEMMA_TIMEOUT,
            )
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except requests.exceptions.RequestException as e:
            log.error("Gemma call failed: %s", e)
            return ""

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    # ---------- high-level tasks ----------

    def clean_ocr(self, raw: str) -> str:
        """Fix OCR artifacts without altering meaning."""
        if not raw.strip():
            return raw
        system = (
            "You are an OCR post-processor. Your only job is to fix "
            "obvious OCR errors in the given text. Fix 'rn' mis-read as 'm', "
            "remove hyphenation line breaks, join broken words, and fix "
            "spacing. DO NOT summarize. DO NOT paraphrase. DO NOT add any "
            "commentary. Return only the cleaned text."
        )
        prompt = f"Clean this OCR output:\n\n{raw}\n\nCleaned text:"
        cleaned = self._generate(prompt, system=system, temperature=0.1)
        return cleaned or raw  # fall back to raw if Gemma is down

    def simplify_for_braille(self, text: str, max_chars: int = 120) -> str:
        """Shorten a passage to fit a short Braille reading session."""
        system = (
            "You compress text for a Braille display. Keep key facts. "
            "Remove filler. Output plain ASCII only (a-z, 0-9, basic "
            "punctuation). No Markdown. No emojis."
        )
        prompt = (f"Compress this to under {max_chars} characters while "
                  f"keeping the core meaning:\n\n{text}\n\nCompressed:")
        return self._generate(prompt, system=system, temperature=0.2,
                              max_tokens=150)

    def parse_intent(self, utterance: str) -> dict:
        """Fallback intent parser. Returns {'intent': str, 'args': {...}}."""
        system = (
            "You convert spoken commands for a Braille reading desk into "
            "JSON. Output ONLY valid JSON, no prose. "
            "Valid intents: SCAN, READ, EXPLAIN, SPELL, BRAILLE, "
            "GO_TO_PAGE, NEXT_WORD, NEXT_LINE, REPEAT, UNKNOWN."
        )
        prompt = (
            "Utterance: \"" + utterance + "\"\n"
            "Example output for 'go to page 85': "
            '{"intent":"GO_TO_PAGE","args":{"page":85}}\n'
            "JSON:"
        )
        raw = self._generate(prompt, system=system,
                             temperature=0.1, max_tokens=80)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            log.warning("Gemma returned non-JSON intent: %s", raw)
            return {"intent": "UNKNOWN", "args": {}}