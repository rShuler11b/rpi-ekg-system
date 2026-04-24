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
#   - Raspberry Pi 5
#   - AD8232 ECG Front End
#   - MCP3202 ADC (SPI)
#
# Filters Implemented:
#   1. High-pass filter  — baseline drift removal   (fc ≈ 0.32 Hz)
#   2. Low-pass filter   — high-frequency smoothing (fc ≈ 40 Hz)
#   3. 60 Hz notch filter — powerline interference removal
#
# Filter constant derivation (all for fs = 200 Hz):
#
#   High-pass alpha:
#       alpha = 1 / (1 + 2*pi*fc/fs)  [first-order IIR approximation]
#       fc = 0.32 Hz → alpha ≈ 0.98
#       Retains all cardiac signal content while blocking DC and
#       very slow baseline wander (respiration, electrode drift).
#
#   Low-pass beta:
#       beta = 1 - exp(-2*pi*fc/fs)
#       fc = 40 Hz → beta ≈ 0.73
#       Preserves QRS energy (dominant content up to ~40 Hz) while
#       attenuating high-frequency noise above that band.
#       
#
#   Notch angular frequency:
#       w0 = 2*pi*60/200 = 1.885 rad/sample
#       Coefficients are computed at startup from fs and target
#       frequency, so they stay correct as long as fs is accurate.
#
# Filter chain order:
#   raw → high-pass → low-pass → notch
#   High-pass removes DC first so the notch operates on a
#   zero-centered signal, which improves its numerical stability.
#
# Thread architecture:
#   - Sampling thread:  owns SPI reads, filtering, buffer writes,
#                       and posting samples to the CSV write queue.
#                       Uses cumulative perf_counter timing to avoid
#                       drift from per-iteration sleep resets.
#   - CSV writer thread: drains the write queue and flushes to disk.
#                       Decoupled from sampling so filesystem stalls
#                       (slow SD card, sync pressure) cannot disrupt
#                       sample timing or RR interval accuracy.
#   - Main thread:      owns the matplotlib event loop and plot
#                       animation. Reads shared buffer under lock.
#                       Never touches the ADC or filters.
#
# Output:
#   - Live graph of FILTERED ECG only
#   - Terminal output of labeled raw and filtered data
#   - CSV recording of sample number, timestamp, raw voltage,
#     filtered voltage, and lead-off flag
#
# Notes:
#   - Lead-off pins use pull-down resistors (active-high signal)
#   - Plot y-axis is fixed for a stable visual reference
#   - MCP3202 is a 12-bit SPI ADC (0–4095 counts → 0–3.3 V)
#   - Pi 5 uses the RP1 I/O controller; verify /dev/spidev0.0
#     exists and spidev overlays are enabled in /boot/firmware/config.txt
# ============================================================

import math
import time
import queue
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

# Display buffer: how many samples are visible in the live plot.
# At 200 Hz, 500 samples = 2.5 seconds of waveform.
buffer_size_number_of_samples = 500

# Target sample interval. 0.005 s = 200 Hz.
# Verify this is being achieved by checking timestamp diffs in CSV.
sample_time_interval_seconds = 0.005

# ------------------------------------------------------------
# FILTER PARAMETERS
# All constants are derived for fs = 200 Hz.
# If you change sample_time_interval_seconds, recalculate these.
# See derivation notes in the file header above.
# ------------------------------------------------------------

# High-pass: blocks DC and baseline wander below ~0.32 Hz
high_pass_alpha = 0.98

# Low-pass: attenuates noise above ~40 Hz while preserving QRS shape.
# Raised from 0.2 (fc ≈ 7 Hz) to 0.73 (fc ≈ 40 Hz).
# Lower values smooth more aggressively but flatten QRS peaks.
low_pass_beta = 0.73

# Notch filter: targets 60 Hz powerline interference.
# Radius controls notch width. 0.98 = narrow (precise), 0.90 = wide.
# Narrower is better when 60 Hz is the only interference; widen if
# harmonics or frequency drift are observed in the FFT of recordings.
notch_filter_frequency_hz = 60.0
notch_filter_radius = 0.98

