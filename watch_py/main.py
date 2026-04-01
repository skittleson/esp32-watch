# main.py — ESP32-S3 Watch main loop (LVGL edition)
#
# Architecture:
#   Main thread (Core 1):
#     - LVGL init + display/touch init
#     - TaskHandler drives LVGL rendering
#     - Main loop: IMU@20ms, battery@30s, touch gestures, screen updates,
#       alarm check, sleep timer, BLE tick@500ms, settings persist@60s
#
#   BLE:
#     - No _thread — _thread.stack_size() is broken on ESP32-S3 (#16129)
#     - BLE IRQ runs on NimBLE's own FreeRTOS task (always was)
#     - ble_watch.tick() called from main loop every 500ms handles
#       advertising timeout and periodic notifications
#     - Advertises immediately on boot; double-tap re-activates after timeout

import time
import ujson

import lvgl as lv
import task_handler

from config import (
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
    print("[WATCH] Booting LVGL edition...")

    settings = load_settings()

    shared = {
        "steps": settings.get("steps", 0),
        "bat_pct": 100,
        "temp": 0.0,
        "acc": [0.0, 0.0, 0.0],
        "gyro": [0.0, 0.0, 0.0],
        "ble_active": False,
        "ble_always": settings.get("ble_always", False),
    }

    # ── Display + LVGL init ───────────────────────────────────────────────────
    from hal.display import Display

    display = Display()

    saved_br = settings.get("brightness", None)
    if saved_br is not None:
        display.set_brightness_from_ble(saved_br)

    # ── Touch init — creates LVGL i2c bus (sole master on SDA=6, SCL=7) ───────
    from hal.touch import CST816S

    touch = CST816S(rst_pin=PIN_TP_RST, int_pin=PIN_TP_INT)

    # ── IMU + Battery — IMU shares i2c bus via adapter ───────────────────────
    from hal.imu import QMI8658
    from hal.battery import Battery

    class I2CAdapter:
        """Adapts i2c.I2C.Bus to readfrom_mem/writeto_mem for QMI8658."""

        def __init__(self, lvgl_bus, addr):
            import i2c as _i2c

            self._dev = _i2c.I2C.Device(bus=lvgl_bus, dev_id=addr, reg_bits=8)

        def readfrom_mem(self, addr, reg, n):
            tx = bytearray([reg])
            rx = bytearray(n)
            self._dev.write_readinto(tx, rx)
            return bytes(rx)

        def writeto_mem(self, addr, reg, data):
            buf = bytearray([reg]) + bytearray(data)
            self._dev.write(buf)

    imu_i2c = I2CAdapter(touch.get_i2c_bus(), 0x6B)
    imu = QMI8658(imu_i2c)
    imu.set_steps(shared["steps"])
    bat = Battery()
    shared["bat_pct"] = bat.read_percent()

    # ── LVGL screens ─────────────────────────────────────────────────────────
    from screens.clock_face import ClockFace
    from screens.stopwatch import Stopwatch
    from screens.alarm import Alarm
    from screens.manager import ScreenManager

    scr_clock = lv.obj()
    scr_sw = lv.obj()
    scr_alarm = lv.obj()

    clock_face = ClockFace(scr_clock)
    stopwatch = Stopwatch(scr_sw)
    alarm = Alarm(scr_alarm, settings)

    mgr = ScreenManager(clock_face, stopwatch, alarm)
    mgr.set_alarm_indicator(alarm.get_enabled())

    # ── TaskHandler — drives LVGL rendering loop ──────────────────────────────
    th = task_handler.TaskHandler(duration=10)

    # ── BLE — starts advertising immediately, no _thread ─────────────────────
    from ble.service import ble_watch

    ble_watch.start(shared, display, alarm, mgr, settings)

    print("[WATCH] Running")

    # ── Timing state ─────────────────────────────────────────────────────────
    last_activity = time.ticks_ms()
    last_imu_tick = time.ticks_ms()
    last_bat_tick = time.ticks_ms()
    last_ble_tick = time.ticks_ms()
    last_persist_tick = time.ticks_ms()
    dimmed = False

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        now = time.ticks_ms()

        # ── IMU poll at ~50Hz (20ms) ──────────────────────────────────────────
        if time.ticks_diff(now, last_imu_tick) >= 20:
            data = imu.read()
            shared["acc"] = data["acc"]
            shared["gyro"] = data["gyro"]
            shared["temp"] = data["temp"]
            shared["steps"] = data["steps"]
            last_imu_tick = now

        # ── Battery read every 30s ────────────────────────────────────────────
        if time.ticks_diff(now, last_bat_tick) >= 30_000:
            shared["bat_pct"] = bat.read_percent()
            last_bat_tick = now

        # ── BLE tick every 500ms (timeout check + notify) ─────────────────────
        if time.ticks_diff(now, last_ble_tick) >= 500:
            ble_watch.tick(shared)
            last_ble_tick = now

        # ── Touch gesture poll ────────────────────────────────────────────────
        t = touch.poll()
        if t:
            last_activity = now
            dimmed = False
            was_off = display.is_off()
            if was_off:
                display.on()

            if t["gesture"] == "double_click":
                ble_watch.activate()
                print("[TOUCH] BLE re-activated")
            elif t["gesture"] != "none" and not was_off:
                prev_fired = alarm._fired
                mgr.handle_gesture(t["gesture"])
                if prev_fired and not alarm._fired:
                    touch.reattach_irq()

        # ── WoM wake ─────────────────────────────────────────────────────────
        if shared.get("wom_wake"):
            shared["wom_wake"] = False
            last_activity = now
            dimmed = False
            if display.is_off():
                display.on()

        # ── Screen update ─────────────────────────────────────────────────────
        if not display.is_off():
            mgr.tick(shared)

        # ── Alarm check ───────────────────────────────────────────────────────
        if alarm.should_fire():
            alarm.fire()
            display.on()
            last_activity = now
            dimmed = False
            mgr.goto(SCREEN_ALARM)

        prev_fired = alarm._fired
        if alarm._fired:
            alarm.tick()
        if prev_fired and not alarm._fired:
            touch.reattach_irq()

        # ── Sleep timer ───────────────────────────────────────────────────────
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

        # ── Persist settings every 60s ────────────────────────────────────────
        if time.ticks_diff(now, last_persist_tick) >= 60_000:
            settings["steps"] = shared["steps"]
            settings["ble_always"] = shared.get("ble_always", False)
            save_settings(settings)
            last_persist_tick = now

        # Yield to TaskHandler LVGL timer
        time.sleep_ms(5)


main()
