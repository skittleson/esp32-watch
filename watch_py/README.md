# Waveshare ESP32-S3-Touch-LCD-1.28 — MicroPython Smart Watch (LVGL Edition)

Firmware for a fully-functional smartwatch built on the
[Waveshare ESP32-S3-Touch-LCD-1.28](https://www.waveshare.com/esp32-s3-touch-lcd-1.28.htm)
(240×240 round GC9A01 display, CST816S touch, QMI8658 IMU).

Two branches exist in this repo:

| Branch | Firmware | Status |
|--------|----------|--------|
| `master` | `gc9a01_mpy` (russhughes) — raw pixel rendering | Working baseline |
| `lvgl` | `lvgl_micropython` — full LVGL widget UI | Active development |

---

## Hardware

| Component | Detail |
|-----------|--------|
| MCU | ESP32-S3, dual-core 240 MHz, 2 MB embedded PSRAM |
| Flash | 16 MB |
| Display | GC9A01A, 240×240 round, SPI |
| Touch | CST816S, I2C, gestures + swipes |
| IMU | QMI8658 accel + gyro, I2C |
| Battery ADC | GPIO1, 3:1 resistor divider |
| Haptic | GPIO5 (shared with Touch INT — see note below) |

### Pin Reference

```
SPI display : CLK=10  MOSI=11  DC=8   CS=9   RST=14  BL_GPIO=40  BL_PWM=2
I2C         : SDA=6   SCL=7
Touch       : RST=13  INT=5
IMU INT1    : GPIO4
Battery ADC : GPIO1
Haptic      : GPIO5   ← SHARES with Touch INT — only drive during alarm
```

---

## Features

- **Clock face** — 12-hour AM/PM, seconds, date, °F temperature
- **Dual arc rings** — outer battery level arc, inner step-count progress arc
- **Stopwatch** — tap start/pause, long-press lap, swipe-up reset; sweep arc
- **Alarm** — 12h display, on/off toggle switch, haptic pulses, pulsing red fired view
- **BLE** — double-tap activates 60 s advertising window; sync time, set alarm,
  adjust brightness, query steps/battery via nRF Connect or any BLE client
- **Sleep** — dims at 10 s idle, off at 30 s; touch or wrist raise wakes
- **Persistence** — steps, alarm, brightness, BLE mode saved to `/settings.json`
- **Dark theme** — Montserrat fonts, cyan accent, deep-navy surface

---

## Repository Layout

```
watch_py/
├── main.py                # Boot entry point
├── config.py              # All pins, UUIDs, theme colours, timing constants
├── settings.json          # Persisted on-device (not in repo)
├── hal/
│   ├── display.py         # lcd_bus.SPIBus + GC9A01 LVGL driver, PWM backlight
│   ├── touch.py           # CST816S LVGL indev + raw I2C gesture poll
│   ├── imu.py             # QMI8658 accel/gyro/temp, software step counter
│   └── battery.py         # ADC voltage → percent
├── screens/
│   ├── manager.py         # Screen state machine, lv.screen_load_anim transitions
│   ├── clock_face.py      # Arc rings, Montserrat 48 time, date, indicators
│   ├── stopwatch.py       # 360° sweep arc, Montserrat 40 timer, lap marker
│   └── alarm.py           # lv.switch toggle, lv.anim pulsing fired view
└── ble/
    ├── service.py         # Raw bluetooth GATT server (_thread, no asyncio)
    └── callbacks.py       # Write handlers: time, alarm, brightness, BLE mode
```

---

## One-time Setup: Build the LVGL Firmware

The LVGL binding must be compiled from source. Do this **once** (or when you
want to update LVGL). This takes 5–15 minutes on a modern machine.

### 1. Install build dependencies (Ubuntu/Debian)

```bash
sudo apt-get install build-essential cmake ninja-build python3 python3-venv libusb-1.0-0-dev
```

### 2. Clone lvgl_micropython

> **Important:** Do NOT run `git submodule init` or `git submodule update`.
> The build script manages submodules itself.

```bash
git clone https://github.com/lvgl-micropython/lvgl_micropython
cd lvgl_micropython
```

### 3. Build for ESP32-S3 with SPIRAM, GC9A01 display, CST816S touch

```bash
python3 make.py esp32 \
  BOARD=ESP32_GENERIC_S3 \
  BOARD_VARIANT=SPIRAM_OCT \
  DISPLAY=gc9a01 \
  INDEV=cst816s \
  --flash-size=16
```

The firmware binary will be written to:
```
build/lvgl_micropy_ESP32_GENERIC_S3.bin
```

### 4. Flash the firmware

> Put the watch into download mode: hold **BOOT**, tap **RESET**, release **BOOT**.
> On this board with USB-CDC you usually don't need to — esptool resets automatically.

```bash
# Erase first (required when switching firmware families)
esptool --port /dev/ttyACM0 --baud 460800 erase_flash

# Flash
esptool --port /dev/ttyACM0 --baud 460800 \
  --before default_reset --after hard_reset \
  write_flash -z 0x0 \
  build/lvgl_micropy_ESP32_GENERIC_S3.bin
```

Or use the combined one-liner (build + flash):

```bash
python3 make.py esp32 \
  BOARD=ESP32_GENERIC_S3 \
  BOARD_VARIANT=SPIRAM_OCT \
  DISPLAY=gc9a01 \
  INDEV=cst816s \
  --flash-size=16 \
  PORT=/dev/ttyACM0 \
  BAUD=460800 \
  deploy
```

---

## Upload Watch Source Files

After flashing, upload the Python source to the device filesystem using `mpremote`.

### Install mpremote (if not already installed)

```bash
pip3 install mpremote
```

### Upload all files

Run from the **repo root** (`watch_py/` parent directory):

```bash
PORT=/dev/ttyACM0

# Create directory structure on device
mpremote connect $PORT mkdir hal
mpremote connect $PORT mkdir screens
mpremote connect $PORT mkdir ble

# Upload HAL
mpremote connect $PORT cp watch_py/hal/display.py  :hal/display.py
mpremote connect $PORT cp watch_py/hal/touch.py    :hal/touch.py
mpremote connect $PORT cp watch_py/hal/imu.py      :hal/imu.py
mpremote connect $PORT cp watch_py/hal/battery.py  :hal/battery.py

# Upload screens
mpremote connect $PORT cp watch_py/screens/manager.py    :screens/manager.py
mpremote connect $PORT cp watch_py/screens/clock_face.py :screens/clock_face.py
mpremote connect $PORT cp watch_py/screens/stopwatch.py  :screens/stopwatch.py
mpremote connect $PORT cp watch_py/screens/alarm.py      :screens/alarm.py

# Upload BLE
mpremote connect $PORT cp watch_py/ble/service.py   :ble/service.py
mpremote connect $PORT cp watch_py/ble/callbacks.py :ble/callbacks.py

# Upload top-level files
mpremote connect $PORT cp watch_py/config.py :config.py
mpremote connect $PORT cp watch_py/main.py   :main.py
```

Or use the helper script below.

### Quick upload script

Save as `upload.sh` in the repo root and run `bash upload.sh`:

```bash
#!/usr/bin/env bash
set -e
PORT=${1:-/dev/ttyACM0}
SRC=watch_py

echo "Uploading to $PORT ..."
mpremote connect $PORT mkdir hal    2>/dev/null || true
mpremote connect $PORT mkdir screens 2>/dev/null || true
mpremote connect $PORT mkdir ble    2>/dev/null || true

for f in hal/display.py hal/touch.py hal/imu.py hal/battery.py \
          screens/manager.py screens/clock_face.py screens/stopwatch.py screens/alarm.py \
          ble/service.py ble/callbacks.py \
          config.py main.py; do
  echo "  -> $f"
  mpremote connect $PORT cp "$SRC/$f" ":$f"
done

echo "Done. Resetting device..."
mpremote connect $PORT reset
```

---

## BLE Usage (nRF Connect or similar)

Once the watch is running, **double-tap** the screen to enable BLE for 60 seconds.
The display will show a **BT** indicator in the top-left corner when advertising/connected.

| Characteristic | UUID | Format | Description |
|---|---|---|---|
| Current Time | `0x2A2B` | 10 bytes (BT spec) | Write to sync time |
| Battery Level | `0x2A19` | uint8 0–100 | Read/notify |
| Alarm Time | `AA01` | `[hour, minute]` | Read/write |
| Alarm Enable | `AA02` | `[0/1]` | Read/write |
| Brightness | `AA03` | uint8 0–255 | Read/write |
| Steps | `AA04` | uint32 LE | Read/notify |
| BLE Always-On | `AA05` | `[0/1]` | Read/write — persisted |

### Sync time from Linux command line

```bash
# Requires gatttool or bluetoothctl
# Current Time Service format: year(LE u16), month, day, hour, min, sec, weekday, frac256, adjust
python3 - <<'EOF'
import struct, datetime
now = datetime.datetime.now()
payload = struct.pack("<H", now.year) + bytes([
    now.month, now.day, now.hour, now.minute, now.second,
    now.weekday() + 1, 0, 0
])
print(payload.hex())
EOF
# Then write that hex to characteristic 0x2A2B via nRF Connect
```

---

## Known Hardware Quirks

1. **RST pin is GPIO14**, not GPIO12. Using GPIO12 results in a black screen with no error.

2. **GPIO5 is shared** between the Touch INT pin and the Haptic motor MOSFET.
   When the alarm fires, `alarm.py` reconfigures GPIO5 as `Pin.OUT` to drive
   the haptic. After dismissal, `main.py` calls `touch.reattach_irq()` to
   restore it as `Pin.IN` with the falling-edge IRQ handler.

3. **CST816S auto-sleep** must be disabled (`0xFE = 0x01`) *before* writing
   any other registers, or all other writes are silently ignored.

4. **LVGL + asyncio are incompatible** on this board. The GC9A01 LVGL driver
   uses ESP32 SPI DMA; asyncio task switching corrupts DMA descriptors.
   Architecture uses a plain `while True` loop with `TaskHandler.tick()` and
   BLE on a `_thread` instead.

5. **SPI host 0** on ESP32 is reserved for flash/SPIRAM. Use `host=1` (SPI2).

---

## Updating LVGL Firmware

To get a newer LVGL version: delete your local `lvgl_micropython` clone and
re-clone from scratch (the maintainer's explicit recommendation — do not `git pull`):

```bash
rm -rf lvgl_micropython
git clone https://github.com/lvgl-micropython/lvgl_micropython
cd lvgl_micropython
python3 make.py esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT \
  DISPLAY=gc9a01 INDEV=cst816s --flash-size=16 PORT=/dev/ttyACM0 deploy
```

Then re-upload the watch source files.

---

## Rollback to gc9a01_mpy (baseline)

The original working firmware lives on the `master` branch:

```bash
git checkout master
```

Flash the original gc9a01_mpy firmware (stored in `watch_py/firmware/` if
you saved it, or download from
https://github.com/russhughes/gc9a01_mpy/releases) then re-upload.
