title: Raspberry Pi Embedded EKG System

overview: >
  This project is an embedded electrocardiogram (EKG) system built on Raspberry Pi platforms.
  It performs real-time signal acquisition, filtering, visualization, and data recording
  using low-cost hardware.

platforms:
  - name: Raspberry Pi Zero 2 W
    adc: ADS1115
    interface: I2C
  - name: Raspberry Pi 5
    adc: MCP3202
    interface: SPI

focus_areas:
  - Biomedical signal acquisition
  - Real-time digital signal processing
  - Embedded system design
  - Noise reduction and signal integrity
  - Data logging and analysis

disclaimer:
  text: >
    This project is for research and educational purposes only.
    It is NOT a medical device and is not intended for diagnosis,
    treatment, or clinical decision-making.
    Use at your own risk.

hardware:
  configurations:
    pi_zero_2w:
      components:
        - Raspberry Pi Zero 2 W
        - AD8232 ECG front-end
        - ADS1115 16-bit ADC (I2C)
        - 3-lead electrodes
        - Breadboard and jumpers
    pi_5:
      components:
        - Raspberry Pi 5
        - AD8232 ECG front-end
        - MCP3202 12-bit ADC (SPI)
        - 3-lead electrodes
        - Breadboard and jumpers

  optional:
    - IMU (motion artifact detection)
    - ST7789 TFT display
    - Perf board / PCB

software:
  language: Python 3
  common_libraries:
    - numpy
    - matplotlib
    - collections (deque)
    - time
    - os
    - csv

  ads1115_libraries:
    - adafruit-circuitpython-ads1x15
    - adafruit-blinka
    - smbus2
    - busio
    - board
    - digitalio

  mcp3202_libraries:
    - spidev
    - RPi.GPIO

features:
  - Real-time ECG acquisition
  - Dual ADC support (ADS1115, MCP3202)
  - High-pass filter (baseline drift removal)
  - Low-pass filter (noise smoothing)
  - 60 Hz notch filter
  - Live waveform visualization
  - Lead-off detection via GPIO
  - Terminal debug output
  - CSV recording
  - Logging system

project_structure:
  root: rpi-ecg
  files:
    - README.md
    - LICENSE
    - .gitignore
  source:
    - ekg_plot.py (ADS1115)
    - ekg_main.py
    - ecg_rpi5.py (MCP3202)
    - recording_utils.py
  directories:
    - recordings
    - logs
    - images
    - documents

adc_architecture:
  ads1115:
    resolution: 16-bit
    interface: I2C
    characteristics:
      - Lower noise
      - Slower sampling
      - Simpler wiring
  mcp3202:
    resolution: 12-bit
    interface: SPI
    characteristics:
      - Faster sampling
      - Deterministic timing
      - Lower latency

run:
  setup:
    - git clone https://github.com/rShuler11b/rpi-ekg-system.git
    - cd rpi-ecg
    - python3 -m venv venv
    - source venv/bin/activate
    - pip install -r requirements.txt

  pi_zero_2w:
    command:
      - cd source
      - python ekg_plot.py

  pi_5:
    enable_spi:
      - sudo raspi-config
      - Interface Options → SPI → Enable
    command:
      - cd source
      - python ecg_rpi5.py

data_recording:
  location: recordings/
  fields:
    - sample_index
    - timestamp_seconds
    - raw_voltage
    - filtered_voltage
    - lead_off_flag
  purpose:
    - Offline analysis
    - Filter tuning
    - Benchmark comparison

logging:
  location: logs/
  includes:
    - Lead-off events
    - Signal anomalies
    - Runtime behavior
  purpose:
    - Troubleshooting
    - Performance tuning

hardware_setup:
  ad8232:
    connections:
      - 3.3V → 3.3V
      - GND → GND
      - OUTPUT → ADC input
      - LO+ → GPIO
      - LO− → GPIO
    electrodes:
      - RA
      - LA
      - RL

  ads1115:
    connections:
      - VDD → 3.3V
      - GND → GND
      - SDA → GPIO2
      - SCL → GPIO3
      - ADDR → GND
      - A0 → AD8232 OUTPUT
    enable:
      - sudo raspi-config
      - Interface Options → I2C → Enable

  mcp3202:
    connections:
      - VDD → 3.3V
      - GND → GND
      - CLK → GPIO11
      - DOUT → GPIO9
      - DIN → GPIO10
      - CS → GPIO8
      - CH0 → AD8232 OUTPUT
    enable:
      - sudo raspi-config
      - Interface Options → SPI → Enable

signal_chain:
  flow: AD8232 → optional RC filter → ADC → digital filters → visualization + recording
  filters:
    - High-pass
    - Low-pass
    - Notch (60 Hz)

configuration_notes:
  sampling:
    ads1115: "~860 SPS max (I2C limited)"
    mcp3202: "Higher, more consistent via SPI"

  scaling:
    note: "Adjust y-axis in plotting code (ECG is low amplitude)"

  tuning_parameters:
    - high_pass_alpha
    - low_pass_beta
    - notch_frequency
    - notch_radius

troubleshooting:
  flatline:
    - Check SDN pin (must be HIGH)
    - Verify electrode contact
    - Confirm wiring

  noise:
    - Improve grounding
    - Shorten wires
    - Add RC filter
    - Adjust low-pass filter

  unstable_plot:
    - Reduce plot update rate
    - Ensure sampling is decoupled
    - Verify timing

  lead_off:
    - Check LO+ and LO− wiring
    - Verify GPIO configuration

performance:
  notes:
    - SPI more deterministic than I2C
    - Decoupled sampling improves stability
    - CSV logging can introduce timing jitter

usage:
  recommendations:
    - Use ADS1115 for initial setup
    - Use MCP3202 for timing-sensitive work
    - Validate signal before tuning filters

author:
  name: Ryan Shuler
  role: Embedded Systems Engineering Student
  institution: Oregon Institute of Technology

license:
  type: MIT