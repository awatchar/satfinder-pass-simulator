# SatFinder Pass Simulator (Pelco-D Pan/Tilt) — Web UI + RS485

Educational satellite pass simulator: a kid-friendly web UI controlling a Pelco-D pan-tilt spotlight over RS485 (Flask).

This repository provides a **classroom demonstration tool** that drives a Pelco-D (extended absolute) pan-tilt device over **RS485**, allowing teachers and students to run a smooth “satellite pass” motion using only a browser.

> Target environment: Windows 11 + USB-RS485 adapter + Pelco-D pan/tilt device  
> UI: minimal “kid-friendly” single page with **Time (minutes)**, **Start**, **Home**, **Stop**  
> Audio: plays `ding.mp3` every 10 seconds during motion (optional resource)

---

## Why this project exists

Many schools can explain satellite passes using slides or videos, but students learn more effectively when they can **see a moving “beam”** that mimics azimuth/elevation behavior. This simulator supports:
- tactile and visual learning
- repeatable classroom demonstrations (5–15 minutes recommended)
- minimal operator workload (no TLE/IMU required in the first version)

---

## Key features

- **Web Interface (Flask)**: one-page UI (Time, Start, Home, Stop)
- **Pelco-D extended absolute** commands:
  - Pan (AZ) command: `0x4B`
  - Tilt (EL) command: `0x4D`
- **Smooth motion model**:
  - AZ sweep with cosine easing (smooth start/stop)
  - EL arc with sine profile (horizon → max → horizon)
  - EMA target filtering
  - Coordinated motion step (one factor `k` drives both axes)
  - Pair sending (AZ+EL in one write) for quasi-simultaneous update
- **Safety clamps**:
  - Avoid rear seam zone by clamping AZ to safe range
  - Clamp EL between horizon and max
- **Fast Home**:
  - Home returns AZ+EL as fast as possible (commanded directly, repeated briefly)
- **Audio cue**:
  - Plays `ding.mp3` every 10 seconds while running

---

## Demo workflow (for classroom)

1. Power on the PTZ/pan-tilt device (Pelco-D).
2. Connect USB-RS485 to the PC.
3. Run the application (from binary release or from source).
4. Open browser: `http://127.0.0.1:5000`
5. Set time (default 5 minutes; recommended 5–15).
6. Press **Start**. Press **Home** anytime to return to North + Horizon.

---

## Hardware & assembly

See: **docs/HARDWARE.md**  
This includes:
- recommended parts (PTZ/pan-tilt, power supply, USB-RS485, mounting)
- RS485 wiring guidance (A/B polarity and best practices)
- classroom calibration method (define “North of the classroom”)

---

## Install & run (Binary from Releases)

See: **docs/INSTALL_BINARY.md**  
This is the recommended method for schools / non-developer machines.

---

## Install & run (From source)

### Requirements
- Python 3.10+ recommended
- Windows 11
- USB-RS485 driver installed

### Setup
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
````

Open: `http://127.0.0.1:5000`

---

## Configuration parameters (in app.py)

Important calibration and safety parameters are at the top of `app.py`, e.g.

* `BAUD = 9600`
* `AZ_HOME_DEG = 175.0`
* `EL_HORIZON_DEG = 32.0`
* `EL_MAX_DEG = 55.0`
* `AZ_MIN_SAFE = 15.0`, `AZ_MAX_SAFE = 335.0`
* `PORT_KEYWORD = "USB Serial Port"`

---

## Building the Windows EXE (for maintainers)

See: **docs/BUILD_RELEASE.md**
Includes PyInstaller commands, bundling `ding.mp3`, and how to publish GitHub Releases.

---

## Safety & classroom notes

* Pan/tilt devices can move quickly. Keep hands/objects clear.
* Use stable mounting; avoid glare directly into eyes.
* Always verify the defined “North” reference in your classroom and re-check Home alignment.

---

## About This Project

โครงการส่งเสริมการเรียนรู้ทางด้านโทรคมนาคมในโรงเรียนทั่วประเทศ
โดย คณะวิศวกรรมศาสตร์ มหาวิทยาลัยธรรมศาสตร์ และ สถาบันวิจัยและให้คำปรึกษาแห่งมหาวิทยาลัยธรรมศาสตร์
สนับสนุนโดย กองทุนวิจัยและพัฒนากิจการกระจายเสียง กิจการโทรทัศน์ และกิจการโทรคมนาคม เพื่อประโยชน์สาธารณะ

---

## License

* MIT for code
* Ensure `ding.mp3` is either your own, properly licensed, or replaced with a CC0/royalty-free sound.

## 6) Offline operation
This app runs locally on `127.0.0.1`. No Internet is required after installation.
