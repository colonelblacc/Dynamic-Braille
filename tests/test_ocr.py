"""
Run OCR on a saved frame, or capture one live.
Usage:
    python tests/test_ocr.py                  # captures live
    python tests/test_ocr.py path/to/img.jpg  # processes an existing image
"""
import logging
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.ocr import process_frame   # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1:
        path = sys.argv[1]
        frame = cv2.imread(path)
        if frame is None:
            print(f"Could not read {path}")
            sys.exit(1)
    else:
        from modules.camera import Camera
        cam = Camera()
        cam.start()
        frame = cam.capture_sharpest(n=3)
        cam.stop()

    result = process_frame(frame)

    print("\n---- OCR RESULT ----")
    print(f"page_number : {result.page_number}")
    print(f"confidence  : {result.confidence:.2f}")
    print(f"text length : {len(result.text)} chars")
    print("---- TEXT (first 800 chars) ----")
    print(result.text[:800])

    if result.warped_image is not None:
        out = "/tmp/brailledesk/last_warp.jpg"
        cv2.imwrite(out, result.warped_image)
        print(f"\nWarped page saved to {out}")


if __name__ == "__main__":
    main()