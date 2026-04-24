# ============================================================
# Name: Ryan Shuler
# Project: Raspberry Pi 5 Embedded ECG System
# File: sampler.py
#
# Description:
#   Contains the ECGSampler class. This class owns the fixed-rate
#   sampling loop and coordinates ADC reads, filtering, Pan Tompkins
#   detection, shared buffers, and CSV queue rows.
# ============================================================

import time


class ECGSampler:
    """
    Runs the real-time ECG sampling loop.

    The sampler coordinates the hardware and processing objects, but
    it does not contain hardware-specific SPI logic or algorithm-specific
    Pan Tompkins logic. Those details live in their own classes.
    """

    def __init__(
        self,
        adc_reader,
        lead_off_detector,
        filter_chain,
        qrs_detector,
        csv_queue,
        data_lock,
        stop_event,
        raw_voltage_buffer,
        filtered_voltage_buffer,
        integrated_buffer,
        qrs_marker_buffer,
        heart_rate_buffer,
        sample_interval_seconds=0.005,
        adc_channel_number=0,
        terminal_print_every_n_samples=20
    ):
        self.adc_reader = adc_reader
        self.lead_off_detector = lead_off_detector
        self.filter_chain = filter_chain
        self.qrs_detector = qrs_detector
        self.csv_queue = csv_queue
        self.data_lock = data_lock
        self.stop_event = stop_event

        self.raw_voltage_buffer = raw_voltage_buffer
        self.filtered_voltage_buffer = filtered_voltage_buffer
        self.integrated_buffer = integrated_buffer
        self.qrs_marker_buffer = qrs_marker_buffer
        self.heart_rate_buffer = heart_rate_buffer

        self.sample_interval_seconds = sample_interval_seconds
        self.adc_channel_number = adc_channel_number
        self.terminal_print_every_n_samples = terminal_print_every_n_samples

        # The recording start reference is captured from perf_counter so
        # that the per-sample timestamps written to CSV are measured on
        # the same monotonic clock used for sampling pacing. Using
        # time.time() here would mix a wall clock (subject to NTP steps
        # and manual adjustments) with a monotonic clock, which can
        # produce negative or jumpy timestamps during a recording.
        self.recording_start_time_seconds = time.perf_counter()

    def run(self):
        """
        Main sampling loop.

        Timing method:
            next_sample_time_seconds is advanced by one fixed sample
            interval every loop. This avoids long-term drift caused by
            repeatedly sleeping relative to the previous loop end time.
        """
        current_sample_index = 0
        next_sample_time_seconds = time.perf_counter()

        while not self.stop_event.is_set():
            lead_off_detected = self.lead_off_detector.is_lead_off()
            # perf_counter matches self.recording_start_time_seconds and
            # the pacing variable next_sample_time_seconds below, so all
            # three quantities come from the same monotonic clock.
            timestamp_seconds = time.perf_counter() - self.recording_start_time_seconds

            if lead_off_detected:
                # Bad electrode contact means the ECG sample is invalid.
                # Reset filters and detector so invalid data does not ring
                # through the IIR filters or corrupt adaptive thresholds.
                self.filter_chain.reset()
                self.qrs_detector.reset()

                adc_code = 0
                raw_voltage = 0.0
                filtered_voltage = 0.0
                integrated_value = 0.0
                qrs_detected = False
                heart_rate_bpm = 0.0
                lead_off_flag = 1

                if current_sample_index % self.terminal_print_every_n_samples == 0:
                    print(
                        "LEAD OFF DETECTED | "
                        "ADC:    0 | RAW: 0.00000 V | FILTERED: 0.00000 V"
                    )

            else:
                adc_code, raw_voltage = self.adc_reader.read_voltage(
                    channel_number=self.adc_channel_number
                )

                filtered_voltage = self.filter_chain.process_sample(raw_voltage)
                pan_tompkins_result = self.qrs_detector.process_sample(filtered_voltage)

                integrated_value = pan_tompkins_result["integrated"]
                qrs_detected = pan_tompkins_result["qrs_detected"]
                heart_rate_bpm = pan_tompkins_result["heart_rate_bpm"]
                lead_off_flag = 0

                if current_sample_index % self.terminal_print_every_n_samples == 0:
                    print(
                        f"ADC: {adc_code:4d} | "
                        f"RAW: {raw_voltage:.5f} V | "
                        f"FILTERED: {filtered_voltage:.5f} V | "
                        f"HR: {heart_rate_bpm:.1f} bpm"
                    )

            # Queue a row for the CSV writer thread. This keeps disk writes
            # from delaying the fixed-rate sampling loop.
            self.csv_queue.put((
                current_sample_index,
                timestamp_seconds,
                raw_voltage,
                filtered_voltage,
                integrated_value,
                qrs_detected,
                heart_rate_bpm,
                lead_off_flag
            ))

            # Store a marker value only on QRS detections. None means no marker
            # should be drawn for that sample.
            qrs_marker_value = filtered_voltage if qrs_detected else None

            # The plotter reads these buffers. The lock prevents the plotter
            # from reading while the sampler is halfway through appending.
            with self.data_lock:
                self.raw_voltage_buffer.append(raw_voltage)
                self.filtered_voltage_buffer.append(filtered_voltage)
                self.integrated_buffer.append(integrated_value)
                self.qrs_marker_buffer.append(qrs_marker_value)
                self.heart_rate_buffer.append(heart_rate_bpm)

            current_sample_index += 1

            next_sample_time_seconds += self.sample_interval_seconds
            remaining_time_seconds = next_sample_time_seconds - time.perf_counter()

            if remaining_time_seconds > 0:
                time.sleep(remaining_time_seconds)
