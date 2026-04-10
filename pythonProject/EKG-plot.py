# File: plot_ekg_waveform_basic.py
# Purpose: Display live ECG waveform from ADS1115

import time
from collections import deque

import board
import busio

from digitalio import DigitalInOut, Direction, Pull

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

import matplotlib.pyplot as plt
import matplotlib.animation as animation


# -----------------------------
# USER SETTINGS
# -----------------------------
buffer_size_number_of_samples = 500
sample_time_interval_seconds = 0.005


# -----------------------------
# SETUP I2C AND ADC
# -----------------------------
i2c_bus = busio.I2C(board.SCL, board.SDA)

adc_device = ADS.ADS1115(i2c_bus)
adc_device.gain = 1
adc_device.data_rate = 860

adc_channel_A0 = AnalogIn(adc_device, 0) # Changed from ADS.P0 to 0 for single-ended input on channel A0


# -----------------------------
# SETUP LEAD-OFF PINS
# -----------------------------
lead_off_positive_pin = DigitalInOut(board.D17)
lead_off_positive_pin.direction = Direction.INPUT
lead_off_positive_pin.pull = Pull.UP

lead_off_negative_pin = DigitalInOut(board.D27)
lead_off_negative_pin.direction = Direction.INPUT
lead_off_negative_pin.pull = Pull.UP


# -----------------------------
# DATA STORAGE (ROLLING BUFFER)
# -----------------------------
# deque automatically removes oldest value when full
ekg_voltage_buffer = deque([0.0] * buffer_size_number_of_samples,
                           maxlen=buffer_size_number_of_samples)

sample_index_buffer = deque(range(buffer_size_number_of_samples),
                            maxlen=buffer_size_number_of_samples)


# -----------------------------
# PLOT SETUP
# -----------------------------
figure_handle, axis_handle = plt.subplots()

line_handle, = axis_handle.plot(sample_index_buffer, ekg_voltage_buffer)

axis_handle.set_title("ECG Waveform")
axis_handle.set_xlabel("Sample Index")
axis_handle.set_ylabel("Voltage (V)")

axis_handle.set_ylim(0.0, 3.3)
axis_handle.set_xlim(0, buffer_size_number_of_samples - 1)

status_text_handle = axis_handle.text(0.02, 0.95, "",
                                      transform=axis_handle.transAxes)


last_sample_time = 0.0


# -----------------------------
# UPDATE FUNCTION (RUNS REPEATEDLY)
# -----------------------------
def update_plot(frame_number):
    global last_sample_time

    current_time = time.time()

    # Control sampling rate
    if current_time - last_sample_time >= sample_time_interval_seconds:
        last_sample_time = current_time

        is_lead_off = (not lead_off_positive_pin.value) or (not lead_off_negative_pin.value)

        if is_lead_off:
            new_voltage_value = 0.0
            status_text_handle.set_text("Lead Off")
        else:
            new_voltage_value = adc_channel_A0.voltage
            status_text_handle.set_text("Connected")

        ekg_voltage_buffer.append(new_voltage_value)

        line_handle.set_ydata(ekg_voltage_buffer)

    return line_handle, status_text_handle


# -----------------------------
# START ANIMATION
# -----------------------------
animation_object = animation.FuncAnimation(
    figure_handle,
    update_plot,
    interval=10
)

plt.show()