# screens/stopwatch.py — LVGL stopwatch screen
#
# Layout:
#   - Title "STOPWATCH" at top
#   - Large arc progress (0-60s one full sweep, lap marker)
#   - Centred time label MM:SS.cs (Montserrat 40)
#   - Status label (READY / RUNNING / PAUSED) with colour coding
#   - Lap label when set
#   - Hint labels at bottom

import lvgl as lv
import time
from micropython import const
from config import (
    C_BG,
    C_BORDER,
    C_TEXT_PRI,
    C_TEXT_SEC,
    C_ACCENT,
    C_GREEN,
    C_ORANGE,
    C_GREY,
)

_IDLE = const(0)
_RUNNING = const(1)
_PAUSED = const(2)


def _c(h):
    return lv.color_hex(h)


def _fmt_ms(ms):
    cs = ms // 10
    return "{:02d}:{:02d}.{:02d}".format((cs // 6000) % 60, (cs // 100) % 60, cs % 100)


class Stopwatch:
    def __init__(self, parent_screen):
        self._scr = parent_screen
        self._state = _IDLE
        self._elapsed = 0
        self._start = 0
        self._lap_ms = None

        self._build_ui()

    def _build_ui(self):
        scr = self._scr
        scr.set_style_bg_color(_c(C_BG), 0)
        scr.set_style_bg_opa(lv.OPA.COVER, 0)

        # ── Title ────────────────────────────────────────────────────────
        title = lv.label(scr)
        title.set_style_text_font(lv.font_montserrat_16, 0)
        title.set_style_text_color(_c(C_TEXT_SEC), 0)
        title.set_text("STOPWATCH")
        title.align(lv.ALIGN.TOP_MID, 0, 18)

        # ── Progress arc (full circle, 360°) ────────────────────────────
        self._arc = lv.arc(scr)
        self._arc.set_size(196, 196)
        self._arc.center()
        self._arc.set_bg_angles(0, 360)
        self._arc.set_angles(0, 0)
        self._arc.set_style_arc_color(_c(C_BORDER), lv.PART.MAIN)
        self._arc.set_style_arc_width(5, lv.PART.MAIN)
        self._arc.set_style_arc_color(_c(C_ACCENT), lv.PART.INDICATOR)
        self._arc.set_style_arc_width(5, lv.PART.INDICATOR)
        self._arc.remove_style(None, lv.PART.KNOB)
        self._arc.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._arc.set_style_bg_opa(lv.OPA.TRANSP, 0)

        # ── Lap tick mark (small arc segment) — hidden until set ─────────
        self._lap_arc = lv.arc(scr)
        self._lap_arc.set_size(196, 196)
        self._lap_arc.center()
        self._lap_arc.set_bg_angles(0, 0)  # invisible bg
        self._lap_arc.set_angles(0, 0)
        self._lap_arc.set_style_arc_color(_c(C_ORANGE), lv.PART.INDICATOR)
        self._lap_arc.set_style_arc_width(5, lv.PART.INDICATOR)
        self._lap_arc.remove_style(None, lv.PART.KNOB)
        self._lap_arc.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._lap_arc.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self._lap_arc.add_flag(lv.obj.FLAG.HIDDEN)

        # ── Time label ───────────────────────────────────────────────────
        self._time_lbl = lv.label(scr)
        self._time_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._time_lbl.set_style_text_color(_c(C_TEXT_PRI), 0)
        self._time_lbl.set_text("00:00.00")
        self._time_lbl.align(lv.ALIGN.CENTER, 0, -8)

        # ── Status label ─────────────────────────────────────────────────
        self._status_lbl = lv.label(scr)
        self._status_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._status_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        self._status_lbl.set_text("TAP TO START")
        self._status_lbl.align(lv.ALIGN.CENTER, 0, 34)

        # ── Lap label ────────────────────────────────────────────────────
        self._lap_lbl = lv.label(scr)
        self._lap_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._lap_lbl.set_style_text_color(_c(C_ORANGE), 0)
        self._lap_lbl.set_text("")
        self._lap_lbl.align(lv.ALIGN.CENTER, 0, 58)

        # ── Hints ────────────────────────────────────────────────────────
        h1 = lv.label(scr)
        h1.set_style_text_font(lv.font_montserrat_12, 0)
        h1.set_style_text_color(_c(C_GREY), 0)
        h1.set_text("swipe up: reset   hold: lap")
        h1.align(lv.ALIGN.BOTTOM_MID, 0, -16)

        # ── Invisible full-screen tap overlay ────────────────────────────
        # Catches LVGL tap events so start/pause works anywhere on screen
        self._tap_overlay = lv.obj(scr)
        self._tap_overlay.set_size(240, 240)
        self._tap_overlay.set_pos(0, 0)
        self._tap_overlay.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self._tap_overlay.set_style_border_width(0, 0)
        self._tap_overlay.add_flag(lv.obj.FLAG.CLICKABLE)
        self._tap_overlay.add_event_cb(self._on_tap, lv.EVENT.SHORT_CLICKED, None)

    def _on_tap(self, e):
        """LVGL tap event — start/pause stopwatch."""
        self.handle_gesture("single_click")

    def handle_gesture(self, gesture):
        if gesture == "single_click":
            if self._state in (_IDLE, _PAUSED):
                self._start = time.ticks_ms()
                self._state = _RUNNING
            else:
                self._elapsed += time.ticks_diff(time.ticks_ms(), self._start)
                self._state = _PAUSED
            self._refresh_status()

        elif gesture == "swipe_up" and self._state != _RUNNING:
            self._elapsed = 0
            self._state = _IDLE
            self._lap_ms = None
            self._lap_arc.add_flag(lv.obj.FLAG.HIDDEN)
            self._lap_lbl.set_text("")
            self._arc.set_angles(0, 0)
            self._time_lbl.set_text("00:00.00")
            self._refresh_status()

        elif gesture == "long_press" and self._state == _RUNNING:
            self._lap_ms = self._elapsed + time.ticks_diff(time.ticks_ms(), self._start)
            self._lap_lbl.set_text("LAP  " + _fmt_ms(self._lap_ms))
            # Show lap tick on arc
            lap_deg = int((self._lap_ms % 60_000) * 360 // 60_000)
            self._lap_arc.set_angles(lap_deg, (lap_deg + 4) % 360)
            self._lap_arc.remove_flag(lv.obj.FLAG.HIDDEN)

    def _refresh_status(self):
        if self._state == _IDLE:
            self._status_lbl.set_text("TAP TO START")
            self._status_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        elif self._state == _RUNNING:
            self._status_lbl.set_text("RUNNING")
            self._status_lbl.set_style_text_color(_c(C_GREEN), 0)
        else:
            self._status_lbl.set_text("PAUSED")
            self._status_lbl.set_style_text_color(_c(C_ORANGE), 0)

    def _current_ms(self):
        if self._state == _RUNNING:
            return self._elapsed + time.ticks_diff(time.ticks_ms(), self._start)
        return self._elapsed

    def update(self, shared):
        """Called each TaskHandler tick when this screen is active."""
        ms = self._current_ms()
        self._time_lbl.set_text(_fmt_ms(ms))
        if self._state == _RUNNING:
            # Arc sweeps one full rotation per 60s
            deg = int((ms % 60_000) * 360 // 60_000)
            self._arc.set_angles(0, deg)
