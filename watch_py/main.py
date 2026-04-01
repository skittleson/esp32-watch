# main.py — ESP32-S3 Watch main loop (LVGL edition)
#
# Architecture:
#   Main thread (Core 1):
#     - LVGL init + display/touch init
#     - TaskHandler drives LVGL rendering (replaces dirty-flag while True)
#     - Thin while True: touch poll → gesture → screen nav → alarm check →
#       sleep timer → settings persist
#     - All LVGL widget updates happen inside screen.update() called by mgr.tick()
#       which is scheduled via a lv.timer (inside TaskHandler loop)
#
#   _thread (Core 0): BLE IRQ + timeout/notify (unchanged from gc9a01 version)
#
# Key difference from gc9a01 version:
#   - No manual tft.fill() / tft.text() calls anywhere
#   - No dirty flags — LVGL handles invalidation automatically
#   - TaskHandler.tick() replaces time.sleep_ms(10) busy loop
#   - Screen objects own lv.screen instances created before lv.screen_load()

import time
import ujson
import _thread

import lvgl as lv
import task_handler  # lvgl_micropython task handler

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
        "ble_active": settings.get("ble_always", False),
        "ble_always": settings.get("ble_always", False),
    }

    # ── Display + LVGL init ────────────────────────────────────────────────
    from hal.display import Display

    display = Display()

    # Restore saved brightness
    saved_br = settings.get("brightness", None)
    if saved_br is not None:
        display.set_brightness_from_ble(saved_br)

    # ── Touch init — creates LVGL i2c bus (sole master on SDA=6, SCL=7) ───────
    from hal.touch import CST816S

    touch = CST816S(rst_pin=PIN_TP_RST, int_pin=PIN_TP_INT)

    # ── IMU + Battery — IMU shares the i2c bus via thin adapter ───────────────
    from hal.imu import QMI8658
    from hal.battery import Battery

    # Wrap LVGL i2c bus so IMU can call readfrom_mem / writeto_mem
    class I2CAdapter:
        """Adapts i2c.I2C.Bus to machine.I2C-like readfrom_mem/writeto_mem API."""

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
    imu = QMI8658(i2c)
    imu.set_steps(shared["steps"])
    bat = Battery()
    shared["bat_pct"] = bat.read_percent()

    # ── Create LVGL screens + screen objects ───────────────────────────────
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

    # ── TaskHandler — drives LVGL rendering loop ───────────────────────────
    # duration=10ms is comfortable for this display; set lower if animations stutter
    th = task_handler.TaskHandler(duration=10)

    # ── BLE (starts _thread internally) ───────────────────────────────────
    from ble.service import ble_watch

    ble_watch.start(shared, display, alarm, mgr, settings)
    if shared["ble_always"]:
        ble_watch.activate()

    print("[WATCH] Running")

    # ── Timing state ───────────────────────────────────────────────────────
    last_activity = time.ticks_ms()
    last_imu_tick = time.ticks_ms()
    last_bat_tick = time.ticks_ms()
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

        # ── Touch gesture poll (for screen navigation) ─────────────────────
        t = touch.poll()
        if t:
            last_activity = now
            dimmed = False
            was_off = display.is_off()
            if was_off:
                display.on()

            if t["gesture"] == "double_click":
                shared["ble_active"] = True
                ble_watch.activate()
                print("[TOUCH] BLE activated")
            elif t["gesture"] != "none" and not was_off:
                prev_fired = alarm._fired
                mgr.handle_gesture(t["gesture"])
                if prev_fired and not alarm._fired:
                    touch.reattach_irq()

        # ── WoM wake ──────────────────────────────────────────────────────
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

        # ── Screen update (widget data) ────────────────────────────────────
        # mgr.tick() calls active_screen.update(shared) which updates LVGL
        # widget properties. TaskHandler drives rendering automatically.
        if not display.is_off():
            mgr.tick(shared)

        # ── Alarm check ────────────────────────────────────────────────────
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

        # Yield to TaskHandler LVGL timer
        time.sleep_ms(5)


main()
