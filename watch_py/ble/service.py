# ble/service.py — Raw bluetooth GATT server (no _thread)
#
# Architecture: BLE runs entirely via IRQ callbacks on the NimBLE internal task.
# The main loop calls ble_watch.tick() every 500ms to handle advertising timeout
# and periodic notifications. No _thread — _thread.stack_size() is broken on
# ESP32-S3 (MicroPython issue #16129) and _thread is not needed since BLE IRQs
# already run on their own FreeRTOS task.
#
# BLE starts advertising automatically on boot. Double-tap re-activates it after
# timeout.

import bluetooth
import struct
import time
from micropython import const
from config import (
    BLE_DEVICE_NAME,
    BLE_TIMEOUT_MS,
    UUID_CURRENT_TIME_SVC,
    UUID_BATTERY_SVC,
    UUID_DEVICE_INFO_SVC,
    UUID_ENV_SENSING_SVC,
    UUID_WATCH_SVC,
    UUID_CURRENT_TIME_CHR,
    UUID_LOCAL_TIME_CHR,
    UUID_BATTERY_LEVEL_CHR,
    UUID_FIRMWARE_REV_CHR,
    UUID_TEMPERATURE_CHR,
    UUID_ALARM_TIME_CHR,
    UUID_ALARM_EN_CHR,
    UUID_BRIGHTNESS_CHR,
    UUID_STEPS_CHR,
    UUID_BLE_MODE_CHR,
    UUID_WIFI_SSID_CHR,
    UUID_WIFI_PASS_CHR,
    UUID_WIFI_SYNC_CHR,
    UUID_SEDENTARY_CHR,
    UUID_NOTIFICATION_CHR,
    UUID_STEP_GOAL_CHR,
    FW_VERSION,
    DEFAULT_STEP_GOAL,
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
            (UUID_CURRENT_TIME_CHR, _FLAG_WRITE | _FLAG_NOTIFY),
            (UUID_LOCAL_TIME_CHR, _FLAG_READ | _FLAG_WRITE),
        ),
    ),
    # Battery Service (0x180F)
    (
        UUID_BATTERY_SVC,
        ((UUID_BATTERY_LEVEL_CHR, _FLAG_READ | _FLAG_NOTIFY),),
    ),
    # Device Information (0x180A)
    (
        UUID_DEVICE_INFO_SVC,
        ((UUID_FIRMWARE_REV_CHR, _FLAG_READ),),
    ),
    # Environmental Sensing Service (0x181A) — standard temperature
    (
        UUID_ENV_SENSING_SVC,
        ((UUID_TEMPERATURE_CHR, _FLAG_READ),),
    ),
    # Custom Watch Service
    (
        UUID_WATCH_SVC,
        (
            (UUID_ALARM_TIME_CHR, _FLAG_READ | _FLAG_WRITE),
            (UUID_ALARM_EN_CHR, _FLAG_READ | _FLAG_WRITE),
            (UUID_BRIGHTNESS_CHR, _FLAG_READ | _FLAG_WRITE),
            (UUID_STEPS_CHR, _FLAG_READ | _FLAG_NOTIFY),
            (UUID_BLE_MODE_CHR, _FLAG_READ | _FLAG_WRITE),
            (UUID_WIFI_SSID_CHR, _FLAG_READ | _FLAG_WRITE),  # UTF-8, max 32 chars
            (UUID_WIFI_PASS_CHR, _FLAG_WRITE),  # write-only, never read back
            (
                UUID_WIFI_SYNC_CHR,
                _FLAG_READ | _FLAG_WRITE,
            ),  # write 0x01 to trigger sync now
            (
                UUID_SEDENTARY_CHR,
                _FLAG_READ | _FLAG_NOTIFY,
            ),  # uint32 epoch of last alert
            (UUID_NOTIFICATION_CHR, _FLAG_WRITE),  # UTF-8 message → watch toast
            (UUID_STEP_GOAL_CHR, _FLAG_READ | _FLAG_WRITE),  # uint16 daily step goal
        ),
    ),
)

# Handle indices (populated after register_services)
_H_CURRENT_TIME = const(0)
_H_LOCAL_TIME = const(1)
_H_BAT_LEVEL = const(2)
_H_FW_REV = const(3)
_H_ESS_TEMP = const(4)  # Environmental Sensing — Temperature (0x2A6E)
_H_ALARM_TIME = const(5)
_H_ALARM_EN = const(6)
_H_BRIGHTNESS = const(7)
_H_STEPS = const(8)
_H_BLE_MODE = const(9)
_H_WIFI_SSID = const(10)
_H_WIFI_PASS = const(11)
_H_WIFI_SYNC = const(12)
_H_SEDENTARY = const(13)  # uint32 epoch timestamp of last sedentary alert
_H_NOTIFICATION = const(14)  # write-only UTF-8 message → watch toast
_H_STEP_GOAL = const(15)  # uint16 daily step goal (default 7000)


