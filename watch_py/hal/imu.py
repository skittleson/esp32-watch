# hal/imu.py — QMI8658 IMU driver (pure-Python I2C)
# No asyncio — polled directly from main loop at ~50Hz.
# Wake-on-Motion uses INT1 IRQ to set shared['wom_wake'] = True.

from machine import Pin
from micropython import const
import math
import time
from config import (
    STEP_MAG_THRESHOLD,
    STEP_LOCKOUT_MS,
    PIN_IMU_INT1,
    SEDENTARY_ALERT_MS,
    SEDENTARY_MOVE_THRESHOLD,
)

# QMI8658 I2C address (SA0 tied to VDD on this board)
_ADDR = const(0x6B)

# Register addresses
_REG_CTRL1 = const(0x02)
_REG_CTRL2 = const(0x03)  # Accel config
_REG_CTRL3 = const(0x04)  # Gyro config
_REG_CTRL5 = const(0x06)  # LPF config
_REG_CTRL7 = const(0x08)  # Enable sensors
_REG_CTRL9 = const(0x0A)  # Command register
_REG_CAL1_L = const(0x0B)  # WoM threshold (CAL1)
_REG_TEMP_L = const(0x33)  # Temperature low byte
_REG_AX_L = const(0x35)  # Accel X low byte

# Sensitivity for configured ranges
_ACC_SENS = 4096.0  # LSB/g  for ±8g range
_GYR_SENS = 64.0  # LSB/dps for ±512dps range


class QMI8658:
    def __init__(self, i2c):
        self._i2c = i2c
        self._steps = 0
        self._prev_mag = 0.0
        self._rising = False
        self._last_step_ms = 0
        self._data = {
            "acc": [0.0, 0.0, 0.0],
            "gyro": [0.0, 0.0, 0.0],
            "temp": 0.0,
            "steps": 0,
        }
        self._init_sensor()

    # ── Init ─────────────────────────────────────────────────────────────────

    def _init_sensor(self):
        # CTRL1: SPI/I2C, auto-increment, little-endian
        self._write(_REG_CTRL1, 0x40)
        # CTRL2: Accel ±8g (0x02<<4), ODR 125Hz (0x06)
        self._write(_REG_CTRL2, (0x02 << 4) | 0x06)
        # CTRL3: Gyro ±512dps (0x04<<4), ODR 125Hz (0x06)
        self._write(_REG_CTRL3, (0x04 << 4) | 0x06)
        # CTRL5: enable LPF for both accel (bit0) and gyro (bit4)
        self._write(_REG_CTRL5, 0x11)
        # CTRL7: enable accel (bit0) + gyro (bit1)
        self._write(_REG_CTRL7, 0x03)

    # ── I2C helpers ──────────────────────────────────────────────────────────

    def _write(self, reg, val):
        try:
            self._i2c.writeto_mem(_ADDR, reg, bytes([val]))
        except OSError:
            pass

    def _read_bytes(self, reg, n):
        try:
            return self._i2c.readfrom_mem(_ADDR, reg, n)
        except OSError:
            return bytes(n)

    def _read16s(self, reg):
        """Read a signed 16-bit little-endian value from reg and reg+1."""
        d = self._read_bytes(reg, 2)
        v = d[0] | (d[1] << 8)
        return v - 65536 if v > 32767 else v

    # ── Step counter ─────────────────────────────────────────────────────────

    def _update_steps(self, ax, ay, az):
        mag = math.sqrt(ax * ax + ay * ay + az * az)
        is_rising = mag > self._prev_mag
        # Detect falling edge after a peak above threshold
        if (not is_rising) and self._rising and self._prev_mag > STEP_MAG_THRESHOLD:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_step_ms) >= STEP_LOCKOUT_MS:
                self._steps += 1
                self._last_step_ms = now
        self._rising = is_rising
        self._prev_mag = mag

    # ── Sensor read ──────────────────────────────────────────────────────────

    def read(self):
        """Read all sensor data, update step counter, return data dict."""
        ax = self._read16s(_REG_AX_L) / _ACC_SENS
        ay = self._read16s(_REG_AX_L + 2) / _ACC_SENS
        az = self._read16s(_REG_AX_L + 4) / _ACC_SENS
        gx = self._read16s(_REG_AX_L + 6) / _GYR_SENS
        gy = self._read16s(_REG_AX_L + 8) / _GYR_SENS
        gz = self._read16s(_REG_AX_L + 10) / _GYR_SENS

        t_raw = self._read16s(_REG_TEMP_L)
        temp = t_raw / 256.0

        self._update_steps(ax, ay, az)

        self._data["acc"] = [ax, ay, az]
        self._data["gyro"] = [gx, gy, gz]
        self._data["temp"] = temp
        self._data["steps"] = self._steps
        return self._data

    # ── Step management ──────────────────────────────────────────────────────

    def set_steps(self, n):
        self._steps = n

    def reset_steps(self):
        self._steps = 0

    def get_steps(self):
        return self._steps

    def setup_wom_irq(self, shared):
        """Configure Wake-on-Motion on INT1 — fires when wrist is raised/moved."""
        # WoM threshold: CAL1_L = 32 (~0.5g)
        self._write(0x0B, 32)
        self._write(0x0C, 0)
        # CAL2_L[6]=INT1 routing, [0]=WoM on accel
        self._write(0x0D, 0x41)
        self._write(0x0E, 0)
        # Issue WoM command via CTRL9
        self._write(0x0A, 0x08)
        time.sleep_ms(10)
        self._write(0x0A, 0x00)  # NOP

        def _wom_isr(_):
            shared["wom_wake"] = True

        p = Pin(PIN_IMU_INT1, Pin.IN)
        p.irq(trigger=Pin.IRQ_RISING, handler=_wom_isr)


