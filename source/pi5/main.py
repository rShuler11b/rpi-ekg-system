# ============================================================
# Name: Ryan Shuler
# Project: Raspberry Pi 5 Embedded ECG System
# File: main.py
#
# Description:
#   Main entry point for the Raspberry Pi 5 ECG program.
#   This file creates the hardware, processing, sampling, CSV,
#   and plotting objects, then starts the worker threads.
# ============================================================

import queue
import signal
import threading
from collections import deque

from adc import MCP3202Reader
from lead_off import LeadOffDetector
from filters import ECGFilterChain
from pan_tompkins import PanTompkinsDetector
from sampler import ECGSampler
from csv_writer import ECGCSVWriter
from plotter import ECGPlotter


# ------------------------------------------------------------
# USER SETTINGS
# ------------------------------------------------------------

BUFFER_SIZE_NUMBER_OF_SAMPLES = 500
SAMPLE_INTERVAL_SECONDS = 0.005          # 0.005 seconds = 200 Hz
SAMPLING_FREQUENCY_HZ = 1.0 / SAMPLE_INTERVAL_SECONDS

ADC_CHANNEL_NUMBER = 0
MCP3202_REFERENCE_VOLTAGE = 3.3
SPI_BUS_NUMBER = 0
SPI_CHIP_SELECT_NUMBER = 0
SPI_CLOCK_SPEED_HZ = 500000

PLOT_Y_AXIS_MINIMUM = -0.5
PLOT_Y_AXIS_MAXIMUM = 0.5
PLOT_REFRESH_INTERVAL_MILLISECONDS = 50

TERMINAL_PRINT_EVERY_N_SAMPLES = 20
RECORDINGS_DIRECTORY = "recordings"

CSV_WRITER_STOP_SENTINEL = None


# ------------------------------------------------------------
# MAIN PROGRAM
# ------------------------------------------------------------

def csv_writer_loop(csv_queue, csv_writer, stop_sentinel):
    """
    Pulls queued sample rows and writes them to the CSV file.

    This runs in its own thread so that file writes do not interrupt
    fixed-rate ECG sampling.
    """
    while True:
        row = csv_queue.get()

        if row is stop_sentinel:
            # Drain remaining rows before exiting. This prevents the last
            # samples from being lost during shutdown.
            while not csv_queue.empty():
                remaining_row = csv_queue.get_nowait()
                if remaining_row is not stop_sentinel:
                    csv_writer.write_row(*remaining_row)
            break

        csv_writer.write_row(*row)


