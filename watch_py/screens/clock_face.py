# screens/clock_face.py — Sci-Fi / Neon Digital watch face
#
# Layout (240x240 round GC9A01):
#   - 4 cardinal neon tick marks (12/3/6/9 o'clock positions)
#   - Battery arc: thick outer neon lime/orange/red ring (270 deg sweep)
#   - Step arc: thick inner neon magenta ring (270 deg sweep)
#   - Centre: digital time (12h) with seconds (opacity toggles on even/odd)
#   - Neon cyan divider line
#   - Date, temp, step count readouts with colored accents
#   - BT / ALM indicators in top corners
#   - Battery % numeric readout
#
# Performance: 15 widgets total (2 arcs, 8 labels, 1 divider, 4 ticks).
# No continuous animations — redraws only on dirty-flag value changes.

import lvgl as lv
import time
from micropython import const
from config import (
    C_BG,
    C_TEXT_SEC,
    C_ORANGE,
    C_RED,
    C_YELLOW,
    C_NEON_CYAN,
    C_NEON_MAGENTA,
    C_NEON_LIME,
    C_NEON_BLUE,
)

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

_STEP_GOAL = const(10_000)

# Arc geometry — centred on 120,120; goes from 135 deg to 45 deg (270 deg sweep)
_ARC_BG_START = const(135)
_ARC_BG_END = const(45)

# Pre-computed tick mark coordinates for 4 cardinal positions (12/3/6/9)
# Each tuple: (x1_inner, y1_inner, x2_outer, y2_outer)
# Centre=120,120  inner_r=107  outer_r=117
# 12 o'clock (top):    angle=-90 deg → cos=0, sin=-1
# 3 o'clock (right):   angle=  0 deg → cos=1, sin=0
# 6 o'clock (bottom):  angle= 90 deg → cos=0, sin=1
# 9 o'clock (left):    angle=180 deg → cos=-1, sin=0
_TICK_COORDS = (
    (120, 13, 120, 3),  # 12 o'clock
    (227, 120, 237, 120),  # 3 o'clock
    (120, 227, 120, 237),  # 6 o'clock
    (13, 120, 3, 120),  # 9 o'clock
)

# Seconds opacity: bright on even seconds, dim on odd — no lv.anim_t needed
_OPA_BRIGHT = const(255)
_OPA_DIM = const(90)


def _c(hex_color):
    return lv.color_hex(hex_color)


