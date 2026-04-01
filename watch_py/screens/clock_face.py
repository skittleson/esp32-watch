# screens/clock_face.py — LVGL clock face
#
# Layout (240×240 round GC9A01):
#   - Outer arc: battery level (bottom 270°, cyan → orange → red)
#   - Inner ring arc: step progress toward 10k goal (top 270°, green)
#   - Centre: large time label (Montserrat 48, 12h AM/PM)
#   - AM/PM: small label top-right of time
#   - Date: Montserrat 20, below time
#   - Temp: bottom-left inside arc
#   - BT / ALM indicators: top corners

import lvgl as lv
import time
from micropython import const
from config import (
    C_BG,
    C_SURFACE,
    C_BORDER,
    C_TEXT_PRI,
    C_TEXT_SEC,
    C_ACCENT,
    C_GREEN,
    C_ORANGE,
    C_RED,
    C_YELLOW,
    C_GREY,
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

# Arc geometry — centred on 120,120; goes from 135° to 45° (270° sweep)
# LVGL arc: start_angle is from 3 o'clock, CCW is positive
# We want a bottom-heavy arc: from 135° (bottom-left) clockwise to 45° (bottom-right)
_ARC_BG_START = const(135)
_ARC_BG_END = const(45)


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

        # ── Battery arc (outer ring, bottom 270°) ─────────────────────────
        self._bat_arc = lv.arc(scr)
        self._bat_arc.set_size(220, 220)
        self._bat_arc.center()
        self._bat_arc.set_bg_angles(_ARC_BG_START, _ARC_BG_END)
        self._bat_arc.set_angles(_ARC_BG_START, _ARC_BG_START)  # starts empty
        self._bat_arc.set_style_arc_color(_c(C_BORDER), lv.PART.MAIN)
        self._bat_arc.set_style_arc_width(6, lv.PART.MAIN)
        self._bat_arc.set_style_arc_color(_c(C_ACCENT), lv.PART.INDICATOR)
        self._bat_arc.set_style_arc_width(6, lv.PART.INDICATOR)
        self._bat_arc.remove_style(None, lv.PART.KNOB)
        self._bat_arc.remove_flag(lv.obj.FLAG.CLICKABLE)

        # ── Step arc (inner ring, same geometry, dimmer green) ─────────────
        self._step_arc = lv.arc(scr)
        self._step_arc.set_size(204, 204)
        self._step_arc.center()
        self._step_arc.set_bg_angles(_ARC_BG_START, _ARC_BG_END)
        self._step_arc.set_angles(_ARC_BG_START, _ARC_BG_START)
        self._step_arc.set_style_arc_color(_c(C_BORDER), lv.PART.MAIN)
        self._step_arc.set_style_arc_width(4, lv.PART.MAIN)
        self._step_arc.set_style_arc_color(_c(C_GREEN), lv.PART.INDICATOR)
        self._step_arc.set_style_arc_width(4, lv.PART.INDICATOR)
        self._step_arc.remove_style(None, lv.PART.KNOB)
        self._step_arc.remove_flag(lv.obj.FLAG.CLICKABLE)

        # Make arcs transparent bg so round display bg shows through
        self._bat_arc.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self._step_arc.set_style_bg_opa(lv.OPA.TRANSP, 0)

        # ── Time label ────────────────────────────────────────────────────
        self._time_lbl = lv.label(scr)
        self._time_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._time_lbl.set_style_text_color(_c(C_TEXT_PRI), 0)
        self._time_lbl.set_text("12:00")
        self._time_lbl.align(lv.ALIGN.CENTER, -12, -18)

        # ── AM/PM label ───────────────────────────────────────────────────
        self._ampm_lbl = lv.label(scr)
        self._ampm_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._ampm_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        self._ampm_lbl.set_text("AM")
        # positioned relative to time label after first update

        # ── Seconds label (small, below time) ────────────────────────────
        self._sec_lbl = lv.label(scr)
        self._sec_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._sec_lbl.set_style_text_color(_c(C_ACCENT), 0)
        self._sec_lbl.set_text("00")
        self._sec_lbl.align(lv.ALIGN.CENTER, 0, 28)

        # ── Date label ────────────────────────────────────────────────────
        self._date_lbl = lv.label(scr)
        self._date_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._date_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        self._date_lbl.set_text("MON 01 JAN 2026")
        self._date_lbl.align(lv.ALIGN.CENTER, 0, 56)

        # ── Temp label (bottom-left) ──────────────────────────────────────
        self._temp_lbl = lv.label(scr)
        self._temp_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._temp_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        self._temp_lbl.set_text("--.-F")
        self._temp_lbl.align(lv.ALIGN.CENTER, -46, 88)

        # ── Step count label (bottom-right) ──────────────────────────────
        self._steps_lbl = lv.label(scr)
        self._steps_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._steps_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        self._steps_lbl.set_text("0 steps")
        self._steps_lbl.align(lv.ALIGN.CENTER, 38, 88)

        # ── BT indicator (top-left) ───────────────────────────────────────
        self._bt_lbl = lv.label(scr)
        self._bt_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._bt_lbl.set_style_text_color(_c(C_ACCENT), 0)
        self._bt_lbl.set_text("BT")
        self._bt_lbl.set_pos(14, 14)
        self._bt_lbl.add_flag(lv.obj.FLAG.HIDDEN)

        # ── ALM indicator (top-right) ─────────────────────────────────────
        self._alm_lbl = lv.label(scr)
        self._alm_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._alm_lbl.set_style_text_color(_c(C_YELLOW), 0)
        self._alm_lbl.set_text("ALM")
        self._alm_lbl.set_pos(194, 14)
        self._alm_lbl.add_flag(lv.obj.FLAG.HIDDEN)

        # ── Thin divider line below seconds ──────────────────────────────
        line = lv.line(scr)
        pts = [{"x": 60, "y": 0}, {"x": 180, "y": 0}]
        line.set_points(pts, 2)
        line.set_style_line_color(_c(C_BORDER), 0)
        line.set_style_line_width(1, 0)
        line.align(lv.ALIGN.CENTER, 0, 46)

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
        sec_str = "{:02d}".format(second)

        if time_str != self._prev_time or ampm != self._prev_ampm:
            self._time_lbl.set_text(time_str)
            self._ampm_lbl.set_text(ampm)
            # Align AM/PM to top-right of time label
            self._ampm_lbl.align_to(self._time_lbl, lv.ALIGN.OUT_RIGHT_TOP, 4, 6)
            self._prev_time = time_str
            self._prev_ampm = ampm

        if sec_str != self._prev_sec:
            self._sec_lbl.set_text(sec_str)
            self._prev_sec = sec_str

        # Date
        date_str = "{} {:02d} {} {}".format(_DAYS[t[6]], t[2], _MONTHS[t[1] - 1], t[0])
        if date_str != self._prev_date:
            self._date_lbl.set_text(date_str)
            self._prev_date = date_str

        # Battery arc + label
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
        # Arc sweeps 270°; map pct 0-100 → 0-270 degrees from start
        sweep = int(pct * 270 // 100)
        end_angle = (_ARC_BG_START + sweep) % 360
        self._bat_arc.set_angles(_ARC_BG_START, end_angle)
        # Colour: green > 50%, orange > 20%, red otherwise
        if pct > 50:
            colour = C_ACCENT
        elif pct > 20:
            colour = C_ORANGE
        else:
            colour = C_RED
        self._bat_arc.set_style_arc_color(_c(colour), lv.PART.INDICATOR)

    def _update_step_arc(self, steps):
        sweep = int(min(steps, _STEP_GOAL) * 270 // _STEP_GOAL)
        end_angle = (_ARC_BG_START + sweep) % 360
        self._step_arc.set_angles(_ARC_BG_START, end_angle)
        # Format steps nicely
        if steps >= 1000:
            s = "{:d},{:03d}".format(steps // 1000, steps % 1000)
        else:
            s = str(steps)
        self._steps_lbl.set_text(s + " steps")
