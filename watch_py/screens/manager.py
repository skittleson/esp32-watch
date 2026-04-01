# screens/manager.py — LVGL screen manager
#
# Each screen has its own lv.screen object. Navigation loads the screen
# with lv.screen_load_anim() for smooth slide transitions.
# Swipe gestures from touch poll drive navigation; non-swipe gestures
# are forwarded to the active screen.

import lvgl as lv
import time
from micropython import const
from config import SCREEN_CLOCK, SCREEN_STOPWATCH, SCREEN_ALARM

_SWIPE_DEBOUNCE_MS = 600  # ignore nav swipes within this window

# Slide animation: 300ms, no delay
_ANIM_TIME = const(300)


class ScreenManager:
    def __init__(self, clock, stopwatch, alarm):
        # screen objects are created externally and passed in
        self._screens = [clock, stopwatch, alarm]
        self._active = SCREEN_CLOCK
        self._last_swipe_ms = 0

        # Load the initial screen (no animation on boot)
        lv.screen_load(clock._scr)

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

    # ── Accessors ────────────────────────────────────────────────────────────

    def active(self):
        return self._active

    def set_ble_indicator(self, active):
        self._screens[SCREEN_CLOCK].set_ble_indicator(active)

    def set_alarm_indicator(self, active):
        self._screens[SCREEN_CLOCK].set_alarm_indicator(active)
