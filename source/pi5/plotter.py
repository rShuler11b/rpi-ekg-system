# ============================================================
# Name: Ryan Shuler
# Project: Raspberry Pi 5 Embedded ECG System
# File: plotter.py
#
# Description:
#   Contains the ECGPlotter class. This class owns matplotlib setup
#   and display updates only.
# ============================================================

import matplotlib.pyplot as plt
import matplotlib.animation as animation


class ECGPlotter:
    """
    Displays the live filtered ECG signal and QRS markers.

    The plotter does not read the ADC, run filters, or write CSV files.
    It only reads shared buffers and redraws the screen.
    """

    def __init__(
        self,
        data_lock,
        stop_event,
        filtered_voltage_buffer,
        qrs_marker_buffer,
        heart_rate_buffer,
        buffer_size_number_of_samples=500,
        y_axis_minimum=-0.5,
        y_axis_maximum=0.5,
        refresh_interval_milliseconds=50
    ):
        self.data_lock = data_lock
        self.stop_event = stop_event
        self.filtered_voltage_buffer = filtered_voltage_buffer
        self.qrs_marker_buffer = qrs_marker_buffer
        self.heart_rate_buffer = heart_rate_buffer
        self.buffer_size_number_of_samples = buffer_size_number_of_samples
        self.y_axis_minimum = y_axis_minimum
        self.y_axis_maximum = y_axis_maximum
        self.refresh_interval_milliseconds = refresh_interval_milliseconds

        self.x_axis_samples = list(range(self.buffer_size_number_of_samples))

        self.figure_object, self.axis_object = plt.subplots()

        self.filtered_line_plot, = self.axis_object.plot(
            self.x_axis_samples,
            list(self.filtered_voltage_buffer),
            linewidth=0.9,
            label="Filtered ECG"
        )

        self.qrs_marker_plot, = self.axis_object.plot(
            [],
            [],
            linestyle="None",
            marker="o",
            markersize=4,
            label="QRS detected"
        )

        self.axis_object.set_title("Live ECG with Pan Tompkins QRS Detection")
        self.axis_object.set_xlabel("Sample Position in Buffer")
        self.axis_object.set_ylabel("Voltage (V)")
        self.axis_object.set_ylim(self.y_axis_minimum, self.y_axis_maximum)
        self.axis_object.legend(loc="upper right")
        self.axis_object.grid(True, alpha=0.3)

        self.heart_rate_text = self.axis_object.text(
            0.02,
            0.95,
            "HR: -- bpm",
            transform=self.axis_object.transAxes,
            verticalalignment="top"
        )

        self.figure_object.canvas.mpl_connect("close_event", self._handle_close)

    def _handle_close(self, close_event):
        """Signals the sampler and writer threads to stop when plot closes."""
        self.stop_event.set()

    def _update_plot(self, frame_number):
        """
        Reads the current buffer snapshot and redraws the plot.

        The lock is held only long enough to copy buffer data. The actual
        plot update happens after the lock is released.
        """
        with self.data_lock:
            filtered_values = list(self.filtered_voltage_buffer)
            qrs_marker_values = list(self.qrs_marker_buffer)
            heart_rate_values = list(self.heart_rate_buffer)

        qrs_x_values = []
        qrs_y_values = []

        for index, marker_value in enumerate(qrs_marker_values):
            if marker_value is not None:
                qrs_x_values.append(index)
                qrs_y_values.append(marker_value)

        current_heart_rate = heart_rate_values[-1] if heart_rate_values else 0.0

        self.filtered_line_plot.set_ydata(filtered_values)
        self.qrs_marker_plot.set_data(qrs_x_values, qrs_y_values)

        if current_heart_rate > 0:
            self.heart_rate_text.set_text(f"HR: {current_heart_rate:.1f} bpm")
        else:
            self.heart_rate_text.set_text("HR: -- bpm")

        return self.filtered_line_plot, self.qrs_marker_plot, self.heart_rate_text

    def show(self):
        """Starts the matplotlib event loop."""
        self.plot_animation = animation.FuncAnimation(
            self.figure_object,
            self._update_plot,
            interval=self.refresh_interval_milliseconds,
            blit=True,
            cache_frame_data=False
        )

        plt.show()
