# ============================================================
# Name: Ryan Shuler
# Project: Embedded ECG Monitoring System
# File: EKG-plot.py
#
# Description:
#   This program reads ECG voltage data from the ADS1115 ADC,
#   applies real-time digital filtering, and displays both
#   raw and filtered ECG signals live using matplotlib.
#
# Hardware:
#   - Raspberry Pi Zero 2 W
#   - AD8232 ECG Front End
#   - ADS1115 ADC (I2C)
#
# Filters Implemented:
#   1. High-pass filter (baseline drift removal)
#   2. Low-pass filter (noise smoothing)
#   3. 60 Hz notch filter (powerline interference)
#
# Output:
#   - Live graph with RAW and FILTERED ECG
#   - Terminal output of labeled raw data
# ============================================================

import time
import math
from collections import deque

import board
import busio
from digitalio import DigitalInOut, Direction, Pull

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

import matplotlib.pyplot as plt
import matplotlib.animation as animation


# ------------------------------------------------------------
# USER SETTINGS
# ------------------------------------------------------------
buffer_size_number_of_samples = 500
sample_time_interval_seconds = 0.005   # 200 Hz sampling rate

# Filter tuning parameters
high_pass_alpha = 0.995
low_pass_beta = 0.12

notch_filter_frequency_hz = 60.0
notch_filter_radius = 0.95


# ------------------------------------------------------------
# SETUP I2C AND ADC
# ------------------------------------------------------------
i2c_bus = busio.I2C(board.SCL, board.SDA)

adc_device = ADS.ADS1115(i2c_bus)
adc_device.gain = 1
adc_device.data_rate = 860

adc_channel_A0 = AnalogIn(adc_device, 0)


# ------------------------------------------------------------
# SETUP LEAD-OFF DETECTION PINS
# ------------------------------------------------------------
lead_off_positive_pin = DigitalInOut(board.D17)
lead_off_positive_pin.direction = Direction.INPUT
lead_off_positive_pin.pull = Pull.UP

lead_off_negative_pin = DigitalInOut(board.D27)
lead_off_negative_pin.direction = Direction.INPUT
lead_off_negative_pin.pull = Pull.UP


# ------------------------------------------------------------
# DATA BUFFERS
# deque automatically drops old data when full
# ------------------------------------------------------------
raw_voltage_buffer = deque([0.0] * buffer_size_number_of_samples,
                           maxlen=buffer_size_number_of_samples)

filtered_voltage_buffer = deque([0.0] * buffer_size_number_of_samples,
                                maxlen=buffer_size_number_of_samples)

sample_number_buffer = deque(range(buffer_size_number_of_samples),
                             maxlen=buffer_size_number_of_samples)


# ------------------------------------------------------------
# FILTER STATE VARIABLES (required for recursive filters)
# ------------------------------------------------------------

# High-pass
previous_raw_sample = 0.0
previous_high_pass_output = 0.0

# Low-pass
previous_low_pass_output = 0.0

# Notch
previous_notch_input_1 = 0.0
previous_notch_input_2 = 0.0
previous_notch_output_1 = 0.0
previous_notch_output_2 = 0.0


# ------------------------------------------------------------
# NOTCH FILTER CONSTANTS
# ------------------------------------------------------------
sampling_frequency_hz = 1.0 / sample_time_interval_seconds
notch_angular_frequency = 2.0 * math.pi * notch_filter_frequency_hz / sampling_frequency_hz
notch_cosine_term = math.cos(notch_angular_frequency)


# ------------------------------------------------------------
# FILTER FUNCTIONS
# ------------------------------------------------------------

def apply_high_pass_filter(current_raw_sample):
    """
    Removes slow baseline drift.

    Formula:
        y[n] = alpha * (y[n-1] + x[n] - x[n-1])

    x[n]   = current raw input sample
    x[n-1] = previous raw input sample
    y[n-1] = previous high-pass output
    y[n]   = current high-pass output
    """
    global previous_raw_sample
    global previous_high_pass_output

    current_high_pass_output = high_pass_alpha * (
        previous_high_pass_output
        + current_raw_sample
        - previous_raw_sample
    )

    # Update stored values for next iteration
    previous_raw_sample = current_raw_sample
    previous_high_pass_output = current_high_pass_output

    return current_high_pass_output


