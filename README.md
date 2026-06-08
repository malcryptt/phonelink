# phonelink
Persistent USB Android connection tool (Linux & Windows), built for IoT and automation.

`phonelink` acts as a superset of `adb` and `scrcpy`, designed to keep Android phones permanently connected to a Linux host without dropping permissions, and providing easy-to-use commands for device automation.

## Features
- **PhoneLink Web Dashboard:** Fully-featured unified command center UI accessible from your phone's browser.
- **Remote Laptop Brightness:** Hardware-level laptop screen dimming natively driven via slider.
- **Live Media StreamingSuite:**
  - View a continuous low-latency Live Stream from the laptop's Webcam.
  - **Two-Way Audio Intercom:** Speak into your phone and play it live out of your laptop's speakers, or listen to the laptop's microphone securely over Wi-Fi.
- **Dynamic Cross-Platform Support:** Runs invisibly in the background on both Linux (systemd) and Windows (WMI/Startup).
- **Auto-healing ADB:** Automatically captures USB connections, transitions to Wireless ADB silently on plug-in, and auto-detects dynamically generated `lsusb` hardware vendor IDs for universal Android compatibility.
- **Persistent Monitor:** Tracks external network changes, dynamically pushes Chrome dashboard URLs directly onto your phone on-screen, and recovers broken disconnected endpoints automatically.
- **Zero-Touch Wi-Fi ADB:** Automatically transitions newly connected USB wires into high-speed TCP/IP routing so the cable can instantly be thrown away (`phonelink watch`).
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

**Cross-Platform Python Install (Recommended):**
```bash
pip install phonelink-cli
# Or from source directory:
pip install .
```

### Windows Setup
1. **Install Dependencies (The fast way):** Open an Administrator PowerShell and run:
   ```powershell
   winget install Gyan.FFmpeg
   winget install Genymobile.scrcpy
   winget install Google.PlatformTools
   ```
   *(Alternatively, if you use Chocolatey: `choco install scrcpy adb ffmpeg -y`)*
2. **Install the Web Daemon:** Double-click `install_windows.bat` located in the source code folder. This will automatically generate a hidden `.vbs` runner inside your Windows Startup folder so the Web Dashboard daemon safely boots silently in the background every time you turn your PC on without opening annoying CMD windows.

### Linux Setup (Alternative)
```bash
chmod +x install.sh
sudo ./install.sh
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
