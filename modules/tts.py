"""
Text-to-speech output using pyttsx3 (offline, espeak on Pi).
Prints every utterance to console so the demo works even without audio hardware.
"""
import logging
import threading
from typing import Optional

import config

log = logging.getLogger(__name__)


class TTSEngine:
    def __init__(self, rate: Optional[int] = None, volume: float = 0.95):
        self._rate = rate or config.TTS_RATE
        self._volume = volume
        self._engine = None
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
            engine.setProperty("volume", self._volume)
            voices = engine.getProperty("voices")
            if voices:
                engine.setProperty("voice", voices[0].id)
            self._engine = engine
            log.info("TTS engine ready (rate=%d)", self._rate)
        except Exception as e:
            log.warning("pyttsx3 unavailable (%s) — console-only output.", e)

    def speak(self, text: str):
        """Speak text, blocking until done."""
        print(f"\n[SPEECH] {text}")
        if not self._engine:
            return
        with self._lock:
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                log.error("TTS speak error: %s", e)

    def speak_async(self, text: str):
        """Speak without blocking the caller."""
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()

    def is_available(self) -> bool:
        return self._engine is not None
