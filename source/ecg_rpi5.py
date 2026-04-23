# ============================================================
# Name: Ryan Shuler
# Project: Embedded ECG Monitoring System
# File: ecg_rpi5.py
#
# Description:
#   This program reads ECG voltage data from the MCP3202 ADC
#   over SPI, applies real-time digital filtering, displays
#   only the filtered ECG signal using matplotlib, and records
#   ECG data to a CSV file during runtime.
#
# Hardware:
#   - Raspberry Pi 5 8GB
#   - AD8232 ECG Front End
#   - MCP3202 ADC (SPI)
#
# Filters Implemented:
#   1. High-pass filter (baseline drift removal)
#   2. Low-pass filter (noise smoothing)
#   3. 60 Hz notch filter (powerline interference)
#
# Output:
#   - Live graph with FILTERED ECG only
#   - Terminal output of labeled raw and filtered data
#   - CSV recording of sample number, timestamp, raw voltage,
#     filtered voltage, and lead-off flag
#
# Notes:
#   - Lead-off pins use pull-down resistors
#   - Plot uses a fixed y-axis for a cleaner waveform display
#   - Sampling is decoupled from plotting for steadier timing
#   - MCP3202 is a 12-bit SPI ADC, so ADC counts are converted
#     to voltage manually using the reference voltage
# ============================================================

import math
import time
import threading
from collections import deque

import board
from digitalio import DigitalInOut, Direction, Pull
import spidev

import matplotlib.pyplot as plt
import matplotlib.animation as animation

from recording_utils import (
    open_recording_file,
    append_sample_to_csv,
    close_recording_file
)


# ------------------------------------------------------------
# USER SETTINGS
# ------------------------------------------------------------
buffer_size_number_of_samples = 500
sample_time_interval_seconds = 0.005   # 200 samples per second

# Filter tuning parameters
high_pass_alpha = 0.98
low_pass_beta = 0.2

notch_filter_frequency_hz = 60.0
notch_filter_radius = 0.98

# Static plot limits
plot_y_axis_minimum = -0.25
plot_y_axis_maximum = 0.25

# Terminal printing
terminal_print_every_n_samples = 10

# MCP3202 ADC settings
mcp3202_reference_voltage = 3.3
mcp3202_channel_number = 0

# SPI settings
spi_bus_number = 0
spi_chip_select_number = 0
spi_clock_speed_hz = 500000

# Plot refresh interval in milliseconds
plot_refresh_interval_milliseconds = 25


# ------------------------------------------------------------
# SETUP SPI AND MCP3202 ADC
# ------------------------------------------------------------
spi_device = spidev.SpiDev()
spi_device.open(spi_bus_number, spi_chip_select_number)
spi_device.max_speed_hz = spi_clock_speed_hz
spi_device.mode = 0b00


def read_mcp3202_voltage(channel_number=0, reference_voltage=3.3):
    """
    Reads one sample from the MCP3202 and converts it to volts.

    Parameters:
        channel_number:
            ADC channel to read. Valid values are 0 and 1.

        reference_voltage:
            Voltage applied to the MCP3202 reference pin.

    Returns:
        adc_code:
            Integer ADC result from 0 to 4095.

        measured_voltage:
            Converted analog voltage in volts.

    Control bits:
        Start bit = 1
        SGL/DIFF  = 1 for single-ended mode
        ODD/SIGN  = 0 for CH0, 1 for CH1
        MSBF      = 1 for MSB-first output
    """
    if channel_number not in (0, 1):
        raise ValueError("channel_number must be 0 or 1")

    if channel_number == 0:
        control_bits = 0b1100
    else:
        control_bits = 0b1110

    spi_response = spi_device.xfer2([0x01, control_bits << 4, 0x00])

    adc_code = ((spi_response[1] & 0x0F) << 8) | spi_response[2]
    measured_voltage = (adc_code / 4095.0) * reference_voltage

    return adc_code, measured_voltage


# ------------------------------------------------------------
# SETUP LEAD-OFF DETECTION PINS
# ------------------------------------------------------------
lead_off_positive_pin = DigitalInOut(board.D17)
lead_off_positive_pin.direction = Direction.INPUT
lead_off_positive_pin.pull = Pull.DOWN

