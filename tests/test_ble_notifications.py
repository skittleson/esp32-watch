#!/usr/bin/env python3
"""BLE integration / smoke test for ESP32Watch.

Connects to the watch over BLE and exercises every readable characteristic
plus the push-notification write characteristic (0xAA0A).

Requirements:
    pip install -r tests/requirements-test.txt   # bleak

Usage:
    python tests/test_ble_notifications.py                # fast run (~5s)
    python tests/test_ble_notifications.py --subscribe     # include notify waits (~70s)
    python tests/test_ble_notifications.py -n MyWatch -t 15 -v
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import time
from dataclasses import dataclass, field

from bleak import BleakClient, BleakScanner

# ── UUIDs ─────────────────────────────────────────────────────────────────────
# Standard services / characteristics
UUID_BATTERY_SVC = "0000180f-0000-1000-8000-00805f9b34fb"
UUID_BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
UUID_TEMPERATURE = "00002a6e-0000-1000-8000-00805f9b34fb"
UUID_CURRENT_TIME = "00002a2b-0000-1000-8000-00805f9b34fb"

# Custom Watch Service
UUID_WATCH_SVC = "0000aa00-0000-1000-8000-00805f9b34fb"
UUID_ALARM_TIME = "0000aa01-0000-1000-8000-00805f9b34fb"
UUID_ALARM_EN = "0000aa02-0000-1000-8000-00805f9b34fb"
UUID_BRIGHTNESS = "0000aa03-0000-1000-8000-00805f9b34fb"
UUID_STEPS = "0000aa04-0000-1000-8000-00805f9b34fb"
UUID_BLE_MODE = "0000aa05-0000-1000-8000-00805f9b34fb"
UUID_WIFI_SSID = "0000aa06-0000-1000-8000-00805f9b34fb"
UUID_WIFI_SYNC = "0000aa08-0000-1000-8000-00805f9b34fb"
UUID_SEDENTARY = "0000aa09-0000-1000-8000-00805f9b34fb"
UUID_NOTIFICATION = "0000aa0a-0000-1000-8000-00805f9b34fb"


# ── Helpers ───────────────────────────────────────────────────────────────────


@dataclass
class Results:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)

    def ok(self, name: str, info: str = "") -> None:
        self.passed += 1
        msg = f"  PASS  {name}"
        if info:
            msg += f"  ({info})"
        print(msg)
        self.details.append(msg)

    def fail(self, name: str, reason: str) -> None:
        self.failed += 1
        msg = f"  FAIL  {name}  -- {reason}"
        print(msg)
        self.details.append(msg)

    def skip(self, name: str, reason: str = "") -> None:
        self.skipped += 1
        msg = f"  SKIP  {name}"
        if reason:
            msg += f"  -- {reason}"
        print(msg)
        self.details.append(msg)

    def summary(self) -> str:
        total = self.passed + self.failed + self.skipped
        return (
            f"\n{'=' * 60}\n"
            f"  {total} tests: {self.passed} passed, "
            f"{self.failed} failed, {self.skipped} skipped\n"
            f"{'=' * 60}"
        )


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


# ── Test cases ────────────────────────────────────────────────────────────────


async def test_service_discovery(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Verify the Watch Custom Service and key characteristics are present."""
    svcs = client.services
    watch_svc = svcs.get_service(UUID_WATCH_SVC)
    if watch_svc is None:
        res.fail("service_discovery", "Watch Custom Service (0xAA00) not found")
        return

    expected_chars = {
        "alarm_time": UUID_ALARM_TIME,
        "alarm_en": UUID_ALARM_EN,
        "brightness": UUID_BRIGHTNESS,
        "steps": UUID_STEPS,
        "ble_mode": UUID_BLE_MODE,
        "wifi_ssid": UUID_WIFI_SSID,
        "wifi_sync": UUID_WIFI_SYNC,
        "sedentary": UUID_SEDENTARY,
        "notification": UUID_NOTIFICATION,
    }
    found_uuids = {str(c.uuid) for c in watch_svc.characteristics}
    missing = [name for name, uuid in expected_chars.items() if uuid not in found_uuids]
    if missing:
        res.fail("service_discovery", f"Missing characteristics: {', '.join(missing)}")
    else:
        res.ok("service_discovery", f"{len(expected_chars)} custom chars found")

    if verbose:
        for c in watch_svc.characteristics:
            print(f"    {c.uuid}  props={c.properties}")


