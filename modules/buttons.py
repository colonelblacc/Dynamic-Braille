"""
Physical button handler using RPi.GPIO (BCM pin numbering).
Falls back silently when not running on a Pi or GPIO is unavailable.

Pin assignments are read from config.BUTTON_PINS, a dict mapping
BCM pin number -> action string (e.g. {17: "NEXT_WORD", 27: "REPEAT", ...}).
"""
import logging
import threading
from typing import Callable, Dict

import config

log = logging.getLogger(__name__)

# Canonical action names (mirror the intent strings in main.py)
SCAN       = "SCAN"
READ       = "READ"
NEXT_WORD  = "NEXT_WORD"
NEXT_LINE  = "NEXT_LINE"
REPEAT     = "REPEAT"
BRAILLE    = "BRAILLE"
EXPLAIN    = "EXPLAIN"
STOP       = "STOP"


class ButtonHandler:
    def __init__(self):
        self._gpio = None
        self._callbacks: Dict[str, Callable] = {}
        self._init()

    def _init(self):
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in config.BUTTON_PINS:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._gpio = GPIO
            log.info("GPIO buttons ready on pins: %s",
                     list(config.BUTTON_PINS.keys()))
        except ImportError:
            log.warning("RPi.GPIO not available — physical buttons disabled.")
        except Exception as e:
            log.warning("GPIO init failed (%s) — buttons disabled.", e)

    def register(self, action: str, callback: Callable):
        """Attach a callback to a button action."""
        self._callbacks[action] = callback
        if not self._gpio:
            return
        for pin, btn_action in config.BUTTON_PINS.items():
            if btn_action == action:
                try:
                    self._gpio.add_event_detect(
                        pin,
                        self._gpio.FALLING,
                        callback=lambda _ch, a=action: self._fire(a),
                        bouncetime=300,
                    )
                except Exception as e:
                    log.warning("GPIO event detect on pin %d failed: %s", pin, e)

    def _fire(self, action: str):
        cb = self._callbacks.get(action)
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def cleanup(self):
        if self._gpio:
            try:
                self._gpio.cleanup()
            except Exception:
                pass

    def is_available(self) -> bool:
        return self._gpio is not None