class ClockFace:
    def __init__(self, parent_screen):
        self._scr = parent_screen
        self._ble_active = False
        self._alarm_on = False

        self._build_ui()

    def _build_ui(self):
        scr = self._scr
        scr.set_style_bg_color(_c(C_BG), 0)
        scr.set_style_bg_opa(lv.OPA.COVER, 0)

        # ── 4 cardinal tick marks (pre-computed, no math import) ──────────
        for x1, y1, x2, y2 in _TICK_COORDS:
            tick = lv.line(scr)
            pts = [{"x": x1, "y": y1}, {"x": x2, "y": y2}]
            tick.set_points(pts, 2)
            tick.set_style_line_color(_c(C_NEON_CYAN), 0)
            tick.set_style_line_width(2, 0)
            tick.set_style_line_opa(200, 0)
            tick.set_pos(0, 0)

        # ── Battery arc (outer ring, thick neon, 270 deg) ─────────────────
        self._bat_arc = lv.arc(scr)
        self._bat_arc.set_size(216, 216)
        self._bat_arc.center()
        self._bat_arc.set_bg_angles(_ARC_BG_START, _ARC_BG_END)
        self._bat_arc.set_angles(_ARC_BG_START, _ARC_BG_START)
        self._bat_arc.set_style_arc_color(_c(0x112211), lv.PART.MAIN)
        self._bat_arc.set_style_arc_width(8, lv.PART.MAIN)
        self._bat_arc.set_style_arc_rounded(True, lv.PART.MAIN)
        self._bat_arc.set_style_arc_color(_c(C_NEON_LIME), lv.PART.INDICATOR)
        self._bat_arc.set_style_arc_width(8, lv.PART.INDICATOR)
        self._bat_arc.set_style_arc_rounded(True, lv.PART.INDICATOR)
        self._bat_arc.remove_style(None, lv.PART.KNOB)
        self._bat_arc.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._bat_arc.set_style_bg_opa(lv.OPA.TRANSP, 0)

        # ── Step arc (inner ring, neon magenta, 270 deg) ──────────────────
        self._step_arc = lv.arc(scr)
        self._step_arc.set_size(196, 196)
        self._step_arc.center()
        self._step_arc.set_bg_angles(_ARC_BG_START, _ARC_BG_END)
        self._step_arc.set_angles(_ARC_BG_START, _ARC_BG_START)
        self._step_arc.set_style_arc_color(_c(0x1A0022), lv.PART.MAIN)
        self._step_arc.set_style_arc_width(6, lv.PART.MAIN)
        self._step_arc.set_style_arc_rounded(True, lv.PART.MAIN)
        self._step_arc.set_style_arc_color(_c(C_NEON_MAGENTA), lv.PART.INDICATOR)
        self._step_arc.set_style_arc_width(6, lv.PART.INDICATOR)
        self._step_arc.set_style_arc_rounded(True, lv.PART.INDICATOR)
        self._step_arc.remove_style(None, lv.PART.KNOB)
        self._step_arc.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._step_arc.set_style_bg_opa(lv.OPA.TRANSP, 0)

        # ── Time label (large, neon cyan) ─────────────────────────────────
        self._time_lbl = lv.label(scr)
        self._time_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._time_lbl.set_style_text_color(_c(C_NEON_CYAN), 0)
        self._time_lbl.set_text("12:00")
        self._time_lbl.align(lv.ALIGN.CENTER, -12, -20)

        # ── AM/PM label ───────────────────────────────────────────────────
        self._ampm_lbl = lv.label(scr)
        self._ampm_lbl.set_style_text_font(lv.font_montserrat_12, 0)
        self._ampm_lbl.set_style_text_color(_c(C_NEON_BLUE), 0)
        self._ampm_lbl.set_text("AM")

        # ── Seconds label (opacity toggled in update, no animation) ───────
        self._sec_lbl = lv.label(scr)
        self._sec_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._sec_lbl.set_style_text_color(_c(C_NEON_CYAN), 0)
        self._sec_lbl.set_text(":00")
        self._sec_lbl.align(lv.ALIGN.CENTER, 0, 0)

        # ── Neon divider line ─────────────────────────────────────────────
        line = lv.line(scr)
        pts = [{"x": 50, "y": 0}, {"x": 190, "y": 0}]
        line.set_points(pts, 2)
        line.set_style_line_color(_c(C_NEON_CYAN), 0)
        line.set_style_line_width(1, 0)
        line.set_style_line_opa(120, 0)
        line.align(lv.ALIGN.CENTER, 0, 20)

        # ── Date label (below divider) ────────────────────────────────────
        self._date_lbl = lv.label(scr)
        self._date_lbl.set_style_text_font(lv.font_montserrat_12, 0)
        self._date_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        self._date_lbl.set_text("MON 01 JAN 2026")
        self._date_lbl.align(lv.ALIGN.CENTER, 0, 34)

        # ── Battery % readout (top-center, below tick ring) ───────────────
        self._bat_lbl = lv.label(scr)
        self._bat_lbl.set_style_text_font(lv.font_montserrat_12, 0)
        self._bat_lbl.set_style_text_color(_c(C_NEON_LIME), 0)
        self._bat_lbl.set_text("100%")
        self._bat_lbl.align(lv.ALIGN.TOP_MID, 0, 30)

        # ── Temp label (bottom-left, orange accent) ───────────────────────
        self._temp_lbl = lv.label(scr)
        self._temp_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._temp_lbl.set_style_text_color(_c(C_ORANGE), 0)
        self._temp_lbl.set_text("--.-F")
        self._temp_lbl.align(lv.ALIGN.CENTER, -46, 72)

        # ── Step count label (bottom-right, magenta accent) ───────────────
        self._steps_lbl = lv.label(scr)
        self._steps_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._steps_lbl.set_style_text_color(_c(C_NEON_MAGENTA), 0)
        self._steps_lbl.set_text("0 steps")
        self._steps_lbl.align(lv.ALIGN.CENTER, 38, 72)

        # ── BT indicator (top-left, neon cyan) ────────────────────────────
        self._bt_lbl = lv.label(scr)
        self._bt_lbl.set_style_text_font(lv.font_montserrat_12, 0)
        self._bt_lbl.set_style_text_color(_c(C_NEON_CYAN), 0)
        self._bt_lbl.set_text("BT")
        self._bt_lbl.set_pos(16, 16)
        self._bt_lbl.add_flag(lv.obj.FLAG.HIDDEN)

        # ── ALM indicator (top-right, yellow) ─────────────────────────────
        self._alm_lbl = lv.label(scr)
        self._alm_lbl.set_style_text_font(lv.font_montserrat_12, 0)
        self._alm_lbl.set_style_text_color(_c(C_YELLOW), 0)
        self._alm_lbl.set_text("ALM")
        self._alm_lbl.set_pos(196, 16)
        self._alm_lbl.add_flag(lv.obj.FLAG.HIDDEN)

        # Cache previous values to avoid redundant label updates
        self._prev_time = None
        self._prev_ampm = None
        self._prev_sec = None
        self._prev_date = None
        self._prev_bat = None
        self._prev_steps = None
        self._prev_temp = None

    # ── Indicator setters ────────────────────────────────────────────────────

    def set_ble_indicator(self, active):
        if active != self._ble_active:
            self._ble_active = active
            if active:
                self._bt_lbl.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self._bt_lbl.add_flag(lv.obj.FLAG.HIDDEN)

    def set_alarm_indicator(self, active):
        if active != self._alarm_on:
            self._alarm_on = active
            if active:
                self._alm_lbl.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self._alm_lbl.add_flag(lv.obj.FLAG.HIDDEN)

    def handle_gesture(self, gesture):
        pass  # clock face has no gesture actions

    # ── Update ───────────────────────────────────────────────────────────────

    def update(self, shared):
        """Called by ScreenManager each TaskHandler tick when this screen is active."""
        t = time.localtime()

        # Time
        hour = t[3]
        minute = t[4]
        second = t[5]
        ampm = "AM" if hour < 12 else "PM"
        h12 = hour % 12 or 12
        time_str = "{:d}:{:02d}".format(h12, minute)
        sec_str = ":{:02d}".format(second)

        if time_str != self._prev_time or ampm != self._prev_ampm:
            self._time_lbl.set_text(time_str)
            self._ampm_lbl.set_text(ampm)
            self._ampm_lbl.align_to(self._time_lbl, lv.ALIGN.OUT_RIGHT_TOP, 4, 2)
            self._prev_time = time_str
            self._prev_ampm = ampm

        if sec_str != self._prev_sec:
            self._sec_lbl.set_text(sec_str)
            # Toggle opacity: bright on even seconds, dim on odd
            opa = _OPA_BRIGHT if (second % 2 == 0) else _OPA_DIM
            self._sec_lbl.set_style_opa(opa, 0)
            self._prev_sec = sec_str

        # Date
        date_str = "{} {:02d} {} {}".format(_DAYS[t[6]], t[2], _MONTHS[t[1] - 1], t[0])
        if date_str != self._prev_date:
            self._date_lbl.set_text(date_str)
            self._prev_date = date_str

        # Battery arc + labels
        bat_pct = shared.get("bat_pct", 100)
        if bat_pct != self._prev_bat:
            self._update_bat_arc(bat_pct)
            self._prev_bat = bat_pct

        # Steps arc + label
        steps = shared.get("steps", 0)
        if steps != self._prev_steps:
            self._update_step_arc(steps)
            self._prev_steps = steps

        # Temp label
        temp = shared.get("temp", 0.0)
        if self._prev_temp is None or abs(temp - self._prev_temp) > 0.2:
            temp_f = temp * 9 / 5 + 32
            self._temp_lbl.set_text("{:.1f}F".format(temp_f))
            self._prev_temp = temp

    def _update_bat_arc(self, pct):
        sweep = int(pct * 270 // 100)
        end_angle = (_ARC_BG_START + sweep) % 360
        self._bat_arc.set_angles(_ARC_BG_START, end_angle)
        if pct > 50:
            colour = C_NEON_LIME
        elif pct > 20:
            colour = C_ORANGE
        else:
            colour = C_RED
        self._bat_arc.set_style_arc_color(_c(colour), lv.PART.INDICATOR)
        self._bat_lbl.set_text("{}%".format(pct))
        self._bat_lbl.set_style_text_color(_c(colour), 0)

    def _update_step_arc(self, steps):
        sweep = int(min(steps, _STEP_GOAL) * 270 // _STEP_GOAL)
        end_angle = (_ARC_BG_START + sweep) % 360
        self._step_arc.set_angles(_ARC_BG_START, end_angle)
        if steps >= 1000:
            s = "{:d},{:03d}".format(steps // 1000, steps % 1000)
        else:
            s = str(steps)
        self._steps_lbl.set_text(s + " steps")
