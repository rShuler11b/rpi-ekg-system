# ============================================================
# Name: Ryan Shuler
# Project: Raspberry Pi 5 Embedded ECG System
# File: csv_writer.py
#
# Description:
#   Contains the ECGCSVWriter class. This class owns CSV file
#   creation and row writing.
# ============================================================

import csv
from datetime import datetime
from pathlib import Path


class ECGCSVWriter:
    """
    Creates and writes ECG recording CSV files.

    The sampler should not directly manage CSV files. It only creates
    row data. This class handles the file path, header, writing, and
    closing behavior.
    """

    def __init__(self, recordings_directory="recordings"):
        self.recordings_directory = Path(recordings_directory)
        self.recordings_directory.mkdir(parents=True, exist_ok=True)

        timestamp_string = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.file_path = self.recordings_directory / f"ecg_recording_{timestamp_string}.csv"

        self.file_object = open(self.file_path, "w", newline="")
        self.csv_writer = csv.writer(self.file_object)

        self.csv_writer.writerow([
            "sample_index",
            "timestamp_seconds",
            "raw_voltage",
            "filtered_voltage",
            "pan_tompkins_integrated",
            "qrs_detected",
            "heart_rate_bpm",
            "lead_off"
        ])

    def write_row(
        self,
        sample_index,
        timestamp_seconds,
        raw_voltage,
        filtered_voltage,
        pan_tompkins_integrated,
        qrs_detected,
        heart_rate_bpm,
        lead_off
    ):
        """Writes one ECG data row to the CSV file."""
        self.csv_writer.writerow([
            sample_index,
            f"{timestamp_seconds:.6f}",
            f"{raw_voltage:.6f}",
            f"{filtered_voltage:.6f}",
            f"{pan_tompkins_integrated:.8f}",
            int(qrs_detected),
            f"{heart_rate_bpm:.2f}",
            int(lead_off)
        ])

    def close(self):
        """Flushes and closes the CSV file."""
        self.file_object.flush()
        self.file_object.close()
