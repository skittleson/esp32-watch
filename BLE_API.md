# ESP32Watch BLE API Guide

This document describes the complete BLE interface of the ESP32Watch firmware.
It is intended for use by a developer or LLM building a companion app or UX.

---

## Device Discovery

- **Advertised name:** `ESP32Watch`
- **Advertising mode:** Starts automatically on boot; re-advertises after disconnect
- **Auto-off:** Advertising stops after 60 seconds if no connection is made AND
  the watch is on battery (not USB/charging). While plugged in (battery voltage
  >= 4.15V), BLE advertises indefinitely.
- **Re-activate:** Double-tap the watch face to restart advertising after timeout.

---

## Services Overview

| Service Name            | UUID     | Type     |
|-------------------------|----------|----------|
| Current Time Service    | `0x1805` | Standard |
| Battery Service         | `0x180F` | Standard |
| Device Information      | `0x180A` | Standard |
| Environmental Sensing   | `0x181A` | Standard |
| Watch Custom Service    | `0000AA00-0000-1000-8000-00805F9B34FB` | Custom |

---

## 1. Current Time Service (`0x1805`)

### Current Time — `0x2A2B`
**Properties:** WRITE, NOTIFY

Used to sync the watch RTC from the phone. The watch does not auto-sync time;
it relies entirely on a BLE write to set the clock.

**Write format — 7 bytes minimum:**

| Byte | Field    | Type    | Notes                  |
|------|----------|---------|------------------------|
| 0–1  | Year     | uint16  | Little-endian, e.g. 2026 → `0xD4 0x07` |
| 2    | Month    | uint8   | 1–12                   |
| 3    | Day      | uint8   | 1–31                   |
| 4    | Hours    | uint8   | 0–23                   |
| 5    | Minutes  | uint8   | 0–59                   |
| 6    | Seconds  | uint8   | 0–59                   |

**Example — set to 2026-04-01 14:30:00:**
```
D4 07 04 01 0E 1E 00
```

**Notifications:** Unused by the watch (write-only in practice).

---

### Local Time Information — `0x2A0F`
**Properties:** READ, WRITE

Accepted but currently ignored by the firmware. Write whatever the standard
requires; it will not affect watch behavior.

---

## 2. Battery Service (`0x180F`)

### Battery Level — `0x2A19`
**Properties:** READ, NOTIFY

**Read response — 1 byte:**

| Byte | Field          | Type  | Notes         |
|------|----------------|-------|---------------|
| 0    | Battery level  | uint8 | 0–100 (%)     |

**Notes:**
- 100% = USB plugged in (charging) OR fully charged battery
- Reading 100% consistently = device is plugged in
- Notified automatically every 60 seconds while connected

---

## 3. Device Information (`0x180A`)

### Firmware Revision — `0x2A26`
**Properties:** READ

**Read response:** UTF-8 string, e.g. `"2.0.0-lvgl"`

---

## 4. Environmental Sensing Service (`0x181A`)

### Temperature — `0x2A6E`
**Properties:** READ

Die temperature from the QMI8658 IMU sensor. Reads warm (~5–10°C above
ambient) because it is the chip die temperature, not a dedicated ambient sensor.
The same value is displayed on the watch clock face.

**Read response — 2 bytes:**

| Byte | Field       | Type   | Notes                        |
|------|-------------|--------|------------------------------|
| 0–1  | Temperature | sint16 | Little-endian, units = 0.01°C |

**Decoding:**
```
raw = int16_from_bytes_little_endian(value)
celsius = raw / 100.0
```

**Example:** `0x0A 0x09` → `0x090A` = 2314 → **23.14°C**

**Notes:** Read on demand only; no notifications.

---

## 5. Custom Watch Service (`0000AA00-0000-1000-8000-00805F9B34FB`)

All custom characteristics use the base UUID pattern:
`0000AANN-0000-1000-8000-00805F9B34FB` where `NN` is the characteristic number.

---

### Alarm Time — `0000AA01-0000-1000-8000-00805F9B34FB`
**Properties:** READ, WRITE

**Read/Write format — 2 bytes:**

| Byte | Field   | Type  | Notes  |
|------|---------|-------|--------|
| 0    | Hour    | uint8 | 0–23   |
| 1    | Minute  | uint8 | 0–59   |

**Example — set alarm to 07:30:**
```
07 1E
```

**Notes:**
- Setting alarm time does NOT enable it. Write to Alarm Enable separately.
- Persisted to `/settings.json` on the watch immediately on write.
- The watch clock face shows an alarm indicator (bell icon) when enabled.

---

### Alarm Enable — `0000AA02-0000-1000-8000-00805F9B34FB`
**Properties:** READ, WRITE

**Read/Write format — 1 byte:**

| Byte | Field   | Type  | Notes           |
|------|---------|-------|-----------------|
| 0    | Enabled | uint8 | `0x01` = on, `0x00` = off |

**Behavior when alarm fires:**
- Watch navigates to the Alarm screen automatically
- Haptic motor pulses (GPIO5)
- LVGL pulse animation plays on screen
- User dismisses by tapping the screen
- Persisted to `/settings.json` immediately on write.

---

### Brightness — `0000AA03-0000-1000-8000-00805F9B34FB`
**Properties:** READ, WRITE

Controls display backlight PWM duty cycle.

**Read/Write format — 1 byte:**

