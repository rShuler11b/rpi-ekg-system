# Raspberry Pi 5 Embedded ECG System

## Overview

This project is a Raspberry Pi 5 based embedded ECG system using an AD8232 ECG front-end module and an MCP3202 SPI ADC.

The program performs:

- Real-time ECG acquisition
- Lead-off detection
- Digital filtering
- Pan Tompkins QRS detection
- Heart rate estimation
- Live plotting
- CSV recording

This project is for biomedical signal processing, embedded systems learning, and ECG algorithm development.

## Disclaimer

This project is for research and educational purposes only.

It is NOT a medical device and is not intended for:

- Diagnosis
- Treatment
- Patient monitoring
- Clinical decision-making

Use at your own risk.

## Project Structure

```text
├── main.py
├── adc.py
├── lead_off.py
├── filters.py
├── pan_tompkins.py
├── sampler.py
├── csv_writer.py
├── plotter.py
├── requirements.txt
├── README.md
```

## File Purpose

| File | Purpose |
|---|---|
| `main.py` | Starts the ECG program and connects all modules |
| `adc.py` | Handles MCP3202 SPI ADC reads |
| `lead_off.py` | Handles AD8232 LO+ and LO- detection |
| `filters.py` | Applies ECG filtering |
| `pan_tompkins.py` | Runs Pan Tompkins QRS detection |
| `sampler.py` | Owns the fixed-rate sampling loop |
| `csv_writer.py` | Records ECG samples to CSV |
| `plotter.py` | Handles live matplotlib display |
| `requirements.txt` | Lists Python dependencies |

## Hardware Used

- Raspberry Pi 5
- AD8232 ECG front-end module
- MCP3202 12-bit SPI ADC
- ECG electrodes
- Breadboard
- Jumper wires
- Optional RC anti-aliasing filter

## Raspberry Pi 5 SPI Wiring

### MCP3202 to Raspberry Pi 5

| MCP3202 Pin | Function | Raspberry Pi 5 Pin | GPIO | Wire Color |
|---|---|---:|---|---|
| VDD | Power | Pin 1 | 3.3V | Red |
| VREF | ADC reference | Pin 1 | 3.3V | Red |
| AGND | Ground | Pin 6 | GND | Black |
| DGND | Ground | Pin 6 | GND | Black |
| CLK | SPI clock | Pin 23 | GPIO11 / SCLK | Yellow |
| DOUT | SPI MISO | Pin 21 | GPIO9 / MISO | Purple |
| DIN | SPI MOSI | Pin 19 | GPIO10 / MOSI | Blue |
| CS/SHDN | SPI chip select | Pin 24 | GPIO8 / CE0 | Orange |
| CH0 | ECG input | AD8232 OUTPUT | Signal wire | Green |

## AD8232 Wiring

| AD8232 Pin | Connects To | Raspberry Pi / ADC Pin | Wire Color |
|---|---|---|---|
| 3.3V | Power | Pi Pin 1, 3.3V | Red |
| GND | Ground | Pi Pin 6, GND | Black |
| OUTPUT | ECG analog output | MCP3202 CH0 | Green |
| LO+ | Lead-off positive | Pi GPIO17, Pin 11 | White |
| LO- | Lead-off negative | Pi GPIO27, Pin 13 | Gray |
| SDN | Shutdown control | Pi 3.3V | Red |

SDN should be tied HIGH to keep the AD8232 enabled.

## Optional RC Anti-Aliasing Filter

Place the RC filter between the AD8232 OUTPUT pin and MCP3202 CH0.

Recommended starting values:

```text
R = 10 kOhm
C = 0.33 uF
```

Wiring:

```text
AD8232 OUTPUT ---- 10 kOhm resistor ---- MCP3202 CH0
                                      |
                                   0.33 uF
                                      |
                                     GND
```

This creates a simple passive low-pass filter before the ADC. It helps reduce high-frequency noise before sampling.

## Enable SPI on Raspberry Pi 5

Run:

```bash
sudo raspi-config
```