lead_off_negative_pin = DigitalInOut(board.D27)
lead_off_negative_pin.direction = Direction.INPUT
lead_off_negative_pin.pull = Pull.DOWN


# ------------------------------------------------------------
# DATA BUFFERS
# ------------------------------------------------------------
raw_voltage_buffer = deque(
    [0.0] * buffer_size_number_of_samples,
    maxlen=buffer_size_number_of_samples
)

filtered_voltage_buffer = deque(
    [0.0] * buffer_size_number_of_samples,
    maxlen=buffer_size_number_of_samples
)

x_axis_samples = list(range(buffer_size_number_of_samples))


# ------------------------------------------------------------
# THREADING OBJECTS
# ------------------------------------------------------------
data_lock = threading.Lock()
stop_event = threading.Event()


# ------------------------------------------------------------
# FILTER STATE VARIABLES
# These values are only written by the sampling thread.
# ------------------------------------------------------------
previous_raw_sample = 0.0
previous_high_pass_output = 0.0
previous_low_pass_output = 0.0

previous_notch_input_1 = 0.0
previous_notch_input_2 = 0.0
previous_notch_output_1 = 0.0
previous_notch_output_2 = 0.0


# ------------------------------------------------------------
# NOTCH FILTER CONSTANTS
# fs = sampling frequency
# w0 = digital notch frequency in radians/sample
# ------------------------------------------------------------
sampling_frequency_hz = 1.0 / sample_time_interval_seconds
notch_angular_frequency = (
    2.0 * math.pi * notch_filter_frequency_hz / sampling_frequency_hz
)
notch_cosine_term = math.cos(notch_angular_frequency)


# ------------------------------------------------------------
# RECORDING SETUP
# ------------------------------------------------------------
csv_file_object, csv_writer_object, csv_file_path = open_recording_file()
print(f"Recording to: {csv_file_path}")

recording_start_time_seconds = time.time()


# ------------------------------------------------------------
# SIGNAL PROCESSING FUNCTIONS
# ------------------------------------------------------------
def apply_high_pass_filter(current_raw_sample):
    """
    Removes slow baseline drift from the ECG signal.

    Formula:
        y[n] = alpha * ( y[n-1] + x[n] - x[n-1] )

    Variables:
        x[n]   = current raw sample
        x[n-1] = previous raw sample
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

    previous_raw_sample = current_raw_sample
    previous_high_pass_output = current_high_pass_output

    return current_high_pass_output


def apply_low_pass_filter(current_input_sample):
    """
    Smooths high-frequency noise.

    Formula:
        y[n] = beta * x[n] + (1 - beta) * y[n-1]

    Variables:
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
    Removes narrowband 60 Hz powerline interference.

    Formula:
        y[n] = x[n]
               - 2*cos(w0)*x[n-1]
               + x[n-2]
               + 2*r*cos(w0)*y[n-1]
               - r^2*y[n-2]

    Variables:
        x[n]   = current input sample
        x[n-1] = previous notch input
        x[n-2] = second previous notch input
        y[n-1] = previous notch output
        y[n-2] = second previous notch output
        w0     = notch angular frequency
        r      = notch radius
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

    previous_notch_input_2 = previous_notch_input_1
    previous_notch_input_1 = current_input_sample

    previous_notch_output_2 = previous_notch_output_1
    previous_notch_output_1 = current_notch_output

    return current_notch_output


def apply_full_filter_chain(current_raw_sample):
    """
    Filter order:
        raw -> high-pass -> low-pass -> notch
    """
    high_pass_output = apply_high_pass_filter(current_raw_sample)
    low_pass_output = apply_low_pass_filter(high_pass_output)
    notch_output = apply_notch_filter(low_pass_output)

    return notch_output


