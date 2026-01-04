# Build & Release (Windows EXE)

This document is for maintainers who build the Windows binary and publish GitHub Releases.

## 1) Build mode recommendation
Prefer **onedir** for classroom distribution:
- faster start
- easier resource handling (audio, static files)

## 2) Prepare environment
```bat
cd satfinder-pass-simulator
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
````

## 3) Ensure resources exist

Place your sound file as either:

* `ding.mp3` next to `app.py`, or
* `assets\ding.mp3`

## 4) PyInstaller build (onedir)

Windows uses `;` as the separator for `--add-data` destinations. ([plainenglish.io][2])

Example (bundle both possible locations; you can keep only one if you prefer):

```bat
rmdir /s /q build
rmdir /s /q dist
del /q *.spec

pyinstaller --clean --noconsole --onedir --name SatellitePassWeb ^
  --add-data "ding.mp3;." ^
  --add-data "assets\ding.mp3;assets" ^
  app.py
```

Output folder:

* `dist\SatellitePassWeb\SatellitePassWeb.exe` and related files

## 5) Create a ZIP for distribution

Zip the whole `dist\SatellitePassWeb\` folder.

## 6) Publish GitHub Release

Releases are based on Git tags. ([GitHub Docs][4])

High-level steps:

1. Create a version tag (e.g. `v1.0.0`)
2. Create a new GitHub Release from that tag
3. Upload the ZIP asset (the built onedir folder zipped)

## 7) Notes on onefile

In onefile mode, PyInstaller unpacks bundled files to a temporary directory and exposes it via `sys._MEIPASS`. ([pyinstaller.org][3])
Our `resource_path()` helper in `app.py` is designed to work in both dev mode and packaged mode.

````
