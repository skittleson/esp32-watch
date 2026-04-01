# screens/manager.py — LVGL screen manager
#
# Each screen has its own lv.screen object. Navigation loads the screen
# with lv.screen_load_anim() for smooth slide transitions.
# Swipe gestures from touch poll drive navigation; non-swipe gestures
# are forwarded to the active screen.

import lvgl as lv
import time
from micropython import const
from config import SCREEN_CLOCK, SCREEN_STOPWATCH, SCREEN_ALARM, C_ORANGE, C_BG

_SWIPE_DEBOUNCE_MS = 600  # ignore nav swipes within this window

# Slide animation: 300ms, no delay
_ANIM_TIME = const(300)

# Toast duration: how long the sedentary banner stays visible
_TOAST_DURATION_MS = const(5000)


class ScreenManager:
    def __init__(self, clock, stopwatch, alarm):
        # screen objects are created externally and passed in
        self._screens = [clock, stopwatch, alarm]
        self._active = SCREEN_CLOCK
        self._last_swipe_ms = 0

        # Load the initial screen (no animation on boot)
        lv.screen_load(clock._scr)

        # ── Sedentary toast (always-on-top layer) ─────────────────────────
        self._toast = None
        self._toast_lbl = None
        self._toast_shown_ms = 0
        self._build_toast()

    # ── Toast ────────────────────────────────────────────────────────────────

    def _build_toast(self):
        """Create sedentary alert banner parented to lv.layer_top()."""
        top = lv.layer_top()
        self._toast = lv.obj(top)
        self._toast.set_size(200, 44)
        self._toast.align(lv.ALIGN.TOP_MID, 0, 16)
        self._toast.set_style_bg_color(lv.color_hex(C_ORANGE), 0)
        self._toast.set_style_bg_opa(lv.OPA.COVER, 0)
        self._toast.set_style_radius(22, 0)
        self._toast.set_style_border_width(0, 0)
        self._toast.set_style_shadow_width(0, 0)
        self._toast.set_style_pad_all(0, 0)
        self._toast.add_flag(lv.obj.FLAG.HIDDEN)

        self._toast_lbl = lv.label(self._toast)
        self._toast_lbl.set_style_text_font(lv.font_montserrat_14, 0)
        self._toast_lbl.set_style_text_color(lv.color_hex(0x000000), 0)
        self._toast_lbl.set_text("Move around!")
        self._toast_lbl.center()

    def show_sedentary_toast(self):
        """Show the sedentary alert banner for _TOAST_DURATION_MS."""
        self._toast.remove_flag(lv.obj.FLAG.HIDDEN)
        self._toast_shown_ms = time.ticks_ms()

    def hide_sedentary_toast(self):
        self._toast.add_flag(lv.obj.FLAG.HIDDEN)

    # ── Navigation ───────────────────────────────────────────────────────────

    def handle_gesture(self, gesture):
        if gesture in ("swipe_left", "swipe_right"):
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_swipe_ms) < _SWIPE_DEBOUNCE_MS:
                return
            self._last_swipe_ms = now
            if gesture == "swipe_left":
                self._goto(
                    (self._active + 1) % 3,
                    lv.SCREEN_LOAD_ANIM.MOVE_LEFT,
                )
            else:
                self._goto(
                    (self._active - 1) % 3,
                    lv.SCREEN_LOAD_ANIM.MOVE_RIGHT,
                )
        else:
            self._screens[self._active].handle_gesture(gesture)

    def _goto(self, idx, anim=lv.SCREEN_LOAD_ANIM.NONE):
        if idx == self._active:
            return
        self._active = idx
        lv.screen_load_anim(
            self._screens[idx]._scr,
            anim,
            _ANIM_TIME,
            0,  # delay ms
            False,  # do not auto-delete old screen
        )

    def goto(self, idx):
        """External navigation (e.g. alarm fire) — no animation."""
        self._goto(idx, lv.SCREEN_LOAD_ANIM.FADE_IN)

    # ── Tick ─────────────────────────────────────────────────────────────────

    def tick(self, shared):
        """Drive the active screen's update() method."""
        self._screens[self._active].update(shared)
        # Auto-hide toast after duration
        if (
            self._toast_shown_ms
            and time.ticks_diff(time.ticks_ms(), self._toast_shown_ms)
            >= _TOAST_DURATION_MS
        ):
            self.hide_sedentary_toast()
            self._toast_shown_ms = 0

    # ── Accessors ────────────────────────────────────────────────────────────

    def active(self):
        return self._active

    def set_ble_indicator(self, active):
        self._screens[SCREEN_CLOCK].set_ble_indicator(active)

    def set_alarm_indicator(self, active):
        self._screens[SCREEN_CLOCK].set_alarm_indicator(active)
