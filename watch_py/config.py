# config.py — All pin numbers, UUIDs, timing constants, colours
# Waveshare ESP32-S3-Touch-LCD-1.28

import bluetooth
import gc9a01

# ─── Pins ────────────────────────────────────────────────────────────────────
# Display (GC9A01A via SPI1)
# Source: https://github.com/russhughes/gc9a01_mpy/blob/main/tft_configs/ESP32-S3-LCD-1.28/tft_config.py
PIN_LCD_DC = 8
PIN_LCD_CS = 9
PIN_LCD_CLK = 10
PIN_LCD_MOSI = 11
PIN_LCD_RST = 14  # reset — Waveshare C demo uses GPIO14 (not 12)
PIN_LCD_BL_GPIO = 40  # backlight on/off — passed to gc9a01 driver
PIN_LCD_BL = 2  # backlight PWM for dimming

# Touch (CST816S via I2C0)
PIN_TP_SDA = 6
PIN_TP_SCL = 7
PIN_TP_RST = 13
PIN_TP_INT = 5

# IMU (QMI8658 via same I2C0 bus)
PIN_IMU_INT1 = 4

# Battery ADC
PIN_BAT_ADC = 1

# Haptic motor (MOSFET2 — shares GPIO with TP_INT; only driven during alarm)
PIN_HAPTIC = 5

# ─── Display / sleep ────────────────────────────────────────────────────────
DISPLAY_DIM_MS = 10_000  # ms idle before dim
DISPLAY_OFF_MS = 30_000  # ms idle before full off
DISPLAY_DIM_DUTY = 20  # PWM duty 0-1023 when dimmed (~2%)
DISPLAY_DEFAULT_DUTY = 700  # PWM duty at full brightness

# ─── Battery ─────────────────────────────────────────────────────────────────
BAT_VOLTAGE_MIN = 3.5
BAT_VOLTAGE_MAX = 4.2
BAT_ADC_SAMPLES = 16

# ─── Step counter ─────────────────────────────────────────────────────────────
STEP_MAG_THRESHOLD = 1.3  # g
STEP_LOCKOUT_MS = 300

# ─── BLE ─────────────────────────────────────────────────────────────────────
BLE_DEVICE_NAME = "ESP32Watch"
BLE_TIMEOUT_MS = 60_000
BLE_ALWAYS_ON_DEFAULT = False

# Standard BLE UUIDs
UUID_CURRENT_TIME_SVC = bluetooth.UUID(0x1805)
UUID_BATTERY_SVC = bluetooth.UUID(0x180F)
UUID_DEVICE_INFO_SVC = bluetooth.UUID(0x180A)
UUID_CURRENT_TIME_CHR = bluetooth.UUID(0x2A2B)
UUID_LOCAL_TIME_CHR = bluetooth.UUID(0x2A0F)
UUID_BATTERY_LEVEL_CHR = bluetooth.UUID(0x2A19)
UUID_FIRMWARE_REV_CHR = bluetooth.UUID(0x2A26)

# Custom Watch Service / Characteristics
UUID_WATCH_SVC = bluetooth.UUID("0000AA00-0000-1000-8000-00805F9B34FB")
UUID_ALARM_TIME_CHR = bluetooth.UUID("0000AA01-0000-1000-8000-00805F9B34FB")
UUID_ALARM_EN_CHR = bluetooth.UUID("0000AA02-0000-1000-8000-00805F9B34FB")
UUID_BRIGHTNESS_CHR = bluetooth.UUID("0000AA03-0000-1000-8000-00805F9B34FB")
UUID_STEPS_CHR = bluetooth.UUID("0000AA04-0000-1000-8000-00805F9B34FB")
UUID_BLE_MODE_CHR = bluetooth.UUID("0000AA05-0000-1000-8000-00805F9B34FB")

# ─── Screen IDs ──────────────────────────────────────────────────────────────
SCREEN_CLOCK = 0
SCREEN_STOPWATCH = 1
SCREEN_ALARM = 2

# ─── Colour palette (RGB565) ──────────────────────────────────────────────────
BLACK = gc9a01.color565(0, 0, 0)
WHITE = gc9a01.color565(255, 255, 255)
GREY = gc9a01.color565(110, 110, 110)
LGREY = gc9a01.color565(180, 180, 180)
RED = gc9a01.color565(220, 40, 40)
GREEN = gc9a01.color565(0, 200, 80)
ORANGE = gc9a01.color565(255, 140, 0)
CYAN = gc9a01.color565(0, 210, 210)
YELLOW = gc9a01.color565(255, 210, 0)

# ─── Settings file ───────────────────────────────────────────────────────────
SETTINGS_FILE = "/settings.json"
FW_VERSION = "1.0.0"
