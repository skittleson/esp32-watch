# ESP32 Watch — BLE Companion PWA

A Progressive Web App for configuring and monitoring the ESP32-S3 smartwatch over Bluetooth Low Energy.

## Browser Requirements

Web Bluetooth is required. Supported browsers:

| Browser | Desktop | Android | iOS |
|---------|---------|---------|-----|
| Chrome  | Yes     | Yes     | No  |
| Edge    | Yes     | Yes     | No  |
| Opera   | Yes     | Yes     | No  |
| Firefox | No      | No      | No  |
| Safari  | No      | No      | No  |

### Linux Setup (Chrome/Edge)

Web Bluetooth is **disabled by default** on Linux. To enable it:

1. Open `chrome://flags/#enable-experimental-web-platform-features`
2. Set to **Enabled**
3. Relaunch the browser

### HTTPS Requirement

Web Bluetooth requires a **secure context**. This means HTTPS or `localhost`.

## Serving the App

### 1. Generate a TLS certificate with mkcert

```bash
# Install mkcert if needed: https://github.com/nicedoc/mkcert
mkcert -install

# Generate cert for your hostname (add it to /etc/hosts first)
mkcert -cert-file pwa/cert.pem -key-file pwa/key.pem esp32app localhost 127.0.0.1
```

Add your hostname to `/etc/hosts` if not already there:

```
127.0.0.1  esp32app
```

### 2. Start the HTTPS server

```bash
npx http-server pwa -p 8443 --ssl --cert pwa/cert.pem --key pwa/key.pem
```

### 3. Open in browser

Navigate to `https://esp32app:8443` (or `https://localhost:8443`).

## Connecting to the Watch

1. **Double-tap** the watch face to start BLE advertising (times out after 60s)
2. Click **Connect** in the PWA
3. Select **ESP32Watch** from the browser's Bluetooth picker
4. All cards will populate with live data from the watch

## Features

| Card | Description | BLE Characteristics |
|------|-------------|-------------------|
| **Time** | Sync phone time to watch RTC | `0x2A2B` (write) |
| **Battery** | Live battery %, charging state | `0x2A19` (read/notify) |
| **Steps** | Step count with goal progress | `AA04` (read/notify), `AA0B` (read/write) |
| **Alarm** | Set alarm time, enable/disable | `AA01`, `AA02` (read/write) |
| **Brightness** | Backlight slider (0-255) | `AA03` (read/write) |
| **Temperature** | IMU die temperature readout | `0x2A6E` (read) |
| **Notification** | Push text messages to watch | `AA0A` (write) |
| **WiFi & NTP** | Configure WiFi, trigger NTP sync | `AA06-AA08` (read/write) |
| **Settings** | BLE mode, firmware version, sedentary alerts | `AA05`, `0x2A26`, `AA09` |

## PWA Install

The app can be installed as a standalone app from the browser menu (Chrome: three-dot menu > "Install app"). Once installed, it works offline via the service worker cache.