async def test_read_battery(client: BleakClient, res: Results, verbose: bool) -> None:
    """Read battery level, expect 0-100."""
    try:
        data = await client.read_gatt_char(UUID_BATTERY_LEVEL)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 1:
            res.fail("read_battery", "empty response")
            return
        pct = data[0]
        if 0 <= pct <= 100:
            res.ok("read_battery", f"{pct}%")
        else:
            res.fail("read_battery", f"value {pct} out of 0-100 range")
    except Exception as e:
        res.fail("read_battery", str(e))


async def test_read_temperature(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Read temperature (sint16, 0.01 deg C resolution)."""
    try:
        data = await client.read_gatt_char(UUID_TEMPERATURE)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 2:
            res.fail("read_temperature", f"expected 2 bytes, got {len(data)}")
            return
        raw = struct.unpack("<h", data[:2])[0]
        temp_c = raw / 100.0
        if -40.0 <= temp_c <= 85.0:
            res.ok("read_temperature", f"{temp_c:.2f} C")
        else:
            res.fail(
                "read_temperature", f"{temp_c:.2f} C outside plausible range (-40..85)"
            )
    except Exception as e:
        res.fail("read_temperature", str(e))


async def test_read_steps(client: BleakClient, res: Results, verbose: bool) -> None:
    """Read step count (uint32 LE)."""
    try:
        data = await client.read_gatt_char(UUID_STEPS)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 4:
            res.fail("read_steps", f"expected 4 bytes, got {len(data)}")
            return
        steps = struct.unpack("<I", data[:4])[0]
        if steps <= 200_000:
            res.ok("read_steps", f"{steps} steps")
        else:
            res.fail("read_steps", f"{steps} seems unreasonably high")
    except Exception as e:
        res.fail("read_steps", str(e))


async def test_read_alarm_time(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Read alarm time [hour, minute]."""
    try:
        data = await client.read_gatt_char(UUID_ALARM_TIME)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 2:
            res.fail("read_alarm_time", f"expected 2 bytes, got {len(data)}")
            return
        hour, minute = data[0], data[1]
        if hour <= 23 and minute <= 59:
            res.ok("read_alarm_time", f"{hour:02d}:{minute:02d}")
        else:
            res.fail("read_alarm_time", f"invalid time {hour}:{minute}")
    except Exception as e:
        res.fail("read_alarm_time", str(e))


async def test_read_alarm_enable(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Read alarm enable (0 or 1)."""
    try:
        data = await client.read_gatt_char(UUID_ALARM_EN)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 1:
            res.fail("read_alarm_enable", "empty response")
            return
        val = data[0]
        if val in (0, 1):
            res.ok("read_alarm_enable", "enabled" if val else "disabled")
        else:
            res.fail("read_alarm_enable", f"expected 0 or 1, got {val}")
    except Exception as e:
        res.fail("read_alarm_enable", str(e))


async def test_read_brightness(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Read display brightness (0-255, firmware returns PWM duty // 4)."""
    try:
        data = await client.read_gatt_char(UUID_BRIGHTNESS)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 1:
            res.fail("read_brightness", "empty response")
            return
        val = data[0]
        if 0 <= val <= 255:
            res.ok("read_brightness", f"{val}/255")
        else:
            res.fail("read_brightness", f"value {val} out of 0-255 range")
    except Exception as e:
        res.fail("read_brightness", str(e))


async def test_read_ble_mode(client: BleakClient, res: Results, verbose: bool) -> None:
    """Read BLE mode (0=auto-off, 1=always-on)."""
    try:
        data = await client.read_gatt_char(UUID_BLE_MODE)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 1:
            res.fail("read_ble_mode", "empty response")
            return
        val = data[0]
        if val in (0, 1):
            res.ok("read_ble_mode", "always-on" if val else "auto-off")
        else:
            res.fail("read_ble_mode", f"expected 0 or 1, got {val}")
    except Exception as e:
        res.fail("read_ble_mode", str(e))


async def test_read_wifi_ssid(client: BleakClient, res: Results, verbose: bool) -> None:
    """Read WiFi SSID (UTF-8 string, may be empty)."""
    try:
        data = await client.read_gatt_char(UUID_WIFI_SSID)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        ssid = data.decode("utf-8", "ignore")
        res.ok("read_wifi_ssid", f"'{ssid}'" if ssid else "(empty)")
    except Exception as e:
        res.fail("read_wifi_ssid", str(e))


async def test_read_sedentary(client: BleakClient, res: Results, verbose: bool) -> None:
    """Read sedentary epoch (uint32 LE, 0 = never)."""
    try:
        data = await client.read_gatt_char(UUID_SEDENTARY)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 4:
            res.fail("read_sedentary", f"expected 4 bytes, got {len(data)}")
            return
        epoch = struct.unpack("<I", data[:4])[0]
        if epoch == 0:
            res.ok("read_sedentary", "no alert recorded")
        else:
            res.ok("read_sedentary", f"last alert epoch={epoch}")
    except Exception as e:
        res.fail("read_sedentary", str(e))


async def test_read_wifi_sync(client: BleakClient, res: Results, verbose: bool) -> None:
    """Read WiFi sync status (0x00=no wifi, 0x01=configured)."""
    try:
        data = await client.read_gatt_char(UUID_WIFI_SYNC)
        if verbose:
            print(f"    raw: {hexdump(data)}")
        if len(data) < 1:
            res.fail("read_wifi_sync", "empty response")
            return
        val = data[0]
        if val in (0, 1):
            res.ok("read_wifi_sync", "wifi configured" if val else "no wifi")
        else:
            res.fail("read_wifi_sync", f"unexpected value {val}")
    except Exception as e:
        res.fail("read_wifi_sync", str(e))


# ── Notification write tests ─────────────────────────────────────────────────


async def test_send_notification(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Write a short notification message to 0xAA0A."""
    msg = "Hello from BLE test!"
    try:
        await client.write_gatt_char(
            UUID_NOTIFICATION, msg.encode("utf-8"), response=False
        )
        res.ok("send_notification", f"wrote '{msg}'")
    except Exception as e:
        res.fail("send_notification", str(e))


async def test_replace_notification(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Write a second notification to verify replacement."""
    msg = "Second notification"
    try:
        await client.write_gatt_char(
            UUID_NOTIFICATION, msg.encode("utf-8"), response=False
        )
        # Small delay so user can visually confirm on the watch
        await asyncio.sleep(1.0)
        res.ok("replace_notification", f"wrote '{msg}'")
    except Exception as e:
        res.fail("replace_notification", str(e))


async def test_long_notification(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Write a 150-char message (watch truncates at 100, BLE write should succeed)."""
    msg = "A" * 150
    try:
        await client.write_gatt_char(
            UUID_NOTIFICATION, msg.encode("utf-8"), response=False
        )
        await asyncio.sleep(1.0)
        res.ok("long_notification", f"wrote {len(msg)} chars (watch truncates to 100)")
    except Exception as e:
        res.fail("long_notification", str(e))


async def test_dismiss_notification(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Write 0x00 to dismiss the notification overlay."""
    try:
        await client.write_gatt_char(UUID_NOTIFICATION, b"\x00", response=False)
        res.ok("dismiss_notification", "sent 0x00")
    except Exception as e:
        res.fail("dismiss_notification", str(e))


# ── Subscribe / notify tests (long-running, behind --subscribe) ──────────────


async def test_subscribe_battery(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Subscribe to battery notifications (expect one within ~65s)."""
    received: list[bytes] = []

    def callback(_sender: int, data: bytearray) -> None:
        received.append(bytes(data))
        if verbose:
            print(f"    battery notify: {hexdump(data)}")

    try:
        await client.start_notify(UUID_BATTERY_LEVEL, callback)
        print("    waiting up to 65s for battery notification...")
        deadline = time.monotonic() + 65
        while not received and time.monotonic() < deadline:
            await asyncio.sleep(1)
        await client.stop_notify(UUID_BATTERY_LEVEL)

        if received:
            pct = received[0][0]
            res.ok(
                "subscribe_battery",
                f"received {len(received)} notification(s), last={pct}%",
            )
        else:
            res.fail("subscribe_battery", "no notification received within 65s")
    except Exception as e:
        res.fail("subscribe_battery", str(e))


async def test_subscribe_steps(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Subscribe to step count notifications (expect one within ~15s)."""
    received: list[bytes] = []

    def callback(_sender: int, data: bytearray) -> None:
        received.append(bytes(data))
        if verbose:
            steps = struct.unpack("<I", bytes(data)[:4])[0] if len(data) >= 4 else "?"
            print(f"    steps notify: {hexdump(data)} = {steps}")

    try:
        await client.start_notify(UUID_STEPS, callback)
        print("    waiting up to 15s for steps notification...")
        deadline = time.monotonic() + 15
        while not received and time.monotonic() < deadline:
            await asyncio.sleep(1)
        await client.stop_notify(UUID_STEPS)

        if received:
            steps = (
                struct.unpack("<I", received[-1][:4])[0]
                if len(received[-1]) >= 4
                else "?"
            )
            res.ok(
                "subscribe_steps",
                f"received {len(received)} notification(s), last={steps} steps",
            )
        else:
            res.fail("subscribe_steps", "no notification received within 15s")
    except Exception as e:
        res.fail("subscribe_steps", str(e))


async def test_subscribe_sedentary(
    client: BleakClient, res: Results, verbose: bool
) -> None:
    """Subscribe to sedentary notifications (just verify subscription works)."""
    try:

        def callback(_sender: int, data: bytearray) -> None:
            if verbose:
                print(f"    sedentary notify: {hexdump(data)}")

        await client.start_notify(UUID_SEDENTARY, callback)
        await asyncio.sleep(0.5)
        await client.stop_notify(UUID_SEDENTARY)
        res.ok("subscribe_sedentary", "subscription succeeded (no 30min wait)")
    except Exception as e:
        res.fail("subscribe_sedentary", str(e))


# ── Main ──────────────────────────────────────────────────────────────────────


async def run(args: argparse.Namespace) -> int:
    res = Results()

    # ── Scan ──
    print(f"\nScanning for '{args.device_name}' (timeout {args.timeout}s)...")
    device = await BleakScanner.find_device_by_name(
        args.device_name, timeout=args.timeout
    )
    if device is None:
        print(f"  ERROR: device '{args.device_name}' not found")
        return 1
    print(f"  Found: {device.name}  addr={device.address}\n")

    # ── Connect ──
    print("Connecting...")
    async with BleakClient(device, timeout=args.timeout) as client:
        if not client.is_connected:
            print("  ERROR: failed to connect")
            return 1
        print(f"  Connected (MTU={client.mtu_size})\n")

        print("── Service & Characteristic Reads ──")
        await test_service_discovery(client, res, args.verbose)
        await test_read_battery(client, res, args.verbose)
        await test_read_temperature(client, res, args.verbose)
        await test_read_steps(client, res, args.verbose)
        await test_read_alarm_time(client, res, args.verbose)
        await test_read_alarm_enable(client, res, args.verbose)
        await test_read_brightness(client, res, args.verbose)
        await test_read_ble_mode(client, res, args.verbose)
        await test_read_wifi_ssid(client, res, args.verbose)
        await test_read_wifi_sync(client, res, args.verbose)
        await test_read_sedentary(client, res, args.verbose)

        print("\n── Notification Writes ──")
        await test_send_notification(client, res, args.verbose)
        await asyncio.sleep(0.5)
        await test_replace_notification(client, res, args.verbose)
        await test_long_notification(client, res, args.verbose)
        await test_dismiss_notification(client, res, args.verbose)

        print("\n── Subscriptions ──")
        await test_subscribe_sedentary(client, res, args.verbose)

        if args.subscribe:
            await test_subscribe_steps(client, res, args.verbose)
            await test_subscribe_battery(client, res, args.verbose)
        else:
            res.skip("subscribe_steps", "use --subscribe to enable")
            res.skip("subscribe_battery", "use --subscribe to enable")

    print(res.summary())
    return 1 if res.failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BLE integration test for ESP32Watch notifications & characteristics"
    )
    parser.add_argument(
        "-n",
        "--device-name",
        default="ESP32Watch",
        help="BLE advertised name to scan for (default: ESP32Watch)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=10.0,
        help="scan / connect timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--subscribe",
        action="store_true",
        help="enable long-running subscribe tests (battery ~65s, steps ~15s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print raw byte dumps for each read/notify",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
