# Install from Binary (Windows 11) — Recommended for Schools

This guide is for running the application using the pre-built EXE from GitHub Releases.

## 1) What you need
- Windows 11 (x64)
- USB-RS485 adapter driver installed (same adapter model you already tested)
- PTZ/pan-tilt powered on and connected via RS485

## 2) Download
1. Go to **Releases** page of this repository.
2. Download the latest asset, e.g. `SatFinderPassSimulator-win11-x64.zip`
3. Extract the ZIP to a folder, for example:
   `C:\SatFinderPassSimulator\`

The extracted folder should include:
- `SatellitePassWeb.exe` (or your chosen name)
- internal PyInstaller files/folders
- `ding.mp3` (either at root or in `assets\ding.mp3` depending on how the release was built)

## 3) Run
1. Double-click the EXE.
2. Open browser and go to:
   `http://127.0.0.1:5000`

(You asked not to auto-open browser, so this is manual.)

## 4) Use
- Default time is 5 minutes.
- Recommended time is 5–15 minutes.
- Click **Home** to return North + Horizon quickly.
- Click **Start** to run pass.
- Click **Stop** to request stop (then Home is executed at end of pass logic).

## 5) Common troubleshooting

### A) “No serial ports found” / ไม่เจออุปกรณ์
- Check Device Manager: COM port must appear.
- Install the USB-RS485 driver for your adapter.
- Try different USB port.

### B) Wrong port auto-detected
The program selects port whose description contains `USB Serial Port`.
If Windows displays a different description for your adapter, update `PORT_KEYWORD` in app.py and rebuild.

### C) No response from pan/tilt
- Check RS485 A/B polarity (swap once).
- Confirm PTZ address matches `ADDR = 0x01` in software.
- Confirm baudrate matches `BAUD = 9600`.

### D) No sound
- Verify `ding.mp3` exists in the distribution folder (or `assets\ding.mp3`).
- Some browsers block audio until user interacts; press Start once (the UI attempts to unlock audio).

## 6) Offline operation
This app runs locally on `127.0.0.1`. No Internet is required after installation.
