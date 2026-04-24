# ============================================================
# Name: Ryan Shuler
# Project: Raspberry Pi 5 Embedded ECG System
# File: lead_off.py
#
# Description:
#   Contains the LeadOffDetector class. This class owns the AD8232
#   LO+ and LO- digital input pins.
# ============================================================

import board
from digitalio import DigitalInOut, Direction, Pull


class LeadOffDetector:
    """
    Reads the AD8232 lead-off detection pins.

    The AD8232 drives LO+ or LO- HIGH when an electrode connection
    is poor or disconnected. The class returns True when either lead
    off pin is active.
    """

    def __init__(self, positive_pin=board.D17, negative_pin=board.D27):
        self.positive_pin = DigitalInOut(positive_pin)
        self.positive_pin.direction = Direction.INPUT
        self.positive_pin.pull = Pull.DOWN

        self.negative_pin = DigitalInOut(negative_pin)
        self.negative_pin.direction = Direction.INPUT
        self.negative_pin.pull = Pull.DOWN

    def is_lead_off(self):
        """Returns True if either AD8232 lead-off pin is HIGH."""
        return self.positive_pin.value is True or self.negative_pin.value is True

    def close(self):
        """Releases the GPIO resources used by the lead-off pins."""
        self.positive_pin.deinit()
        self.negative_pin.deinit()
