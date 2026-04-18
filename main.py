"""
DynaBraille — AI-assisted multimodal reading desk for blind students.

Pipeline:
    Voice command / button press
        → intent parsing (rule-based, Gemma fallback)
        → camera capture + OCR
        → Gemma text cleanup / simplification
        → Gemini explanation / Q&A / navigation guidance
        → TTS spoken response
        → Braille cell output

Run:
    python main.py [--no-braille] [--no-gemma] [--no-gemini] [--no-voice]
"""
import argparse
import logging
import re
import textwrap
import threading
from typing import List, Optional

import config
from modules.camera import Camera
from modules.ocr import process_frame, OcrResult
from modules.gemma import GemmaClient
from modules.gemini import GeminiClient
from modules.tts import TTSEngine
from modules.voice import VoiceListener
from modules.braille import BrailleController
from modules.buttons import ButtonHandler


def _setup_logging():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )


# ---------------------------------------------------------------------------
# Intent parser — rule-based first, Gemma fallback
# ---------------------------------------------------------------------------

_GO_RE  = re.compile(r"(?:go to|open|turn to|find|page)\s+page\s*(\d+)", re.I)
_PAGE_RE = re.compile(r"\bpage\s*(\d+)\b", re.I)

def parse_intent(utterance: str, gemma: Optional[GemmaClient] = None) -> dict:
    t = utterance.lower().strip()

    m = _GO_RE.search(t) or _PAGE_RE.search(t) if "page" in t else None
    if m:
        return {"intent": "GO_TO_PAGE", "args": {"page": int(m.group(1))}}

    if any(w in t for w in ("scan", "capture", "take a photo", "photograph")):
        return {"intent": "SCAN", "args": {}}
    if re.search(r"\bread\b", t):
        return {"intent": "READ", "args": {}}
    if any(w in t for w in ("explain", "what does", "what is", "simplify",
                             "tell me about", "describe")):
        return {"intent": "EXPLAIN", "args": {}}
    if re.search(r"\bspell\b", t):
        return {"intent": "SPELL", "args": {}}
    if "next word" in t:
        return {"intent": "NEXT_WORD", "args": {}}
    if "next line" in t or "next sentence" in t:
        return {"intent": "NEXT_LINE", "args": {}}
    if "next" in t:
        return {"intent": "NEXT_WORD", "args": {}}
    if any(w in t for w in ("repeat", "say again", "again")):
        return {"intent": "REPEAT", "args": {}}
    if "braille" in t:
        return {"intent": "BRAILLE", "args": {}}
    if "summar" in t:
        return {"intent": "SUMMARY", "args": {}}
    if any(w in t for w in ("stop", "pause", "quiet", "silence")):
        return {"intent": "STOP", "args": {}}

    # Ask Gemma only if nothing matched locally
    if gemma:
        return gemma.parse_intent(utterance)
    return {"intent": "UNKNOWN", "args": {}}


# ---------------------------------------------------------------------------
# BrailleDesk — main application class
# ---------------------------------------------------------------------------

