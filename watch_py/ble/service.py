# ble/service.py — Raw bluetooth GATT server (no asyncio, runs in _thread)
#
# Architecture: BLE runs entirely via IRQ callbacks on a background _thread.
# The main display loop never touches bluetooth.
# Shared state is passed via a thread-safe dict (GIL ensures atomic dict ops).

import bluetooth
import struct
import time
import _thread
from micropython import const
from config import (
    BLE_DEVICE_NAME,
    BLE_TIMEOUT_MS,
    UUID_CURRENT_TIME_SVC,
    UUID_BATTERY_SVC,
    UUID_DEVICE_INFO_SVC,
    UUID_WATCH_SVC,
    UUID_CURRENT_TIME_CHR,
    UUID_LOCAL_TIME_CHR,
    UUID_BATTERY_LEVEL_CHR,
    UUID_FIRMWARE_REV_CHR,
    UUID_ALARM_TIME_CHR,
    UUID_ALARM_EN_CHR,
    UUID_BRIGHTNESS_CHR,
    UUID_STEPS_CHR,
    UUID_BLE_MODE_CHR,
    FW_VERSION,
)

# ── IRQ event constants ────────────────────────────────────────────────────────
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_GATTS_READ_REQUEST = const(4)

# ── GATT property flags ───────────────────────────────────────────────────────
_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESP = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

# ── Service / Characteristic definitions ─────────────────────────────────────
_SERVICES = (
    # Current Time Service (0x1805)
    (
        UUID_CURRENT_TIME_SVC,
        (
            (
                UUID_CURRENT_TIME_CHR,
                _FLAG_WRITE | _FLAG_NOTIFY,
            ),
            (
                UUID_LOCAL_TIME_CHR,
                _FLAG_READ | _FLAG_WRITE,
            ),
        ),
    ),
    # Battery Service (0x180F)
    (
        UUID_BATTERY_SVC,
        (
            (
                UUID_BATTERY_LEVEL_CHR,
                _FLAG_READ | _FLAG_NOTIFY,
            ),
        ),
    ),
    # Device Information (0x180A)
    (
        UUID_DEVICE_INFO_SVC,
        (
            (
                UUID_FIRMWARE_REV_CHR,
                _FLAG_READ,
            ),
        ),
    ),
    # Custom Watch Service
    (
        UUID_WATCH_SVC,
        (
            (
                UUID_ALARM_TIME_CHR,
                _FLAG_READ | _FLAG_WRITE,
            ),
            (
                UUID_ALARM_EN_CHR,
                _FLAG_READ | _FLAG_WRITE,
            ),
            (
                UUID_BRIGHTNESS_CHR,
                _FLAG_READ | _FLAG_WRITE,
            ),
            (
                UUID_STEPS_CHR,
                _FLAG_READ | _FLAG_NOTIFY,
            ),
            (
                UUID_BLE_MODE_CHR,
                _FLAG_READ | _FLAG_WRITE,
            ),
        ),
    ),
)

# Handle indices (populated after register_services)
# Current Time Service
_H_CURRENT_TIME = 0
_H_LOCAL_TIME = 1
# Battery
_H_BAT_LEVEL = 2
# Device Info
_H_FW_REV = 3
# Watch service
_H_ALARM_TIME = 4
_H_ALARM_EN = 5
_H_BRIGHTNESS = 6
_H_STEPS = 7
_H_BLE_MODE = 8


