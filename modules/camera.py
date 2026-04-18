"""
Pi Camera 3 capture wrapper using picamera2.
Falls back to a USB camera via OpenCV if picamera2 isn't available
(handy when developing on a laptop).
"""
import logging
import os
import time
from datetime import datetime

import cv2
import numpy as np

import config

log = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    _HAS_PICAMERA = True
except ImportError:
    _HAS_PICAMERA = False
    log.warning("picamera2 not available, will fall back to USB camera")


class Camera:
    """Encapsulates frame capture. Call start() once, capture() many times."""

    def __init__(self, resolution=None):
        self.resolution = resolution or config.CAMERA_RESOLUTION
        self._picam = None
        self._usbcap = None
        self._started = False

    def start(self):
        if self._started:
            return
        if _HAS_PICAMERA:
            self._picam = Picamera2()
            cfg = self._picam.create_still_configuration(
                main={"size": self.resolution, "format": "RGB888"}
            )
            self._picam.configure(cfg)
            self._picam.start()
            time.sleep(config.CAMERA_WARMUP_SEC)
            log.info("Pi Camera started at %s", self.resolution)
        else:
            self._usbcap = cv2.VideoCapture(0)
            self._usbcap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self._usbcap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            if not self._usbcap.isOpened():
                raise RuntimeError("No camera available (Pi or USB).")
            time.sleep(config.CAMERA_WARMUP_SEC)
            log.info("USB camera started")
        self._started = True

    def capture(self):
        """Return a single BGR frame as a numpy array."""
        if not self._started:
            self.start()
        if self._picam is not None:
            frame_rgb = self._picam.capture_array()
            # picamera2 gives RGB, OpenCV expects BGR
            return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        ok, frame = self._usbcap.read()
        if not ok:
            raise RuntimeError("Failed to read frame from USB camera")
        return frame

    def capture_sharpest(self, n=3):
        """Capture n frames, return the sharpest (highest Laplacian variance)."""
        best = None
        best_score = -1.0
        for _ in range(n):
            f = self.capture()
            score = cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY),
                                  cv2.CV_64F).var()
            if score > best_score:
                best_score, best = score, f
            time.sleep(0.1)
        log.info("Sharpest of %d frames, score=%.1f", n, best_score)
        return best

    def save(self, frame, path=None):
        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(config.CAPTURE_DIR, f"capture_{ts}.jpg")
        cv2.imwrite(path, frame)
        log.info("Saved frame to %s", path)
        return path

    def stop(self):
        if self._picam is not None:
            self._picam.stop()
        if self._usbcap is not None:
            self._usbcap.release()
        self._started = False