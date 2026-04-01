# hal/wifi.py — WiFi connect + NTP time sync
#
# Design:
#   - Credentials (ssid, password) stored in settings.json
#   - sync() connects, runs ntptime.settime(), disconnects
#   - Keeps WiFi off when idle to save power
#   - Called from main.py on: boot, USB charge event, every 8 hours

import network
import ntptime
import time
from machine import RTC
from micropython import const

# NTP retry / timeout
_NTP_RETRIES = const(3)
_NTP_TIMEOUT = const(20)  # seconds to wait for connect
_CONNECT_POLL = const(250)  # ms between connection polls

# LA (PDT) is UTC-7. Adjust here if needed; the RTC stores local time.
# 0 = store UTC (recommended — convert in display layer)
UTC_OFFSET_HOURS = -7


class WiFiSync:
    def __init__(self):
        self._sta = network.WLAN(network.STA_IF)

    def _connect(self, ssid, password, timeout_s=_NTP_TIMEOUT):
        """Bring up STA, connect, wait up to timeout_s seconds."""
        self._sta.active(True)
        if self._sta.isconnected():
            return True
        self._sta.connect(ssid, password)
        deadline = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._sta.isconnected():
                return True
            time.sleep_ms(_CONNECT_POLL)
        return False

    def _disconnect(self):
        try:
            self._sta.disconnect()
            self._sta.active(False)
        except Exception:
            pass

    def sync(self, settings):
        """Connect to WiFi, sync NTP, update RTC, disconnect.

        Args:
            settings: dict — must contain 'wifi_ssid' and 'wifi_pass'

        Returns:
            True on success, False on any failure.
        """
        ssid = settings.get("wifi_ssid", "")
        password = settings.get("wifi_pass", "")

        if not ssid:
            print("[WIFI] No SSID configured, skipping NTP sync")
            return False

        print("[WIFI] Connecting to", ssid)
        try:
            if not self._connect(ssid, password):
                print("[WIFI] Connect timeout")
                self._disconnect()
                return False

            print("[WIFI] Connected:", self._sta.ifconfig()[0])

            # NTP sync with retries
            ntptime.host = "pool.ntp.org"
            for attempt in range(_NTP_RETRIES):
                try:
                    ntptime.settime()  # sets RTC to UTC
                    # Apply UTC offset to store local time in RTC
                    if UTC_OFFSET_HOURS != 0:
                        t = time.time() + UTC_OFFSET_HOURS * 3600
                        tm = time.localtime(t)
                        RTC().datetime(
                            (
                                tm[0],
                                tm[1],
                                tm[2],  # year, month, day
                                tm[6],  # weekday (0=Mon)
                                tm[3],
                                tm[4],
                                tm[5],  # hour, min, sec
                                0,  # subseconds
                            )
                        )
                    print(
                        "[WIFI] NTP sync OK — UTC offset {}h".format(UTC_OFFSET_HOURS)
                    )
                    self._disconnect()
                    return True
                except Exception as e:
                    print(
                        "[WIFI] NTP attempt {}/{} failed: {}".format(
                            attempt + 1, _NTP_RETRIES, e
                        )
                    )
                    time.sleep_ms(1000)

            print("[WIFI] NTP failed after {} attempts".format(_NTP_RETRIES))
            self._disconnect()
            return False

        except Exception as e:
            print("[WIFI] Error:", e)
            self._disconnect()
            return False

    def has_credentials(self, settings):
        return bool(settings.get("wifi_ssid", ""))

    def is_connected(self):
        return self._sta.isconnected()


# Module-level singleton
wifi_sync = WiFiSync()