class BrailleDesk:
    def __init__(self, args):
        self.log = logging.getLogger("BrailleDesk")
        self._lock = threading.Lock()

        # Session state
        self.current_page: Optional[int] = None
        self.current_text: str = ""
        self.current_frame = None
        self.last_spoken: str = ""
        self._words: List[str] = []
        self._lines: List[str] = []
        self._word_idx: int = 0
        self._line_idx: int = 0

        # Hardware / AI modules (all optional with graceful degradation)
        self.cam = Camera()
        self.cam.start()

        self.tts = TTSEngine()

        self.gemma: Optional[GemmaClient] = None
        if not args.no_gemma:
            g = GemmaClient()
            if g.is_available():
                self.gemma = g
            else:
                self.log.warning("Gemma/Ollama not reachable; OCR cleanup disabled.")

        self.gemini: Optional[GeminiClient] = None
        if not args.no_gemini:
            g2 = GeminiClient()
            if g2.is_available():
                self.gemini = g2
            else:
                self.log.warning("Gemini not available; advanced AI disabled.")

        self.braille: Optional[BrailleController] = None
        if not args.no_braille:
            try:
                bc = BrailleController()
                bc.connect()
                self.braille = bc
            except Exception as e:
                self.log.warning("Braille controller unavailable (%s).", e)

        self.voice: Optional[VoiceListener] = None
        if not args.no_voice:
            vl = VoiceListener()
            if vl.is_available():
                self.voice = vl
            else:
                self.log.warning("Voice input unavailable; keyboard fallback active.")

        self.buttons = ButtonHandler()
        self._register_buttons()

    # -----------------------------------------------------------------------
    # Button wiring
    # -----------------------------------------------------------------------

    def _register_buttons(self):
        mapping = {
            "SCAN":      self.do_scan,
            "READ":      self.do_read,
            "NEXT_WORD": self.do_next_word,
            "NEXT_LINE": self.do_next_line,
            "REPEAT":    self.do_repeat,
            "BRAILLE":   self.do_braille_mode,
            "EXPLAIN":   self.do_explain,
            "STOP":      self.do_stop,
        }
        for action, cb in mapping.items():
            self.buttons.register(action, cb)

    # -----------------------------------------------------------------------
    # Core actions
    # -----------------------------------------------------------------------

    def do_scan(self):
        """Capture frame, run OCR, clean with Gemma, update session state."""
        self.say("Scanning the page...")
        frame = self.cam.capture_sharpest(n=3)
        self.cam.save(frame)
        self.current_frame = frame

        result: OcrResult = process_frame(frame)
        raw = result.text

        cleaned = raw
        if self.gemma and raw.strip():
            cleaned = self.gemma.clean_ocr(raw)

        self.current_text = cleaned.strip()
        self.current_page = result.page_number
        self._words = self.current_text.split()
        self._lines = [l.strip() for l in self.current_text.splitlines() if l.strip()]
        self._word_idx = 0
        self._line_idx = 0

        if result.page_number:
            self.say(f"Scanned page {result.page_number}.")
        else:
            self.say("Page scanned. Page number not detected.")

        if not self.current_text:
            self.say("No readable text found on this page.")
            return

        # Preview: read first line aloud
        preview = self._lines[0][:120] if self._lines else ""
        if preview:
            self.say(preview)

    def do_read(self):
        """Read the full page text aloud."""
        if not self.current_text:
            self.say("Nothing scanned yet. Please scan a page first.")
            return
        self.say("Reading the page.")
        chunk = textwrap.fill(self.current_text[:800], width=200)
        self.say(chunk)

    def do_next_word(self):
        """Speak and Braille the next word in the text."""
        if not self._words:
            self.say("Please scan a page first.")
            return
        if self._word_idx >= len(self._words):
            self.say("End of page.")
            self._word_idx = 0
            return
        word = self._words[self._word_idx]
        self._word_idx += 1
        self.say(word)
        self._braille_send(word + " ")

    def do_next_line(self):
        """Speak and Braille the next line."""
        if not self._lines:
            self.say("Please scan a page first.")
            return
        if self._line_idx >= len(self._lines):
            self.say("End of page.")
            self._line_idx = 0
            return
        line = self._lines[self._line_idx]
        self._line_idx += 1
        self.say(line)
        self._braille_send(line[:40])

    def do_repeat(self):
        """Repeat the last spoken text."""
        if self.last_spoken:
            self.say(self.last_spoken, record=False)
        else:
            self.say("Nothing to repeat yet.")

    def do_explain(self):
        """Use Gemini to explain the current page in simple language."""
        if not self.current_text:
            self.say("Nothing scanned yet. Please scan a page first.")
            return
        if not self.gemini:
            self.say("Explanation requires an internet connection and Gemini API key.")
            return
        self.say("Let me explain that for you...")
        explanation = self.gemini.explain_text(self.current_text[:1500])
        if explanation:
            self.say(explanation)
        else:
            self.say("I could not generate an explanation right now.")

    def do_braille_mode(self):
        """Send the first 40 characters of current text to the Braille cell."""
        if not self.current_text:
            self.say("Nothing scanned yet.")
            return
        if not self.braille:
            self.say("Braille cell not connected.")
            return
        preview = self.current_text[:40]
        self.say(f"Sending to Braille: {preview}")
        self._braille_send(preview)

    def do_stop(self):
        self.say("Stopping.")

    def do_go_to_page(self, target: int):
        """Guide the user to find a specific page."""
        if self.gemini:
            msg = self.gemini.guide_navigation(self.current_page, target)
        else:
            if self.current_page is None:
                msg = f"Please scan a page first so I can tell where you are."
            elif self.current_page == target:
                msg = f"You are already on page {target}."
            else:
                diff = target - self.current_page
                direction = "forward" if diff > 0 else "backward"
                n = abs(diff)
                msg = (f"You are on page {self.current_page}. "
                       f"Turn {n} {'page' if n == 1 else 'pages'} "
                       f"{direction} to reach page {target}.")
        self.say(msg)

    def do_spell(self):
        """Spell out the current word letter by letter."""
        if not self._words:
            self.say("Please scan a page first.")
            return
        idx = max(0, self._word_idx - 1)
        word = self._words[idx]
        spelled = ", ".join(word.upper())
        self.say(f"{word}: {spelled}")
        self._braille_send(word)

    def do_summary(self):
        """Use Gemini to summarize the page."""
        if not self.current_text:
            self.say("Nothing scanned yet.")
            return
        if not self.gemini:
            self.say("Summary requires Gemini. Please set GEMINI_API_KEY.")
            return
        self.say("Summarizing the page...")
        summary = self.gemini.summarize_page(self.current_text[:2000])
        if summary:
            self.say(summary)
        else:
            self.say("Could not generate a summary right now.")

    # -----------------------------------------------------------------------
    # Command dispatch
    # -----------------------------------------------------------------------

    def handle_command(self, utterance: str):
        self.log.info("Command: %r", utterance)
        intent = parse_intent(utterance, self.gemma)
        name = intent.get("intent", "UNKNOWN")
        args = intent.get("args", {})

        dispatch = {
            "SCAN":       self.do_scan,
            "READ":       self.do_read,
            "NEXT_WORD":  self.do_next_word,
            "NEXT_LINE":  self.do_next_line,
            "REPEAT":     self.do_repeat,
            "EXPLAIN":    self.do_explain,
            "BRAILLE":    self.do_braille_mode,
            "SPELL":      self.do_spell,
            "SUMMARY":    self.do_summary,
            "STOP":       self.do_stop,
        }

        if name == "GO_TO_PAGE":
            self.do_go_to_page(args.get("page", 1))
        elif name in dispatch:
            dispatch[name]()
        else:
            self.say("I didn't understand that. Try saying: scan, read, explain, "
                     "next word, next line, repeat, or go to page number.")

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def say(self, text: str, record: bool = True):
        if record:
            self.last_spoken = text
        self.tts.speak(text)

    def _braille_send(self, text: str):
        if self.braille:
            threading.Thread(
                target=self.braille.send_text,
                args=(text,),
                kwargs={"per_cell_delay_ms": 900},
                daemon=True,
            ).start()

    def shutdown(self):
        self.cam.stop()
        if self.braille:
            self.braille.close()
        if self.voice:
            self.voice.stop()
        self.buttons.cleanup()
        self.log.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Entry point — voice loop or keyboard fallback