# ------------------------------------------------------------
# DISPLAY SETTINGS
# ------------------------------------------------------------

# Y-axis bounds for the live plot (volts, filtered signal).
# After the low-pass beta change, filtered peaks may be larger than
# before. Widen these bounds if peaks are clipping off-screen.
plot_y_axis_minimum = -0.5
plot_y_axis_maximum = 0.5

# How often the live plot redraws. 50 ms = 20 fps, low CPU cost.
# The plot reads from the shared buffer; it does not affect sample rate.
plot_refresh_interval_milliseconds = 50

# Print one terminal line every N samples to avoid console flooding.
terminal_print_every_n_samples = 20

# ------------------------------------------------------------
# MCP3202 ADC AND SPI SETTINGS
# ------------------------------------------------------------

mcp3202_reference_voltage = 3.3     # Volts applied to VREF pin
mcp3202_channel_number = 0          # 0 or 1

spi_bus_number = 0
spi_chip_select_number = 0
spi_clock_speed_hz = 500000         # 500 kHz; MCP3202 max is 1.8 MHz at 3.3V
                                    # Increase cautiously if timing is tight

# ------------------------------------------------------------
# CSV WRITER QUEUE
# The sampling thread enqueues row tuples here.
# The CSV writer thread drains this queue and writes to disk.
# Queue is unbounded — in practice it stays near-empty at 200 Hz,
# but will buffer safely during any brief filesystem stall.
# ------------------------------------------------------------
csv_write_queue = queue.Queue()

# Sentinel value that signals the writer thread to exit cleanly.
_CSV_WRITER_STOP_SENTINEL = None


# ------------------------------------------------------------
# SETUP SPI AND MCP3202 ADC
# ------------------------------------------------------------
spi_device = spidev.SpiDev()
spi_device.open(spi_bus_number, spi_chip_select_number)
spi_device.max_speed_hz = spi_clock_speed_hz
spi_device.mode = 0b00              # MCP3202 uses SPI mode 0,0


def read_mcp3202_voltage(channel_number=0, reference_voltage=3.3):
    """
    Reads one sample from the MCP3202 and converts it to volts.

    The MCP3202 is a 12-bit ADC with an SPI
    interface. Each transaction sends a 3-byte command and receives
    the 12-bit result packed across the response bytes.

    Parameters
    ----------
    channel_number : int
        ADC channel to sample. Must be 0 or 1.
    reference_voltage : float
        Voltage applied to the MCP3202 VREF pin (typ. 3.3 V on Pi).

    Returns
    -------
    adc_code : int
        Raw 12-bit ADC result, 0 to 4095.
    measured_voltage : float
        Converted analog voltage in volts.

    SPI control word (sent in byte 1, upper nibble):
        Bit 3 (START)    = 1 — begins conversion
        Bit 2 (SGL/DIFF) = 1 — single-ended mode
        Bit 1 (ODD/SIGN) = 0 for CH0, 1 for CH1
        Bit 0 (MSBF)     = 1 — MSB-first output order

    Response decoding:
        Byte 1, lower nibble = ADC bits 11–8
        Byte 2               = ADC bits 7–0
    """
    if channel_number not in (0, 1):
        raise ValueError("channel_number must be 0 or 1")

    # Build the 4-bit control nibble for the selected channel
    control_bits = 0b1100 if channel_number == 0 else 0b1110

    # xfer2 holds CS low for the full 3-byte transaction
    spi_response = spi_device.xfer2([0x01, control_bits << 4, 0x00])

    # Reconstruct 12-bit result from response bytes 1 and 2
    adc_code = ((spi_response[1] & 0x0F) << 8) | spi_response[2]
    measured_voltage = (adc_code / 4095.0) * reference_voltage

    return adc_code, measured_voltage


# ------------------------------------------------------------
# SETUP LEAD-OFF DETECTION PINS
#
# The AD8232 drives LO+ and LO- high when an electrode is not
# making contact. Pull-down resistors ensure the pins read LOW
# when leads are properly attached (active-high detection).
# ------------------------------------------------------------
lead_off_positive_pin = DigitalInOut(board.D17)
lead_off_positive_pin.direction = Direction.INPUT
lead_off_positive_pin.pull = Pull.DOWN

