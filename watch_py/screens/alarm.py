# screens/alarm.py — Alarm screen using gc9a01 font modules

import time
import gc9a01
import vga2_bold_16x32  # 16x32 — alarm time display
import vga1_8x16  # 8x16  — status, hints
import vga1_8x8  # 8x8   — small hints

from machine import Pin, PWM
from config import BLACK, WHITE, GREY, LGREY, GREEN, RED, YELLOW, PIN_HAPTIC, PIN_TP_INT


class Alarm:
    def __init__(self, settings):
        self.dirty = True
        self._hour = settings.get("alarm_hour", 7)
        self._minute = settings.get("alarm_minute", 30)
        self._enabled = settings.get("alarm_enabled", False)
        self._fired = False
        self._dismissed = False
        self._fire_start = 0
        self._haptic_pulse = 0
        self._haptic_state = False
        self._haptic_pin = None

    # ── Setters ─────────────────────────────────────────────────────────────

    def set_time(self, hour, minute):
        self._hour = hour
        self._minute = minute
        self._dismissed = False
        self.dirty = True

    def set_enabled(self, en):
        self._enabled = en
        self._dismissed = False
        self.dirty = True

    def get_hour(self):
        return self._hour

    def get_minute(self):
        return self._minute

    def get_enabled(self):
        return self._enabled

    def to_settings(self):
        return {
            "alarm_hour": self._hour,
            "alarm_minute": self._minute,
            "alarm_enabled": self._enabled,
        }

    # ── Gesture handling ─────────────────────────────────────────────────────

    def handle_gesture(self, gesture):
        if gesture == "single_click":
            if self._fired:
                self.dismiss()
            else:
                self._enabled = not self._enabled
                self._dismissed = False
                self.dirty = True

    # ── Logic ────────────────────────────────────────────────────────────────

    def should_fire(self):
        if not self._enabled or self._fired or self._dismissed:
            return False
        t = time.localtime()
        if t[3] == self._hour and t[4] == self._minute and t[5] < 5:
            return True
        if t[4] != self._minute:
            self._dismissed = False
        return False

    def fire(self):
        self._fired = True
        self._haptic_pulse = 0
        self._haptic_state = False
        self._fire_start = time.ticks_ms()
        # GPIO5 is shared with the touch INT pin.
        # Take ownership as output to drive haptic; touch IRQ is re-attached in dismiss().
        self._haptic_pin = Pin(PIN_HAPTIC, Pin.OUT)
        self._haptic_pin(1)
        self.dirty = True

    def dismiss(self):
        self._fired = False
        self._dismissed = True
        if self._haptic_pin:
            self._haptic_pin(0)
            self._haptic_pin = None
        # Restore GPIO5 as input so the touch IRQ can be re-attached by the caller.
        Pin(PIN_TP_INT, Pin.IN)
        self.dirty = True

    # ── Tick (haptic + flash) ─────────────────────────────────────────────

    def tick(self, tft):
        if not self._fired:
            return
        elapsed = time.ticks_diff(time.ticks_ms(), self._fire_start)
        if elapsed > 60_000:
            self.dismiss()
            return

        # Haptic: 5 × (500ms on / 100ms off)
        if self._haptic_pulse < 5:
            if elapsed % 600 < 500:
                if not self._haptic_state:
                    self._haptic_pin(1)
                    self._haptic_state = True
            else:
                if self._haptic_state:
                    self._haptic_pin(0)
                    self._haptic_state = False
                    self._haptic_pulse += 1
        else:
            if self._haptic_state:
                self._haptic_pin(0)
                self._haptic_state = False

        # Flash: alternate red/black every 500ms
        bg = RED if (elapsed // 500) % 2 == 0 else BLACK
        tft.fill(bg)
        h12 = self._hour % 12 or 12
        ampm = "AM" if self._hour < 12 else "PM"
        time_str = "{:d}:{:02d}".format(h12, self._minute)
        x = (240 - len(time_str) * 16 - 24) // 2
        tft.text(vga2_bold_16x32, time_str, x, 85, WHITE, bg)
        tft.text(vga1_8x8, ampm, x + len(time_str) * 16 + 4, 88, WHITE, bg)
        msg = "TAP TO DISMISS"
        tft.text(vga1_8x16, msg, (240 - len(msg) * 8) // 2, 175, WHITE, bg)

    # ── Draw ────────────────────────────────────────────────────────────────

    def draw(self, tft, shared):
        if self._fired:
            self.tick(tft)
            return
        if not self.dirty:
            return
        self._full_draw(tft)
        self.dirty = False

    def _full_draw(self, tft):
        tft.fill(BLACK)
        # Title
        tft.text(vga1_8x16, "ALARM", (240 - 5 * 8) // 2, 22, LGREY, BLACK)
        # Dividers
        tft.fill_rect(20, 78, 200, 1, GREY)
        tft.fill_rect(20, 158, 200, 1, GREY)
        # Time — 12h format, vga2_bold_16x32
        h12 = self._hour % 12 or 12
        ampm = "AM" if self._hour < 12 else "PM"
        time_str = "{:d}:{:02d}".format(h12, self._minute)
        x = (240 - len(time_str) * 16 - 24) // 2
        tft.text(vga2_bold_16x32, time_str, x, 95, WHITE, BLACK)
        tft.text(vga1_8x8, ampm, x + len(time_str) * 16 + 4, 98, LGREY, BLACK)
        # Status
        if self._enabled:
            label, color = "ALARM ON", GREEN
        else:
            label, color = "ALARM OFF", GREY
        x = (240 - len(label) * 8) // 2
        tft.text(vga1_8x16, label, x, 168, color, BLACK)
        # Hint
        hint = "Tap: toggle | BLE: set time"
        tft.text(vga1_8x8, hint, (240 - len(hint) * 8) // 2, 215, GREY, BLACK)
