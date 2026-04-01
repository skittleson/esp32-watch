# screens/clock_face.py — Digital watch face using gc9a01 font modules

import time
import gc9a01
import vga2_bold_16x32  # 16x32 — large time display
import vga1_8x16  # 8x16  — date, labels
import vga1_8x8  # 8x8   — small indicators

from config import BLACK, WHITE, GREY, LGREY, GREEN, ORANGE, RED, CYAN, YELLOW

_DAYS = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
_MONTHS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


def _fmt_time_12h(hour, minute, second):
    """Return (time_str, ampm_str) in 12-hour format."""
    ampm = "AM" if hour < 12 else "PM"
    h12 = hour % 12
    if h12 == 0:
        h12 = 12
    return "{:d}:{:02d}:{:02d}".format(h12, minute, second), ampm


class ClockFace:
    def __init__(self):
        self.dirty = True
        self._dirty_time = True
        self._ble_active = False
        self._alarm_on = False
        self._prev_time = None
        self._prev_ampm = None
        self._prev_bat = None
        self._prev_steps = None
        self._prev_temp = None

    def set_ble_indicator(self, active):
        if active != self._ble_active:
            self._ble_active = active
            self.dirty = True

    def set_alarm_indicator(self, active):
        if active != self._alarm_on:
            self._alarm_on = active
            self.dirty = True

    def handle_gesture(self, gesture):
        pass

    def mark_time_dirty(self):
        self._dirty_time = True

    def draw(self, tft, shared):
        now = time.localtime()
        time_str, ampm = _fmt_time_12h(now[3], now[4], now[5])
        bat_pct = shared.get("bat_pct", 100)
        steps = shared.get("steps", 0)
        temp = shared.get("temp", 0.0)

        if self.dirty:
            self._full_draw(tft, now, time_str, ampm, bat_pct, steps, temp)
            self.dirty = self._dirty_time = False
            self._prev_time = time_str
            self._prev_ampm = ampm
            self._prev_bat = bat_pct
            self._prev_steps = steps
            self._prev_temp = temp
            return

        if self._dirty_time or time_str != self._prev_time or ampm != self._prev_ampm:
            self._draw_time(tft, time_str, ampm)
            self._prev_time = time_str
            self._prev_ampm = ampm
            self._dirty_time = False

        if bat_pct != self._prev_bat:
            self._draw_battery(tft, bat_pct)
            self._prev_bat = bat_pct

        if steps != self._prev_steps:
            self._draw_steps(tft, steps)
            self._prev_steps = steps

        if self._prev_temp is None or abs(temp - self._prev_temp) > 0.2:
            self._draw_temp(tft, temp)
            self._prev_temp = temp

    def _full_draw(self, tft, now, time_str, ampm, bat_pct, steps, temp):
        tft.fill(BLACK)

        # Corner indicators
        if self._ble_active:
            tft.text(vga1_8x8, "BT", 10, 10, CYAN, BLACK)
        if self._alarm_on:
            tft.text(vga1_8x8, "ALM", 200, 10, YELLOW, BLACK)

        # Date — centred
        date_str = "{} {:02d} {} {}".format(
            _DAYS[now[6]], now[2], _MONTHS[now[1] - 1], now[0]
        )
        x = (240 - len(date_str) * 8) // 2
        tft.text(vga1_8x16, date_str, x, 55, LGREY, BLACK)

        # Divider lines
        tft.fill_rect(20, 78, 200, 1, GREY)
        tft.fill_rect(20, 155, 200, 1, GREY)

        self._draw_time(tft, time_str, ampm)
        self._draw_temp(tft, temp)
        self._draw_battery(tft, bat_pct)
        self._draw_steps(tft, steps)

    def _draw_time(self, tft, time_str, ampm):
        # Clear time + AM/PM area
        tft.fill_rect(10, 83, 220, 42, BLACK)

        # Time string — vga2_bold_16x32 (16px/char, 32px tall)
        # Max "12:34:56" = 8 chars × 16 = 128px; shift left to make room for AM/PM
        x = (240 - len(time_str) * 16 - 24) // 2  # 24px gap for AM/PM label
        tft.text(vga2_bold_16x32, time_str, x, 85, WHITE, BLACK)

        # AM/PM — vga1_8x8 (8px/char), top-right of time, vertically centred
        tft.text(vga1_8x8, ampm, x + len(time_str) * 16 + 4, 88, LGREY, BLACK)

    def _draw_temp(self, tft, temp):
        tft.fill_rect(20, 162, 90, 16, BLACK)
        tft.text(vga1_8x16, "{:.1f}F".format(temp * 9 / 5 + 32), 22, 163, WHITE, BLACK)

    def _draw_battery(self, tft, pct):
        tft.fill_rect(130, 162, 90, 16, BLACK)
        colour = GREEN if pct > 50 else (ORANGE if pct > 20 else RED)
        tft.text(vga1_8x16, "BAT {:d}%".format(pct), 132, 163, colour, BLACK)

    def _draw_steps(self, tft, steps):
        tft.fill_rect(20, 183, 200, 16, BLACK)
        if steps >= 1000:
            s = "{:d},{:03d} steps".format(steps // 1000, steps % 1000)
        else:
            s = "{:d} steps".format(steps)
        x = (240 - len(s) * 8) // 2
        tft.text(vga1_8x16, s, x, 184, LGREY, BLACK)
