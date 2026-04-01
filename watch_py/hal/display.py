# hal/display.py — LVGL display driver for GC9A01 via lcd_bus.SPIBus
#
# Uses lvgl_micropython's lcd_bus + gc9a01 LVGL driver.
# Backlight dimming via PWM on Pin(2); Pin(40) is the gc9a01 driver on/off.
#
# Pin map (Waveshare ESP32-S3-Touch-LCD-1.28):
#   CLK=10, MOSI=11, DC=8, CS=9, RST=14, BL_GPIO=40, BL_PWM=2

import lvgl as lv
import lcd_bus
import gc9a01 as _gc9a01_drv  # LVGL driver, not gc9a01_mpy
from machine import Pin, PWM
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

_WIDTH = const(240)
_HEIGHT = const(240)
# Frame buffer: 1/10 of screen = 240*24*2 bytes (RGB565) — fits in IRAM
_BUF_SIZE = const(_WIDTH * 24 * 2)


class Display:
    WIDTH = _WIDTH
    HEIGHT = _HEIGHT

    def __init__(self):
        import machine

        spi_bus = machine.SPI.Bus(
            host=1,  # SPI2 — host 0 is reserved for flash/SPIRAM
            mosi=PIN_LCD_MOSI,
            miso=-1,  # no MISO on this display
            sck=PIN_LCD_CLK,
        )

        self._bus = lcd_bus.SPIBus(
            spi_bus=spi_bus,
            freq=60_000_000,
            dc=PIN_LCD_DC,
            cs=PIN_LCD_CS,
        )

        # Allocate two partial frame buffers in IRAM with DMA capability
        fb1 = self._bus.allocate_framebuffer(
            _BUF_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA
        )
        fb2 = self._bus.allocate_framebuffer(
            _BUF_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA
        )

        self._display = _gc9a01_drv.GC9A01(
            data_bus=self._bus,
            frame_buffer1=fb1,
            frame_buffer2=fb2,
            display_width=_WIDTH,
            display_height=_HEIGHT,
            reset_pin=PIN_LCD_RST,
            reset_state=_gc9a01_drv.STATE_LOW,
            backlight_pin=PIN_LCD_BL_GPIO,
            color_space=lv.COLOR_FORMAT.RGB565,
            color_byte_order=_gc9a01_drv.BYTE_ORDER_BGR,
            rgb565_byte_swap=True,
        )

        # PWM on Pin(2) for smooth dimming (gc9a01 backlight kwarg = on/off only)
        self._bl = PWM(Pin(PIN_LCD_BL), freq=5000)
        self._brightness = DISPLAY_DEFAULT_DUTY
        self._off = False
        self._bl.duty(self._brightness)

        self._display.set_power(True)
        self._display.init()
        self._display.set_backlight(100)

    def get_display(self):
        """Return the LVGL display driver object."""
        return self._display

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