Then go to:

```text
Interface Options -> SPI -> Enable
```

Reboot:

```bash
sudo reboot
```

Check that SPI is available:

```bash
ls /dev/spidev*
```

Expected output:

```text
/dev/spidev0.0
/dev/spidev0.1
```

## Install Dependencies

From the project folder:

```bash
cd ~/Desktop/rpi_EKG/rpi-ecg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## How to Run

From the project folder:

```bash
cd ~/Desktop/rpi_EKG/rpi-ecg
source .venv/bin/activate
python main.py
```

The program will:

1. Open the MCP3202 SPI device
2. Start ECG sampling
3. Apply filtering
4. Run Pan Tompkins QRS detection
5. Plot the filtered ECG signal with QRS markers
6. Save ECG data to CSV

## Algorithm Pipeline

```text
AD8232 ECG Signal
        |
        v
MCP3202 ADC
        |
        v
Raw Voltage Sample
        |
        v
Digital Filter Chain
        |
        v
Pan Tompkins Processing
        |
        v
QRS Detection + Heart Rate Estimate
        |
        v
Live Plot + CSV Recording
```

## Filtering Pipeline

```text
raw ECG
   |
   v
high-pass filter
   |
   v
low-pass filter
   |
   v
60 Hz notch filter
   |
   v
filtered ECG
```

The high-pass filter reduces baseline drift, the low-pass filter reduces high-frequency noise, and the notch filter reduces 60 Hz powerline interference.

## Pan Tompkins Pipeline

The Pan Tompkins detector uses this sequence:

```text
filtered ECG
   |
   v
derivative
   |
   v
squaring
   |
   v
moving window integration
   |
   v
adaptive thresholding
   |
   v
QRS detection
   |
   v
RR interval + heart rate estimate
```

| Stage | Purpose |
|---|---|
| Derivative | Emphasizes steep QRS slopes |
| Squaring | Makes all values positive and exaggerates large changes |
| Moving window integration | Measures QRS energy over a short time window |
| Adaptive thresholding | Separates likely QRS events from noise |
| Refractory period | Prevents double-counting the same heartbeat |
| RR interval calculation | Estimates heart rate from time between detected beats |

## Pan Tompkins References

This implementation is based on the original Pan Tompkins QRS detection method and a Python reference implementation.

- Pan, Jiapu, and Willis J. Tompkins. A Real-Time QRS Detection Algorithm. IEEE Transactions on Biomedical Engineering, 1985.
- Oxford copy of the Pan Tompkins paper: https://www.robots.ox.ac.uk/~gari/teaching/cdt/A3/readings/ECG/Pan+Tompkins.pdf
- Python reference implementation: https://github.com/Pramod07Ch/Pan-Tompkins-algorithm-python/blob/main/Pan_tompkins_algorithm.py

## CSV Recording

The program records sample data during runtime.

CSV fields:

```text
sample_index
timestamp_seconds
raw_voltage
filtered_voltage
pan_tompkins_integrated
qrs_detected
heart_rate_bpm
lead_off
```

Example row:

```text
1520,7.600000,1.512300,0.084100,0.02170000,1,72.40,0
```

## Lead-Off Detection

The AD8232 provides two lead-off pins:

```text
LO+
LO-
```

If either pin goes HIGH, the program treats the ECG leads as disconnected.

When lead-off is detected:

- The sample is marked with `lead_off = 1`
- QRS detection is ignored
- Filter state is reset
- Pan Tompkins threshold state is reset
- The CSV still records the event

## Sampling Rate

Default sampling rate:

```text
200 Hz
```

This means:

```text
sample interval = 0.005 seconds
```

A stable sampling rate matters because ECG timing is used for RR intervals and heart rate estimation.

## Notes

- Keep ECG wires short when possible.
- Use a shared ground between the Pi, MCP3202, and AD8232.
- Use 3.3V logic only.
- Do not connect ECG electrodes to wall-powered test equipment.
- Battery power is safer for early testing.
- This system is for learning and research only.
