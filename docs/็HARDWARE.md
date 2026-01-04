# Hardware & Assembly Guide (Pelco-D Pan/Tilt + RS485)

This document describes a practical classroom build for the SatFinder Pass Simulator.

## 1) Hardware overview

### Minimum required
1. **Pelco-D compatible pan/tilt (PTZ/pan-tilt head)**
   - Must support **RS485** and **Pelco-D**
   - Must support **extended absolute pan/tilt** commands (Pan `0x4B`, Tilt `0x4D`) in your tested setup
2. **USB-RS485 adapter** (the same model you already tested)
3. **Power supply** for the pan/tilt device (per device rating)
4. **PC / Laptop (Windows 11)**

### Recommended for classroom use
- Stable tripod / wall mount / lab stand
- A small spotlight or flashlight mount (securely fixed)
- Cable strain relief (zip ties / cable clips)
- Optional: label “North” direction on classroom floor/wall

---

## 2) RS485 wiring (general best practice)

RS485 typically uses a differential pair:
- `A` (also called `D+` on some adapters)
- `B` (also called `D-` on some adapters)

**Rule**: connect **A ↔ A** and **B ↔ B**.
If nothing works (no response), one common cause is A/B swapped.
- Safest debug: swap A/B once (only once) and retry.

### Ground reference (optional but helpful)
Some devices/adapters expose GND/COM.
- If available, connect **GND ↔ GND** (optional) to reduce noise issues.
- Do not mix power ground in unsafe ways; follow your device’s manual.

---

## 3) Device configuration

Your device was tested with:
- RS485 control enabled
- DIP switch setting: **1 and 8 ON, others OFF** (your tested setup)

Because DIP mapping differs across manufacturers:
- Document the exact device model & manual page later (optional improvement)
- Keep a photo of DIP switch position in `docs/images/` (recommended)

---

## 4) Mechanical assembly (classroom-ready)

1. Mount the pan/tilt device on a stable base (tripod or fixed stand).
2. Attach the flashlight/spotlight securely:
   - avoid wobble and center-of-mass offset
   - use a bracket or clamp; do not rely on tape alone
3. Route cables with strain relief:
   - avoid twisting RS485 wires at extremes of motion
   - keep power and signal wires separated where possible

---

## 5) Classroom calibration concept (important)

The simulator uses **device degrees** (as your PTZ defines them).
Your confirmed calibration in software:
- “North of classroom” = `AZ_HOME_DEG = 175.0`
- “Horizon/level” = `EL_HORIZON_DEG = 32.0`
- `EL_MAX_DEG = 55.0` (max elevation used for the demo arc)

### Recommended operational rule
- Ask students to physically install the unit so that:
  - the device’s “Home” points to a known reference direction
  - the classroom’s **North direction** is consistent

### Quick calibration method (for teachers)
1. Power on device.
2. Click **Home** in the UI.
3. Adjust the physical device orientation (rotate the base/tripod) until the beam points to the classroom’s “North marker”.
4. Confirm beam is near horizon/level at Home.
5. Start a 5-minute pass and confirm motion is within safe limits.

---

## 6) Safety notes

- Do not allow students to put hands near moving joints.
- Avoid shining light into eyes.
- Ensure cables do not snag during motion.
- Keep a “Stop/Home” operator ready during the first run.
