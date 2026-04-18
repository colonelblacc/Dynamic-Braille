"""
Text -> Grade-1 Braille -> 6-bit packet -> Arduino serial.

Packet format: "BRAILLE:abcdef\n"
where a..f are '0' or '1' for dots 1..6.

Dot numbering (standard Braille):
    1 4
    2 5
    3 6
"""
import logging
import time
from typing import List, Optional

import serial

import config

log = logging.getLogger(__name__)


# ---------- Grade-1 (uncontracted) Braille table ----------
# Each value is a 6-char string for dots 1..6.
# Standard English Braille (EBAE / UEB Grade 1 basic letters).

_LETTERS = {
    "a": "100000", "b": "110000", "c": "100100", "d": "100110",
    "e": "100010", "f": "110100", "g": "110110", "h": "110010",
    "i": "010100", "j": "010110", "k": "101000", "l": "111000",
    "m": "101100", "n": "101110", "o": "101010", "p": "111100",
    "q": "111110", "r": "111010", "s": "011100", "t": "011110",
    "u": "101001", "v": "111001", "w": "010111", "x": "101101",
    "y": "101111", "z": "101011",
}

# Digits use the letters a-j preceded by the number prefix (dots 3,4,5,6 = 001111)
_DIGIT_TO_LETTER = {
    "0": "j", "1": "a", "2": "b", "3": "c", "4": "d",
    "5": "e", "6": "f", "7": "g", "8": "h", "9": "i",
}

_PUNCT = {
    " ": "000000",
    ",": "010000",
    ";": "011000",
    ":": "010010",
    ".": "010011",
    "!": "011010",
    "?": "010011",
    "'": "001000",
    "-": "001001",
}

NUMBER_PREFIX = "001111"
CAPITAL_PREFIX = "000001"
ALL_DOWN = "000000"


def char_to_cells(ch: str) -> List[str]:
    """
    Return the sequence of 6-bit cells needed to render `ch`.
    Uppercase letters emit [CAPITAL_PREFIX, letter].
    Digits emit [NUMBER_PREFIX, letter a-j]  (caller should manage number mode
    if rendering a run of digits).
    """
    if ch.isupper():
        return [CAPITAL_PREFIX, _LETTERS.get(ch.lower(), ALL_DOWN)]
    if ch.isdigit():
        return [NUMBER_PREFIX, _LETTERS[_DIGIT_TO_LETTER[ch]]]
    if ch in _LETTERS:
        return [_LETTERS[ch]]
    if ch in _PUNCT:
        return [_PUNCT[ch]]
    return [ALL_DOWN]  # unknown char -> blank


def text_to_cells(text: str) -> List[str]:
    """
    Convert a full string into a cell sequence.
    Handles a basic 'number mode' so runs of digits only use one number prefix.
    """
    cells: List[str] = []
    in_number_mode = False
    for ch in text:
        if ch.isdigit():
            if not in_number_mode:
                cells.append(NUMBER_PREFIX)
                in_number_mode = True
            cells.append(_LETTERS[_DIGIT_TO_LETTER[ch]])
        else:
            in_number_mode = False
            cells.extend(char_to_cells(ch))
    return cells


# ---------- Serial interface ----------

class BrailleController:
    def __init__(self, port: Optional[str] = None,
                 baud: Optional[int] = None):
        self.port = port or config.SERIAL_PORT
        self.baud = baud or config.SERIAL_BAUD
        self.ser: Optional[serial.Serial] = None

    def connect(self):
        self.ser = serial.Serial(self.port, self.baud,
                                 timeout=config.SERIAL_TIMEOUT)
        time.sleep(2.0)  # Arduino resets on connect; wait for bootloader
        log.info("Connected to Arduino on %s @ %d baud", self.port, self.baud)
        # Drain any startup noise
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def close(self):
        if self.ser and self.ser.is_open:
            # Release all dots before disconnecting
            self.send_cell(ALL_DOWN)
            self.ser.close()

    def send_cell(self, six_bits: str) -> bool:
        """Send a single cell. Returns True on 'OK' acknowledgement."""
        if self.ser is None:
            raise RuntimeError("Serial not connected. Call connect() first.")
        if len(six_bits) != 6 or any(c not in "01" for c in six_bits):
            raise ValueError(f"Bad cell: {six_bits!r}")
        packet = f"BRAILLE:{six_bits}\n".encode("ascii")
        self.ser.write(packet)
        self.ser.flush()
        time.sleep(config.BRAILLE_SETTLE_MS / 1000.0)
        # Non-blocking read of ack
        try:
            line = self.ser.readline().decode(errors="ignore").strip()
            return line.startswith("OK")
        except Exception:
            return False

    def send_text(self, text: str, per_cell_delay_ms: int = 800):
        """Stream a text string through the single cell, one cell at a time."""
        cells = text_to_cells(text)
        log.info("Sending %d cells for %r", len(cells), text)
        for cell in cells:
            self.send_cell(cell)
            time.sleep(per_cell_delay_ms / 1000.0)
        self.send_cell(ALL_DOWN)  # rest state