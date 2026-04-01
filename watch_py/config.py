# config.py — All pin numbers, UUIDs, timing constants, LVGL theme colours
# Waveshare ESP32-S3-Touch-LCD-1.28

import bluetooth

# ─── Pins ────────────────────────────────────────────────────────────────────
# Display (GC9A01A via SPI2/host=1)
PIN_LCD_DC = 8
PIN_LCD_CS = 9
PIN_LCD_CLK = 10
PIN_LCD_MOSI = 11
PIN_LCD_RST = 14  # CRITICAL — Waveshare uses GPIO14, not 12
PIN_LCD_BL_GPIO = 40  # backlight on/off managed by gc9a01 LVGL driver
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

# Haptic motor — shares GPIO5 with TP_INT; only driven during alarm
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
BLE_ALWAYS_ON_DEFAULT = False  # overridden at runtime when USB charging detected

# Standard BLE UUIDs
UUID_CURRENT_TIME_SVC = bluetooth.UUID(0x1805)
UUID_BATTERY_SVC = bluetooth.UUID(0x180F)
UUID_DEVICE_INFO_SVC = bluetooth.UUID(0x180A)
UUID_ENV_SENSING_SVC = bluetooth.UUID(0x181A)  # Environmental Sensing Service
UUID_CURRENT_TIME_CHR = bluetooth.UUID(0x2A2B)
UUID_LOCAL_TIME_CHR = bluetooth.UUID(0x2A0F)
UUID_BATTERY_LEVEL_CHR = bluetooth.UUID(0x2A19)
UUID_FIRMWARE_REV_CHR = bluetooth.UUID(0x2A26)
UUID_TEMPERATURE_CHR = bluetooth.UUID(0x2A6E)  # sint16, 0.01°C resolution

# Custom Watch Service / Characteristics
UUID_WATCH_SVC = bluetooth.UUID("0000AA00-0000-1000-8000-00805F9B34FB")
UUID_ALARM_TIME_CHR = bluetooth.UUID("0000AA01-0000-1000-8000-00805F9B34FB")
UUID_ALARM_EN_CHR = bluetooth.UUID("0000AA02-0000-1000-8000-00805F9B34FB")
UUID_BRIGHTNESS_CHR = bluetooth.UUID("0000AA03-0000-1000-8000-00805F9B34FB")
UUID_STEPS_CHR = bluetooth.UUID("0000AA04-0000-1000-8000-00805F9B34FB")
UUID_BLE_MODE_CHR = bluetooth.UUID("0000AA05-0000-1000-8000-00805F9B34FB")
UUID_WIFI_SSID_CHR = bluetooth.UUID("0000AA06-0000-1000-8000-00805F9B34FB")
UUID_WIFI_PASS_CHR = bluetooth.UUID("0000AA07-0000-1000-8000-00805F9B34FB")
UUID_WIFI_SYNC_CHR = bluetooth.UUID("0000AA08-0000-1000-8000-00805F9B34FB")
UUID_SEDENTARY_CHR = bluetooth.UUID("0000AA09-0000-1000-8000-00805F9B34FB")
UUID_NOTIFICATION_CHR = bluetooth.UUID("0000AA0A-0000-1000-8000-00805F9B34FB")

# ─── NTP / WiFi ───────────────────────────────────────────────────────────────
NTP_SYNC_INTERVAL_MS = 8 * 60 * 60 * 1000  # 8 hours in ms

# ─── Sedentary alert ──────────────────────────────────────────────────────────
SEDENTARY_ALERT_MS = 30 * 60 * 1000  # alert after 30 min of inactivity
SEDENTARY_MOVE_THRESHOLD = 0.04  # g — minimum acc delta to count as movement

# ─── Screen IDs ──────────────────────────────────────────────────────────────
SCREEN_CLOCK = 0
SCREEN_STOPWATCH = 1
SCREEN_ALARM = 2

# ─── Dark theme palette (LVGL lv.color_hex) ──────────────────────────────────
# Use lv.color_hex(0xRRGGBB) at runtime — do not import lv here (not yet inited)
C_BG = 0x000000  # Pure black background
C_SURFACE = 0x1A1A2E  # Deep navy card surface
C_BORDER = 0x2A2A4A  # Subtle border
C_TEXT_PRI = 0xEEEEEE  # Primary text — near-white
C_TEXT_SEC = 0x888899  # Secondary / muted
C_ACCENT = 0x00D4FF  # Cyan accent (time, active arc)
C_GREEN = 0x00C853  # Running / OK
C_ORANGE = 0xFF8C00  # Warning / paused
C_RED = 0xFF3B30  # Alarm / low battery
C_YELLOW = 0xFFD600  # Alarm indicator
C_GREY = 0x555566  # Dividers / hints

# Sci-Fi / Neon accent palette
C_NEON_CYAN = 0x00FFFF  # Bright cyan — time, dividers
C_NEON_MAGENTA = 0xFF00FF  # Magenta — step arc / accents
C_NEON_LIME = 0x39FF14  # Lime — battery arc healthy
C_NEON_BLUE = 0x4466FF  # Electric blue — tick marks

# ─── Settings file ───────────────────────────────────────────────────────────
SETTINGS_FILE = "/settings.json"
FW_VERSION = "2.0.0-lvgl"
