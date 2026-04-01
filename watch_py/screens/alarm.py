# screens/alarm.py — LVGL alarm screen
#
# Normal view:
#   - Title "ALARM"
#   - Large time display (12h format, Montserrat 28)
#   - Toggle switch (ON/OFF)
#   - Status label
#   - Hint label
#
# Fired view:
#   - Animated red pulsing arc (lv.anim on arc bg colour)
#   - Time centred
#   - "TAP TO DISMISS" blinking label
#   - Haptic pulses via GPIO5 (same as before)
#
# Tap on this screen: dismiss if firing, else toggle alarm on/off
# GPIO5 haptic conflict: same fix as before — reattach_irq() called by main.py

import lvgl as lv
import time
from machine import Pin
from config import (
    C_BG,
    C_SURFACE,
    C_BORDER,
    C_TEXT_PRI,
    C_TEXT_SEC,
    C_ACCENT,
    C_GREEN,
    C_RED,
    C_YELLOW,
    C_GREY,
    PIN_HAPTIC,
    PIN_TP_INT,
    get_font_big,
)


def _c(h):
    return lv.color_hex(h)


class Alarm:
    def __init__(self, parent_screen, settings):
        self._scr = parent_screen
        self._hour = settings.get("alarm_hour", 7)
        self._minute = settings.get("alarm_minute", 30)
        self._enabled = settings.get("alarm_enabled", False)
        self._fired = False
        self._dismissed = False
        self._fire_start = 0
        self._haptic_pulse = 0
        self._haptic_state = False
        self._haptic_pin = None
        self._flash_state = False  # for pulsing arc colour

        self._build_ui()
        self._refresh_display()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        scr = self._scr
        scr.set_style_bg_color(_c(C_BG), 0)
        scr.set_style_bg_opa(lv.OPA.COVER, 0)

        # ── Normal view container ─────────────────────────────────────────
        self._normal = lv.obj(scr)
        self._normal.set_size(240, 240)
        self._normal.set_pos(0, 0)
        self._normal.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self._normal.set_style_border_width(0, 0)
        self._normal.set_style_pad_all(0, 0)

        title = lv.label(self._normal)
        title.set_style_text_font(lv.font_montserrat_16, 0)
        title.set_style_text_color(_c(C_TEXT_SEC), 0)
        title.set_text("ALARM")
        title.align(lv.ALIGN.TOP_MID, 0, 18)

        # Thin divider
        line = lv.line(self._normal)
        pts = [{"x": 50, "y": 0}, {"x": 190, "y": 0}]
        line.set_points(pts, 2)
        line.set_style_line_color(_c(C_BORDER), 0)
        line.set_style_line_width(1, 0)
        line.align(lv.ALIGN.TOP_MID, 0, 44)

        # Alarm time display
        self._time_lbl = lv.label(self._normal)
        self._time_lbl.set_style_text_font(get_font_big(), 0)
        self._time_lbl.set_style_text_color(_c(C_TEXT_PRI), 0)
        self._time_lbl.set_text("7:30")
        self._time_lbl.align(lv.ALIGN.CENTER, -12, -22)

        self._ampm_lbl = lv.label(self._normal)
        self._ampm_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._ampm_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        self._ampm_lbl.set_text("AM")

        # Toggle switch
        self._sw = lv.switch(self._normal)
        self._sw.set_size(56, 28)
        self._sw.align(lv.ALIGN.CENTER, 0, 36)
        self._sw.add_event_cb(self._on_switch, lv.EVENT.VALUE_CHANGED, None)

        # Status label
        self._status_lbl = lv.label(self._normal)
        self._status_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._status_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)
        self._status_lbl.set_text("ALARM OFF")
        self._status_lbl.align(lv.ALIGN.CENTER, 0, 72)

        # Hint
        hint = lv.label(self._normal)
        hint.set_style_text_font(lv.font_montserrat_12, 0)
        hint.set_style_text_color(_c(C_GREY), 0)
        hint.set_text("tap switch or use BLE to set time")
        hint.align(lv.ALIGN.BOTTOM_MID, 0, -16)

        # ── Fired view (hidden by default) ───────────────────────────────
        self._fired_view = lv.obj(scr)
        self._fired_view.set_size(240, 240)
        self._fired_view.set_pos(0, 0)
        self._fired_view.set_style_bg_color(_c(C_RED), 0)
        self._fired_view.set_style_bg_opa(lv.OPA.COVER, 0)
        self._fired_view.set_style_border_width(0, 0)
        self._fired_view.set_style_pad_all(0, 0)
        self._fired_view.add_flag(lv.obj.FLAG.HIDDEN)

        self._fire_time_lbl = lv.label(self._fired_view)
        self._fire_time_lbl.set_style_text_font(get_font_big(), 0)
        self._fire_time_lbl.set_style_text_color(_c(0xFFFFFF), 0)
        self._fire_time_lbl.set_text("7:30")
        self._fire_time_lbl.align(lv.ALIGN.CENTER, 0, -20)

        self._fire_ampm_lbl = lv.label(self._fired_view)
        self._fire_ampm_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._fire_ampm_lbl.set_style_text_color(_c(0xFFFFFF), 0)
        self._fire_ampm_lbl.set_text("AM")

        self._dismiss_lbl = lv.label(self._fired_view)
        self._dismiss_lbl.set_style_text_font(lv.font_montserrat_16, 0)
        self._dismiss_lbl.set_style_text_color(_c(0xFFFFFF), 0)
        self._dismiss_lbl.set_text("TAP TO DISMISS")
        self._dismiss_lbl.align(lv.ALIGN.CENTER, 0, 50)

        # Pulsing animation on fired view bg colour (red ↔ dark-red)
        self._anim = lv.anim_t()
        self._anim.init()
        self._anim.set_var(self._fired_view)
        self._anim.set_custom_exec_cb(self._pulse_anim_cb)
        self._anim.set_values(0, 100)
        self._anim.set_duration(500)
        self._anim.set_reverse_duration(500)
        self._anim.set_repeat_count(lv.ANIM_REPEAT_INFINITE)

    def _on_switch(self, e):
        self._enabled = self._sw.has_state(lv.STATE.CHECKED)
        self._dismissed = False
        self._refresh_display()

    @staticmethod
    def _pulse_anim_cb(obj, val):
        # val 0-100: interpolate bg between dark-red and bright-red
        r = 100 + val
        obj.set_style_bg_color(lv.color_make(r, 0, 0), 0)

    # ── Display refresh ──────────────────────────────────────────────────────

    def _refresh_display(self):
        h12 = self._hour % 12 or 12
        ampm = "AM" if self._hour < 12 else "PM"
        time_str = "{:d}:{:02d}".format(h12, self._minute)

        self._time_lbl.set_text(time_str)
        self._ampm_lbl.set_text(ampm)
        self._ampm_lbl.align_to(self._time_lbl, lv.ALIGN.OUT_RIGHT_TOP, 4, 6)

        self._fire_time_lbl.set_text(time_str)
        self._fire_ampm_lbl.set_text(ampm)
        self._fire_ampm_lbl.align_to(self._fire_time_lbl, lv.ALIGN.OUT_RIGHT_TOP, 4, 6)

        if self._enabled:
            self._sw.add_state(lv.STATE.CHECKED)
            self._status_lbl.set_text("ALARM ON")
            self._status_lbl.set_style_text_color(_c(C_GREEN), 0)
        else:
            self._sw.remove_state(lv.STATE.CHECKED)
            self._status_lbl.set_text("ALARM OFF")
            self._status_lbl.set_style_text_color(_c(C_TEXT_SEC), 0)

    # ── Gesture ──────────────────────────────────────────────────────────────

    def handle_gesture(self, gesture):
        if gesture == "single_click":
            if self._fired:
                self.dismiss()
            # switch toggling is handled by the lv.switch callback directly

    # ── Logic ────────────────────────────────────────────────────────────────

    def set_time(self, hour, minute):
        self._hour = hour
        self._minute = minute
        self._dismissed = False
        self._refresh_display()

    def set_enabled(self, en):
        self._enabled = en
        self._dismissed = False
        self._refresh_display()

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
        # GPIO5 shared with touch INT — take ownership as haptic output
        self._haptic_pin = Pin(PIN_HAPTIC, Pin.OUT)
        self._haptic_pin(1)
        # Show fired view, hide normal view
        self._normal.add_flag(lv.obj.FLAG.HIDDEN)
        self._fired_view.remove_flag(lv.obj.FLAG.HIDDEN)
        self._anim.start()

    def dismiss(self):
        self._fired = False
        self._dismissed = True
        lv.anim_delete_all()  # stop pulse animation
        if self._haptic_pin:
            self._haptic_pin(0)
            self._haptic_pin = None
        # Restore GPIO5 as input for touch IRQ reattachment by caller
        Pin(PIN_TP_INT, Pin.IN)
        self._fired_view.add_flag(lv.obj.FLAG.HIDDEN)
        self._normal.remove_flag(lv.obj.FLAG.HIDDEN)
        self._fired_view.set_style_bg_color(_c(C_RED), 0)  # reset colour

    # ── Tick (haptic, called from main loop) ─────────────────────────────────

    def tick(self):
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

    def update(self, shared):
        """Called by ScreenManager each tick when this screen is active."""
        self.tick()