lead_off_negative_pin = DigitalInOut(board.D27)
lead_off_negative_pin.direction = Direction.INPUT
lead_off_negative_pin.pull = Pull.DOWN


# ------------------------------------------------------------
# DATA BUFFERS
#
# deque with maxlen acts as a circular buffer — oldest sample is
# automatically discarded when a new one is appended. The plot
# thread reads a snapshot of this buffer under the data_lock.
# ------------------------------------------------------------
raw_voltage_buffer = deque(
    [0.0] * buffer_size_number_of_samples,
    maxlen=buffer_size_number_of_samples
)

filtered_voltage_buffer = deque(
    [0.0] * buffer_size_number_of_samples,
    maxlen=buffer_size_number_of_samples
)

# Static x-axis for the plot (sample positions 0 to N-1)
x_axis_samples = list(range(buffer_size_number_of_samples))


# ------------------------------------------------------------
# THREADING OBJECTS
# ------------------------------------------------------------
data_lock = threading.Lock()        # Guards raw/filtered deque access
stop_event = threading.Event()      # Signals all threads to exit


# ------------------------------------------------------------
# FILTER STATE VARIABLES
#
# Each variable holds the value from the previous sample needed
# by the IIR recurrence. Written only by the sampling thread.
# No lock needed — the sampling thread is the sole writer.
# ------------------------------------------------------------
previous_raw_sample = 0.0
previous_high_pass_output = 0.0
previous_low_pass_output = 0.0

# Notch filter uses two previous inputs and two previous outputs
# because it is a second-order (biquad) IIR filter.
previous_notch_input_1 = 0.0    # x[n-1]
previous_notch_input_2 = 0.0    # x[n-2]
previous_notch_output_1 = 0.0   # y[n-1]
previous_notch_output_2 = 0.0   # y[n-2]


