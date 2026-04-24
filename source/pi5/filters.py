# ============================================================
# Name: Ryan Shuler
# Project: Raspberry Pi 5 Embedded ECG System
# File: filters.py
#
# Description:
#   Contains the ECGFilterChain class. This class owns all filter
#   state so the main sampling loop stays clean.
# ============================================================

import math


class ECGFilterChain:
    """
    Applies the basic real-time ECG filter chain.

    Pipeline:
        raw sample -> high-pass -> low-pass -> 60 Hz notch

    Object-oriented purpose:
        IIR filters need previous input and output values. Keeping
        those values inside a class prevents the program from relying
        on several global state variables.
    """

    def __init__(
        self,
        sampling_frequency_hz=200.0,
        high_pass_alpha=0.98,
        low_pass_beta=0.73,
        notch_frequency_hz=60.0,
        notch_radius=0.98
    ):
        self.sampling_frequency_hz = sampling_frequency_hz
        self.high_pass_alpha = high_pass_alpha
        self.low_pass_beta = low_pass_beta
        self.notch_frequency_hz = notch_frequency_hz
        self.notch_radius = notch_radius

        # High-pass and low-pass filter memory.
        self.previous_raw_sample = 0.0
        self.previous_high_pass_output = 0.0
        self.previous_low_pass_output = 0.0

        # Notch filter memory. The notch is a second-order IIR filter,
        # so it needs two previous inputs and two previous outputs.
        self.previous_notch_input_1 = 0.0
        self.previous_notch_input_2 = 0.0
        self.previous_notch_output_1 = 0.0
        self.previous_notch_output_2 = 0.0

        self.notch_angular_frequency = (
            2.0 * math.pi * self.notch_frequency_hz / self.sampling_frequency_hz
        )
        self.notch_cosine_term = math.cos(self.notch_angular_frequency)

        # DC gain normalization for the notch section.
        #
        # The unnormalized difference equation is:
        #   y[n] = x[n] - 2*cos(w)*x[n-1] + x[n-2]
        #          + 2*r*cos(w)*y[n-1] - r^2 * y[n-2]
        #
        # Evaluating its transfer function H(z) at z = 1 (DC) gives:
        #   H(1) = (1 - 2*cos(w) + 1) / (1 - 2*r*cos(w) + r^2)
        #
        # Dividing the numerator coefficients by this factor forces the DC
        # gain to exactly 1.0 and removes the small passband droop that an
        # unnormalized pole-zero notch otherwise introduces near 0 Hz.
        numerator_dc_gain = 1.0 - 2.0 * self.notch_cosine_term + 1.0
        denominator_dc_gain = (
            1.0
            - 2.0 * self.notch_radius * self.notch_cosine_term
            + self.notch_radius ** 2
        )
        self.notch_gain_normalization = denominator_dc_gain / numerator_dc_gain

    def reset(self):
        """
        Clears filter memory.

        This is useful after lead-off events because invalid samples
        should not be allowed to ring through the IIR filters.
        """
        self.previous_raw_sample = 0.0
        self.previous_high_pass_output = 0.0
        self.previous_low_pass_output = 0.0
        self.previous_notch_input_1 = 0.0
        self.previous_notch_input_2 = 0.0
        self.previous_notch_output_1 = 0.0
        self.previous_notch_output_2 = 0.0

    def apply_high_pass_filter(self, current_raw_sample):
        """
        Removes slow baseline drift using a first-order IIR high-pass filter.

        Formula:
            y[n] = alpha * (y[n - 1] + x[n] - x[n - 1])
        """
        current_high_pass_output = self.high_pass_alpha * (
            self.previous_high_pass_output
            + current_raw_sample
            - self.previous_raw_sample
        )

        self.previous_raw_sample = current_raw_sample
        self.previous_high_pass_output = current_high_pass_output

        return current_high_pass_output

    def apply_low_pass_filter(self, current_input_sample):
        """
        Smooths high-frequency noise using a first-order IIR low-pass filter.

        Formula:
            y[n] = beta * x[n] + (1 - beta) * y[n - 1]
        """
        current_low_pass_output = (
            self.low_pass_beta * current_input_sample
            + (1.0 - self.low_pass_beta) * self.previous_low_pass_output
        )

        self.previous_low_pass_output = current_low_pass_output

        return current_low_pass_output

    def apply_notch_filter(self, current_input_sample):
        """
        Reduces narrowband 60 Hz noise using a second-order IIR notch filter.

        The numerator is scaled by self.notch_gain_normalization so that the
        overall filter has unity gain at DC. Without this scaling, a pole
        radius less than 1 leaves a small dip in the passband near 0 Hz.
        That dip is harmless for QRS detection but unhelpful if the filtered
        signal is used for waveform measurements.
        """
        # The normalization factor multiplies only the input (numerator)
        # terms. The feedback (denominator) terms are left unchanged so the
        # notch depth and bandwidth are preserved.
        scaled_input = current_input_sample * self.notch_gain_normalization
        scaled_input_delay_1 = self.previous_notch_input_1 * self.notch_gain_normalization
        scaled_input_delay_2 = self.previous_notch_input_2 * self.notch_gain_normalization

        current_notch_output = (
            scaled_input
            - 2.0 * self.notch_cosine_term * scaled_input_delay_1
            + scaled_input_delay_2
            + 2.0 * self.notch_radius * self.notch_cosine_term * self.previous_notch_output_1
            - (self.notch_radius ** 2) * self.previous_notch_output_2
        )

        # Shift old values back by one sample. The raw (unscaled) input is
        # stored so the scaling is applied consistently on each call.
        self.previous_notch_input_2 = self.previous_notch_input_1
        self.previous_notch_input_1 = current_input_sample
        self.previous_notch_output_2 = self.previous_notch_output_1
        self.previous_notch_output_1 = current_notch_output

        return current_notch_output

    def process_sample(self, current_raw_sample):
        """Runs one raw ECG sample through the full filter chain."""
        high_pass_output = self.apply_high_pass_filter(current_raw_sample)
        low_pass_output = self.apply_low_pass_filter(high_pass_output)
        notch_output = self.apply_notch_filter(low_pass_output)

        return notch_output
