# phonelink
Persistent USB Android connection tool for Linux, built for IoT and automation.

`phonelink` acts as a superset of `adb` and `scrcpy`, designed to keep Android phones permanently connected to a Linux host without dropping permissions, and providing easy-to-use commands for device automation.

## Features
- **Auto-healing ADB:** Automatically diagnoses and applies udev rules for 40+ OEM vendor IDs to ensure Linux never drops USB permissions unexpectedly.
- **Persistent Monitor:** Runs in the background, automatically restarting ADB and reconnecting to the phone if the USB connection bounces.
- **Screen Mirroring:** Wraps `scrcpy` to instantly mirror the screen upon connection.
- **Wireless ADB / Wi-Fi IoT:** Pair automatically over Wi-Fi so the phone can be disconnected from USB and placed anywhere (`phonelink wifi`).
- **IoT / Automation Toolkit:**
  - `phonelink wake`: Wakes the screen and attempts a swipe-to-unlock.
  - `phonelink app <pkg>`: Remotely launches any Android package.
  - `phonelink type "text"`: Injects keyboard strokes directly into the device.
  - `phonelink metrics`: Exports battery level, temperature, and charging status as JSON.
  - `phonelink screenshot`: Quietly captures the screen to the PC.
  - `phonelink net`: Prepares reverse-tethering (internet over USB) via `gnirehtet`.
  - `phonelink logs`: Streams logcat, optionally filtering via `--filter` or `--errors`.
  - `phonelink sync <pc_folder> <phone_folder>`: Watches a local folder natively and auto-pushes files on changes.

## Installation

**Via pip (Recommended):**
```bash
pip install phonelink-cli
# Or from source:
pip install .
```

**Manual script install:**
```bash
chmod +x install.sh
./install.sh
```

## Quick Start

1. **Fix ADB permissions permanently (Run once):**
    ```bash
    phonelink fix
    ```
2. **Start the persistent connection monitor:**
    ```bash
    phonelink watch --screen
    ```

Run `phonelink --help` to see all available commands.
