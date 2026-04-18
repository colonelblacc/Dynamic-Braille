"""
Smoke-test the Arduino Braille cell.
Cycles through 'HELLO' then 'abc123' and finally all-down.

Usage:
    python tests/test_arduino.py
    python tests/test_arduino.py /dev/ttyUSB0   # override the port

If you only want to test a single dot at a time, pass --single and a dot number:
    python tests/test_arduino.py --single 1
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.braille import BrailleController, text_to_cells, ALL_DOWN  # noqa: E402


def cycle_single(ctrl, dot_index):
    bits = ["0"] * 6
    bits[dot_index - 1] = "1"
    on = "".join(bits)
    for _ in range(3):
        ctrl.send_cell(on)
        time.sleep(0.8)
        ctrl.send_cell(ALL_DOWN)
        time.sleep(0.8)


def main():
    logging.basicConfig(level=logging.INFO)
    port = None
    single = None
    args = sys.argv[1:]
    if args and args[0] == "--single":
        single = int(args[1])
    elif args:
        port = args[0]

    ctrl = BrailleController(port=port)
    ctrl.connect()
    try:
        if single is not None:
            print(f"Cycling dot {single}")
            cycle_single(ctrl, single)
            return
        print("Writing 'HELLO'...")
        ctrl.send_text("HELLO", per_cell_delay_ms=1200)
        time.sleep(0.5)
        print("Writing 'abc 123'...")
        ctrl.send_text("abc 123", per_cell_delay_ms=1200)
        print("Resting.")
    finally:
        ctrl.close()


if __name__ == "__main__":
    main()