class BLEWatch:
    def __init__(self):
        self._ble = bluetooth.BLE()
        self._handles = []
        self._conn = None
        self._active = False
        self._timeout_start = 0
        self._shared = None
        self._display = None
        self._alarm = None
        self._mgr = None
        self._settings = None
        self._battery = None
        # tick() timing state
        self._last_bat_notify = 0
        self._last_steps_notify = 0

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _register(self):
        self._ble.active(True)
        self._ble.irq(self._irq)
        (
            (h_ct, h_lt),
            (h_bat,),
            (h_fw,),
            (h_ess_temp,),
            (
                h_at,
                h_ae,
                h_br,
                h_st,
                h_bm,
                h_wssid,
                h_wpass,
                h_wsync,
                h_sed,
                h_notif,
                h_sgoal,
            ),
        ) = self._ble.gatts_register_services(_SERVICES)
        self._handles = [
            h_ct,
            h_lt,
            h_bat,
            h_fw,
            h_ess_temp,
            h_at,
            h_ae,
            h_br,
            h_st,
            h_bm,
            h_wssid,
            h_wpass,
            h_wsync,
            h_sed,
            h_notif,
            h_sgoal,
        ]
        # Seed static characteristic values
        self._ble.gatts_write(h_fw, FW_VERSION.encode())
        self._ble.gatts_write(h_lt, bytes([0, 0]))  # UTC offset, DST
        self._ble.gatts_write(h_bat, bytes([100]))
        self._ble.gatts_write(h_st, struct.pack("<I", 0))
        self._ble.gatts_write(h_ess_temp, struct.pack("<h", 0))  # 0.00°C initial
        self._ble.gatts_write(h_wssid, b"")  # empty until set
        self._ble.gatts_write(h_wsync, bytes([0x00]))
        self._ble.gatts_write(h_sed, struct.pack("<I", 0))  # 0 = never alerted
        self._ble.gatts_write(h_notif, b"")  # empty until written
        goal = (
            self._shared.get("step_goal", DEFAULT_STEP_GOAL)
            if self._shared
            else DEFAULT_STEP_GOAL
        )
        self._ble.gatts_write(h_sgoal, struct.pack("<H", goal))

    def _advertise(self):
        name = BLE_DEVICE_NAME.encode()
        payload = bytes([2, 0x01, 0x06]) + bytes([1 + len(name), 0x09]) + name
        self._ble.gap_advertise(100_000, adv_data=payload)
        self._active = True
        self._timeout_start = time.ticks_ms()
        print("[BLE] Advertising as", BLE_DEVICE_NAME)

    def _stop_advertise(self):
        self._ble.gap_advertise(None)
        self._active = False

    # ── IRQ handler ───────────────────────────────────────────────────────────

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._conn = conn_handle
            self._ble.gap_advertise(None)
            print("[BLE] Connected:", conn_handle)
            if self._mgr:
                self._mgr.set_ble_indicator(True)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn = None
            print("[BLE] Disconnected")
            if self._mgr:
                self._mgr.set_ble_indicator(False)
            # Restart advertising if still in active window or always-on
            if self._active or (self._shared and self._shared.get("ble_always")):
                self._advertise()

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            self._handle_write(attr_handle)

        elif event == _IRQ_GATTS_READ_REQUEST:
            conn_handle, attr_handle = data
            self._handle_read(attr_handle)

    # ── Write handler ─────────────────────────────────────────────────────────

    def _handle_write(self, h):
        handles = self._handles
        val = self._ble.gatts_read(h)

        if h == handles[_H_CURRENT_TIME]:
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

        elif h == handles[_H_WIFI_SSID]:
            ssid = val.decode("utf-8", "ignore").strip("\x00")
            if self._settings is not None:
                self._settings["wifi_ssid"] = ssid
            print("[BLE] WiFi SSID set:", ssid)

        elif h == handles[_H_WIFI_PASS]:
            pw = val.decode("utf-8", "ignore").strip("\x00")
            if self._settings is not None:
                self._settings["wifi_pass"] = pw
            print("[BLE] WiFi password updated ({} chars)".format(len(pw)))

        elif h == handles[_H_WIFI_SYNC]:
            # Write 0x01 to trigger an immediate NTP sync
            if len(val) >= 1 and val[0] == 0x01 and self._shared is not None:
                self._shared["wifi_sync_now"] = True
                print("[BLE] WiFi NTP sync requested")

        elif h == handles[_H_NOTIFICATION]:
            message = val.decode("utf-8", "ignore").strip("\x00")
            if message and self._mgr:
                self._mgr.show_notification(message)
                print("[BLE] Notification:", message)
            elif self._mgr:
                # Empty write clears/dismisses any showing notification
                self._mgr.hide_notification()

        elif h == handles[_H_STEP_GOAL]:
            if len(val) >= 2:
                goal = struct.unpack("<H", val[:2])[0]
                if 1 <= goal <= 65535:
                    if self._shared is not None:
                        self._shared["step_goal"] = goal
                    if self._settings is not None:
                        self._settings["step_goal"] = goal
                    print("[BLE] Step goal:", goal)

        elif h == handles[_H_LOCAL_TIME]:
            pass  # Accept but ignore

    # ── Read handler ──────────────────────────────────────────────────────────

    def _handle_read(self, h):
        handles = self._handles
        if self._shared is None:
            return
        if h == handles[_H_ESS_TEMP]:
            # sint16, units = 0.01°C per GATT spec (0x2A6E)
            temp_c = self._shared.get("temp", 0.0)
            temp_int16 = max(-32768, min(32767, int(round(temp_c * 100))))
            self._ble.gatts_write(h, struct.pack("<h", temp_int16))
        elif h == handles[_H_BAT_LEVEL]:
            self._ble.gatts_write(h, bytes([self._shared.get("bat_pct", 100)]))
        elif h == handles[_H_STEPS]:
            self._ble.gatts_write(h, struct.pack("<I", self._shared.get("steps", 0)))
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
        elif h == handles[_H_WIFI_SSID]:
            ssid = (self._settings or {}).get("wifi_ssid", "")
            self._ble.gatts_write(h, ssid.encode())
        elif h == handles[_H_SEDENTARY]:
            epoch = self._shared.get("sedentary_epoch", 0) if self._shared else 0
            self._ble.gatts_write(h, struct.pack("<I", epoch))
        elif h == handles[_H_WIFI_SYNC]:
            # Return 0x01 if WiFi is configured, 0x00 if not
            has_wifi = bool((self._settings or {}).get("wifi_ssid", ""))
            self._ble.gatts_write(h, bytes([0x01 if has_wifi else 0x00]))
        elif h == handles[_H_STEP_GOAL]:
            goal = (
                self._shared.get("step_goal", DEFAULT_STEP_GOAL)
                if self._shared
                else DEFAULT_STEP_GOAL
            )
            self._ble.gatts_write(h, struct.pack("<H", goal))

    # ── Notify helpers ────────────────────────────────────────────────────────

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

    def notify_sedentary(self, epoch):
        """Notify phone of sedentary alert with epoch timestamp."""
        h = self._handles[_H_SEDENTARY]
        self._ble.gatts_write(h, struct.pack("<I", epoch))
        if self._conn is not None:
            self._ble.gatts_notify(self._conn, h)

    # ── tick() — call from main loop every ~500ms ─────────────────────────────

    def tick(self, shared):
        """Handle advertising timeout and periodic notifications.
        Replaces the old _thread_fn. Call this from the main loop every 500ms.
        """
        if not self._active and self._conn is None:
            return

        now = time.ticks_ms()

        # Advertising timeout: stop after BLE_TIMEOUT_MS if not connected,
        # not in always-on mode, and not plugged in (charging)
        charging = self._battery.is_charging() if self._battery else False
        if (
            self._conn is None
            and not shared.get("ble_always", False)
            and not charging
            and time.ticks_diff(now, self._timeout_start) >= BLE_TIMEOUT_MS
        ):
            self._stop_advertise()
            print("[BLE] Timed out, stopping advertising")
            return

        # Periodic notifications when connected
        if self._conn is not None:
            if time.ticks_diff(now, self._last_bat_notify) >= 60_000:
                self.notify_battery(shared.get("bat_pct", 100))
                self._last_bat_notify = now

            if time.ticks_diff(now, self._last_steps_notify) >= 10_000:
                self.notify_steps(shared.get("steps", 0))
                self._last_steps_notify = now

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, shared, display, alarm, mgr, settings, battery=None):
        """Register GATT services and begin advertising immediately on boot."""
        self._shared = shared
        self._display = display
        self._alarm = alarm
        self._mgr = mgr
        self._settings = settings
        self._battery = battery  # used to detect USB charging / plugged in
        self._register()
        self._advertise()  # advertise immediately on boot

    def activate(self):
        """Re-start advertising (double-tap or after timeout)."""
        if self._conn is not None:
            return  # already connected, nothing to do
        self._advertise()

    def deactivate(self):
        self._stop_advertise()
        if self._mgr:
            self._mgr.set_ble_indicator(False)

    def is_active(self):
        return self._active or (self._conn is not None)


# Module-level singleton
ble_watch = BLEWatch()