# ------------------------------------------------------------
# SAMPLING THREAD
# This loop owns timing, acquisition, filtering, and recording.
# ------------------------------------------------------------
def sampling_loop():
    current_sample_index = 0
    next_sample_time_seconds = time.perf_counter()

    while not stop_event.is_set():
        lead_off_detected = (
            lead_off_positive_pin.value is True
            or lead_off_negative_pin.value is True
        )

        timestamp_seconds = time.time() - recording_start_time_seconds

        if lead_off_detected:
            adc_code = 0
            new_raw_voltage = 0.0
            new_filtered_voltage = 0.0
            lead_off_flag = 1

            if current_sample_index % terminal_print_every_n_samples == 0:
                print("LEAD OFF DETECTED | ADC:    0 | RAW: 0.00000 V | FILTERED: 0.00000 V")

        else:
            adc_code, new_raw_voltage = read_mcp3202_voltage(
                channel_number=mcp3202_channel_number,
                reference_voltage=mcp3202_reference_voltage
            )

            new_filtered_voltage = apply_full_filter_chain(new_raw_voltage)
            lead_off_flag = 0

            if current_sample_index % terminal_print_every_n_samples == 0:
                print(
                    f"ADC: {adc_code:4d} | "
                    f"RAW: {new_raw_voltage:.5f} V | "
                    f"FILTERED: {new_filtered_voltage:.5f} V"
                )

        append_sample_to_csv(
            csv_writer_object=csv_writer_object,
            sample_index=current_sample_index,
            timestamp_seconds=timestamp_seconds,
            raw_voltage=new_raw_voltage,
            filtered_voltage=new_filtered_voltage,
            lead_off_flag=lead_off_flag
        )

        with data_lock:
            raw_voltage_buffer.append(new_raw_voltage)
            filtered_voltage_buffer.append(new_filtered_voltage)

        current_sample_index += 1

        # Advance the target time by exactly one sample period.
        # This keeps the loop aligned to the intended sample clock
        # instead of sleeping for a fresh full interval each time.
        next_sample_time_seconds += sample_time_interval_seconds

        remaining_time_seconds = (
            next_sample_time_seconds - time.perf_counter()
        )

        if remaining_time_seconds > 0:
            time.sleep(remaining_time_seconds)
        else:
            # If the loop falls behind, timing continues from the
            # already scheduled target sequence instead of resetting
            # around a delayed iteration.
            pass


# ------------------------------------------------------------
# PLOT SETUP
# The plot reads existing data only. It does not acquire samples.
# ------------------------------------------------------------
figure_object, axis_object = plt.subplots()

filtered_line_plot, = axis_object.plot(
    x_axis_samples,
    list(filtered_voltage_buffer),
    label="FILTERED ECG"
)

axis_object.set_title("Filtered Live ECG Display")
axis_object.set_xlabel("Sample Position in Buffer")
axis_object.set_ylabel("Voltage (V)")
axis_object.set_ylim(plot_y_axis_minimum, plot_y_axis_maximum)
axis_object.legend()
axis_object.grid(True)


# ------------------------------------------------------------
# PLOT UPDATE LOOP
# This function only reads the shared buffer and redraws the line.
# ------------------------------------------------------------
def update_plot(frame_number):
    with data_lock:
        filtered_values_for_plot = list(filtered_voltage_buffer)

    filtered_line_plot.set_ydata(filtered_values_for_plot)
    return (filtered_line_plot,)


def handle_plot_close(close_event):
    stop_event.set()


figure_object.canvas.mpl_connect("close_event", handle_plot_close)


# ------------------------------------------------------------
# START SAMPLING THREAD
# ------------------------------------------------------------
sampling_thread = threading.Thread(
    target=sampling_loop,
    daemon=False
)
sampling_thread.start()


# ------------------------------------------------------------
# START LIVE DISPLAY
# ------------------------------------------------------------
plot_animation = animation.FuncAnimation(
    figure_object,
    update_plot,
    interval=plot_refresh_interval_milliseconds,
    blit=True,
    cache_frame_data=False
)

try:
    plt.show()
finally:
    stop_event.set()
    sampling_thread.join(timeout=2.0)
    close_recording_file(csv_file_object)
    spi_device.close()
    print("Recording file closed.")
    print("SPI device closed.")