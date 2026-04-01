// ============================================================
// ESP32 Watch BLE Companion — app.js
// Web Bluetooth GATT client for ESP32-S3 MicroPython Watch
// ============================================================

(() => {
  'use strict';

  // ── BLE UUIDs ──────────────────────────────────────────────
  const UUID = {
    // Standard services
    CURRENT_TIME:    0x1805,
    BATTERY:         0x180F,
    DEVICE_INFO:     0x180A,
    ENV_SENSING:     0x181A,
    // Custom service
    CUSTOM:          '0000aa00-0000-1000-8000-00805f9b34fb',

    // Standard characteristics
    CURRENT_TIME_CHAR: 0x2A2B,
    LOCAL_TIME_INFO:   0x2A0F,
    BATTERY_LEVEL:     0x2A19,
    FW_REVISION:       0x2A26,
    TEMPERATURE:       0x2A6E,

    // Custom characteristics
    ALARM_TIME:      '0000aa01-0000-1000-8000-00805f9b34fb',
    ALARM_ENABLE:    '0000aa02-0000-1000-8000-00805f9b34fb',
    BRIGHTNESS:      '0000aa03-0000-1000-8000-00805f9b34fb',
    STEP_COUNT:      '0000aa04-0000-1000-8000-00805f9b34fb',
    BLE_MODE:        '0000aa05-0000-1000-8000-00805f9b34fb',
    WIFI_SSID:       '0000aa06-0000-1000-8000-00805f9b34fb',
    WIFI_PASS:       '0000aa07-0000-1000-8000-00805f9b34fb',
    WIFI_SYNC:       '0000aa08-0000-1000-8000-00805f9b34fb',
    SEDENTARY:       '0000aa09-0000-1000-8000-00805f9b34fb',
    NOTIFICATION:    '0000aa0a-0000-1000-8000-00805f9b34fb',
    STEP_GOAL:       '0000aa0b-0000-1000-8000-00805f9b34fb',
  };

  // ── State ──────────────────────────────────────────────────
  let device = null;
  let server = null;
  const chars = {};  // keyed by UUID string

  // ── DOM refs ───────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const statusText   = $('#status-text');
  const btnConnect   = $('#btn-connect');
  const dashboard    = $('#dashboard');

  // ── Helpers ────────────────────────────────────────────────
  const enc = new TextEncoder();
  const dec = new TextDecoder();

  function toast(msg, type = '') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    $('#toast-container').appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  function setStatus(state, text) {
    statusText.textContent = text;
    statusText.className = `status-pill ${state}`;
  }

  function setCardsEnabled(enabled) {
    dashboard.querySelectorAll('.card').forEach(c => {
      c.classList.toggle('disabled', !enabled);
    });
    // Disable interactive elements
    dashboard.querySelectorAll('button, input, select').forEach(el => {
      el.disabled = !enabled;
    });
  }

  function pad(n) { return String(n).padStart(2, '0'); }

  // ── Check Web Bluetooth support ────────────────────────────
  // Show a warning but don't disable the connect button — the user
  // may be on a browser/context where the API becomes available after
  // a user gesture, or they may want to test the UI layout.
  if (!navigator.bluetooth) {
    const secure = window.isSecureContext ? 'yes' : 'no';
    const proto = location.protocol;
    const ua = navigator.userAgent;
    const isChromium = /Chrome\//.test(ua) && !/Edg\//.test(ua);
    const isEdge = /Edg\//.test(ua);
    const isFirefox = /Firefox\//.test(ua);
    const isSafari = /Safari\//.test(ua) && !/Chrome\//.test(ua);
    let browser = isChromium ? 'Chrome' : isEdge ? 'Edge' : isFirefox ? 'Firefox' : isSafari ? 'Safari' : 'Unknown';
    const diag = `Secure context: ${secure} | Protocol: ${proto} | Browser: ${browser}`;
    console.warn('[BLE] Not available.', diag);

    let hint = '';
    if (isFirefox) hint = 'Firefox does not support Web Bluetooth. Use Chrome or Edge.';
    else if (isSafari) hint = 'Safari does not support Web Bluetooth. Use Chrome or Edge.';
    else if (!window.isSecureContext) hint = `Page is not a secure context (${proto}). Serve over HTTPS or use localhost.`;
    else hint = `Web Bluetooth not detected. Try chrome://flags/#enable-web-bluetooth or use Chrome/Edge.`;

    $('#ble-unsupported').textContent = hint + ` (${diag})`;
    $('#ble-unsupported').hidden = false;
  }

  // Disable cards initially
  setCardsEnabled(false);

  // ── Connect / Disconnect ───────────────────────────────────
  btnConnect.addEventListener('click', async () => {
    if (device && device.gatt.connected) {
      device.gatt.disconnect();
      return;
    }
    if (!navigator.bluetooth) {
      toast('Web Bluetooth not available — use Chrome/Edge/Opera over HTTPS or localhost', 'error');
      return;
    }
    try {
      setStatus('connecting', 'Scanning...');
      btnConnect.disabled = true;

      device = await navigator.bluetooth.requestDevice({
        filters: [{ name: 'ESP32Watch' }],
        optionalServices: [
          UUID.CURRENT_TIME,
          UUID.BATTERY,
          UUID.DEVICE_INFO,
          UUID.ENV_SENSING,
          UUID.CUSTOM,
        ],
      });

      device.addEventListener('gattserverdisconnected', onDisconnect);

      setStatus('connecting', 'Connecting...');
      server = await device.gatt.connect();

      setStatus('connected', `Connected: ${device.name}`);
      btnConnect.querySelector('span').textContent = 'Disconnect';
      btnConnect.classList.add('btn-disconnect');
      btnConnect.disabled = false;

      await discoverCharacteristics();
      setCardsEnabled(true);
      await readAllInitial();
      await subscribeNotifications();

      toast('Connected to watch', 'success');
    } catch (err) {
      console.error(err);
      setStatus('disconnected', 'Disconnected');
      btnConnect.querySelector('span').textContent = 'Connect';
      btnConnect.classList.remove('btn-disconnect');
      btnConnect.disabled = false;
      if (err.name !== 'NotFoundError') {
        toast(`Connection failed: ${err.message}`, 'error');
      }
    }
  });

  function onDisconnect() {
    setStatus('disconnected', 'Disconnected');
    btnConnect.querySelector('span').textContent = 'Connect';
    btnConnect.classList.remove('btn-disconnect');
    btnConnect.disabled = false;
    setCardsEnabled(false);
    Object.keys(chars).forEach(k => delete chars[k]);
    server = null;
    toast('Watch disconnected');
  }

  // ── Discover all characteristics ───────────────────────────
  async function discoverCharacteristics() {
    const services = [
      { svc: UUID.CURRENT_TIME, chars: [UUID.CURRENT_TIME_CHAR, UUID.LOCAL_TIME_INFO] },
      { svc: UUID.BATTERY,      chars: [UUID.BATTERY_LEVEL] },
      { svc: UUID.DEVICE_INFO,  chars: [UUID.FW_REVISION] },
      { svc: UUID.ENV_SENSING,  chars: [UUID.TEMPERATURE] },
      { svc: UUID.CUSTOM,       chars: [
        UUID.ALARM_TIME, UUID.ALARM_ENABLE, UUID.BRIGHTNESS,
        UUID.STEP_COUNT, UUID.BLE_MODE, UUID.WIFI_SSID,
        UUID.WIFI_PASS, UUID.WIFI_SYNC, UUID.SEDENTARY,
        UUID.NOTIFICATION, UUID.STEP_GOAL,
      ]},
    ];

    for (const { svc, chars: charUuids } of services) {
      try {
        const service = await server.getPrimaryService(svc);
        for (const uuid of charUuids) {
          try {
            chars[uuid] = await service.getCharacteristic(uuid);
          } catch (e) {
            console.warn(`Char ${uuid} not found`, e);
          }
        }
      } catch (e) {
        console.warn(`Service ${svc} not found`, e);
      }
    }
  }

  // ── Read helpers ───────────────────────────────────────────
  async function readChar(uuid) {
    const c = chars[uuid];
    if (!c) return null;
    try {
      return await c.readValue();
    } catch (e) {
      console.warn(`Read ${uuid} failed`, e);
      return null;
    }
  }

  async function writeChar(uuid, data) {
    const c = chars[uuid];
    if (!c) { toast('Characteristic not available', 'error'); return false; }
    try {
      await c.writeValueWithResponse(data);
      return true;
    } catch (e) {
      // Fallback for write-without-response characteristics
      try {
        await c.writeValueWithoutResponse(data);
        return true;
      } catch (e2) {
        console.error(`Write ${uuid} failed`, e, e2);
        toast(`Write failed: ${e.message}`, 'error');
        return false;
      }
    }
  }

  // ── Read all initial values ────────────────────────────────
  async function readAllInitial() {
    // Battery
    const batt = await readChar(UUID.BATTERY_LEVEL);
    if (batt) updateBattery(batt);

    // Firmware
    const fw = await readChar(UUID.FW_REVISION);
    if (fw) $('#fw-version').textContent = dec.decode(fw);

    // Temperature
    const temp = await readChar(UUID.TEMPERATURE);
    if (temp) updateTemp(temp);

    // Alarm time
    const alarmTime = await readChar(UUID.ALARM_TIME);
    if (alarmTime) {
      $('#alarm-hour').value = alarmTime.getUint8(0);
      $('#alarm-min').value = alarmTime.getUint8(1);
    }

    // Alarm enable
    const alarmEn = await readChar(UUID.ALARM_ENABLE);
    if (alarmEn) {
      const on = alarmEn.getUint8(0) === 1;
      $('#alarm-enabled').checked = on;
      $('#alarm-toggle-label').textContent = on ? 'On' : 'Off';
      $('#alarm-badge').textContent = on ? 'ON' : 'OFF';
    }

    // Brightness
    const bright = await readChar(UUID.BRIGHTNESS);
    if (bright) {
      const val = bright.getUint8(0);
      $('#brightness-slider').value = val;
      $('#brightness-badge').textContent = val;
    }

    // Step count
    const steps = await readChar(UUID.STEP_COUNT);
    if (steps) updateSteps(steps);

    // Step goal
    const goal = await readChar(UUID.STEP_GOAL);
    if (goal) {
      const g = goal.getUint16(0, true);
      $('#input-step-goal').value = g;
      $('#step-goal-display').textContent = g.toLocaleString();
      updateStepProgress();
    }

    // BLE mode
    const bleMode = await readChar(UUID.BLE_MODE);
    if (bleMode) {
      const on = bleMode.getUint8(0) === 1;
      $('#ble-mode-toggle').checked = on;
      $('#ble-mode-desc').textContent = on ? 'Always-on (higher battery drain)' : 'Timeout after 60s on battery';
    }

    // WiFi SSID
    const ssid = await readChar(UUID.WIFI_SSID);
    if (ssid) {
      const s = dec.decode(ssid);
      if (s && s !== '\x00') $('#wifi-ssid').value = s;
    }

    // WiFi sync status
    const wifiSync = await readChar(UUID.WIFI_SYNC);
    if (wifiSync) {
      const configured = wifiSync.getUint8(0) === 1;
      $('#wifi-badge').textContent = configured ? 'Configured' : 'Not Set';
      $('#wifi-status').textContent = configured ? 'WiFi credentials saved on watch' : 'No WiFi configured';
    }

    // Sedentary
    const sed = await readChar(UUID.SEDENTARY);
    if (sed) updateSedentary(sed);
  }

  // ── Subscribe to notifications ─────────────────────────────
  async function subscribeNotifications() {
    // Battery
    if (chars[UUID.BATTERY_LEVEL]) {
      try {
        chars[UUID.BATTERY_LEVEL].addEventListener('characteristicvaluechanged', (e) => {
          updateBattery(e.target.value);
        });
        await chars[UUID.BATTERY_LEVEL].startNotifications();
      } catch (e) { console.warn('Battery notify failed', e); }
    }

    // Steps
    if (chars[UUID.STEP_COUNT]) {
      try {
        chars[UUID.STEP_COUNT].addEventListener('characteristicvaluechanged', (e) => {
          updateSteps(e.target.value);
        });
        await chars[UUID.STEP_COUNT].startNotifications();
      } catch (e) { console.warn('Steps notify failed', e); }
    }

    // Sedentary
    if (chars[UUID.SEDENTARY]) {
      try {
        chars[UUID.SEDENTARY].addEventListener('characteristicvaluechanged', (e) => {
          updateSedentary(e.target.value);
          toast('Sedentary alert received!', 'error');
        });
        await chars[UUID.SEDENTARY].startNotifications();
      } catch (e) { console.warn('Sedentary notify failed', e); }
    }
  }

  // ── Update UI functions ────────────────────────────────────
  function updateBattery(dv) {
    const pct = dv.getUint8(0);
    $('#battery-badge').textContent = `${pct}%`;
    const fill = $('#battery-fill');
    fill.style.width = `${pct}%`;
    fill.classList.remove('low', 'mid');
    if (pct <= 15) fill.classList.add('low');
    else if (pct <= 40) fill.classList.add('mid');
    $('#battery-status').textContent = pct === 100 ? 'Charging / USB connected' : `${pct}% remaining`;
  }

  function updateSteps(dv) {
    const count = dv.getUint32(0, true);
    $('#step-count').textContent = count.toLocaleString();
    $('#steps-badge').textContent = count.toLocaleString();
    updateStepProgress();
  }

  function updateStepProgress() {
    const count = parseInt($('#step-count').textContent.replace(/,/g, '')) || 0;
    const goal = parseInt($('#step-goal-display').textContent.replace(/,/g, '')) || 7000;
    const pct = Math.min(100, (count / goal) * 100);
    $('#steps-fill').style.width = `${pct}%`;
  }

  function updateTemp(dv) {
    const raw = dv.getInt16(0, true);
    const celsius = (raw / 100).toFixed(1);
    $('#temp-value').innerHTML = `${celsius}&deg;C`;
  }

  function updateSedentary(dv) {
    const epoch = dv.getUint32(0, true);
    if (epoch === 0) {
      $('#sedentary-time').textContent = 'Never';
    } else {
      const d = new Date(epoch * 1000);
      $('#sedentary-time').textContent = d.toLocaleString();
    }
  }

  // ── Time Sync ──────────────────────────────────────────────
  $('#btn-sync-time').addEventListener('click', async () => {
    const now = new Date();
    const buf = new ArrayBuffer(7);
    const view = new DataView(buf);
    view.setUint16(0, now.getFullYear(), true);  // year LE
    view.setUint8(2, now.getMonth() + 1);         // month 1-12
    view.setUint8(3, now.getDate());               // day
    view.setUint8(4, now.getHours());              // hour
    view.setUint8(5, now.getMinutes());            // minute
    view.setUint8(6, now.getSeconds());            // second

    if (await writeChar(UUID.CURRENT_TIME_CHAR, buf)) {
      // Show the synced time on the card
      $('#watch-time').textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      $('#watch-date').textContent = `${now.getFullYear()}/${pad(now.getMonth()+1)}/${pad(now.getDate())}`;
      toast('Time synced to phone', 'success');
    }
  });

  // ── Alarm ──────────────────────────────────────────────────
  $('#btn-set-alarm').addEventListener('click', async () => {
    const hour = Math.max(0, Math.min(23, parseInt($('#alarm-hour').value) || 0));
    const min  = Math.max(0, Math.min(59, parseInt($('#alarm-min').value) || 0));
    const enabled = $('#alarm-enabled').checked;

    // Set alarm time
    const timeBuf = new Uint8Array([hour, min]);
    const timeOk = await writeChar(UUID.ALARM_TIME, timeBuf);

    // Set alarm enable
    const enBuf = new Uint8Array([enabled ? 1 : 0]);
    const enOk = await writeChar(UUID.ALARM_ENABLE, enBuf);

    if (timeOk && enOk) {
      $('#alarm-badge').textContent = enabled ? 'ON' : 'OFF';
      toast(`Alarm set to ${pad(hour)}:${pad(min)} (${enabled ? 'ON' : 'OFF'})`, 'success');
    }
  });

  $('#alarm-enabled').addEventListener('change', (e) => {
    $('#alarm-toggle-label').textContent = e.target.checked ? 'On' : 'Off';
  });

  // ── Brightness ─────────────────────────────────────────────
  let brightnessTimeout = null;
  $('#brightness-slider').addEventListener('input', (e) => {
    const val = parseInt(e.target.value);
    $('#brightness-badge').textContent = val;

    // Debounce writes to avoid flooding BLE
    clearTimeout(brightnessTimeout);
    brightnessTimeout = setTimeout(async () => {
      const buf = new Uint8Array([val]);
      if (await writeChar(UUID.BRIGHTNESS, buf)) {
        toast(`Brightness: ${val}`, 'success');
      }
    }, 200);
  });

  // ── Temperature ────────────────────────────────────────────
  $('#btn-read-temp').addEventListener('click', async () => {
    const temp = await readChar(UUID.TEMPERATURE);
    if (temp) {
      updateTemp(temp);
      toast('Temperature updated', 'success');
    }
  });

  // ── Step Goal ──────────────────────────────────────────────
  $('#btn-set-goal').addEventListener('click', async () => {
    const goal = Math.max(100, Math.min(65535, parseInt($('#input-step-goal').value) || 7000));
    const buf = new ArrayBuffer(2);
    new DataView(buf).setUint16(0, goal, true);

    if (await writeChar(UUID.STEP_GOAL, buf)) {
      $('#step-goal-display').textContent = goal.toLocaleString();
      updateStepProgress();
      toast(`Step goal: ${goal.toLocaleString()}`, 'success');
    }
  });

  // ── Notification ───────────────────────────────────────────
  $('#btn-send-notify').addEventListener('click', async () => {
    const text = $('#notify-text').value.trim();
    if (!text) { toast('Enter a message first', 'error'); return; }
    const data = enc.encode(text.substring(0, 100));
    if (await writeChar(UUID.NOTIFICATION, data)) {
      toast('Notification sent', 'success');
      $('#notify-text').value = '';
    }
  });

  $('#btn-clear-notify').addEventListener('click', async () => {
    const data = new Uint8Array([0]);
    if (await writeChar(UUID.NOTIFICATION, data)) {
      toast('Notification cleared', 'success');
    }
  });

  // Allow Enter key to send notification
  $('#notify-text').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') $('#btn-send-notify').click();
  });

  // ── WiFi & NTP ─────────────────────────────────────────────
  $('#btn-save-wifi').addEventListener('click', async () => {
    const ssid = $('#wifi-ssid').value.trim();
    const pass = $('#wifi-pass').value;

    if (!ssid) { toast('Enter an SSID', 'error'); return; }

    let ok = true;
    // Write SSID
    ok = ok && await writeChar(UUID.WIFI_SSID, enc.encode(ssid));
    // Write password
    if (pass) {
      ok = ok && await writeChar(UUID.WIFI_PASS, enc.encode(pass));
    }

    if (ok) {
      $('#wifi-badge').textContent = 'Configured';
      $('#wifi-status').textContent = 'WiFi credentials saved on watch';
      toast('WiFi saved', 'success');
    }
  });

  $('#btn-ntp-sync').addEventListener('click', async () => {
    toast('Triggering NTP sync...');
    const buf = new Uint8Array([1]);
    if (await writeChar(UUID.WIFI_SYNC, buf)) {
      toast('NTP sync triggered — watch will connect to WiFi', 'success');
    }
  });

  // ── BLE Mode ───────────────────────────────────────────────
  $('#ble-mode-toggle').addEventListener('change', async (e) => {
    const on = e.target.checked;
    const buf = new Uint8Array([on ? 1 : 0]);
    if (await writeChar(UUID.BLE_MODE, buf)) {
      $('#ble-mode-desc').textContent = on ? 'Always-on (higher battery drain)' : 'Timeout after 60s on battery';
      toast(`BLE mode: ${on ? 'always-on' : 'timeout'}`, 'success');
    } else {
      // Revert toggle on failure
      e.target.checked = !on;
    }
  });

  // ── Service Worker Registration ────────────────────────────
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(console.warn);
  }

})();