# ------------------------------------------------------------
# NOTCH FILTER CONSTANTS
#
# Computed once at startup from the target frequency and sample rate.
# w0 is the notch frequency in radians per sample.
# cosine_term is reused in every sample's recurrence calculation.
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
    First-order IIR high-pass filter. Removes slow baseline drift.

    Recurrence:
        y[n] = alpha * ( y[n-1] + x[n] - x[n-1] )

    At fs=200 Hz and alpha=0.98, the -3dB cutoff is approximately
    0.32 Hz. This passes all cardiac signal content (>1 Hz) while
    blocking electrode drift and respiration-induced baseline sway.

    Parameters
    ----------
    current_raw_sample : float
        Voltage reading directly from the ADC.

    Returns
    -------
    float : High-pass filtered voltage.
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
    First-order IIR low-pass filter. Attenuates high-frequency noise.

    Recurrence:
        y[n] = beta * x[n] + (1 - beta) * y[n-1]

    At fs=200 Hz and beta=0.73, the -3dB cutoff is approximately
    40 Hz. This preserves QRS complex energy (dominant content up to
    ~40 Hz) while smoothing noise above that band.

    Tuning guidance:
        Higher beta → higher cutoff → sharper peaks, more noise
        Lower beta  → lower cutoff  → smoother signal, flatter peaks
        Do not go below ~0.4 or QRS peaks will be visibly attenuated.

    Parameters
    ----------
    current_input_sample : float
        Output of the high-pass filter.

    Returns
    -------
    float : Low-pass filtered voltage.
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
    Second-order IIR notch filter. Removes narrowband 60 Hz interference.

    This is a classic pole-zero notch: zeros are placed exactly on the
    unit circle at ±w0 (canceling 60 Hz), and poles are placed slightly
    inside the circle at radius r to restore gain away from the notch.

    Recurrence:
        y[n] = x[n]
               - 2*cos(w0)*x[n-1]
               + x[n-2]
               + 2*r*cos(w0)*y[n-1]
               - r^2*y[n-2]

    Notch width is controlled by r (notch_filter_radius):
        r closer to 1.0 → narrower notch, better selectivity
        r further from 1.0 → wider notch, more margin for freq drift

    Parameters
    ----------
    current_input_sample : float
        Output of the low-pass filter.

    Returns
    -------
    float : Notch-filtered voltage.
    """
    global previous_notch_input_1, previous_notch_input_2
    global previous_notch_output_1, previous_notch_output_2

    current_notch_output = (
        current_input_sample
        - 2.0 * notch_cosine_term * previous_notch_input_1
        + previous_notch_input_2
        + 2.0 * notch_filter_radius * notch_cosine_term * previous_notch_output_1
        - (notch_filter_radius ** 2) * previous_notch_output_2
    )

    # Shift delay line: n-1 becomes n-2, current becomes n-1
    previous_notch_input_2  = previous_notch_input_1
    previous_notch_input_1  = current_input_sample
    previous_notch_output_2 = previous_notch_output_1
    previous_notch_output_1 = current_notch_output

    return current_notch_output


def apply_full_filter_chain(current_raw_sample):
    """
    Runs the sample through the complete three-stage filter chain.

    Order: raw → high-pass → low-pass → notch

    High-pass runs first to remove DC offset, ensuring the notch
    filter operates on a zero-centered signal. Low-pass smooths
    noise before the notch sees it, which reduces ringing artifacts
    at the notch output.

    Parameters
    ----------
    current_raw_sample : float
        Raw ADC voltage for this sample.

    Returns
    -------
    float : Fully filtered voltage ready for display and recording.
    """
    high_pass_output = apply_high_pass_filter(current_raw_sample)
    low_pass_output  = apply_low_pass_filter(high_pass_output)
    notch_output     = apply_notch_filter(low_pass_output)

    return notch_output


# ------------------------------------------------------------
# CSV WRITER THREAD
#
# Drains csv_write_queue and calls append_sample_to_csv for each
# row tuple. Running this in its own thread means that slow SD
# card writes or sync stalls cannot delay the sampling loop or
# corrupt RR interval timing in future Phase 3 work.
#
# The sampling thread enqueues a tuple of:
#   (sample_index, timestamp, raw_voltage, filtered_voltage, lead_off)
# This thread dequeues and writes them in order.
# A None sentinel in the queue signals a clean shutdown.
# ------------------------------------------------------------
def csv_writer_loop():
    while True:
        row = csv_write_queue.get()

        if row is _CSV_WRITER_STOP_SENTINEL:
            # Drain any remaining rows before exiting
            while not csv_write_queue.empty():
                row = csv_write_queue.get_nowait()
                if row is not _CSV_WRITER_STOP_SENTINEL:
                    append_sample_to_csv(csv_writer_object, *row)
            break

        append_sample_to_csv(csv_writer_object, *row)


# ------------------------------------------------------------
# SAMPLING THREAD
#
# This thread owns: timing, ADC acquisition, filtering, buffer
# writes, and queuing CSV rows. It must not be blocked by I/O.
#
# Timing approach:
#   A cumulative target time is advanced by exactly one sample
#   period each iteration. If an iteration runs long, the next
#   sleep will be shorter to compensate, keeping the average rate
#   accurate. If the loop falls behind by more than one period,
#   it catches up without sleeping rather than resetting the
#   clock, which would cause drift accumulation over a session.
# ------------------------------------------------------------
def sampling_loop():
    current_sample_index = 0
    next_sample_time_seconds = time.perf_counter()

    while not stop_event.is_set():

        # Read lead-off detection pins.
        # Either pin going HIGH means an electrode is not in contact.
        lead_off_detected = (
            lead_off_positive_pin.value is True
            or lead_off_negative_pin.value is True
        )

        # Elapsed time since recording began (for CSV timestamps)
        timestamp_seconds = time.time() - recording_start_time_seconds

        if lead_off_detected:
            # Output zeros and flag the row — do not run filters on
            # invalid data, as this would corrupt the IIR state variables
            # and cause ringing artifacts when contact is restored.
            adc_code            = 0
            new_raw_voltage     = 0.0
            new_filtered_voltage = 0.0
            lead_off_flag       = 1

            if current_sample_index % terminal_print_every_n_samples == 0:
                print(
                    "LEAD OFF DETECTED | "
                    "ADC:    0 | RAW: 0.00000 V | FILTERED: 0.00000 V"
                )

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

        # Enqueue the row for the CSV writer thread.
        # This returns immediately regardless of disk speed.
        csv_write_queue.put((
            current_sample_index,
            timestamp_seconds,
            new_raw_voltage,
            new_filtered_voltage,
            lead_off_flag
        ))

        # Update the shared display buffers under lock.
        # The lock window is kept as short as possible — only the
        # append calls, not the ADC read or filter computation.
        with data_lock:
            raw_voltage_buffer.append(new_raw_voltage)
            filtered_voltage_buffer.append(new_filtered_voltage)

        current_sample_index += 1

        # Advance the target time by exactly one sample period.
        # This is the key to maintaining a stable sample clock:
        # each iteration targets an absolute time, not a relative
        # offset from whenever the previous sleep ended.
        next_sample_time_seconds += sample_time_interval_seconds

        remaining_time_seconds = (
            next_sample_time_seconds - time.perf_counter()
        )

        if remaining_time_seconds > 0:
            time.sleep(remaining_time_seconds)
        # If remaining_time is negative the loop is running behind.
        # Do not sleep — proceed immediately to the next sample.
        # The cumulative target continues advancing, so the loop
        # will self-correct without accumulating a growing offset.


# ------------------------------------------------------------
# PLOT SETUP
#
# The plot displays only the filtered signal. Raw data is
# available in recordings for offline comparison if needed.
# The y-axis is fixed so the waveform does not jump around
# as amplitude varies during breathing or posture changes.
# ------------------------------------------------------------
figure_object, axis_object = plt.subplots()

filtered_line_plot, = axis_object.plot(
    x_axis_samples,
    list(filtered_voltage_buffer),
    color='#e05c2a',
    linewidth=0.9,
    label="Filtered ECG"
)

axis_object.set_title("Live ECG — Filtered Signal")
axis_object.set_xlabel("Sample Position in Buffer")
axis_object.set_ylabel("Voltage (V)")
axis_object.set_ylim(plot_y_axis_minimum, plot_y_axis_maximum)
axis_object.legend(loc="upper right")
axis_object.grid(True, alpha=0.3)


# ------------------------------------------------------------
# PLOT UPDATE FUNCTION
#
# Called by FuncAnimation at plot_refresh_interval_milliseconds.
# Reads a snapshot of the shared buffer under lock and redraws
# the filtered line. blit=True means only the changed artist
# is redrawn, reducing CPU cost on the main thread.
# ------------------------------------------------------------
def update_plot(frame_number):
    with data_lock:
        filtered_values_for_plot = list(filtered_voltage_buffer)

    filtered_line_plot.set_ydata(filtered_values_for_plot)
    return (filtered_line_plot,)


def handle_plot_close(close_event):
    """Triggers a clean shutdown when the plot window is closed."""
    stop_event.set()


figure_object.canvas.mpl_connect("close_event", handle_plot_close)


# ------------------------------------------------------------
# START THREADS
# ------------------------------------------------------------

# CSV writer thread — daemon=False so it finishes writing before exit
csv_writer_thread = threading.Thread(
    target=csv_writer_loop,
    daemon=False
)
csv_writer_thread.start()

# Sampling thread — daemon=False so it completes its current sample
sampling_thread = threading.Thread(
    target=sampling_loop,
    daemon=False
)
sampling_thread.start()


# ------------------------------------------------------------
# START LIVE DISPLAY
#
# plt.show() blocks the main thread and runs the matplotlib
# event loop. When the window is closed, handle_plot_close()
# sets stop_event, which causes the sampling loop to exit.
# The finally block then ensures all resources are closed
# cleanly regardless of how the program exits.
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
    # Signal threads to stop
    stop_event.set()

    # Wait for the sampling thread to finish its current sample
    sampling_thread.join(timeout=2.0)

    # Signal the CSV writer to flush remaining rows and exit
    csv_write_queue.put(_CSV_WRITER_STOP_SENTINEL)
    csv_writer_thread.join(timeout=5.0)

    # Close file and SPI handles
    close_recording_file(csv_file_object)
    spi_device.close()

    print("Sampling thread stopped.")
    print("CSV writer thread stopped.")
    print("Recording file closed.")
    print("SPI device closed.")