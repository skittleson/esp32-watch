# screens/manager.py — Screen state machine: routes gestures, drives tick/draw

import time
from config import SCREEN_CLOCK, SCREEN_STOPWATCH, SCREEN_ALARM

_SWIPE_DEBOUNCE_MS = 600  # ignore nav swipes within this window after a swipe


class ScreenManager:
    def __init__(self, clock, stopwatch, alarm):
        self._screens = [clock, stopwatch, alarm]
        self._active = SCREEN_CLOCK
        self._last_swipe_ms = 0

    # ── Navigation ───────────────────────────────────────────────────────────

    def handle_gesture(self, gesture):
        """Route gesture to active screen or navigate between screens."""
        if gesture in ("swipe_left", "swipe_right"):
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_swipe_ms) < _SWIPE_DEBOUNCE_MS:
                return  # too soon — ignore repeated swipe events from one drag
            self._last_swipe_ms = now
            if gesture == "swipe_left":
                self._goto((self._active + 1) % 3)
            else:
                self._goto((self._active - 1) % 3)
        else:
            self._screens[self._active].handle_gesture(gesture)

    def _goto(self, idx):
        if idx == self._active:
            return
        self._active = idx
        self._screens[idx].dirty = True  # force full repaint on first draw

    def goto(self, idx):
        """External navigation (e.g. alarm fire)."""
        self._goto(idx)

    # ── Draw tick ────────────────────────────────────────────────────────────

    def tick(self, tft, shared):
        """Call active screen's draw() — screens self-manage dirty flags."""
        self._screens[self._active].draw(tft, shared)

    # ── Accessors ────────────────────────────────────────────────────────────

    def active(self):
        return self._active

    def set_ble_indicator(self, active):
        """Proxy to clock face BLE indicator."""
        self._screens[SCREEN_CLOCK].set_ble_indicator(active)

    def set_alarm_indicator(self, active):
        """Proxy to clock face alarm bell indicator."""
        self._screens[SCREEN_CLOCK].set_alarm_indicator(active)