class BLEWatch:
    def __init__(self):
        self._ble = bluetooth.BLE()
        self._handles = []
        self._conn = None
        self._active = False
        self._timeout_start = 0
        self._shared = None  # set by start()
        self._display = None
        self._alarm = None
        self._mgr = None
        self._settings = None

    # ── Setup ──────────────────────────────────────────────────────────────

    def _register(self):
        self._ble.active(True)
        self._ble.irq(self._irq)
        (
            (h_ct, h_lt),
            (h_bat,),
            (h_fw,),
            (h_at, h_ae, h_br, h_st, h_bm),
        ) = self._ble.gatts_register_services(_SERVICES)
        self._handles = [h_ct, h_lt, h_bat, h_fw, h_at, h_ae, h_br, h_st, h_bm]
        # Seed static values
        self._ble.gatts_write(h_fw, FW_VERSION.encode())
        self._ble.gatts_write(h_lt, bytes([0, 0]))  # UTC offset 0, DST 0
        self._ble.gatts_write(h_bat, bytes([100]))
        self._ble.gatts_write(h_st, struct.pack("<I", 0))

    def _advertise(self, timeout_ms=None):
        name = BLE_DEVICE_NAME.encode()
        # AD: Flags (0x01), Complete Local Name (0x09)
        payload = bytes([2, 0x01, 0x06]) + bytes([1 + len(name), 0x09]) + name
        self._ble.gap_advertise(100_000, adv_data=payload)  # 100ms interval
        self._active = True
        self._timeout_start = time.ticks_ms()
        print("[BLE] Advertising as", BLE_DEVICE_NAME)

    def _stop_advertise(self):
        self._ble.gap_advertise(None)
        self._active = False

    # ── IRQ handler ────────────────────────────────────────────────────────

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._conn = conn_handle
            self._ble.gap_advertise(None)  # stop advertising while connected
            print("[BLE] Connected:", conn_handle)
            if self._mgr:
                self._mgr.set_ble_indicator(True)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn = None
            print("[BLE] Disconnected")
            # Restart advertising if still active
            if self._active and self._shared:
                self._advertise()

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            self._handle_write(attr_handle)

        elif event == _IRQ_GATTS_READ_REQUEST:
            conn_handle, attr_handle = data
            self._handle_read(attr_handle)

    # ── Write handler ─────────────────────────────────────────────────────

    def _handle_write(self, h):
        handles = self._handles
        val = self._ble.gatts_read(h)

        if h == handles[_H_CURRENT_TIME]:
            # 10-byte Current Time: year(LE u16), month, day, hour, min, sec, ...
            if len(val) >= 7:
                yr = struct.unpack_from("<H", val, 0)[0]
                mo, dy, hr, mn, sc = val[2], val[3], val[4], val[5], val[6]
                from machine import RTC

                RTC().datetime((yr, mo, dy, 0, hr, mn, sc, 0))
                print(
                    "[BLE] Time set: {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                        yr, mo, dy, hr, mn, sc
                    )
                )

        elif h == handles[_H_ALARM_TIME]:
            if len(val) >= 2 and self._alarm:
                h2, m = val[0], val[1]
                if h2 <= 23 and m <= 59:
                    self._alarm.set_time(h2, m)
                    if self._mgr:
                        self._mgr.set_alarm_indicator(self._alarm.get_enabled())
                    if self._settings is not None:
                        self._settings.update(self._alarm.to_settings())
                    print("[BLE] Alarm:", h2, m)

        elif h == handles[_H_ALARM_EN]:
            if len(val) >= 1 and self._alarm:
                en = val[0] != 0
                self._alarm.set_enabled(en)
                if self._mgr:
                    self._mgr.set_alarm_indicator(en)
                if self._settings is not None:
                    self._settings.update(self._alarm.to_settings())
                print("[BLE] Alarm enabled:", en)

        elif h == handles[_H_BRIGHTNESS]:
            if len(val) >= 1 and self._display:
                self._display.set_brightness_from_ble(val[0])
                if self._settings is not None:
                    self._settings["brightness"] = val[0]
                print("[BLE] Brightness:", val[0])

        elif h == handles[_H_BLE_MODE]:
            if len(val) >= 1 and self._shared is not None:
                always = val[0] != 0
                self._shared["ble_always"] = always
                if self._settings is not None:
                    self._settings["ble_always"] = always
                print("[BLE] Always-on:", always)

        elif h == handles[_H_LOCAL_TIME]:
            pass  # Accept but ignore for now

    # ── Read handler ──────────────────────────────────────────────────────

    def _handle_read(self, h):
        handles = self._handles
        if self._shared is None:
            return

        if h == handles[_H_BAT_LEVEL]:
            self._ble.gatts_write(h, bytes([self._shared.get("bat_pct", 100)]))
        elif h == handles[_H_STEPS]:
            s = self._shared.get("steps", 0)
            self._ble.gatts_write(h, struct.pack("<I", s))
        elif h == handles[_H_ALARM_TIME] and self._alarm:
            self._ble.gatts_write(
                h, bytes([self._alarm.get_hour(), self._alarm.get_minute()])
            )
        elif h == handles[_H_ALARM_EN] and self._alarm:
            self._ble.gatts_write(
                h, bytes([0x01 if self._alarm.get_enabled() else 0x00])
            )
        elif h == handles[_H_BRIGHTNESS] and self._display:
            self._ble.gatts_write(h, bytes([self._display.get_brightness_duty() // 4]))
        elif h == handles[_H_BLE_MODE]:
            always = self._shared.get("ble_always", False)
            self._ble.gatts_write(h, bytes([0x01 if always else 0x00]))

    # ── Notify helpers ────────────────────────────────────────────────────

    def notify_battery(self, pct):
        if self._conn is None:
            return
        h = self._handles[_H_BAT_LEVEL]
        self._ble.gatts_write(h, bytes([pct]))
        self._ble.gatts_notify(self._conn, h)

    def notify_steps(self, steps):
        if self._conn is None:
            return
        h = self._handles[_H_STEPS]
        self._ble.gatts_write(h, struct.pack("<I", steps))
        self._ble.gatts_notify(self._conn, h)

    # ── Background thread ─────────────────────────────────────────────────

    def _thread_fn(self):
        """Runs on Core 0. Manages advertising timeout + periodic notifications."""
        last_bat = time.ticks_ms()
        last_steps = time.ticks_ms()

        while True:
            time.sleep_ms(500)

            if not self._active:
                continue

            now = time.ticks_ms()

            # Advertising timeout (only when not connected and not always-on)
            if (
                self._conn is None
                and not self._shared.get("ble_always", False)
                and time.ticks_diff(now, self._timeout_start) >= BLE_TIMEOUT_MS
            ):
                self._stop_advertise()
                if self._mgr:
                    self._mgr.set_ble_indicator(False)
                print("[BLE] Timed out, stopping advertising")
                continue

            # Battery notify every 60 s
            if self._conn is not None and time.ticks_diff(now, last_bat) >= 60_000:
                self.notify_battery(self._shared.get("bat_pct", 100))
                last_bat = now

            # Steps notify every 10 s
            if self._conn is not None and time.ticks_diff(now, last_steps) >= 10_000:
                self.notify_steps(self._shared.get("steps", 0))
                last_steps = now

    # ── Public API ────────────────────────────────────────────────────────

    def start(self, shared, display, alarm, mgr, settings):
        self._shared = shared
        self._display = display
        self._alarm = alarm
        self._mgr = mgr
        self._settings = settings
        self._register()
        # Start background thread for timeout/notify management
        _thread.start_new_thread(self._thread_fn, ())

    def activate(self):
        if self._active:
            return
        self._advertise()

    def deactivate(self):
        self._stop_advertise()
        if self._mgr:
            self._mgr.set_ble_indicator(False)

    def is_active(self):
        return self._active or (self._conn is not None)


# Module-level singleton
ble_watch = BLEWatch()
