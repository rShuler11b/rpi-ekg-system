# ============================================================
# Name: Ryan Shuler
# Project: Raspberry Pi 5 Embedded ECG System
# File: pan_tompkins.py
#
# Description:
#   Contains a streaming PanTompkinsDetector class for real-time
#   QRS detection and heart-rate estimation.
#
# References:
#   - Pan, J. and Tompkins, W. J. A Real-Time QRS Detection Algorithm.
#   - Python reference implementation provided by Pramod07Ch.
#
# Note:
#   The original Pan Tompkins algorithm is often shown as a batch
#   process. This version is adapted for a live sample-by-sample
#   Raspberry Pi program.
# ============================================================

from collections import deque


class PanTompkinsDetector:
    """
    Streaming Pan Tompkins style QRS detector.

    Processing pipeline:
        filtered ECG -> derivative -> squaring -> moving window integration
        -> adaptive threshold -> refractory check -> QRS event

    Object-oriented purpose:
        QRS detection needs memory across samples: previous values,
        moving integration window, adaptive signal and noise estimates,
        previous beat times, and heart-rate state. Keeping that state
        inside this class keeps the sampler readable.
    """

    def __init__(
        self,
        sampling_frequency_hz=200.0,
        integration_window_seconds=0.150,
        refractory_period_seconds=0.250,
        learning_period_seconds=2.0,
        threshold_weight=0.25,
        signal_learning_rate=0.125,
        noise_learning_rate=0.125,
        minimum_threshold=0.000001,
        rr_average_length=8,
        searchback_rr_multiplier=1.66,
        searchback_threshold_fraction=0.5
    ):
        self.sampling_frequency_hz = sampling_frequency_hz
        self.integration_window_samples = max(
            1,
            int(integration_window_seconds * sampling_frequency_hz)
        )
        self.refractory_period_samples = int(
            refractory_period_seconds * sampling_frequency_hz
        )
        self.learning_period_samples = int(
            learning_period_seconds * sampling_frequency_hz
        )

        self.threshold_weight = threshold_weight
        self.signal_learning_rate = signal_learning_rate
        self.noise_learning_rate = noise_learning_rate
        self.minimum_threshold = minimum_threshold
        self.rr_average_length = rr_average_length

        # Searchback parameters from the original Pan Tompkins paper.
        #
        # If no QRS has been detected for longer than
        #     searchback_rr_multiplier * average_rr
        # seconds, the detector temporarily lowers its threshold to
        #     searchback_threshold_fraction * current_threshold
        # and looks for the largest integrated value in the unexamined
        # region. This recovers missed beats when the adaptive threshold
        # has drifted above the signal amplitude.
        self.searchback_rr_multiplier = searchback_rr_multiplier
        self.searchback_threshold_fraction = searchback_threshold_fraction

        # Rolling buffer of recent integrated values used by searchback
        # to locate a missed peak. It is sized to hold at least one full
        # searchback window at the longest plausible RR interval. The
        # 2.0 second cap matches the RR sanity range used below.
        searchback_buffer_length = max(
            self.integration_window_samples,
            int(self.searchback_rr_multiplier * 2.0 * self.sampling_frequency_hz)
        )
        self.searchback_history_length = searchback_buffer_length
        self.searchback_history = deque(maxlen=searchback_buffer_length)

        # Recent ECG samples used by the derivative stage.
        self.derivative_buffer = deque([0.0] * 5, maxlen=5)

        # The 5-tap derivative needs four prior samples before its output
        # is meaningful. This counter suppresses the derivative (and
        # therefore the downstream squared and integrated values) until
        # the buffer has been primed, which avoids the startup transient
        # that otherwise ripples into the adaptive threshold. The same
        # counter is reloaded by reset() after a lead-off event.
        self.derivative_priming_samples_remaining = 4

        # Moving window integration state.
        self.integration_window = deque(
            [0.0] * self.integration_window_samples,
            maxlen=self.integration_window_samples
        )
        self.integration_sum = 0.0

        # Adaptive threshold state.
        self.signal_peak_estimate = 0.0
        self.noise_peak_estimate = 0.0
        self.current_threshold = self.minimum_threshold

        # Beat timing state.
        self.sample_index = 0
        self.last_qrs_sample_index = None
        self.rr_intervals_seconds = deque(maxlen=self.rr_average_length)
        self.heart_rate_bpm = 0.0

    def reset(self):
        """
        Clears all detector memory.

        This is useful after lead-off detection because invalid ECG
        data should not contribute to the adaptive thresholds.
        """
        self.derivative_buffer = deque([0.0] * 5, maxlen=5)
        # Reprime the derivative guard so the first post-reset samples do
        # not produce a spurious slope estimate from the zeroed buffer.
        self.derivative_priming_samples_remaining = 4
        self.integration_window = deque(
            [0.0] * self.integration_window_samples,
            maxlen=self.integration_window_samples
        )
        self.integration_sum = 0.0
        self.signal_peak_estimate = 0.0
        self.noise_peak_estimate = 0.0
        self.current_threshold = self.minimum_threshold
        self.sample_index = 0
        self.last_qrs_sample_index = None
        self.rr_intervals_seconds.clear()
        self.heart_rate_bpm = 0.0
        self.searchback_history.clear()

    def _derivative_step(self, filtered_sample):
        """
        Emphasizes steep slopes in the ECG signal.

        The QRS complex has a steep slope compared with slower P and T
        waves. This stage makes those rapid changes stand out.

        For the first four samples after construction or reset, the
        derivative buffer still holds zeros at positions the kernel
        depends on. Returning 0.0 during this priming period avoids a
        large artificial slope that would otherwise corrupt the initial
        signal and noise peak estimates.
        """
        self.derivative_buffer.append(filtered_sample)

        if self.derivative_priming_samples_remaining > 0:
            self.derivative_priming_samples_remaining -= 1
            return 0.0

        # Five-point derivative approximation used in many Pan Tompkins
        # descriptions. It estimates slope while smoothing slightly.
        derivative_output = (
            2.0 * self.derivative_buffer[4]
            + self.derivative_buffer[3]
            - self.derivative_buffer[1]
            - 2.0 * self.derivative_buffer[0]
        ) / 8.0

        return derivative_output

    def _squaring_step(self, derivative_output):
        """
        Makes all values positive and emphasizes large slope changes.
        """
        return derivative_output * derivative_output

    def _moving_window_integration_step(self, squared_output):
        """
        Tracks short-window ECG energy.

        QRS complexes are not only steep. They also have energy over a
        short duration. The moving average helps identify that energy.
        """
        oldest_value = self.integration_window[0]
        self.integration_sum -= oldest_value

        self.integration_window.append(squared_output)
        self.integration_sum += squared_output

        integrated_output = self.integration_sum / self.integration_window_samples
        return integrated_output

    def _update_threshold(self):
        """
        Recalculates the adaptive threshold from signal and noise estimates.

        The threshold sits above the noise estimate but below the signal
        peak estimate. This lets the detector adapt as electrode contact,
        motion, or amplitude changes.
        """
        self.current_threshold = (
            self.noise_peak_estimate
            + self.threshold_weight * (self.signal_peak_estimate - self.noise_peak_estimate)
        )

        if self.current_threshold < self.minimum_threshold:
            self.current_threshold = self.minimum_threshold

    def _try_searchback(self):
        """
        Attempts to recover a missed QRS using the Pan Tompkins searchback rule.

        The rule: if the interval since the last confirmed beat exceeds
        searchback_rr_multiplier times the running average RR interval,
        the detector assumes a beat was missed because the adaptive
        threshold drifted too high. It then scans the integrated-signal
        history between the end of the last refractory period and the
        current sample, and if the largest value there exceeds a reduced
        threshold (searchback_threshold_fraction of the normal threshold),
        that peak is accepted as a retroactive QRS detection.

        Returns
        -------
        searchback_triggered : bool
            True if a missed beat was recovered. False otherwise.

        Notes
        -----
        A recovered beat updates RR history, heart-rate, and the signal
        peak estimate exactly as a normal detection would, but it does
        NOT flag qrs_detected on the current sample. The beat occurred
        earlier in time, so marking it on the current sample would
        misplace it on the plot. This is an intentional tradeoff: we
        keep heart rate accurate and let the detector escape from a
        drifted-threshold condition, at the cost of possibly not
        rendering a visible marker for that one recovered beat.
        """
        # Searchback requires a prior beat and at least one established
        # RR interval. Without a stable RR history, "missed beat" is not
        # a meaningful concept yet and the learning logic should handle
        # the startup regime instead.
        if self.last_qrs_sample_index is None:
            return False
        if len(self.rr_intervals_seconds) == 0:
            return False

        average_rr_seconds = (
            sum(self.rr_intervals_seconds) / len(self.rr_intervals_seconds)
        )
        elapsed_samples = self.sample_index - self.last_qrs_sample_index
        elapsed_seconds = elapsed_samples / self.sampling_frequency_hz

        if elapsed_seconds < self.searchback_rr_multiplier * average_rr_seconds:
            return False

        # Define the searchback window in sample-offset terms relative to
        # the current (most recent) entry in searchback_history. The
        # earliest candidate is one refractory period after the last QRS,
        # because anything closer would have been suppressed anyway.
        earliest_offset_back = elapsed_samples - self.refractory_period_samples
        latest_offset_back = 1  # the most recent integrated sample

        if earliest_offset_back < latest_offset_back:
            return False
        if earliest_offset_back > len(self.searchback_history):
            earliest_offset_back = len(self.searchback_history)

        # Scan the window for the largest integrated value. deque supports
        # negative indexing only via conversion, but we stay inside the
        # deque by iterating over the relevant slice of its length.
        history_length = len(self.searchback_history)
        best_value = -1.0
        best_offset_back = None
        for offset_back in range(latest_offset_back, earliest_offset_back + 1):
            history_position = history_length - offset_back
            if history_position < 0:
                break
            candidate_value = self.searchback_history[history_position]
            if candidate_value > best_value:
                best_value = candidate_value
                best_offset_back = offset_back

        if best_offset_back is None:
            return False

        # Accept the candidate only if it exceeds the reduced searchback
        # threshold. This prevents searchback from conjuring beats out of
        # pure noise during long asystolic pauses or during lead-off.
        searchback_threshold = (
            self.searchback_threshold_fraction * self.current_threshold
        )
        if best_value <= searchback_threshold:
            return False

        # Register the recovered beat at its original sample index.
        recovered_sample_index = self.sample_index - best_offset_back
        rr_interval_seconds = (
            (recovered_sample_index - self.last_qrs_sample_index)
            / self.sampling_frequency_hz
        )

        if 0.30 <= rr_interval_seconds <= 2.00:
            self.rr_intervals_seconds.append(rr_interval_seconds)
            average_rr = (
                sum(self.rr_intervals_seconds) / len(self.rr_intervals_seconds)
            )
            self.heart_rate_bpm = 60.0 / average_rr

        # The signal estimate is updated using the recovered peak so the
        # threshold tracks the true signal amplitude going forward.
        self.signal_peak_estimate = (
            (1.0 - self.signal_learning_rate) * self.signal_peak_estimate
            + self.signal_learning_rate * best_value
        )
        self.last_qrs_sample_index = recovered_sample_index
        self._update_threshold()
        return True

    def process_sample(self, filtered_sample):
        """
        Processes one filtered ECG sample.

        Parameters
        ----------
        filtered_sample : float
            ECG sample after the main filter chain.

        Returns
        -------
        result : dict
            Contains derivative, squared, integrated, qrs_detected,
            searchback_triggered, threshold, and heart_rate_bpm values
            for plotting or logging.
        """
        derivative_output = self._derivative_step(filtered_sample)
        squared_output = self._squaring_step(derivative_output)
        integrated_output = self._moving_window_integration_step(squared_output)

        # Keep a rolling history of integrated values so searchback has
        # something to scan. Appended regardless of learning state so the
        # history is already populated by the time searchback can fire.
        self.searchback_history.append(integrated_output)

        qrs_detected = False
        searchback_triggered = False

        # During the learning period, the detector builds initial estimates
        # instead of immediately trusting the threshold.
        if self.sample_index < self.learning_period_samples:
            if integrated_output > self.signal_peak_estimate:
                self.signal_peak_estimate = integrated_output
            else:
                self.noise_peak_estimate = (
                    (1.0 - self.noise_learning_rate) * self.noise_peak_estimate
                    + self.noise_learning_rate * integrated_output
                )
            self._update_threshold()
        else:
            enough_time_since_last_qrs = (
                self.last_qrs_sample_index is None
                or self.sample_index - self.last_qrs_sample_index >= self.refractory_period_samples
            )

            if integrated_output > self.current_threshold and enough_time_since_last_qrs:
                qrs_detected = True

                # Update the signal estimate toward this detected peak.
                self.signal_peak_estimate = (
                    (1.0 - self.signal_learning_rate) * self.signal_peak_estimate
                    + self.signal_learning_rate * integrated_output
                )

                if self.last_qrs_sample_index is not None:
                    rr_interval_seconds = (
                        self.sample_index - self.last_qrs_sample_index
                    ) / self.sampling_frequency_hz

                    # Basic sanity range for adult ECG RR intervals.
                    # This avoids obvious false detections from producing
                    # extreme heart-rate values.
                    if 0.30 <= rr_interval_seconds <= 2.00:
                        self.rr_intervals_seconds.append(rr_interval_seconds)
                        average_rr = sum(self.rr_intervals_seconds) / len(self.rr_intervals_seconds)
                        self.heart_rate_bpm = 60.0 / average_rr

                self.last_qrs_sample_index = self.sample_index
            else:
                # Anything below threshold, or inside the refractory period,
                # is treated as noise for threshold adaptation.
                self.noise_peak_estimate = (
                    (1.0 - self.noise_learning_rate) * self.noise_peak_estimate
                    + self.noise_learning_rate * integrated_output
                )

                # Only attempt searchback when no normal detection fired.
                # Running it after a normal detection would be pointless
                # because the RR clock was just reset.
                searchback_triggered = self._try_searchback()

            self._update_threshold()

        result = {
            "derivative": derivative_output,
            "squared": squared_output,
            "integrated": integrated_output,
            "threshold": self.current_threshold,
            "qrs_detected": qrs_detected,
            "searchback_triggered": searchback_triggered,
            "heart_rate_bpm": self.heart_rate_bpm
        }

        self.sample_index += 1
        return result
