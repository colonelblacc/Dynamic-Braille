"""
Capture a single frame from the Pi Camera 3 (or USB fallback) and save it.
Run: python tests/test_camera.py
"""
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.camera import Camera   # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO)
    cam = Camera()
    try:
        cam.start()
        frame = cam.capture_sharpest(n=3)
        path = cam.save(frame)
        print(f"Saved: {path}")
        print(f"Frame shape: {frame.shape}")
    finally:
        cam.stop()


if __name__ == "__main__":
    main()