def apply_low_pass_filter(current_input_sample):
    """
    Smooths high-frequency noise.

    Formula:
        y[n] = beta * x[n] + (1 - beta) * y[n-1]

    x[n]   = current input sample
    y[n-1] = previous low-pass output
    y[n]   = current low-pass output
    """
    global previous_low_pass_output

    current_low_pass_output = (
        low_pass_beta * current_input_sample
        + (1.0 - low_pass_beta) * previous_low_pass_output
    )

    previous_low_pass_output = current_low_pass_output

    return current_low_pass_output


def apply_notch_filter(current_input_sample):
    """
    Removes 60 Hz powerline noise. (USA specific))

    Formula:
        y[n] = x[n]
               - 2*cos(w0)*x[n-1]
               + x[n-2]
               + 2*r*cos(w0)*y[n-1]
               - r^2*y[n-2]

    where:
        w0 = 2*pi*f/fs
        f  = notch frequency (60 Hz)
        fs = sample frequency
        r  = notch radius, close to 1 for a narrow notch
    """
    global previous_notch_input_1
    global previous_notch_input_2
    global previous_notch_output_1
    global previous_notch_output_2

    current_notch_output = (
        current_input_sample
        - 2.0 * notch_cosine_term * previous_notch_input_1
        + previous_notch_input_2
        + 2.0 * notch_filter_radius * notch_cosine_term * previous_notch_output_1
        - (notch_filter_radius ** 2) * previous_notch_output_2
    )

    # Shift stored values (acts like memory)
    previous_notch_input_2 = previous_notch_input_1
    previous_notch_input_1 = current_input_sample

    previous_notch_output_2 = previous_notch_output_1
    previous_notch_output_1 = current_notch_output

    return current_notch_output


def apply_full_filter_chain(current_raw_sample):
    """
    Apply filters in sequence:
    raw -> high-pass -> low-pass -> notch
    """
    hp = apply_high_pass_filter(current_raw_sample)
    lp = apply_low_pass_filter(hp)
    notch = apply_notch_filter(lp)

    return notch


# ------------------------------------------------------------
# PLOT SETUP
# ------------------------------------------------------------
figure_object, axis_object = plt.subplots()

raw_line_plot, = axis_object.plot(sample_number_buffer,
                                  raw_voltage_buffer,
                                  label="RAW ECG")

filtered_line_plot, = axis_object.plot(sample_number_buffer,
                                       filtered_voltage_buffer,
                                       label="FILTERED ECG")

axis_object.set_title("Live ECG Display")
axis_object.set_xlabel("Sample Number")
axis_object.set_ylabel("Voltage (V)")
axis_object.legend()
axis_object.grid(True)


# ------------------------------------------------------------
# ANIMATION LOOP (runs continuously)
# ------------------------------------------------------------
def update_plot(frame_number):

    lead_off_detected = (
        lead_off_positive_pin.value is True
        or lead_off_negative_pin.value is True
    )

    if lead_off_detected:
        print("LEAD OFF DETECTED")

        new_raw_voltage = 0.0
        new_filtered_voltage = 0.0
    else:
        new_raw_voltage = adc_channel_A0.voltage
        new_filtered_voltage = apply_full_filter_chain(new_raw_voltage)

        # ----------------------------------------------------
        # TERMINAL OUTPUT (LABELED)
        # ----------------------------------------------------
        print(f"RAW: {new_raw_voltage:.5f} V | FILTERED: {new_filtered_voltage:.5f} V")

    # Update buffers
    raw_voltage_buffer.append(new_raw_voltage)
    filtered_voltage_buffer.append(new_filtered_voltage)

    # Update graph lines
    raw_line_plot.set_ydata(raw_voltage_buffer)
    filtered_line_plot.set_ydata(filtered_voltage_buffer)

    # Auto-scale Y axis
    combined_minimum = min(min(raw_voltage_buffer), min(filtered_voltage_buffer))
    combined_maximum = max(max(raw_voltage_buffer), max(filtered_voltage_buffer))

    axis_object.set_ylim(combined_minimum - 0.1,
                         combined_maximum + 0.1)

    return raw_line_plot, filtered_line_plot


# ------------------------------------------------------------
# START LIVE DISPLAY
# ------------------------------------------------------------
plot_animation = animation.FuncAnimation(
    figure_object,
    update_plot,
    interval=sample_time_interval_seconds * 1000,
    blit=False
)

plt.show()