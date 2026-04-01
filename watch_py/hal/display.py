# hal/display.py — GC9A01A display driver
# Uses official tft_config for ESP32-S3-LCD-1.28:
#   https://github.com/russhughes/gc9a01_mpy/blob/main/tft_configs/ESP32-S3-LCD-1.28/tft_config.py
#   SPI1, 60MHz, no MISO, reset=Pin(12), backlight=Pin(40) managed by driver

import gc9a01
from machine import SPI, Pin, PWM
from config import (
    PIN_LCD_CLK,
    PIN_LCD_MOSI,
    PIN_LCD_RST,
    PIN_LCD_DC,
    PIN_LCD_CS,
    PIN_LCD_BL,
    PIN_LCD_BL_GPIO,
    DISPLAY_DEFAULT_DUTY,
    DISPLAY_DIM_DUTY,
)


class Display:
    WIDTH = 240
    HEIGHT = 240

    def __init__(self):
        spi = SPI(
            1,
            baudrate=60_000_000,
            sck=Pin(PIN_LCD_CLK),
            mosi=Pin(PIN_LCD_MOSI),
        )
        # backlight=Pin(40) is managed by the gc9a01 driver (on/off only).
        # For PWM brightness control we also keep a PWM handle on Pin(2).
        self.tft = gc9a01.GC9A01(
            spi,
            240,
            240,
            reset=Pin(PIN_LCD_RST, Pin.OUT),
            cs=Pin(PIN_LCD_CS, Pin.OUT),
            dc=Pin(PIN_LCD_DC, Pin.OUT),
            backlight=Pin(PIN_LCD_BL_GPIO, Pin.OUT),
            rotation=0,
        )
        # Secondary PWM on Pin(2) for dimming (gc9a01 backlight kwarg is on/off only)
        self._bl = PWM(Pin(PIN_LCD_BL), freq=5000)
        self._brightness = DISPLAY_DEFAULT_DUTY
        self._off = False
        self._bl.duty(self._brightness)
        # Must call init() explicitly — constructor alone does not send init commands
        self.tft.init()

    # ── Brightness ───────────────────────────────────────────────────────────

    def set_brightness(self, val):
        val = max(0, min(1023, int(val)))
        self._brightness = val
        self._bl.duty(val)
        self._off = val == 0

    def dim(self):
        self._bl.duty(DISPLAY_DIM_DUTY)

    def off(self):
        self._bl.duty(0)
        self._off = True

    def on(self):
        self._off = False
        self._bl.duty(self._brightness)

    def is_off(self):
        return self._off

    def get_brightness_duty(self):
        return self._brightness

    def set_brightness_from_ble(self, val_0_255):
        """BLE writes 0-255; map to 0-1023 PWM duty."""
        self.set_brightness(val_0_255 * 4)
