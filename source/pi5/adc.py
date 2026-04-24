# ============================================================
# Name: Ryan Shuler
# Project: Raspberry Pi 5 Embedded ECG System
# File: adc.py
#
# Description:
#   Contains the MCP3202Reader class. This class owns the SPI
#   connection and converts MCP3202 ADC codes into voltage values.
# ============================================================

import spidev


class MCP3202Reader:
    """
    Reads analog voltage from an MCP3202 12-bit SPI ADC.

    Object-oriented purpose:
        This class keeps all ADC-specific behavior in one place.
        The sampler does not need to know how the MCP3202 command
        bytes work. It only asks this object for a voltage sample.
    """

    def __init__(
        self,
        bus_number=0,
        chip_select_number=0,
        reference_voltage=3.3,
        clock_speed_hz=500000,
        spi_mode=0b00
    ):
        self.bus_number = bus_number
        self.chip_select_number = chip_select_number
        self.reference_voltage = reference_voltage
        self.clock_speed_hz = clock_speed_hz
        self.spi_mode = spi_mode

        self.spi_device = spidev.SpiDev()
        self.spi_device.open(self.bus_number, self.chip_select_number)
        self.spi_device.max_speed_hz = self.clock_speed_hz
        self.spi_device.mode = self.spi_mode

    def read_voltage(self, channel_number=0):
        """
        Reads one ADC sample and returns both the raw ADC code and voltage.

        Parameters
        ----------
        channel_number : int
            MCP3202 channel number. Valid values are 0 and 1.

        Returns
        -------
        adc_code : int
            Raw 12-bit ADC count from 0 to 4095.
        measured_voltage : float
            Converted voltage based on the ADC reference voltage.
        """
        if channel_number not in (0, 1):
            raise ValueError("channel_number must be 0 or 1")

        # MCP3202 control bits, in the order the datasheet specifies them
        # for the second transmitted byte (occupying its upper nibble):
        #   bit 3 = start bit            -> 1
        #   bit 2 = SGL/DIFF             -> 1 for single-ended mode
        #   bit 1 = ODD/SIGN             -> 0 for channel 0, 1 for channel 1
        #   bit 0 = MSBF                 -> 1 for MSB-first output format
        #
        # Channel 0 -> 0b1101
        # Channel 1 -> 0b1111
        #
        # Explicitly setting MSBF = 1 matches the canonical MCP3202 command
        # sequence. Leaving MSBF = 0 selects the LSB-first-after-MSB-first
        # output mode, which happens to produce the same leading bits we
        # read here but is not the documented way to request MSB-first data.
        control_bits = 0b1101 if channel_number == 0 else 0b1111

        # xfer2 keeps chip select active for the full transaction.
        spi_response = self.spi_device.xfer2([0x01, control_bits << 4, 0x00])

        # The MCP3202 returns the 12-bit result across byte 1 and byte 2.
        adc_code = ((spi_response[1] & 0x0F) << 8) | spi_response[2]
        measured_voltage = (adc_code / 4095.0) * self.reference_voltage

        return adc_code, measured_voltage

    def close(self):
        """Closes the SPI device cleanly when the program exits."""
        self.spi_device.close()
