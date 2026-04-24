# ------------------------------------------------------------
# Name: Ryan Shuler
# Project: Embedded ECG Monitoring System
# File: recording_utils.py
#
# Description:
#   This file handles CSV recording for ECG sessions.
#   It creates a timestamped filename, opens a CSV file,
#   writes the header row, appends sample rows, and closes
#   the file cleanly when recording is finished.
# ------------------------------------------------------------

import csv
import os
from datetime import datetime


# ------------------------------------------------------------
# USER RECORDING FOLDER
# Change this path only if your project folder changes.
# ------------------------------------------------------------
RECORDINGS_FOLDER_PATH = "/home/pi/Desktop/rpi-ekg-system/recordings"


# ------------------------------------------------------------
# Function: ensure_recordings_folder_exists
#
# Purpose:
#   Makes sure the recordings folder exists before trying to
#   create a CSV file inside it.
# ------------------------------------------------------------
def ensure_recordings_folder_exists():
    os.makedirs(RECORDINGS_FOLDER_PATH, exist_ok=True)


# ------------------------------------------------------------
# Function: create_recording_filename
#
# Purpose:
#   Creates a unique CSV filename based on the current date
#   and time.
#
# Returns:
#   full_csv_file_path (str)
# ------------------------------------------------------------
def create_recording_filename():
    current_timestamp_string = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    csv_filename = f"session_{current_timestamp_string}.csv"
    full_csv_file_path = os.path.join(RECORDINGS_FOLDER_PATH, csv_filename)
    return full_csv_file_path


# ------------------------------------------------------------
# Function: open_recording_file
#
# Purpose:
#   Creates and opens the CSV file for writing, then writes
#   the header row immediately.
#
# Returns:
#   csv_file_object
#   csv_writer_object
#   csv_file_path
# ------------------------------------------------------------
def open_recording_file():
    ensure_recordings_folder_exists()

    csv_file_path = create_recording_filename()

    csv_file_object = open(csv_file_path, mode="w", newline="")
    csv_writer_object = csv.writer(csv_file_object)

    csv_writer_object.writerow([
        "sample_index",
        "timestamp_seconds",
        "raw_voltage",
        "filtered_voltage",
        "lead_off"
    ])

    return csv_file_object, csv_writer_object, csv_file_path


# ------------------------------------------------------------
# Function: append_sample_to_csv
#
# Purpose:
#   Writes one ECG sample row to the CSV file.
#
# Parameters:
#   csv_writer_object     -> CSV writer used to write rows
#   sample_index          -> integer sample number
#   timestamp_seconds     -> elapsed time in seconds
#   raw_voltage           -> raw ADC voltage
#   filtered_voltage      -> filtered ECG voltage
#   lead_off_flag         -> 1 if lead off, 0 if connected
# ------------------------------------------------------------
def append_sample_to_csv(
    csv_writer_object,
    sample_index,
    timestamp_seconds,
    raw_voltage,
    filtered_voltage,
    lead_off_flag
):
    csv_writer_object.writerow([
        sample_index,
        f"{timestamp_seconds:.3f}",
        f"{raw_voltage:.4f}",
        f"{filtered_voltage:.4f}",
        lead_off_flag
    ])


# ------------------------------------------------------------
# Function: close_recording_file
#
# Purpose:
#   Closes the CSV file safely.
# ------------------------------------------------------------
def close_recording_file(csv_file_object):
    if csv_file_object is not None:
        csv_file_object.close()
