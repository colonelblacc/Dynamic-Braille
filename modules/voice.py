"""
Voice input using SpeechRecognition.
Primary backend: Google Web Speech API (online, no key needed).
Offline fallback: Vosk (if installed and model path configured).
"""
import logging
import queue
import threading
from typing import Callable, Optional

import config

log = logging.getLogger(__name__)


class VoiceListener:
    def __init__(self):
        self._rec = None
        self._mic = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init()

    def _init(self):
        try:
            import speech_recognition as sr
            self._sr = sr
            self._rec = sr.Recognizer()
            self._rec.energy_threshold = config.MIC_ENERGY_THRESHOLD
            self._rec.pause_threshold = 0.8
            self._rec.dynamic_energy_threshold = True
            log.info("Voice listener initialized")
        except ImportError:
            log.warning("SpeechRecognition not installed — voice input disabled.")

    def _get_mic(self):
        if self._mic is None:
            idx = config.MIC_DEVICE_INDEX  # None = system default
            self._mic = self._sr.Microphone(device_index=idx)
        return self._mic

    def listen_once(self, timeout: float = 6.0,
                    phrase_limit: float = 10.0) -> Optional[str]:
        """Blocking single utterance capture. Returns lowercase text or None."""
        if not self._rec:
            return None
        mic = self._get_mic()
        try:
            with mic as source:
                self._rec.adjust_for_ambient_noise(source, duration=0.3)
                log.info("Listening for command...")
                audio = self._rec.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
        except self._sr.WaitTimeoutError:
            return None
        except Exception as e:
            log.error("Mic capture failed: %s", e)
            return None
        return self._recognize(audio)

    def _recognize(self, audio) -> Optional[str]:
        try:
            text = self._rec.recognize_google(audio)
            log.info("Recognized: %r", text)
            return text.lower().strip()
        except self._sr.UnknownValueError:
            return None
        except self._sr.RequestError as e:
            log.warning("Google ASR error (%s); trying Vosk...", e)
            return self._vosk_fallback(audio)

    def _vosk_fallback(self, audio) -> Optional[str]:
        if not config.VOSK_MODEL_PATH:
            return None
        try:
            import json
            from vosk import Model, KaldiRecognizer
            model = Model(config.VOSK_MODEL_PATH)
            rec = KaldiRecognizer(model, 16000)
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            rec.AcceptWaveform(raw)
            result = json.loads(rec.FinalResult())
            return result.get("text", "").strip() or None
        except Exception as e:
            log.error("Vosk fallback failed: %s", e)
            return None

    def start_continuous(self, callback: Callable[[str], None]):
        """
        Background thread that calls callback(text) for each utterance.
        Runs until stop() is called.
        """
        if not self._rec:
            log.warning("Voice listener not available; ignoring start_continuous.")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, args=(callback,), daemon=True
        )
        self._thread.start()
        log.info("Continuous voice listening started")

    def _loop(self, callback: Callable[[str], None]):
        mic = self._get_mic()
        while self._running:
            try:
                with mic as source:
                    self._rec.adjust_for_ambient_noise(source, duration=0.2)
                    audio = self._rec.listen(
                        source, timeout=4.0, phrase_time_limit=8.0
                    )
                text = self._recognize(audio)
                if text:
                    callback(text)
            except self._sr.WaitTimeoutError:
                pass
            except Exception as e:
                log.error("Voice loop error: %s", e)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)

    def is_available(self) -> bool:
        return self._rec is not None