# ---------------------------------------------------------------------------

def run(args):
    _setup_logging()
    log = logging.getLogger("main")

    desk = BrailleDesk(args)
    desk.say(
        "DynaBraille is ready. "
        "Say a command like: scan, read, explain, next word, or go to page 85."
    )

    try:
        if desk.voice and not args.no_voice:
            log.info("Starting continuous voice listening...")
            desk.say("Voice mode active. Listening for your commands.")
            desk.voice.start_continuous(desk.handle_command)

            # Keep main thread alive; voice runs in background thread
            while True:
                try:
                    cmd = input()           # still allows keyboard override
                    if cmd.strip():
                        desk.handle_command(cmd.strip())
                except EOFError:
                    import time; time.sleep(1)

        else:
            # Keyboard fallback — useful on a laptop or when no mic available
            desk.say("Keyboard mode. Type a command and press Enter.")
            while True:
                try:
                    cmd = input("\nCommand> ").strip()
                    if cmd:
                        desk.handle_command(cmd)
                except EOFError:
                    break

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        desk.shutdown()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DynaBraille reading desk")
    ap.add_argument("--no-braille", action="store_true",
                    help="Skip Arduino/Braille output")
    ap.add_argument("--no-gemma",   action="store_true",
                    help="Skip local Gemma OCR cleanup")
    ap.add_argument("--no-gemini",  action="store_true",
                    help="Skip Gemini cloud AI features")
    ap.add_argument("--no-voice",   action="store_true",
                    help="Keyboard input only (no microphone)")
    run(ap.parse_args())