def main():
    """Builds the ECG system objects and starts the program."""

    # Shared buffers. Deque with maxlen acts like a circular buffer.
    raw_voltage_buffer = deque(
        [0.0] * BUFFER_SIZE_NUMBER_OF_SAMPLES,
        maxlen=BUFFER_SIZE_NUMBER_OF_SAMPLES
    )
    filtered_voltage_buffer = deque(
        [0.0] * BUFFER_SIZE_NUMBER_OF_SAMPLES,
        maxlen=BUFFER_SIZE_NUMBER_OF_SAMPLES
    )
    integrated_buffer = deque(
        [0.0] * BUFFER_SIZE_NUMBER_OF_SAMPLES,
        maxlen=BUFFER_SIZE_NUMBER_OF_SAMPLES
    )
    qrs_marker_buffer = deque(
        [None] * BUFFER_SIZE_NUMBER_OF_SAMPLES,
        maxlen=BUFFER_SIZE_NUMBER_OF_SAMPLES
    )
    heart_rate_buffer = deque(
        [0.0] * BUFFER_SIZE_NUMBER_OF_SAMPLES,
        maxlen=BUFFER_SIZE_NUMBER_OF_SAMPLES
    )

    # Threading objects.
    data_lock = threading.Lock()
    stop_event = threading.Event()
    csv_queue = queue.Queue()

    adc_reader = None
    lead_off_detector = None
    csv_writer = None
    sampler_thread = None
    writer_thread = None
    previous_sigint_handler = None

    try:
        # Hardware objects.
        adc_reader = MCP3202Reader(
            bus_number=SPI_BUS_NUMBER,
            chip_select_number=SPI_CHIP_SELECT_NUMBER,
            reference_voltage=MCP3202_REFERENCE_VOLTAGE,
            clock_speed_hz=SPI_CLOCK_SPEED_HZ
        )

        lead_off_detector = LeadOffDetector()

        # Processing objects.
        filter_chain = ECGFilterChain(
            sampling_frequency_hz=SAMPLING_FREQUENCY_HZ
        )

        qrs_detector = PanTompkinsDetector(
            sampling_frequency_hz=SAMPLING_FREQUENCY_HZ
        )

        # CSV object.
        csv_writer = ECGCSVWriter(recordings_directory=RECORDINGS_DIRECTORY)
        print(f"Recording to: {csv_writer.file_path}")

        # Sampling object.
        sampler = ECGSampler(
            adc_reader=adc_reader,
            lead_off_detector=lead_off_detector,
            filter_chain=filter_chain,
            qrs_detector=qrs_detector,
            csv_queue=csv_queue,
            data_lock=data_lock,
            stop_event=stop_event,
            raw_voltage_buffer=raw_voltage_buffer,
            filtered_voltage_buffer=filtered_voltage_buffer,
            integrated_buffer=integrated_buffer,
            qrs_marker_buffer=qrs_marker_buffer,
            heart_rate_buffer=heart_rate_buffer,
            sample_interval_seconds=SAMPLE_INTERVAL_SECONDS,
            adc_channel_number=ADC_CHANNEL_NUMBER,
            terminal_print_every_n_samples=TERMINAL_PRINT_EVERY_N_SAMPLES
        )

        # Plotting object.
        plotter = ECGPlotter(
            data_lock=data_lock,
            stop_event=stop_event,
            filtered_voltage_buffer=filtered_voltage_buffer,
            qrs_marker_buffer=qrs_marker_buffer,
            heart_rate_buffer=heart_rate_buffer,
            buffer_size_number_of_samples=BUFFER_SIZE_NUMBER_OF_SAMPLES,
            y_axis_minimum=PLOT_Y_AXIS_MINIMUM,
            y_axis_maximum=PLOT_Y_AXIS_MAXIMUM,
            refresh_interval_milliseconds=PLOT_REFRESH_INTERVAL_MILLISECONDS
        )

        # Install a Ctrl-C (SIGINT) handler so a keyboard interrupt from
        # the terminal sets stop_event instead of propagating as a bare
        # KeyboardInterrupt. Without this, the only clean way to stop the
        # program is to close the matplotlib window. If the plot window
        # ever becomes unresponsive, Ctrl-C in the terminal still brings
        # the whole pipeline down through the normal shutdown path.
        #
        # The handler is installed here, after all objects exist but
        # before the worker threads are started, so the stop_event is
        # guaranteed to be valid at the moment the signal could fire.
        def handle_sigint(signal_number, current_frame):
            print("\nCtrl-C received. Shutting down...")
            stop_event.set()

        previous_sigint_handler = signal.signal(signal.SIGINT, handle_sigint)

        # Start the writer thread first so CSV rows can be accepted as soon
        # as the sampler starts producing data.
        writer_thread = threading.Thread(
            target=csv_writer_loop,
            args=(csv_queue, csv_writer, CSV_WRITER_STOP_SENTINEL),
            daemon=False
        )
        writer_thread.start()

        sampler_thread = threading.Thread(
            target=sampler.run,
            daemon=False
        )
        sampler_thread.start()

        # plt.show() blocks until the user closes the plot window.
        plotter.show()

    finally:
        # Signal threads to stop.
        stop_event.set()

        if sampler_thread is not None:
            sampler_thread.join(timeout=2.0)

        if csv_queue is not None:
            csv_queue.put(CSV_WRITER_STOP_SENTINEL)

        if writer_thread is not None:
            writer_thread.join(timeout=5.0)

        if csv_writer is not None:
            csv_writer.close()
            print("Recording file closed.")

        if adc_reader is not None:
            adc_reader.close()
            print("SPI device closed.")

        if lead_off_detector is not None:
            lead_off_detector.close()
            print("Lead-off GPIO pins released.")

        # Restore whatever SIGINT handler was in place before main() ran.
        # This keeps main() polite if it is ever imported and called from
        # a larger program rather than executed as __main__.
        if previous_sigint_handler is not None:
            signal.signal(signal.SIGINT, previous_sigint_handler)

        print("ECG program stopped.")


if __name__ == "__main__":
    main()
