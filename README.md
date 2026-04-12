# Raspberry Pi Embedded EKG System

## Overview
This project is an embedded electrocardiogram (EKG) system built on a Raspberry Pi platform. It focuses on real-time signal acquisition, filtering, visualization, and data recording using low-cost hardware.

The system is being developed in phases, progressing from basic signal acquisition to advanced signal processing and eventual hardware acceleration.

Core areas of focus:
- Biomedical signal acquisition
- Real-time digital signal processing
- Embedded system design
- Noise reduction and signal integrity
- Data logging and analysis

---

## !! Disclaimer !!
This project is for research and educational purposes only.

It is NOT a medical device and is not intended for:
- Diagnosis
- Treatment
- Clinical decision-making

Use at your own risk.

---

## Hardware Components

- Raspberry Pi Zero 2 W
- AD8232 EKG front-end module
- ADS1115 16-bit ADC (I2C)
- 3-lead electrode configuration
- Breadboard and jumper wires

Optional / In Progress:
- IMU (motion artifact detection)
- ST7789 TFT display
- Perf board / PCB prototype

---

## Software Components

- Python 3

Libraries used:
- adafruit-circuitpython-ads1x15
- adafruit-blinka
- smbus2
- busio
- board
- digitalio
- numpy
- matplotlib
- collections (deque)
- time (standard library)
- os (file handling)
- csv (data recording)

---

## Features (Current)

- Real-time EKG signal acquisition via ADS1115
- Digital filtering pipeline:
  - High-pass filter (baseline drift removal)
  - Low-pass filter (noise smoothing)
  - 60 Hz notch filter (powerline interference)
- Live waveform visualization (filtered signal)
- Lead-off detection using GPIO
- Terminal output for debugging (raw + filtered)
- Adjustable filter parameters
- CSV data recording per session
- Logging system for debugging and troubleshooting

---

## Project Structure

rpi-ecg/
│
├── README.md
├── LICENSE
├── .gitignore
│
├── source/
│   ├── ekg_plot.py
│   ├── ekg_main.py
│   ├── recording_utils.py
│
├── recordings/          # Saved ECG data (.csv)
├── logs/                # Runtime logs / debug output
├── images/
└── documents/
    └── troubleshooting.doc

---

## How to Run

1. Clone repository:
git clone https://github.com/rShuler11b/rpi-ekg-system.git
cd rpi-ecg

2. Create virtual environment:
python3 -m venv venv
source venv/bin/activate

3. Install dependencies:
pip install -r requirements.txt

4. Run the system:
cd source
python ekg_plot.py

---

## Data Recording

Recorded sessions are saved as CSV files in the `recordings/` directory.

Each file contains:
- sample_index
- timestamp_seconds
- raw_voltage
- filtered_voltage
- lead_off_flag

Example:
sample_index,timestamp_seconds,raw_voltage,filtered_voltage,lead_off  
0,0.000,1.5123,0.0021,0  

Purpose:
- Offline analysis
- Filter tuning and validation
- Comparison against benchmark datasets (PhysioNet)

---

## Logging

The `logs/` directory stores runtime and debug information.

This includes:
- Lead-off events
- Signal anomalies
- System behavior during runtime

Used for:
- Troubleshooting
- Performance tuning
- Debugging hardware/software interaction

---

## Development Phases

### Phase 1: Signal Acquisition and Filtering (Current)
- Hardware integration (AD8232 + ADS1115)
- Real-time filtering pipeline
- Stable waveform visualization
- Data recording and logging

### Phase 2: Signal Interpretation (Next)
- PQRST detection
- Heart rate calculation
- Feature extraction
- Motion artifact reduction using IMU

### Phase 3: Hardware Acceleration (Planned)
- Port filtering pipeline to FPGA
- Real-time deterministic processing
- Optimized embedded architecture

---

## Future Work

- Adaptive filtering (LMS, Kalman)
- IMU-based motion compensation
- Improved analog front-end design
- Shielding and grounding improvements
- Perf board / PCB design
- Validation using PhysioNet datasets (MIT-BIH, NSTDB)
- Real-time metrics (HR, HRV)

---

## Author

Ryan Shuler  
Embedded Systems Engineering Student  
Oregon Institute of Technology  

---

## License

This project is licensed under the MIT License. See the LICENSE file for details.