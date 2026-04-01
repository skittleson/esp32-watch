# ESP32-S3 Watch — Firmware Specification

**Hardware:** Waveshare ESP32-S3-Touch-LCD-1.28  
**Firmware:** MicroPython (gc9a01_mpy build for ESP32_GENERIC_S3)  
**Version:** 1.0.0  
**Timezone:** America/Los_Angeles (PDT, UTC-7) — set manually on device RTC

---

## Table of Contents

1. [Hardware Overview](#1-hardware-overview)
2. [Architecture](#2-architecture)
3. [File Structure](#3-file-structure)
4. [Screens](#4-screens)
5. [BLE Interface](#5-ble-interface)
6. [Settings Persistence](#6-settings-persistence)
7. [Power / Sleep](#7-power--sleep)
8. [Known Quirks & Critical Notes](#8-known-quirks--critical-notes)
9. [Updating the Firmware](#9-updating-the-firmware)
10. [Tuning Constants](#10-tuning-constants)

---

## 1. Hardware Overview

### Board
Waveshare ESP32-S3-Touch-LCD-1.28 — 240×240 round GC9A01A display, capacitive touch, 6-axis IMU, LiPo battery.

### Pin Map

| Function         | GPIO  | Notes |
|------------------|-------|-------|
| LCD SPI CLK      | 10    | SPI1 |
| LCD SPI MOSI     | 11    | SPI1, display is write-only (no MISO) |
| LCD DC           | 8     | |
| LCD CS           | 9     | |
| LCD RESET        | **14**| Critical — NOT GPIO12 (wrong on some docs) |
| LCD Backlight    | 40    | On/off managed by gc9a01 driver |
| Backlight PWM    | 2     | Software PWM for dimming |
| Touch I2C SDA    | 6     | Shared bus with IMU |
| Touch I2C SCL    | 7     | Shared bus with IMU |
| Touch RESET      | 13    | |
| Touch INT        | 5     | IRQ_FALLING; also used as haptic output during alarm |
| IMU INT1         | 4     | Wake-on-Motion IRQ (rising edge) |
| Battery ADC      | 1     | ADC1, 3:1 resistor divider, 11dB attenuation |

### ICs
| IC      | Bus  | Address | Role |
|---------|------|---------|------|
| GC9A01A | SPI1 | —       | 240×240 round display |
| CST816S | I2C0 | 0x15    | Capacitive touch + gesture |
| QMI8658 | I2C0 | 0x6B    | 6-axis IMU (accel + gyro), step counter |

---

## 2. Architecture

```
Core 1 (main thread)          Core 0 (_thread)
─────────────────────         ───────────────────────────
while True:                   BLE IRQ callbacks
  poll touch (IRQ flag)         _irq_central_connect
  poll IMU (~50 Hz)             _irq_central_disconnect
  poll battery (30 s)           _irq_gatts_write
  update screen                 _irq_gatts_read_request
  check alarm                 BLE timeout loop (500 ms tick)
  sleep timer                   advertising timeout
  persist settings (60 s)       battery/steps notify
```

**Why no asyncio:** The `gc9a01_mpy` C driver uses ESP32 SPI DMA. asyncio task-switches corrupt DMA descriptors, causing display corruption or crashes. All display operations run exclusively on the main thread in a plain `while True` loop.

**Thread safety:** Shared state lives in a single Python dict (`shared`). The MicroPython GIL guarantees atomic dict reads/writes, so no explicit locks are needed for the small values used here.

---

## 3. File Structure

```
watch_py/
├── main.py                 # Entry point; main loop; all timing state
├── config.py               # Pins, UUIDs, timing constants, colour palette
├── settings.json           # Persisted settings on device flash (auto-created)
│
├── hal/
│   ├── display.py          # GC9A01A SPI init, PWM backlight, on/off/dim
│   ├── touch.py            # CST816S I2C driver, gesture IRQ
│   ├── imu.py              # QMI8658 I2C driver, step counter, WoM IRQ
│   └── battery.py          # ADC battery voltage → percentage
│
├── screens/
│   ├── manager.py          # Screen state machine, swipe navigation, dirty-flag
│   ├── clock_face.py       # Clock screen (time, date, temp, battery, steps)
│   ├── stopwatch.py        # Stopwatch screen (start/pause/lap/reset)
│   └── alarm.py            # Alarm screen (set via BLE, haptic + flash on fire)
│
└── ble/
    ├── service.py          # Raw bluetooth GATT server (no asyncio)
    └── callbacks.py        # Stub (logic is inside service.py)
```

---

## 4. Screens

Navigate between screens by swiping left or right. A 600 ms debounce prevents a single drag from skipping multiple screens.

### 4.1 Clock Face (`screens/clock_face.py`)

The default/home screen. Updates once per second.

| Region             | Content | Format |
|--------------------|---------|--------|
| Top-left corner    | `BT` indicator | Cyan — shown when BLE is active |
| Top-right corner   | `ALM` indicator | Yellow — shown when alarm is enabled |
| Upper area         | Date | `WED 14 MAY 2025` |
| Centre             | Time | `3:04:22 PM` (12-hour, AM/PM) |
| Lower-left         | Temperature | `72.5F` (°F, from IMU die temp) |
| Lower-right        | Battery | `BAT 85%` (green >50%, orange >20%, red ≤20%) |
| Bottom             | Steps | `1,234 steps` |

Partial redraws: only changed fields are repainted each second to minimise SPI traffic.

### 4.2 Stopwatch (`screens/stopwatch.py`)

| Gesture       | Action |
|---------------|--------|
| Single tap    | Start / pause toggle |
| Swipe up      | Reset (only when paused or idle) |
| Long press    | Record lap (only while running) |

Display shows elapsed time as `MM:SS.cs` (centiseconds). Lap time appears below the timer.

### 4.3 Alarm (`screens/alarm.py`)

Displays the currently set alarm time in 12-hour format, and its on/off status.

| Gesture       | Action |
|---------------|--------|
| Single tap    | Toggle alarm on/off |

Alarm time is set via BLE (see Section 5). When the alarm fires:
- Screen switches to Alarm and flashes red/black at 2 Hz.
- Haptic motor pulses 5× (500 ms on / 100 ms off).
- Auto-dismisses after 60 seconds if not manually dismissed.
- Tap anywhere to dismiss early.

---

## 5. BLE Interface

BLE is **off by default**. Activate it with a **double-tap** on the display; it advertises for 60 seconds then stops automatically. It can be set to always-on via characteristic `0xAA05`.

Device name: `ESP32Watch`  
Advertising interval: 100 ms

### Standard Services

| Service                | UUID   | Characteristic         | UUID   | Properties |
|------------------------|--------|------------------------|--------|------------|
| Current Time Service   | 0x1805 | Current Time           | 0x2A2B | Write, Notify |
| Current Time Service   | 0x1805 | Local Time Information | 0x2A0F | Read, Write |
| Battery Service        | 0x180F | Battery Level          | 0x2A19 | Read, Notify |
| Device Information     | 0x180A | Firmware Revision      | 0x2A26 | Read |

**Set time (0x2A2B):** Write 10 bytes — `year` (LE uint16), `month`, `day`, `hour`, `minute`, `second`, then 4 more bytes (ignored). Sets the RTC immediately.

**Battery Level (0x2A19):** Returns current battery percentage 0–100. Notified every 60 seconds when connected.

**Firmware Revision (0x2A26):** Returns the ASCII string from `FW_VERSION` in `config.py`.

### Custom Watch Service — `0000AA00-0000-1000-8000-00805F9B34FB`

| Characteristic | UUID suffix | Properties    | Format | Description |
|----------------|-------------|---------------|--------|-------------|
| Alarm Time     | `AA01`      | Read, Write   | 2 bytes: `[hour, minute]` (24h) | Set alarm time |
| Alarm Enable   | `AA02`      | Read, Write   | 1 byte: `0x00` = off, `0x01` = on | Enable/disable alarm |
| Brightness     | `AA03`      | Read, Write   | 1 byte: `0`–`255` | Backlight level (maps to 0–1023 PWM) |
| Step Count     | `AA04`      | Read, Notify  | uint32 LE | Current step count; notified every 10 s |
| BLE Mode       | `AA05`      | Read, Write   | 1 byte: `0x00` = timeout, `0x01` = always-on | BLE advertising mode |

All writes are persisted to `settings.json` at the next 60-second save cycle.

### Connecting with nRF Connect (iOS/Android)

1. Double-tap the watch face to start advertising.
2. Scan — device appears as `ESP32Watch`.
3. Connect and browse services.
4. To sync time: write the Current Time characteristic (0x2A2B) — nRF Connect has a built-in "Set to current time" button on this characteristic.
5. To set alarm: write `AA01` with `[hour, minute]` in 24h format, then write `AA02` with `0x01`.

---

## 6. Settings Persistence

Settings are saved to `/settings.json` on the device flash every 60 seconds.

```json
{
  "steps": 4231,
  "alarm_hour": 7,
  "alarm_minute": 30,
  "alarm_enabled": false,
  "brightness": 175,
  "ble_always": false
}
```

| Key             | Type    | Default | Description |
|-----------------|---------|---------|-------------|
| `steps`         | int     | 0       | Step count carried over across reboots |
| `alarm_hour`    | int     | 7       | Alarm hour (24h) |
| `alarm_minute`  | int     | 30      | Alarm minute |
| `alarm_enabled` | bool    | false   | Alarm active state |
| `brightness`    | int     | —       | BLE brightness value (0–255); absent = use default |
| `ble_always`    | bool    | false   | BLE always-on mode |

To reset all settings, delete `/settings.json` via mpremote:
```
mpremote connect auto rm :settings.json
```

---

## 7. Power / Sleep

| Timeout        | Action |
|----------------|--------|
| 10 s idle      | Backlight dims to ~2% PWM duty |
| 30 s idle      | Backlight off completely |
| Any touch      | Backlight fully on, idle timer resets |
| Double-tap     | Backlight on + BLE activates |
| IMU WoM INT1   | Backlight on (wrist-raise wake) |

The display is turned off by cutting PWM to 0 — the ESP32 itself does not enter deep sleep in this build, so BLE and the main loop continue running.

---

## 8. Known Quirks & Critical Notes

### GC9A01 reset pin is GPIO14, not GPIO12
Multiple sources (including some gc9a01_mpy examples) list GPIO12. This board uses **GPIO14**. Using 12 results in a blank display with no error.

### CST816S auto-sleep must be disabled first
The touch chip enters auto-sleep and ignores I2C writes unless `REG_DIS_AUTOSLEEP (0xFE) = 0x01` is written **before** any other register. The init sequence in `hal/touch.py` does this correctly.

### Single-click fires with `fingers=0`
The CST816S reports `fingers=0` on `single_click` events. Do not filter out events where `fingers == 0`; doing so drops single-tap gestures entirely.

### Temperature reads IMU die temp, not ambient
The temperature shown on the clock face is the QMI8658 die temperature, which typically reads 5–10°C above ambient due to self-heating. It is a rough indicator, not a precision sensor.

### Haptic pin shares GPIO5 with touch INT
GPIO5 drives both the touch interrupt input and the haptic motor MOSFET. The touch IRQ is detached before driving haptic output; the alarm code (`alarm.py`) sets the pin to output mode when the alarm fires, overriding the touch IRQ for the duration.

### asyncio is not safe with gc9a01_mpy
Do not add `asyncio` to this firmware. The gc9a01 C driver uses SPI DMA; asyncio task switches during DMA transfers cause display corruption. All screen drawing must stay on the main thread.

---

## 9. Updating the Firmware

### Prerequisites
```bash
pip install mpremote
```

Connect the watch via USB-C. The device appears as a serial port (e.g. `/dev/ttyUSB0` on Linux, `COMx` on Windows, `/dev/cu.usbmodem*` on macOS).

### Upload a single file
```bash
mpremote connect auto cp watch_py/screens/manager.py :screens/manager.py
```

### Upload all files
```bash
# HAL
mpremote connect auto cp watch_py/hal/display.py  :hal/display.py
mpremote connect auto cp watch_py/hal/touch.py    :hal/touch.py
mpremote connect auto cp watch_py/hal/imu.py      :hal/imu.py
mpremote connect auto cp watch_py/hal/battery.py  :hal/battery.py

# Screens
mpremote connect auto cp watch_py/screens/manager.py    :screens/manager.py
mpremote connect auto cp watch_py/screens/clock_face.py :screens/clock_face.py
mpremote connect auto cp watch_py/screens/stopwatch.py  :screens/stopwatch.py
mpremote connect auto cp watch_py/screens/alarm.py      :screens/alarm.py

# BLE
mpremote connect auto cp watch_py/ble/service.py   :ble/service.py
mpremote connect auto cp watch_py/ble/callbacks.py :ble/callbacks.py

# Root
mpremote connect auto cp watch_py/config.py :config.py
mpremote connect auto cp watch_py/main.py   :main.py
```

### Reset after upload
```bash
mpremote connect auto reset
```

### View serial output (logs / errors)
```bash
mpremote connect auto repl
```
Press `Ctrl+C` to interrupt the running script and get a REPL prompt. Press `Ctrl+D` to soft-reset. Press `Ctrl+X` to exit mpremote.

### Check what's on the device
```bash
mpremote connect auto ls :
mpremote connect auto ls :hal/
mpremote connect auto ls :screens/
mpremote connect auto ls :ble/
```

### Read settings.json from device
```bash
mpremote connect auto cat :settings.json
```

### Reflash MicroPython firmware (only needed if firmware is corrupted)
Download the gc9a01_mpy firmware for `ESP32_GENERIC_S3` (no SPIRAM_OCT) from the gc9a01_mpy releases page, then:
```bash
esptool.py --chip esp32s3 erase_flash
esptool.py --chip esp32s3 write_flash 0x0 firmware.bin
```
After reflashing, recreate the directory structure on the device:
```bash
mpremote connect auto mkdir :hal
mpremote connect auto mkdir :screens
mpremote connect auto mkdir :ble
```
Then re-upload all files as above.

---

## 10. Tuning Constants

All tunable values are in `config.py`. Edit on your machine and upload `config.py` to apply.

| Constant              | Default     | Description |
|-----------------------|-------------|-------------|
| `DISPLAY_DIM_MS`      | `10_000`    | ms idle before backlight dims |
| `DISPLAY_OFF_MS`      | `30_000`    | ms idle before backlight off |
| `DISPLAY_DIM_DUTY`    | `20`        | PWM duty when dimmed (0–1023) |
| `DISPLAY_DEFAULT_DUTY`| `700`       | PWM duty at full brightness |
| `BLE_TIMEOUT_MS`      | `60_000`    | ms BLE advertises after double-tap |
| `BLE_ALWAYS_ON_DEFAULT`| `False`   | BLE always-on at boot (before settings load) |
| `STEP_MAG_THRESHOLD`  | `1.3`       | Accel magnitude (g) to count a step |
| `STEP_LOCKOUT_MS`     | `300`       | Min ms between counted steps |
| `BAT_VOLTAGE_MIN`     | `3.5`       | Voltage mapped to 0% |
| `BAT_VOLTAGE_MAX`     | `4.2`       | Voltage mapped to 100% |
| `BAT_ADC_SAMPLES`     | `16`        | ADC reads averaged per battery reading |

In `screens/manager.py`:

| Constant            | Default | Description |
|---------------------|---------|-------------|
| `_SWIPE_DEBOUNCE_MS`| `600`   | Min ms between swipe-navigation events |