class SedentaryMonitor:
    """Tracks movement inactivity and fires an alert after SEDENTARY_ALERT_MS.

    Call update(acc) at the IMU poll rate (~50Hz) with the current [ax,ay,az].
    Call check() from the main loop — returns True once when the threshold is
    crossed, then resets so it won't fire again until the next idle window.
    Call reset() on any user activity (touch, gesture, display wake).
    """

    def __init__(self):
        self._last_acc = [0.0, 0.0, 1.0]  # assume upright at start
        self._idle_since = time.ticks_ms()  # when idle window started
        self._alerted = False  # fired this idle window already
        self._last_alert_epoch = 0  # unix timestamp of last alert

    def update(self, acc):
        """Feed latest accelerometer reading. Resets idle timer on movement."""
        ax, ay, az = acc[0], acc[1], acc[2]
        dx = abs(ax - self._last_acc[0])
        dy = abs(ay - self._last_acc[1])
        dz = abs(az - self._last_acc[2])
        if (
            dx > SEDENTARY_MOVE_THRESHOLD
            or dy > SEDENTARY_MOVE_THRESHOLD
            or dz > SEDENTARY_MOVE_THRESHOLD
        ):
            self._idle_since = time.ticks_ms()
            self._alerted = False  # allow alert again next idle window
        self._last_acc = [ax, ay, az]

    def check(self):
        """Return True exactly once per idle window when threshold exceeded."""
        if self._alerted:
            return False
        if time.ticks_diff(time.ticks_ms(), self._idle_since) >= SEDENTARY_ALERT_MS:
            self._alerted = True
            # record epoch time if RTC is set
            try:
                self._last_alert_epoch = time.time()
            except Exception:
                self._last_alert_epoch = 0
            return True
        return False

    def reset(self):
        """Call on any user activity to restart the idle window."""
        self._idle_since = time.ticks_ms()
        self._alerted = False

    def last_alert_epoch(self):
        return self._last_alert_epoch