| Byte | Field      | Type  | Notes                              |
|------|------------|-------|------------------------------------|
| 0    | Brightness | uint8 | 0–255 mapped to PWM duty 0–1023   |

**Scale:** `duty = value * 4` (0 = off, 255 = full ~1020/1023 duty)

**Recommended range:** 50–200. Below ~20 the display is effectively off.

**Notes:** Persisted to `/settings.json` on write. Survives reboot.

---

### Step Count — `0000AA04-0000-1000-8000-00805F9B34FB`
**Properties:** READ, NOTIFY

Pedometer step count since last reset. The step counter persists across reboots
(saved to `/settings.json` every 60 seconds).

**Read response — 4 bytes:**

| Byte | Field | Type   | Notes              |
|------|-------|--------|--------------------|
| 0–3  | Steps | uint32 | Little-endian      |

**Example:** `0x64 0x00 0x00 0x00` → 100 steps

**Notifications:** Sent automatically every 10 seconds while connected.

**Notes:**
- Step detection uses IMU accelerometer magnitude threshold (1.3g) with 300ms
  lockout. This is a basic pedometer — accuracy is approximate.
- There is no BLE command to reset the step counter.

---

### BLE Mode — `0000AA05-0000-1000-8000-00805F9B34FB`
**Properties:** READ, WRITE

Controls whether BLE stays on permanently when on battery (always-on mode).
When USB/charging is detected, BLE is always on regardless of this setting.

**Read/Write format — 1 byte:**

| Byte | Field     | Type  | Notes                     |
|------|-----------|-------|---------------------------|
| 0    | Always-on | uint8 | `0x01` = always on, `0x00` = timeout after 60s |

**Default:** `0x00` (timeout mode). When USB is plugged in this has no effect —
BLE stays on regardless.

**Notes:** Persisted to `/settings.json` on write.

---

## Notification Summary

| Characteristic | UUID     | Interval    | Trigger             |
|----------------|----------|-------------|---------------------|
| Battery Level  | `0x2A19` | Every 60s   | Timer while connected |
| Step Count     | `0xAA04` | Every 10s   | Timer while connected |

All other characteristics are read-on-demand only.

---

## Connection Behavior

| Event                  | Watch behavior                                      |
|------------------------|-----------------------------------------------------|
| Phone connects         | Stops advertising, shows BT icon on clock face      |
| Phone disconnects      | Clears BT icon, immediately restarts advertising    |
| Advertising timeout    | Stops after 60s on battery (unless always-on/charging) |
| Double-tap watch face  | Restarts advertising if timed out                   |
| USB plugged in         | BLE stays on indefinitely (charging proxy)          |

---

## Typical UX Flows

### Time Sync on Connect
1. On connection, immediately write Current Time (`0x2A2B`) with current
   UTC time in the 7-byte format above.
2. The watch RTC is updated instantly. The clock face reflects the new time
   on the next LVGL tick (~50ms).

### Read Current Watch State
1. Read Battery Level (`0x2A19`) → display charge %
2. Read Temperature (`0x2A6E`) → decode as `int16 / 100.0` → display °C or °F
3. Read Step Count (`0xAA04`) → decode as uint32 → display steps
4. Read Alarm Time (`0xAA01`) + Alarm Enable (`0xAA02`) → show alarm state

### Set Alarm
1. Write Alarm Time (`0xAA01`) with `[hour, minute]`
2. Write Alarm Enable (`0xAA02`) with `[0x01]`
3. Optionally read back both to confirm

### Adjust Brightness
1. Write Brightness (`0xAA03`) with a uint8 value (recommended: 128 for 50%)

### Subscribe to Live Updates
1. Enable notifications on Battery Level (`0x2A19`) — updates every 60s
2. Enable notifications on Step Count (`0xAA04`) — updates every 10s

---

## Wire Format Quick Reference

```
Time sync write (0x2A2B):   [YR_LO, YR_HI, MO, DY, HR, MN, SC]
Temperature read (0x2A6E):  [VAL_LO, VAL_HI]  → int16 / 100.0 = °C
Battery read (0x2A19):      [PCT]              → uint8 0–100
Step read (0xAA04):         [S0, S1, S2, S3]  → uint32 little-endian
Alarm time (0xAA01):        [HR, MN]           → uint8 each
Alarm enable (0xAA02):      [EN]               → 0x00 or 0x01
Brightness (0xAA03):        [VAL]              → uint8 0–255
BLE mode (0xAA05):          [EN]               → 0x00 or 0x01
```

---

## Notes for App Developers

- **No pairing/bonding required.** The watch uses open BLE (no PIN, no encryption).
- **MTU:** Default BLE MTU (23 bytes). All characteristics fit within one packet.
- **Reconnect:** After any disconnect the watch immediately re-advertises as
  `ESP32Watch`. Apps should scan and reconnect automatically.
- **Time zone:** The watch stores raw UTC values in the RTC. If you want the
  clock face to show local time, write local time (not UTC) to `0x2A2B`.
  The watch has no concept of time zones.
- **Temperature units:** The watch always sends Celsius. Convert in the app:
  `fahrenheit = celsius * 9/5 + 32`.
- **Step counter persistence:** Steps accumulate indefinitely and persist across
  reboots. The step counter is never reset by the firmware. If your app wants
  a "today" step count, record the value at midnight and subtract.
