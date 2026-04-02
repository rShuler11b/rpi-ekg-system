# File: read_ekg_adc_basic.py
# Purpose: Read analog ECG signal from ADS1115 (A0) and print values

import time

import board
import busio

from digitalio import DigitalInOut, Direction, Pull

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn


# -----------------------------
# SETUP I2C COMMUNICATION
# -----------------------------
# board.SCL and board.SDA map to Pi pins 5 and 3
i2c_bus = busio.I2C(board.SCL, board.SDA)


# -----------------------------
# SETUP ADC (ADS1115)
# -----------------------------
adc_device = ADS.ADS1115(i2c_bus)

# Gain = input voltage range setting
adc_device.gain = 1

# Data rate = samples per second (max 860 for ADS1115)
adc_device.data_rate = 860


# -----------------------------
# SETUP ANALOG INPUT CHANNEL
# -----------------------------
# ADS.P0 corresponds to A0 pin on ADS1115
adc_channel_A0 = AnalogIn(adc_device, ADS.P0)


# -----------------------------
# SETUP LEAD-OFF DETECTION PINS
# -----------------------------
# These tell you if electrodes are disconnected

lead_off_positive_pin = DigitalInOut(board.D17)
lead_off_positive_pin.direction = Direction.INPUT
lead_off_positive_pin.pull = Pull.UP

lead_off_negative_pin = DigitalInOut(board.D27)
lead_off_negative_pin.direction = Direction.INPUT
lead_off_negative_pin.pull = Pull.UP


print("Starting ECG read loop...")
print("Voltage (V), Raw ADC Value, Lead Off Status")


# -----------------------------
# MAIN LOOP
# -----------------------------
while True:
    # Read analog voltage from AD8232 through ADS1115
    measured_voltage = adc_channel_A0.voltage

    # Raw ADC integer value
    measured_raw_value = adc_channel_A0.value

    # Lead-off logic (True if disconnected)
    is_lead_off = (not lead_off_positive_pin.value) or (not lead_off_negative_pin.value)

    print(f"{measured_voltage:.4f}, {measured_raw_value}, {int(is_lead_off)}")

    # Small delay to avoid flooding terminal
    time.sleep(0.01)