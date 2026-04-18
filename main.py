"""
BrailleDesk - integrated demo loop.

Happy path:
    press Enter -> capture -> OCR -> Gemma cleanup -> print -> stream to Braille
Quit with Ctrl+C.

This is deliberately a simple console loop. The voice layer and the full
state machine plug in on top of this scaffolding.
"""
import argparse
import logging
import sys
import textwrap

from modules.camera import Camera
from modules.ocr import process_frame
from modules.gemma import GemmaClient
from modules.braille import BrailleController


def run(no_braille: bool, no_gemma: bool):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    log = logging.getLogger("main")

    cam = Camera()
    cam.start()

    gem = None
    if not no_gemma:
        gem = GemmaClient()
        if not gem.is_available():
            log.warning("Gemma/Ollama not reachable; continuing without cleanup.")
            gem = None

    braille = None
    if not no_braille:
        try:
            braille = BrailleController()
            braille.connect()
        except Exception as e:
            log.warning("Braille controller not connected (%s); continuing.", e)
            braille = None

    try:
        while True:
            input("\nPress Enter to scan the page (Ctrl+C to quit)...")
            frame = cam.capture_sharpest(n=3)
            cam.save(frame)

            result = process_frame(frame)
            raw_text = result.text

            cleaned = raw_text
            if gem and raw_text.strip():
                log.info("Cleaning OCR with Gemma...")
                cleaned = gem.clean_ocr(raw_text)

            print("\n======== PAGE ========")
            print(f"page_number : {result.page_number}")
            print(f"confidence  : {result.confidence:.2f}")
            print("---- cleaned text ----")
            print(textwrap.fill(cleaned[:600], width=80))

            if braille:
                preview = cleaned.strip().split("\n")[0][:20]
                if preview:
                    log.info("Streaming first line to Braille: %r", preview)
                    braille.send_text(preview, per_cell_delay_ms=900)

    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        cam.stop()
        if braille:
            braille.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-braille", action="store_true",
                    help="skip Arduino/Braille output")
    ap.add_argument("--no-gemma", action="store_true",
                    help="skip Gemma cleanup step")
    args = ap.parse_args()
    run(no_braille=args.no_braille, no_gemma=args.no_gemma)