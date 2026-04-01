# main.py — ESP32-S3 Watch main loop (no asyncio)
#
# Architecture:
#   Main thread (Core 1) — owns all SPI/display operations
#     while True: touch → gesture → draw → sleep timer → alarm check
#   _thread (Core 0) — BLE IRQ + BLE timeout/notify loop (inside ble/service.py)
#   IMU polled in main loop at ~50Hz (fast enough, no separate thread needed)

import time
import ujson
import _thread
from machine import I2C, Pin

from config import (
    PIN_TP_SDA,
    PIN_TP_SCL,
    PIN_TP_RST,
    PIN_TP_INT,
    DISPLAY_DIM_MS,
    DISPLAY_OFF_MS,
    SCREEN_CLOCK,
    SCREEN_STOPWATCH,
    SCREEN_ALARM,
    SETTINGS_FILE,
)

# ── Settings helpers ──────────────────────────────────────────────────────────


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            return ujson.load(f)
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(SETTINGS_FILE, "w") as f:
            ujson.dump(d, f)
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    print("[WATCH] Booting...")

    settings = load_settings()

    shared = {
        "steps": settings.get("steps", 0),
        "bat_pct": 100,
        "temp": 0.0,
        "acc": [0.0, 0.0, 0.0],
        "gyro": [0.0, 0.0, 0.0],
        "ble_active": settings.get("ble_always", False),
        "ble_always": settings.get("ble_always", False),
    }

    # ── HAL ────────────────────────────────────────────────────────────────
    from hal.display import Display
    from hal.touch import CST816S
    from hal.imu import QMI8658
    from hal.battery import Battery

    display = Display()
    display.tft.fill(0)  # black screen on boot (safe: main thread, no tasks yet)

    # Restore brightness
    saved_br = settings.get("brightness", None)
    if saved_br is not None:
        display.set_brightness_from_ble(saved_br)

    i2c = I2C(0, sda=Pin(PIN_TP_SDA), scl=Pin(PIN_TP_SCL), freq=400_000)
    touch = CST816S(i2c, rst_pin=PIN_TP_RST, int_pin=PIN_TP_INT)
    imu = QMI8658(i2c)
    imu.set_steps(shared["steps"])
    bat = Battery()
    shared["bat_pct"] = bat.read_percent()

    # ── Screens ────────────────────────────────────────────────────────────
    from screens.clock_face import ClockFace
    from screens.stopwatch import Stopwatch
    from screens.alarm import Alarm
    from screens.manager import ScreenManager

    clock_face = ClockFace()
    stopwatch = Stopwatch()
    alarm = Alarm(settings)
    mgr = ScreenManager(clock_face, stopwatch, alarm)
    mgr.set_alarm_indicator(alarm.get_enabled())

    # ── BLE (starts _thread internally) ───────────────────────────────────
    from ble.service import ble_watch

    ble_watch.start(shared, display, alarm, mgr, settings)
    if shared["ble_always"]:
        ble_watch.activate()

    print("[WATCH] Running")

    # ── Timing state ───────────────────────────────────────────────────────
    last_activity = time.ticks_ms()
    last_clock_tick = time.ticks_ms()
    last_bat_tick = time.ticks_ms()
    last_imu_tick = time.ticks_ms()
    last_persist_tick = time.ticks_ms()
    dimmed = False

    # ── Main loop ──────────────────────────────────────────────────────────
    while True:
        now = time.ticks_ms()

        # ── IMU poll at ~50Hz (20ms) ───────────────────────────────────────
        if time.ticks_diff(now, last_imu_tick) >= 20:
            data = imu.read()
            shared["acc"] = data["acc"]
            shared["gyro"] = data["gyro"]
            shared["temp"] = data["temp"]
            shared["steps"] = data["steps"]
            last_imu_tick = now

        # ── Battery read every 30s ─────────────────────────────────────────
        if time.ticks_diff(now, last_bat_tick) >= 30_000:
            shared["bat_pct"] = bat.read_percent()
            last_bat_tick = now

        # ── Touch ──────────────────────────────────────────────────────────
        t = touch.poll()
        if t:
            last_activity = now
            dimmed = False
            was_off = display.is_off()
            if was_off:
                display.on()
                # Force full redraw so screen isn't blank after wake
                mgr._screens[mgr.active()].dirty = True

            # Always process gesture — even on wake tap
            # (double-click wakes AND activates BLE in one tap)
            if t["gesture"] == "double_click":
                shared["ble_active"] = True
                ble_watch.activate()
                print("[TOUCH] BLE activated")
            elif t["gesture"] != "none" and not was_off:
                # Only forward nav gestures if screen was already on
                # (avoids accidentally navigating on a wake tap)
                prev_fired = alarm._fired
                mgr.handle_gesture(t["gesture"])
                # If a tap just dismissed the alarm, restore touch IRQ on GPIO5
                if prev_fired and not alarm._fired:
                    touch.reattach_irq()

        # ── WoM wake (IMU INT1 woke display) ──────────────────────────────
        # imu.py handles the INT1 pin via irq — it sets shared['wom_wake']
        if shared.get("wom_wake"):
            shared["wom_wake"] = False
            last_activity = now
            dimmed = False
            if display.is_off():
                display.on()

        # ── BLE double-click activation from shared ────────────────────────
        if shared.get("ble_active") and not ble_watch.is_active():
            ble_watch.activate()
            shared["ble_active"] = True

        # ── Display render ─────────────────────────────────────────────────
        if not display.is_off():
            # Clock face updates every 1s; other screens update on dirty flag
            if mgr.active() == SCREEN_CLOCK:
                if time.ticks_diff(now, last_clock_tick) >= 1000:
                    clock_face.mark_time_dirty()
                    last_clock_tick = now
            mgr.tick(display.tft, shared)

        # ── Alarm check ────────────────────────────────────────────────────
        if alarm.should_fire():
            alarm.fire()
            display.on()
            last_activity = now
            dimmed = False
            mgr.goto(SCREEN_ALARM)

        # Tick alarm (haptic + flash) when fired
        prev_fired = alarm._fired
        if alarm._fired and not display.is_off():
            alarm.tick(display.tft)
        # If alarm just dismissed (fired → not fired), restore touch IRQ on GPIO5
        if prev_fired and not alarm._fired:
            touch.reattach_irq()

        # ── Sleep timer ────────────────────────────────────────────────────
        idle = time.ticks_diff(now, last_activity)
        if idle >= DISPLAY_OFF_MS and not display.is_off():
            display.off()
            dimmed = True
            print("[SLEEP] off")
        elif idle >= DISPLAY_DIM_MS and not dimmed and not display.is_off():
            display.dim()
            dimmed = True
            print("[SLEEP] dim")
        elif idle < DISPLAY_DIM_MS and dimmed and not display.is_off():
            display.on()
            dimmed = False

        # ── Persist settings every 60s ─────────────────────────────────────
        if time.ticks_diff(now, last_persist_tick) >= 60_000:
            settings["steps"] = shared["steps"]
            settings["ble_always"] = shared.get("ble_always", False)
            save_settings(settings)
            last_persist_tick = now

        # Small sleep to avoid 100% CPU on the SPI bus
        time.sleep_ms(10)


main()
