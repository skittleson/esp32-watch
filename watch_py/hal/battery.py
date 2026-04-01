# hal/battery.py — Battery voltage/percentage via ADC

from machine import ADC, Pin
from config import BAT_VOLTAGE_MIN, BAT_VOLTAGE_MAX, BAT_ADC_SAMPLES, PIN_BAT_ADC


class Battery:
    def __init__(self, pin=None):
        if pin is None:
            pin = PIN_BAT_ADC
        # ADC1, full range 0-3.3V with 11dB attenuation
        self._adc = ADC(Pin(pin), atten=ADC.ATTN_11DB)
        self._pct = 100

    def read_voltage(self):
        """Return battery terminal voltage in volts (3:1 divider on ADC pin)."""
        total = 0
        for _ in range(BAT_ADC_SAMPLES):
            total += self._adc.read()
        raw_avg = total // BAT_ADC_SAMPLES
        # 12-bit ADC (0-4095), 3.3V full-scale, 3:1 resistor divider
        vpin = raw_avg / 4095 * 3.3
        return vpin * 3.0

    def read_percent(self):
        """Return battery level 0-100 %, clamped."""
        v = self.read_voltage()
        pct = (v - BAT_VOLTAGE_MIN) / (BAT_VOLTAGE_MAX - BAT_VOLTAGE_MIN) * 100.0
        self._pct = max(0, min(100, int(pct)))
        return self._pct

    def cached_percent(self):
        return self._pct

    def is_charging(self):
        """Return True when USB is plugged in (voltage above full-charge threshold).
        At 100% on battery the voltage is ~4.2V; on USB it reads >= 4.15V.
        We use this as a proxy for 'plugged in' since there is no dedicated
        VBUS/CHG pin exposed.
        """
        return self.read_voltage() >= 4.15
