# hal/touch.py — CST816S touch driver adapted for LVGL indev
#
# LVGL indev registration replaces the raw IRQ-to-poll approach.
# The CST816S LVGL driver (compiled into firmware) is used for
# gesture + point data. We also keep the raw I2C gestures for
# screen navigation (swipes, double-click BLE activation).
#
# CRITICAL: GPIO5 is shared with the haptic motor. reattach_irq()
# must be called after alarm dismissal to restore the touch IRQ.

import lvgl as lv
import cst816s  # LVGL indev driver compiled into lvgl_micropython firmware
import i2c  # LVGL i2c bus helper compiled into firmware
from machine import I2C, Pin
import time

from config import PIN_TP_SDA, PIN_TP_SCL, PIN_TP_RST, PIN_TP_INT

# CST816S I2C address
_ADDR = const(0x15)

# Register map (for raw gesture reads used by screen navigation)
_REG_GESTURE_ID = const(0x01)
_REG_MOTION_MASK = const(0xEC)
_REG_IRQ_CTL = const(0xFA)
_REG_DIS_AUTOSLEEP = const(0xFE)

# Gesture byte → string name (for screen manager)
_GESTURE_MAP = {
    0x00: "none",
    0x01: "swipe_up",
    0x02: "swipe_down",
    0x03: "swipe_left",
    0x04: "swipe_right",
    0x05: "single_click",
    0x0B: "double_click",
    0x0C: "long_press",
}


class CST816S:
    """
    Touch driver wrapping the lvgl_micropython CST816S LVGL indev driver.

    LVGL pointer input is handled automatically by the driver.
    We add raw gesture polling on top for swipe-based screen navigation.
    """

    def __init__(self, rst_pin=PIN_TP_RST, int_pin=PIN_TP_INT):
        self._int_pin_num = int_pin
        self._event = False

        # Hardware reset
        rst = Pin(rst_pin, Pin.OUT)
        rst(0)
        time.sleep_ms(10)
        rst(1)
        time.sleep_ms(100)

        # Raw I2C bus for register access (gestures/config)
        self._i2c_raw = I2C(0, sda=Pin(PIN_TP_SDA), scl=Pin(PIN_TP_SCL), freq=400_000)

        # CRITICAL: disable auto-sleep FIRST
        self._write(_REG_DIS_AUTOSLEEP, 0x01)
        time.sleep_ms(10)
        # Enable double-click detection
        self._write(_REG_MOTION_MASK, 0x01)
        time.sleep_ms(10)
        # IRQ fires on touch + gesture in standby
        self._write(_REG_IRQ_CTL, 0x71)
        time.sleep_ms(10)

        # LVGL i2c bus object for the CST816S LVGL driver
        i2c_bus = i2c.I2C.Bus(
            host=0,
            scl=PIN_TP_SCL,
            sda=PIN_TP_SDA,
            freq=400_000,
            use_locks=False,
        )
        touch_dev = i2c.I2C.Device(
            bus=i2c_bus,
            dev_id=cst816s.I2C_ADDR,
            reg_bits=cst816s.BITS,
        )

        # Create LVGL indev — this registers it with LVGL automatically
        self._indev = cst816s.CST816S(touch_dev)

        # Attach raw gesture IRQ for screen navigation
        self._irq_pin = Pin(int_pin, Pin.IN)
        self._irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=self._isr)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _isr(self, _):
        self._event = True

    def _write(self, reg, val):
        try:
            self._i2c_raw.writeto_mem(_ADDR, reg, bytes([val]))
        except OSError:
            pass

    # ── Public API ───────────────────────────────────────────────────────────

    def poll(self):
        """
        Return raw gesture dict for screen navigation, or None.

        LVGL pointer events are handled independently by the indev driver.
        This only returns gesture info needed by the ScreenManager.

        Returns: {'gesture': str, 'x': int, 'y': int} or None
        """
        if not self._event:
            return None
        self._event = False
        try:
            data = self._i2c_raw.readfrom_mem(_ADDR, _REG_GESTURE_ID, 6)
        except OSError:
            return None

        if data[1] == 0 and data[0] == 0x00:
            return None  # spurious interrupt

        x = ((data[2] & 0x0F) << 8) | data[3]
        y = ((data[4] & 0x0F) << 8) | data[5]
        gesture = _GESTURE_MAP.get(data[0], "none")

        return {"gesture": gesture, "x": x, "y": y}

    def reattach_irq(self):
        """Re-attach the touch IRQ after GPIO5 was used as haptic output."""
        self._irq_pin = Pin(self._int_pin_num, Pin.IN)
        self._irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=self._isr)

    def get_indev(self):
        """Return the LVGL indev object."""
        return self._indev
