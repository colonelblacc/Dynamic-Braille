"""
Verify Gemma is reachable via Ollama and runs the three main tasks.
Run: python tests/test_gemma.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.gemma import GemmaClient   # noqa: E402


SAMPLE_OCR = (
    "Photosyn-\n"
    "thesis is the process by which gr een plants use sunliglit to\n"
    "convert carbon dioxide and water into glucose and oxgyen.\n"
    "The pro cess takes place in the chloro plasts, specifically\n"
    "using tbe green pigment chlorophyll."
)


def main():
    logging.basicConfig(level=logging.INFO)
    gem = GemmaClient()

    print("1) Availability check...")
    if not gem.is_available():
        print("   Ollama is not reachable at", gem.base_url)
        print("   Start it with:  ollama serve")
        sys.exit(1)
    print("   OK")

    print("\n2) Cleaning noisy OCR text...")
    cleaned = gem.clean_ocr(SAMPLE_OCR)
    print("---- cleaned ----")
    print(cleaned)

    print("\n3) Simplifying for Braille (<=120 chars)...")
    short = gem.simplify_for_braille(cleaned, max_chars=120)
    print(f"---- short ({len(short)} chars) ----")
    print(short)

    print("\n4) Intent parsing...")
    for u in [
        "open page 85",
        "read this paragraph for me",
        "show the word photosynthesis in braille",
        "repeat that",
    ]:
        print(f"   {u!r:55s} -> {gem.parse_intent(u)}")


if __name__ == "__main__":
    main()