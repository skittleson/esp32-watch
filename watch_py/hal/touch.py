# hal/touch.py — CST816S capacitive touch controller (pure-Python I2C)

from machine import I2C, Pin
import time

# CST816S I2C address
_ADDR = const(0x15)

# Register map
_REG_GESTURE_ID = const(0x01)
_REG_FINGER_NUM = const(0x02)
_REG_X_H = const(0x03)
_REG_MOTION_MASK = const(0xEC)  # bit0 = enable double-click
_REG_IRQ_CTL = const(0xFA)  # 0x70 = fire on touch/gesture, even in standby
_REG_DIS_AUTOSLEEP = const(0xFE)  # 0x01 = keep chip awake

# Gesture byte → string name
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
    def __init__(self, i2c, rst_pin, int_pin):
        self._i2c = i2c
        self._event = False

        # Hardware reset — longer settle time needed
        rst = Pin(rst_pin, Pin.OUT)
        rst(0)
        time.sleep_ms(10)
        rst(1)
        time.sleep_ms(100)  # CST816S needs ~100ms to fully wake after reset

        # CRITICAL: disable auto-sleep FIRST — chip ignores other register
        # writes if it enters auto-sleep before they complete
        self._write(_REG_DIS_AUTOSLEEP, 0x01)
        time.sleep_ms(10)
        # Enable double-click detection
        self._write(_REG_MOTION_MASK, 0x01)
        time.sleep_ms(10)
        # IRQ fires on touch + gesture, also in standby so touch wakes display
        # 0x71 = EnTest(7) | EnChange(6) | EnTouch(4) | EnMotion(0)
        self._write(_REG_IRQ_CTL, 0x71)
        time.sleep_ms(10)

        # Attach falling-edge interrupt
        self._int_pin_num = int_pin
        self._irq_pin = Pin(int_pin, Pin.IN)
        self._irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=self._isr)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _isr(self, _):
        self._event = True

    def _write(self, reg, val):
        try:
            self._i2c.writeto_mem(_ADDR, reg, bytes([val]))
        except OSError:
            pass

    # ── Public API ───────────────────────────────────────────────────────────

    def poll(self):
        """Return touch event dict or None if nothing pending.

        Returns: {'gesture': str, 'x': int, 'y': int}
        """
        if not self._event:
            return None
        self._event = False
        try:
            # Read 6 bytes: gestureID, fingerNum, XposH, XposL, YposH, YposL
            data = self._i2c.readfrom_mem(_ADDR, _REG_GESTURE_ID, 6)
        except OSError:
            return None

        if data[1] == 0 and data[0] == 0x00:
            # No fingers and no gesture — spurious interrupt, ignore
            return None

        x = ((data[2] & 0x0F) << 8) | data[3]
        y = ((data[4] & 0x0F) << 8) | data[5]
        gesture = _GESTURE_MAP.get(data[0], "none")

        return {"gesture": gesture, "x": x, "y": y}

    def reattach_irq(self):
        """Re-attach the touch IRQ after GPIO5 was used as haptic output."""
        self._irq_pin = Pin(self._int_pin_num, Pin.IN)
        self._irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=self._isr)

    def sleep(self):
        """Allow the CST816S to enter auto-sleep (saves ~0.5 mA)."""
        self._write(_REG_DIS_AUTOSLEEP, 0x00)

    def wake(self):
        """Re-disable auto-sleep after waking."""
        self._write(_REG_DIS_AUTOSLEEP, 0x01)
