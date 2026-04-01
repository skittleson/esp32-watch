# hal/touch.py — CST816S touch using firmware's frozen cst816s + pointer_framework
#
# Uses i2c.I2C.Bus (LVGL i2c) exclusively — machine.I2C must NOT be opened on
# the same pins simultaneously. The i2c bus object is shared with the IMU.
#
# Exposes:
#   .poll()          — returns gesture dict for screen navigation or None
#   .get_i2c_bus()   — returns the i2c.I2C.Bus instance for sharing with IMU
#   .reattach_irq()  — re-enables touch IRQ after haptic GPIO5 use

import cst816s
import i2c
import pointer_framework  # noqa — needed by cst816s frozen driver
from machine import Pin
import time

from config import PIN_TP_SDA, PIN_TP_SCL, PIN_TP_RST, PIN_TP_INT

_ADDR = const(0x15)
_REG_GESTURE_ID = const(0x01)
_REG_MOTION_MASK = const(0xEC)
_REG_DIS_AUTOSLEEP = const(0xFE)

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
    def __init__(self, rst_pin=PIN_TP_RST, int_pin=PIN_TP_INT):
        self._int_pin_num = int_pin
        self._event = False

        # Create LVGL i2c bus — this is the ONLY i2c master on SDA=6, SCL=7
        self._i2c_bus = i2c.I2C.Bus(
            host=0,
            scl=PIN_TP_SCL,
            sda=PIN_TP_SDA,
            freq=400_000,
            use_locks=False,
        )
        touch_dev = i2c.I2C.Device(
            bus=self._i2c_bus,
            dev_id=cst816s.I2C_ADDR,
            reg_bits=cst816s.BITS,
        )

        # Instantiate the frozen cst816s driver (registers LVGL indev automatically)
        rst = Pin(rst_pin, Pin.OUT)
        self._driver = cst816s.CST816S(touch_dev, reset_pin=rst)

        # Enable double-click via MotionMask register
        self._driver._write_reg(_REG_MOTION_MASK, 0x01)

        # Attach falling-edge IRQ for gesture name polling
        self._irq_pin = Pin(int_pin, Pin.IN)
        self._irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=self._isr)

    def _isr(self, _):
        self._event = True

    def get_i2c_bus(self):
        """Return the i2c.I2C.Bus for sharing with IMU driver."""
        return self._i2c_bus

    def poll(self):
        """Return gesture dict for screen navigation, or None."""
        if not self._event:
            return None
        self._event = False
        try:
            # Read 6 bytes starting at GestureID register via raw i2c bus
            tx = bytearray([_REG_GESTURE_ID])
            rx = bytearray(6)
            # Use the i2c bus write_readinto via a temporary device at raw addr
            dev = i2c.I2C.Device(
                bus=self._i2c_bus,
                dev_id=_ADDR,
                reg_bits=8,
            )
            dev.write_readinto(tx, rx)
        except Exception:
            return None

        if rx[1] == 0 and rx[0] == 0x00:
            return None

        x = ((rx[2] & 0x0F) << 8) | rx[3]
        y = ((rx[4] & 0x0F) << 8) | rx[5]
        gesture = _GESTURE_MAP.get(rx[0], "none")
        return {"gesture": gesture, "x": x, "y": y}

    def reattach_irq(self):
        """Re-attach the touch IRQ after GPIO5 was used as haptic output."""
        self._irq_pin = Pin(self._int_pin_num, Pin.IN)
        self._irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=self._isr)
