# Raspberry Pi Embedded EKG System

## Overview
This project is an embedded electrocardiogram (EKG) system built on a Raspberry Pi platform. It focuses on real-time signal acquisition, filtering, and visualization using low-cost hardware.

The goal is to explore:
- Biomedical signal acquisition
- Real-time digital filtering
- Embedded system design
- Noise reduction techniques (including motion artifact mitigation)

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
- Electrodes (3-lead configuration)
- Breadboard and jumper wires
- Optional:
  - IMU (for motion artifact research)
  - TFT display (ST7789)

---

## Software Components

- Python 3
- Libraries:
  - adafruit-circuitpython-ads1x15
  - smbus2
  - matplotlib
  - numpy

---

## Features

- Real-time EKG signal acquisition
- Digital filtering:
  - Baseline wander removal
  - Noise smoothing
- Live plotting of waveform
- Lead-off detection
- Terminal output of raw data

---

## Project Structure

rpi-ekg-system/
│
├── README.md
├── LICENSE
├── .gitignore
│
├── python/
│   ├── ekg-plot.py
│   ├── ekg-main.py
│
├── images/   
│
└── documents/
    └── troubleshooting.doc

---

## How to Run

1. Clone repo:
git clone https://github.com/rShuler11b/rpi-ekg-system.git
cd rpi-ekg-system

2. Setup virtual environment (recommended):
python3 -m venv venv
source venv/bin/activate

3. Install dependencies:
pip install -r requirements.txt

4. Run program:
python ekg_plot.py

---

## Future Work

- IMU-based motion artifact removal
- Improved filtering (bandpass / adaptive filters)
- Hardware PCB design
- Isolation and safety improvements
- Clinical validation pathway

---

## Author

Ryan Shuler  
Embedded Systems Engineering Student  
Oregon Institute of Technology

---

## License

This project is licensed under the MIT License. See the LICENSE file for details.