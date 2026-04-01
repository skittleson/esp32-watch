# ESP32 Smartwatch

MicroPython smartwatch firmware and BLE companion PWA for the [Waveshare ESP32-S3-Touch-LCD-1.28](https://www.waveshare.com/esp32-s3-touch-lcd-1.28.htm).

## Repository Layout

```
firmware/          Pre-built LVGL MicroPython firmware binary
watch_py/          MicroPython watch source (screens, BLE, HAL drivers)
pwa/               Progressive Web App — BLE companion UI
tests/             Test suite
BLE_API.md         Full BLE GATT characteristic reference
WATCH_CASE.md      3D-printable watch case documentation
watch_case.py      CadQuery watch case generator
```

## Quick Start

### Prerequisites

- [Node.js](https://nodejs.org/) (for `npx`)
- [mkcert](https://github.com/FiloSottile/mkcert) (for local TLS certificates)
- **Chrome/Edge:** Enable Web Bluetooth by navigating to `chrome://flags/#enable-experimental-web-platform-features`, setting it to **Enabled**, and relaunching the browser

### 1. Generate TLS certificates (first time only)

Web Bluetooth requires HTTPS. Generate a locally-trusted certificate with mkcert:

```bash
mkcert -install
mkcert -cert-file pwa/cert.pem -key-file pwa/key.pem localhost 127.0.0.1
```

### 2. Run the PWA locally

```bash
npx http-server pwa -p 8443 --ssl --cert pwa/cert.pem --key pwa/key.pem
```

Open <https://localhost:8443> in Chrome or Edge.

### 3. Connect to the watch

1. Double-tap the watch face to start BLE advertising (60s timeout)
2. Click **Connect** in the PWA
3. Select **ESP32Watch** from the browser Bluetooth picker

## Further Documentation

- [`watch_py/README.md`](watch_py/README.md) — Firmware build, flash, upload, fonts, hardware quirks
- [`pwa/README.md`](pwa/README.md) — PWA features, browser compatibility, install
- [`BLE_API.md`](BLE_API.md) — Complete BLE GATT API reference
