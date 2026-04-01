# screens/stopwatch.py — Stopwatch using gc9a01 font modules

import time
import gc9a01
import vga2_bold_16x32  # 16x32 — stopwatch timer
import vga1_8x16  # 8x16  — status, hint
import vga1_8x8  # 8x8   — small hints

from config import BLACK, WHITE, GREY, LGREY, GREEN, ORANGE

_IDLE = const(0)
_RUNNING = const(1)
_PAUSED = const(2)

_LABELS = {_IDLE: "TAP TO START", _RUNNING: "RUNNING", _PAUSED: "PAUSED"}
_COLORS = {_IDLE: LGREY, _RUNNING: GREEN, _PAUSED: ORANGE}


def _fmt_ms(ms):
    cs = ms // 10
    return "{:02d}:{:02d}.{:02d}".format((cs // 6000) % 60, (cs // 100) % 60, cs % 100)


class Stopwatch:
    def __init__(self):
        self.dirty = True
        self._state = _IDLE
        self._elapsed = 0
        self._start = 0
        self._lap_str = ""
        self._prev_display = None

    def handle_gesture(self, gesture):
        if gesture == "single_click":
            if self._state in (_IDLE, _PAUSED):
                self._start = time.ticks_ms()
                self._state = _RUNNING
            else:
                self._elapsed += time.ticks_diff(time.ticks_ms(), self._start)
                self._state = _PAUSED
            self.dirty = True
        elif gesture == "swipe_up" and self._state != _RUNNING:
            self._elapsed = 0
            self._state = _IDLE
            self._lap_str = ""
            self.dirty = True
        elif gesture == "long_press" and self._state == _RUNNING:
            total = self._elapsed + time.ticks_diff(time.ticks_ms(), self._start)
            self._lap_str = "LAP  " + _fmt_ms(total)
            self.dirty = True

    def _current_ms(self):
        if self._state == _RUNNING:
            return self._elapsed + time.ticks_diff(time.ticks_ms(), self._start)
        return self._elapsed

    def draw(self, tft, shared):
        display_str = _fmt_ms(self._current_ms())
        if not self.dirty and display_str == self._prev_display:
            return
        if self.dirty:
            self._full_draw(tft, display_str)
            self.dirty = False
        else:
            # Partial: only time area
            tft.fill_rect(20, 88, 200, 40, BLACK)
            x = (240 - len(display_str) * 16) // 2
            tft.text(vga2_bold_16x32, display_str, x, 90, WHITE, BLACK)
        self._prev_display = display_str

    def _full_draw(self, tft, display_str):
        tft.fill(BLACK)
        # Title
        title = "STOPWATCH"
        tft.text(vga1_8x16, title, (240 - len(title) * 8) // 2, 22, LGREY, BLACK)
        # Dividers
        tft.fill_rect(20, 78, 200, 1, GREY)
        tft.fill_rect(20, 145, 200, 1, GREY)
        # Time — vga2_bold_16x32
        x = (240 - len(display_str) * 16) // 2
        tft.text(vga2_bold_16x32, display_str, x, 90, WHITE, BLACK)
        # Status — vga1_8x16
        label = _LABELS[self._state]
        color = _COLORS[self._state]
        x = (240 - len(label) * 8) // 2
        tft.text(vga1_8x16, label, x, 155, color, BLACK)
        # Lap
        if self._lap_str:
            x = (240 - len(self._lap_str) * 8) // 2
            tft.text(vga1_8x16, self._lap_str, x, 178, LGREY, BLACK)
        # Hints
        h1 = "Swipe up: reset"
        h2 = "Hold: lap"
        tft.text(vga1_8x8, h1, (240 - len(h1) * 8) // 2, 208, GREY, BLACK)
        tft.text(vga1_8x8, h2, (240 - len(h2) * 8) // 2, 220, GREY, BLACK)
