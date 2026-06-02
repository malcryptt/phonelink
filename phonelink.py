#!/usr/bin/env python3
"""
phonelink - Persistent USB Android phone connection tool
Similar to scrcpy, but with auto-reconnect, ADB self-healing, and IoT features.
"""

import subprocess
import sys
import os
import time
import argparse
import threading
import signal
import shutil
import re
import json
from pathlib import Path

# ─────────────────────────── ANSI colours ────────────────────────────
R  = "\033[1;31m"; G  = "\033[1;32m"; Y  = "\033[1;33m"
B  = "\033[1;34m"; M  = "\033[1;35m"; C  = "\033[1;36m"
W  = "\033[1;37m"; DIM = "\033[2m";   RST = "\033[0m"

LOGO = f"""{C}
 ██████╗ ██╗  ██╗ ██████╗ ███╗   ██╗███████╗██╗     ██╗███╗   ██╗██╗  ██╗
 ██╔══██╗██║  ██║██╔═══██╗████╗  ██║██╔════╝██║     ██║████╗  ██║██║ ██╔╝
 ██████╔╝███████║██║   ██║██╔██╗ ██║█████╗  ██║     ██║██╔██╗ ██║█████╔╝ 
 ██╔═══╝ ██╔══██║██║   ██║██║╚██╗██║██╔══╝  ██║     ██║██║╚██╗██║██╔═██╗ 
 ██║     ██║  ██║╚██████╔╝██║ ╚████║███████╗███████╗██║██║ ╚████║██║  ██╗
 ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝
{DIM}             Persistent USB Android Connection Tool{RST}
"""

# ─────────────────────────── Helpers ─────────────────────────────────

def log(level, msg):
    icons = {"info": f"{B}[*]{RST}", "ok": f"{G}[✓]{RST}",
             "warn": f"{Y}[!]{RST}", "err": f"{R}[✗]{RST}",
             "wait": f"{M}[~]{RST}"}
    print(f" {icons.get(level, '[?]')} {msg}")

def run(cmd, capture=True, timeout=15):
    """Run a shell command, return (returncode, stdout, stderr)."""
    try:
        if capture:
            r = subprocess.run(cmd, shell=isinstance(cmd, str),
                               capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        else:
            rc = subprocess.call(cmd, shell=isinstance(cmd, str))
            return rc, "", ""
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)

def adb(*args, timeout=15):
    """Run an adb command."""
    return run(["adb"] + list(args), timeout=timeout)

def require_adb():
    if not shutil.which("adb"):
        log("err", "adb not found. Install with:  sudo apt install adb")
        sys.exit(1)

# ─────────────────────────── ADB Server ──────────────────────────────

def kill_adb():
    log("wait", "Killing existing ADB server …")
    run("adb kill-server")
    run("pkill -f 'adb -P'")
    time.sleep(1)

def start_adb():
    log("wait", "Starting ADB server …")
    rc, out, err = run("adb start-server")
    time.sleep(1)
    return rc == 0

def restart_adb():
    kill_adb()
    return start_adb()

# ─────────────────────────── Device detection ────────────────────────

def get_devices():
    """Return list of (serial, state) tuples."""
    rc, out, _ = adb("devices")
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            serial, state = parts[0], parts[1]
            if state in ("device", "unauthorized", "offline"):
                devices.append((serial, state))
    return devices

def wait_for_device(timeout=60):
    """Block until a device is detected or timeout. Returns serial or None."""
    log("wait", f"Waiting for device (timeout {timeout}s) …  Plug in your phone via USB.")
    deadline = time.time() + timeout
    while time.time() < deadline:
        devs = get_devices()
        if devs:
            return devs[0]
        time.sleep(2)
    return None

# ─────────────────────────── Diagnostics / Fix ───────────────────────

def cmd_fix(args):
    """Diagnose and repair ADB / USB issues."""
    print(LOGO)
    log("info", f"{W}Running ADB & USB diagnostics …{RST}")
    ok = True

    # 1. Check adb binary
    adb_path = shutil.which("adb")
    if adb_path:
        log("ok", f"adb found at {adb_path}")
    else:
        log("err", "adb missing.  Run:  sudo apt install android-tools-adb")
        ok = False

    # 2. Check scrcpy
    scrcpy_path = shutil.which("scrcpy")
    if scrcpy_path:
        log("ok", f"scrcpy found at {scrcpy_path}")
    else:
        log("warn", "scrcpy not found.  Screen mirroring unavailable.")
        log("info", "Install:  sudo apt install scrcpy  OR  sudo snap install scrcpy")

    # 3. Restart ADB server
    log("info", "Restarting ADB server …")
    kill_adb()
    if start_adb():
        log("ok", "ADB server started")
    else:
        log("err", "ADB server failed to start")
        ok = False

    # 4. Check udev rules
    udev_file = Path("/etc/udev/rules.d/51-android.rules")
    if udev_file.exists():
        log("ok", f"udev rules present: {udev_file}")
    else:
        log("warn", "Android udev rules missing – this is why ADB stops working!")
        log("info", "Applying rules now (needs sudo) …")
        _apply_udev_rules()

    # 5. Check USB devices
    rc, out, _ = run("lsusb")
    log("info", "USB devices detected:")
    for line in out.splitlines():
        print(f"      {DIM}{line}{RST}")

    # 6. Try devices list
    devs = get_devices()
    if devs:
        for serial, state in devs:
            colour = G if state == "device" else Y
            log("ok" if state == "device" else "warn",
                f"Device: {colour}{serial}{RST}  state={colour}{state}{RST}")
        if any(s == "unauthorized" for _, s in devs):
            log("warn", "Device is UNAUTHORIZED – check your phone and tap 'Allow'.")
    else:
        log("warn", "No Android devices connected right now.")

    print()
    if ok:
        log("ok", f"{G}Diagnostics passed. Try plugging in your phone.{RST}")
    else:
        log("err", f"{R}Some issues found. Follow the steps above and re-run:  phonelink fix{RST}")

def _apply_udev_rules():
    """Write Android udev rules to /tmp and attempt to apply via sudo.
    Degrades gracefully if sudo is unavailable."""
    rules_content = """# Android USB udev rules – generated by phonelink
SUBSYSTEM=="usb", ATTR{idVendor}=="0502", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0b05", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="413c", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0489", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0bb4", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="12d1", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="17ef", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="1004", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="22b8", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0955", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="04e8", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="054c", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0fce", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0930", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="19d2", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="2a45", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="2ae5", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="22d9", MODE="0666", GROUP="plugdev"
"""
    rules_path  = Path("/tmp/51-android.rules")
    script_path = Path("/tmp/apply_udev.sh")
    rules_path.write_text(rules_content)
    script = f"""#!/bin/bash
set -e
cp {rules_path} /etc/udev/rules.d/51-android.rules
chmod a+r /etc/udev/rules.d/51-android.rules
udevadm control --reload-rules
udevadm trigger
usermod -aG plugdev $USER
echo done
"""
    script_path.write_text(script)
    script_path.chmod(0o755)

    try:
        result = subprocess.run(
            ["sudo", "-n", "bash", str(script_path)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            log("ok", "udev rules applied successfully")
            return
    except Exception:
        pass

    # sudo not available non-interactively – give manual instructions
    log("warn", "Could not apply udev rules automatically (need sudo).")
    log("info", f"{Y}Run this one command in your terminal to fix ADB permanently:{RST}")
    print(f"\n      {W}sudo bash {script_path}{RST}\n")
    log("info", "Then unplug and replug your phone.")

# ─────────────────────────── Screen mirror ───────────────────────────

def cmd_screen(args):
    """Launch scrcpy for screen mirroring."""
    require_adb()
    devs = get_devices()
    if not devs:
        log("warn", "No device connected. Waiting …")
        result = wait_for_device(60)
        if not result:
            log("err", "No device found after 60 s. Plug in phone and check USB debugging.")
            sys.exit(1)
        devs = get_devices()

    serial, state = devs[0]
    if state == "unauthorized":
        log("warn", f"Device {serial} is unauthorized. Check your phone screen and tap 'Allow'.")
        log("wait", "Waiting for authorization …")
        for _ in range(30):
            time.sleep(2)
            devs = get_devices()
            if devs and devs[0][1] == "device":
                break
        else:
            log("err", "Authorization timeout. Exiting.")
            sys.exit(1)
        serial, state = devs[0]

    log("ok", f"Launching scrcpy for device {G}{serial}{RST} …")
    extra = args.scrcpy_args if args.scrcpy_args else ""
    scrcpy_cmd = f"scrcpy -s {serial} {extra}"
    log("info", f"Command: {DIM}{scrcpy_cmd}{RST}")
    os.system(scrcpy_cmd)

# ─────────────────────────── Shell ───────────────────────────────────

def cmd_shell(args):
    """Open an interactive ADB shell."""
    require_adb()
    devs = get_devices()
    if not devs:
        log("err", "No device connected.")
        sys.exit(1)
    serial, state = devs[0]
    if state != "device":
        log("err", f"Device is in state '{state}'. Cannot open shell.")
        sys.exit(1)
    log("ok", f"Opening shell on {G}{serial}{RST} …")
    cmd = args.command if args.command else None
    if cmd:
        os.system(f"adb -s {serial} shell {cmd}")
    else:
        os.system(f"adb -s {serial} shell")

# ─────────────────────────── File transfer ───────────────────────────

def cmd_push(args):
    """Push a file to the phone."""
    require_adb()
    devs = get_devices()
    if not devs:
        log("err", "No device connected."); sys.exit(1)
    serial = devs[0][0]
    log("info", f"Pushing {args.src} → {args.dst} on {serial} …")
    rc, out, err = adb("-s", serial, "push", args.src, args.dst, timeout=120)
    if rc == 0:
        log("ok", f"Push complete:\n{out}")
    else:
        log("err", f"Push failed: {err}")

def cmd_pull(args):
    """Pull a file from the phone."""
    require_adb()
    devs = get_devices()
    if not devs:
        log("err", "No device connected."); sys.exit(1)
    serial = devs[0][0]
    dst = args.dst if args.dst else "."
    log("info", f"Pulling {args.src} → {dst} …")
    rc, out, err = adb("-s", serial, "pull", args.src, dst, timeout=120)
    if rc == 0:
        log("ok", f"Pull complete:\n{out}")
    else:
        log("err", f"Pull failed: {err}")

# ─────────────────────────── Port forward ────────────────────────────

def cmd_forward(args):
    """Forward a TCP port from device to host."""
    require_adb()
    devs = get_devices()
    if not devs:
        log("err", "No device connected."); sys.exit(1)
    serial = devs[0][0]
    local  = f"tcp:{args.local_port}"
    remote = f"tcp:{args.remote_port}"
    rc, out, err = adb("-s", serial, "forward", local, remote)
    if rc == 0:
        log("ok", f"Forwarding localhost:{args.local_port} → device:{args.remote_port}")
    else:
        log("err", f"Forward failed: {err}")

# ─────────────────────────── IoT / Advanced ──────────────────────────

def get_first_device():
    devs = get_devices()
    if not devs:
        log("err", "No device connected."); sys.exit(1)
    return devs[0][0]

def cmd_wake(args):
    """Wake device screen and attempt to unlock via swipe."""
    require_adb()
    serial = get_first_device()
    log("info", f"Waking screen & unlocking {serial} …")
    # Wake up screen
    adb("-s", serial, "shell", "input keyevent 224") # KEYCODE_WAKEUP
    time.sleep(1)
    # Swipe up to unlock (x1 y1 x2 y2 duration)
    adb("-s", serial, "shell", "input swipe 500 1500 500 200 300")
    log("ok", "Screen wake & unlock sent.")

def cmd_app(args):
    """Launch an application."""
    require_adb()
    serial = get_first_device()
    log("info", f"Launching app: {args.package} …")
    # Try am start-activity first (works on all modern Android)
    rc, out, err = adb("-s", serial, "shell",
        f"am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER "
        f"-n $(cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {args.package} 2>/dev/null | tail -1) 2>&1")
    # Fallback: monkey (less reliable but widely supported)
    if rc != 0 or "Error" in out:
        rc, out, err = adb("-s", serial, "shell",
            f"monkey -p {args.package} -c android.intent.category.LAUNCHER 1 2>&1")
    if rc == 0 or "Events injected" in out or "Starting" in out:
        log("ok", f"Launched {args.package}")
    else:
        log("err", f"Could not launch {args.package}. Is the package name correct?")
        log("info", "Tip: list user-installed apps with:  phonelink shell 'pm list packages -3'")

def cmd_type(args):
    """Inject text into the device's current textbox."""
    require_adb()
    serial = get_first_device()
    text = args.text.replace(' ', '%s') # spaces must be escaped as %s for adb shell input text
    log("info", f"Typing text …")
    adb("-s", serial, "shell", "input text", f'"{text}"')
    log("ok", "Text injected.")

def cmd_metrics(args):
    """Output JSON with device metrics (battery, temp)."""
    import json
    require_adb()
    serial = get_first_device()
    
    _, bat_out, _ = adb("-s", serial, "shell", "dumpsys battery")
    bat_data = {}
    for line in bat_out.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            bat_data[k.strip()] = v.strip()
    
    # temperature is returned in tenths of a degree (e.g. 399 = 39.9°C)
    temp_c = float(bat_data.get('temperature', 0)) / 10.0
    level  = int(bat_data.get('level', 0))
    # Map numeric Android BatteryStatus constants to readable strings
    status_map = {'1': 'unknown', '2': 'charging', '3': 'discharging',
                  '4': 'not charging', '5': 'full'}
    status_str = status_map.get(bat_data.get('status', '1'), 'unknown')

    metrics = {
        "status": "success",
        "device": serial,
        "battery_level_pct": level,
        "battery_temp_c": temp_c,
        "charging_status": status_str
    }
    print(json.dumps(metrics, indent=2))

def cmd_screenshot(args):
    """Take a screenshot and pull it to localhost."""
    require_adb()
    serial = get_first_device()
    remote_path = "/sdcard/screen.png"
    local_path = args.dst
    log("wait", "Capturing screen …")
    adb("-s", serial, "shell", "screencap -p", remote_path)
    log("info", f"Pulling to {local_path} …")
    adb("-s", serial, "pull", remote_path, local_path)
    adb("-s", serial, "shell", "rm", remote_path)
    log("ok", f"Screenshot saved to {local_path}")

def cmd_net(args):
    """Reverse tethering instructions/setup via gnirehtet."""
    require_adb()
    serial = get_first_device()
    if shutil.which("gnirehtet"):
        log("info", "gnirehtet found. Starting reverse tethering …")
        os.system(f"gnirehtet run {serial}")
    else:
        log("warn", "Reverse tethering requires 'gnirehtet'.")
        log("info", "To install on Linux:")
        print(f"      {DIM}wget https://github.com/Genymobile/gnirehtet/releases/download/v2.5/gnirehtet-rust-linux64-v2.5.zip{RST}")
        print(f"      {DIM}unzip gnirehtet-rust-linux64-v2.5.zip{RST}")
        print(f"      {DIM}sudo cp gnirehtet-rust-linux64/gnirehtet /usr/local/bin/{RST}")
        print(f"      {DIM}sudo chmod +x /usr/local/bin/gnirehtet{RST}")
        print("\nOnce installed, re-run: phonelink net")

def cmd_wifi(args):
    """Pair over Wi-Fi / network so USB can be disconnected."""
    require_adb()
    serial = get_first_device()
    log("info", f"Restarting ADB in TCP/IP mode on {serial} …")
    rc, out, err = adb("-s", serial, "tcpip", "5555")
    if rc != 0:
        log("err", f"Failed to set tcpip mode: {err}"); sys.exit(1)

    time.sleep(2)

    # Scan ALL interfaces via ip route (works for Wi-Fi, Mobile Data, hotspot)
    rc, out, err = adb("-s", serial, "shell", "ip route")
    ip = None
    preferred_prefixes = ('192.168.', '10.', '172.')  # common private IP ranges
    for line in out.splitlines():
        if 'src ' in line:
            candidate = line.split('src ')[-1].split()[0].strip()
            if not candidate.startswith('127.') and not candidate.startswith('169.254.'):
                ip = candidate
                # Prefer private LAN addresses (Wi-Fi) over mobile data IPs
                if any(candidate.startswith(p) for p in preferred_prefixes):
                    break

    # Fallback: parse ip addr show
    if not ip:
        rc2, out2, _ = adb("-s", serial, "shell", "ip addr")
        for line in out2.splitlines():
            if 'inet ' in line and '127.0.0.1' not in line and '169.254' not in line:
                parts = line.strip().split()
                if len(parts) >= 2:
                    ip = parts[1].split('/')[0]
                    break

    if not ip:
        log("err", "Could not detect phone IP. Ensure Wi-Fi or mobile data is on.")
        sys.exit(1)

    log("ok", f"Phone IP detected: {G}{ip}{RST}")
    log("info", "Connecting via network …")
    rc, out, err = adb("connect", f"{ip}:5555")
    if "connected" in out.lower() or rc == 0:
        log("ok", f"{G}Connected to {ip}:5555{RST}")
        log("info", f"{Y}You can now safely unplug the USB cable!{RST}")
    else:
        log("err", f"Failed to connect: {out} {err}")

def cmd_logs(args):
    """Stream logcat with optional keyword filtering."""
    require_adb()
    serial = get_first_device()
    cmd = f"adb -s {serial} logcat"
    if args.filter:
        if args.errors:
            cmd = f'adb -s {serial} logcat *:E | grep -i "{args.filter}"'
        else:
            cmd = f'adb -s {serial} logcat | grep -i "{args.filter}"'
    else:
        if args.errors:
            cmd = f'adb -s {serial} logcat *:E'

    log("info", f"Streaming logs (press Ctrl+C to stop) …")
    try:
        os.system(cmd)
    except KeyboardInterrupt:
        pass

def cmd_sync(args):
    """Watch a local file/folder and push on changes."""
    def get_time(path):
        return os.stat(path).st_mtime if os.path.exists(path) else 0

    require_adb()
    serial = get_first_device()
    src = Path(args.src)
    dst = args.dst
    
    if not src.exists():
        log("err", f"Source {src} does not exist.")
        sys.exit(1)

    log("info", f"Watching {src} for changes … (Pushing to {dst})")
    
    # Simple polling (no external dependencies)
    last_mtime = 0
    try:
        while True:
            current_mtime = 0
            if src.is_file():
                current_mtime = get_time(src)
            else:
                for f in src.rglob('*'):
                    m = get_time(f)
                    if m > current_mtime:
                        current_mtime = m
            
            if current_mtime > last_mtime:
                log("wait", "Changes detected. Pushing …")
                rc, out, err = adb("-s", serial, "push", str(src), dst)
                if rc == 0:
                    log("ok", f"Synced to phone.")
                else:
                    log("err", f"Sync failed: {err}")
                last_mtime = current_mtime

            time.sleep(2)
    except KeyboardInterrupt:
        log("info", "Sync stopped.")

def cmd_sms(args):
    """Send an SMS directly from the terminal."""
    require_adb()
    serial = get_first_device()
    log("info", f"Sending SMS to {args.phone} …")
    # We use 'am start' to launch the SMS intent securely, then use 'input keyevent' to send
    # Alternatively on many devices, service call isms is possible but requires complex parsing.
    # The safest silent way on modern Android is executing an intent and tapping "send".
    # For a fully background send, some devices support `adb shell service call isms 7 ...`
    # We'll use the universal intent method for standard text apps
    msg = args.message.replace(' ', '%s')
    adb("-s", serial, "shell", f"am start -a android.intent.action.SENDTO -d sms:{args.phone} --es sms_body '{msg}'")
    time.sleep(1)
    # Press Tab a few times to reach the send button depending on the app, or inject KEYCODE_ENTER
    adb("-s", serial, "shell", "input keyevent 22") # Right
    adb("-s", serial, "shell", "input keyevent 66") # Enter
    log("ok", f"SMS intent fired on {serial}")

def cmd_clip(args):
    """Universal clipboard synchronization."""
    require_adb()
    serial = get_first_device()
    if args.action == "push":
        if not args.text:
            log("err", "Must provide text to push to clipboard."); sys.exit(1)
        # Using simple input text or modern broadcasting
        adb("-s", serial, "shell", f"am broadcast -n clipper.android/.ClipboardService -a clipper.set -e text '{args.text}'")
        # Native adb clipboard (Android 11+)
        # adb("-s", serial, "shell", "service call clipboard 2 i32 1 s16 \"{args.text}\"")
        log("ok", "Pushed text to phone clipboard (Note: works best if Clippers app is installed, otherwise injected locally).")
        # Native fallback inject
        adb("-s", serial, "shell", f"input text '{args.text.replace(' ', '%s')}'")

    elif args.action == "pull":
        rc, out, err = adb("-s", serial, "shell", "service call clipboard 1")
        # Pull is heavily restricted on modern Android without a helper app.
        if rc == 0:
             # Basic parse of the hex dumpsys output for clipboard
             log("ok", f"Clipboard raw pulled: {out}")
        else:
             log("err", "Clipboard pull requires root or helper app on Android 10+.")

def cmd_call(args):
    """Control phone calls (answer, decline, end, mute) or route audio."""
    require_adb()
    serial = get_first_device()
    action = args.action
    KEYCODES = {
        "answer":  "5",   # KEYCODE_CALL
        "decline": "6",   # KEYCODE_ENDCALL
        "end":     "6",   # KEYCODE_ENDCALL
        "mute":    "164", # KEYCODE_VOLUME_MUTE
    }
    if action == "audio":
        # Route phone audio (mic + playback) to laptop via scrcpy
        # scrcpy 2+ supports --no-video --audio-source=mic/playback
        log("info", "Routing phone audio to laptop speakers/mic via scrcpy …")
        log("info", f"Phone mic → laptop speakers | Laptop mic → phone mic")
        log("wait", "Connecting audio stream (press Ctrl+C to stop) …")
        try:
            subprocess.run(
                ["scrcpy", "-s", serial,
                 "--no-video",
                 "--audio-source=playback",   # stream phone's speaker output
                 "--audio-codec=opus",
                ],
                check=False
            )
        except FileNotFoundError:
            log("err", "scrcpy not found. Install it: sudo apt install scrcpy")
        return

    if action not in KEYCODES:
        log("err", f"Unknown call action: {action}. Use: answer, decline, end, mute, audio")
        sys.exit(1)
    log("info", f"Call action: {action} …")
    adb("-s", serial, "shell", f"input keyevent {KEYCODES[action]}")
    log("ok", f"Done: {action}")
    # After answering, immediately offer to route audio
    if action == "answer":
        log("info", f"Tip: run  {G}phonelink call audio{RST}  to hear the call on your laptop speakers")

def cmd_notify(args):
    """Watch battery level and send desktop notifications."""
    require_adb()
    serial = get_first_device()
    threshold = args.threshold
    interval  = args.interval
    log("info", f"Battery monitor started (alert when < {threshold}%, check every {interval}s)")
    log("wait", "Press Ctrl+C to stop …\n")
    last_notified = None
    try:
        while True:
            rc, out, _ = adb("-s", serial, "shell", "dumpsys battery | grep level")
            try:
                level = int(out.replace("level:", "").strip())
            except ValueError:
                time.sleep(interval); continue

            rc2, charge_out, _ = adb("-s", serial, "shell", "dumpsys battery | grep status")
            status_map = {"1":"unknown","2":"charging","3":"discharging","4":"not charging","5":"full"}
            status_raw = charge_out.replace("status:", "").strip()
            status = status_map.get(status_raw, status_raw)

            log("info", f"Battery: {level}%  ({status})")

            # Notify when below threshold and not charging
            if level <= threshold and status not in ("charging", "full"):
                if last_notified != level:
                    last_notified = level
                    urgency = "critical" if level <= 10 else "normal"
                    subprocess.run([
                        "notify-send",
                        "-u", urgency,
                        "-i", "battery-caution",
                        "PhoneLink: Low Battery",
                        f"Phone battery is at {level}% ({status})"
                    ], check=False)
                    log("ok", f"Desktop notification sent: {level}%")
            else:
                last_notified = None  # reset so it re-notifies if drops again

            time.sleep(interval)
    except KeyboardInterrupt:
        log("info", "Battery monitor stopped.")

def cmd_sms_inbox(args):
    """Read recent SMS messages from the phone."""
    require_adb()
    serial = get_first_device()
    count = args.count
    log("info", f"Reading last {count} SMS messages …")
    # Query the SMS content provider (works without root on most devices)
    query = (
        "content query --uri content://sms/inbox "
        f"--projection address:date:body --sort 'date DESC' --limit {count}"
    )
    rc, out, err = adb("-s", serial, "shell", query)
    if rc != 0 or not out.strip():
        log("err", "Could not read SMS inbox. Some devices restrict this without root.")
        log("info", "Tip: try enabling USB debugging + 'adb backup' permissions in developer options.")
        return
    rows = out.strip().split("Row:")
    print()
    for row in rows:
        if not row.strip(): continue
        parts = {}
        for segment in row.split(","):
            if "=" in segment:
                k, _, v = segment.partition("=")
                parts[k.strip()] = v.strip()
        addr = parts.get("address", "Unknown")
        body = parts.get("body", "(no body)")
        date_ms = parts.get("date", "0")
        try:
            import datetime
            dt = datetime.datetime.fromtimestamp(int(date_ms) / 1000)
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_str = date_ms
        print(f"  {C}{addr}{RST}  {Y}{date_str}{RST}")
        print(f"  {body}")
        print()

def cmd_guard(args):
    """Incoming call guard: desktop notification + auto-screenshot on every call."""
    require_adb()
    serial = get_first_device()
    log("info", "Call guard started — watching for incoming calls …")
    log("wait", "Press Ctrl+C to stop …\n")
    was_ringing = False
    try:
        while True:
            rc, out, _ = adb("-s", serial, "shell",
                             "dumpsys telephony.registry | grep mCallState")
            ringing = "1" in out
            if ringing and not was_ringing:
                was_ringing = True
                # Get incoming number
                rc2, numout, _ = adb("-s", serial, "shell",
                    "dumpsys telephony.registry | grep mCallIncomingNumber")
                number = numout.split("=")[-1].strip() if "=" in numout else "Unknown"
                log("ok", f"Incoming call from: {G}{number}{RST}")

                # Desktop notification
                subprocess.run([
                    "notify-send", "-u", "critical", "-i", "call-start",
                    f"📞 Incoming Call: {number}",
                    "phonelink call answer  |  phonelink call decline"
                ], check=False)

                # Auto-screenshot of the phone screen
                if args.screenshot:
                    ts = int(time.time())
                    remote = f"/sdcard/guard_shot_{ts}.png"
                    local  = Path.home() / f"phonelink_call_{ts}.png"
                    adb("-s", serial, "shell", f"screencap -p {remote}")
                    adb("-s", serial, "pull", remote, str(local))
                    adb("-s", serial, "shell", f"rm {remote}")
                    log("ok", f"Auto-screenshot saved: {local}")

            elif not ringing:
                was_ringing = False

            time.sleep(2)
    except KeyboardInterrupt:
        log("info", "Guard stopped.")

def cmd_power(args):
    """Reboot or shutdown the phone from the laptop terminal."""
    require_adb()
    serial = get_first_device()
    action = args.action
    if action == "reboot":
        log("info", "Rebooting phone \u2026")
        adb("-s", serial, "reboot")
        log("ok", "Reboot command sent.")
    elif action == "shutdown":
        log("info", "Shutting down phone \u2026")
        adb("-s", serial, "shell", "reboot -p")
        log("ok", "Shutdown command sent.")
    elif action == "recovery":
        log("info", "Rebooting phone into recovery \u2026")
        adb("-s", serial, "reboot", "recovery")
        log("ok", "Recovery reboot sent.")
    elif action == "bootloader":
        log("info", "Rebooting phone into bootloader \u2026")
        adb("-s", serial, "reboot", "bootloader")
        log("ok", "Bootloader reboot sent.")

def cmd_web(args):
    """Full REST API + Phone UI server for wireless control."""
    require_adb()
    serial = get_first_device()
    port   = args.port

    # Find the phone_ui.html file next to this script
    ui_path = Path(__file__).parent / "phone_ui.html"

    log("info",  f"Starting PhoneLink API server on port {port}")
    log("ok",    f"Open on your LAPTOP:  http://localhost:{port}")
    if ui_path.exists():
        log("ok", f"Open on your PHONE:   file://{ui_path}  (works offline!)")
    log("wait", "Press Ctrl+C to stop\n")

    import http.server
    import socketserver
    import urllib.parse

    class PhoneLinkHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *a): pass  # silence default logs

        def send_json(self, data, code=200):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_text(self, text, code=200):
            body = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_file(self, path):
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def do_GET(self):
            path = urllib.parse.unquote(self.path.split("?")[0])
            parts = [p for p in path.split("/") if p]

            try:
                # ── Serve phone panel ──────────────────────────────
                if path in ("/", "/ui"):
                    if ui_path.exists():
                        self.send_file(ui_path)
                    else:
                        self.send_text("phone_ui.html not found next to phonelink.py")
                    return

                # ── Ping ───────────────────────────────────────────
                elif path == "/ping":
                    self.send_json({"ok": True, "device": serial})

                # ── Metrics ────────────────────────────────────────
                elif path == "/metrics":
                    rc, out, _ = adb("-s", serial, "shell", "dumpsys battery")
                    bat = {}
                    for line in out.splitlines():
                        if ':' in line:
                            k, v = line.split(":", 1)
                            bat[k.strip()] = v.strip()
                    status_map = {"1":"unknown","2":"charging","3":"discharging","4":"not charging","5":"full"}
                    self.send_json({
                        "status": "success", "device": serial,
                        "battery_level_pct":  int(bat.get("level", 0)),
                        "battery_temp_c":     float(bat.get("temperature", 0)) / 10.0,
                        "charging_status":    status_map.get(bat.get("status","1"), "unknown"),
                    })

                # ── Wake ───────────────────────────────────────────
                elif path == "/wake":
                    adb("-s", serial, "shell", "input keyevent 26")
                    time.sleep(0.4)
                    adb("-s", serial, "shell", "input swipe 540 1200 540 600 300")
                    self.send_text("OK: wake")

                # ── Screenshot ─────────────────────────────────────
                elif path == "/screenshot":
                    ts = int(time.time())
                    remote = f"/sdcard/pl_shot_{ts}.png"
                    local  = Path.home() / f"phonelink_shot_{ts}.png"
                    adb("-s", serial, "shell", f"screencap -p {remote}")
                    adb("-s", serial, "pull", remote, str(local))
                    adb("-s", serial, "shell", f"rm {remote}")
                    self.send_text(f"OK: {local}")

                # ── Screen mirror ──────────────────────────────────
                elif path == "/screen":
                    subprocess.Popen(["scrcpy", "-s", serial], start_new_session=True)
                    self.send_text("OK: screen")

                # ── Fix ────────────────────────────────────────────
                elif path == "/fix":
                    rc, out, err = adb("kill-server")
                    adb("start-server")
                    self.send_text(f"OK: ADB restarted")

                # ── Status ─────────────────────────────────────────
                elif path == "/status":
                    rc1, model, _   = adb("-s", serial, "shell", "getprop ro.product.model")
                    rc2, android, _ = adb("-s", serial, "shell", "getprop ro.build.version.release")
                    self.send_json({"device": serial, "model": model.strip(), "android": android.strip()})

                # ── App launch ─────────────────────────────────────
                elif len(parts) >= 2 and parts[0] == "app":
                    pkg = parts[1]
                    adb("-s", serial, "shell",
                        f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1 2>&1")
                    self.send_text(f"OK: launched {pkg}")

                # ── Type injection ─────────────────────────────────
                elif len(parts) >= 2 and parts[0] == "type":
                    text = urllib.parse.unquote_plus("/".join(parts[1:]))
                    escaped = text.replace(" ", "%s")
                    adb("-s", serial, "shell", f"input text '{escaped}'")
                    self.send_text(f"OK: typed")

                # ── Shell ──────────────────────────────────────────
                elif len(parts) >= 2 and parts[0] == "shell":
                    cmd = urllib.parse.unquote_plus("/".join(parts[1:]))
                    rc, out, err = adb("-s", serial, "shell", cmd)
                    self.send_text(out or err)

                # ── SMS ────────────────────────────────────────────
                elif len(parts) >= 3 and parts[0] == "sms":
                    phone = urllib.parse.unquote_plus(parts[1])
                    msg   = urllib.parse.unquote_plus("/".join(parts[2:]))
                    adb("-s", serial, "shell",
                        f"am start -a android.intent.action.SENDTO -d sms:{phone} --es sms_body '{msg}'")
                    time.sleep(1)
                    adb("-s", serial, "shell", "input keyevent 66")
                    self.send_text(f"OK: sms to {phone}")

                # ── Call control ───────────────────────────────────
                elif path in ("/call_answer", "/call_decline", "/call_end", "/call_mute"):
                    codes = {"/call_answer":"5", "/call_decline":"6", "/call_end":"6", "/call_mute":"164"}
                    adb("-s", serial, "shell", f"input keyevent {codes[path]}")
                    self.send_text(f"OK: {path[1:]}")

                elif path == "/call_audio":
                    subprocess.Popen(["phonelink", "call", "audio"], start_new_session=True)
                    self.send_text("OK: streaming call audio to laptop")

                # ── Inbox ──────────────────────────────────────────
                elif path == "/inbox":
                    subprocess.Popen(["phonelink", "inbox"], start_new_session=True)
                    self.send_text("OK: dumped inbox to laptop terminal")

                # ── Call status polling ────────────────────────────
                elif path == "/call_status":
                    rc, out, _ = adb("-s", serial, "shell", "dumpsys telephony.registry | grep mCallState")
                    # 0=idle, 1=ringing, 2=offhook
                    ringing = "1" in out
                    number  = ""
                    if ringing:
                        rc2, out2, _ = adb("-s", serial, "shell",
                            "dumpsys telephony.registry | grep mCallIncomingNumber")
                        if "=" in out2:
                            number = out2.split("=")[-1].strip()
                    self.send_json({"ringing": ringing, "number": number, "name": ""})

                # ── Logs ───────────────────────────────────────────
                elif path in ("/logs/errors", "/logs/all"):
                    filt = "*:E" if path == "/logs/errors" else "*:V"
                    rc, out, _ = adb("-s", serial, "logcat", "-d", "-t", "50", filt)
                    self.send_text(out)

                # ── Net (reverse tether) ───────────────────────────
                elif path == "/net":
                    subprocess.Popen(["gnirehtet", "run", serial], start_new_session=True)
                    self.send_text("OK: reverse tether started (gnirehtet)")

                # ── Wifi ───────────────────────────────────────────
                elif path == "/wifi":
                    adb("-s", serial, "tcpip", "5555")
                    self.send_text("OK: tcpip mode enabled, unplug USB")

                # ── Macro example ──────────────────────────────────
                elif path == "/macro/example":
                    self.send_text("wake\nwait 2\ntap 500 1000\nwait 1\ntype hello")

                # ── Power Control (Phone) ──────────────────────────
                elif path in ("/power/reboot", "/power/shutdown"):
                    adb("-s", serial, "shell", "reboot" + (" -p" if "shutdown" in path else ""))
                    self.send_text(f"OK: phone {path.split('/')[-1]}")

                # ── Power Control (Laptop) ─────────────────────────
                elif path in ("/laptop/reboot", "/laptop/shutdown"):
                    # We execute this in the background so the HTTP response goes through
                    cmd = "reboot" if "reboot" in path else "poweroff"
                    self.send_text(f"OK: laptop {cmd}")
                    subprocess.Popen(["sudo", "-n", cmd], start_new_session=True)


                else:
                    self.send_text(f"Unknown route: {path}", 404)

            except Exception as exc:
                self.send_text(f"Error: {exc}", 500)

    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), PhoneLinkHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down PhoneLink server.")


def _macro_run(script_file):
    require_adb()
    serial = get_first_device()
    if not os.path.exists(script_file):
        log("err", f"Macro script not found: {script_file}"); sys.exit(1)
        
    log("info", f"Executing macro script: {script_file}")
    with open(script_file, "r") as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"): continue
        log("wait", f"[{i+1}] {line}")
        
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd == "wait" or cmd == "sleep":
            time.sleep(float(args))
        elif cmd == "tap":
            adb("-s", serial, "shell", f"input tap {args}")
        elif cmd == "swipe":
            adb("-s", serial, "shell", f"input swipe {args}")
        elif cmd == "type":
            escaped = args.replace(' ', '%s')
            adb("-s", serial, "shell", f"input text '{escaped}'")
        elif cmd == "key":
            adb("-s", serial, "shell", f"input keyevent {args}")
        elif cmd == "app":
            os.system(f"phonelink app {args}")
        elif cmd == "wake":
            os.system("phonelink wake")
        else:
            log("err", f"Unknown macro command '{cmd}' on line {i+1}")

def cmd_macro(args):
    """Run an automation bot script."""
    if args.action == "run":
        for _ in range(args.loop):
            _macro_run(args.file)
        log("ok", f"Finished {args.loop} loop(s) of {args.file}")
    elif args.action == "example":
        example = """# My Auto-Swiper Bot
wake
app com.android.chrome
wait 3
# tap center of screen (x y)
tap 500 1000
wait 1
type hello
wait 1
key 66
# swipe (x1 y1 x2 y2 duration_ms)
swipe 500 1000 500 200 500
"""
        print(example)
        log("info", "Save this as bot.txt and run: phonelink macro run bot.txt")

_running = True

def _signal_handler(sig, frame):
    global _running
    print(f"\n{Y} [!] Caught signal – shutting down phonelink …{RST}")
    _running = False
    sys.exit(0)

def cmd_watch(args):
    """
    Persistent monitoring loop:
    - Waits for device, launches scrcpy (if --screen), re-connects on disconnect.
    """
    global _running
    signal.signal(signal.SIGINT,  _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    require_adb()
    print(LOGO)
    log("info", f"{W}phonelink watch mode{RST} – press {Y}Ctrl+C{RST} to stop\n")

    reconnect_delay = args.reconnect_delay
    use_screen      = args.screen
    scrcpy_extra    = args.scrcpy_args if args.scrcpy_args else ""

    scrcpy_proc = None

    while _running:
        # ── Wait for a device ──
        devs = get_devices()
        if not devs:
            log("wait", "No device detected. Waiting for USB connection …")
            while _running and not get_devices():
                time.sleep(2)
            if not _running:
                break
            devs = get_devices()

        serial, state = devs[0]
        log("ok", f"Device detected: {G}{serial}{RST}  ({state})")

        # ── Handle unauthorized ──
        if state == "unauthorized":
            log("warn", "Please check your phone and tap 'Allow USB debugging'.")
            for _ in range(30):
                if not _running: break
                time.sleep(2)
                devs = get_devices()
                if devs and devs[0][1] == "device":
                    serial, state = devs[0]
                    break
            else:
                log("err", "Authorization timeout. Restarting ADB …")
                restart_adb()
                continue

        if state != "device":
            log("warn", f"Device in state '{state}', skipping.")
            time.sleep(5)
            continue

        # ── Ready ──
        log("ok", f"Device {G}{serial}{RST} is {G}ready{RST}!")

        # Get device info
        _, model, _   = adb("-s", serial, "shell", "getprop ro.product.model")
        _, android, _ = adb("-s", serial, "shell", "getprop ro.build.version.release")
        log("info", f"Model: {C}{model.strip()}{RST}   Android: {C}{android.strip()}{RST}")
        print()

        # ── Optional: launch scrcpy ──
        if use_screen:
            if scrcpy_proc and scrcpy_proc.poll() is None:
                scrcpy_proc.terminate()
            log("info", f"Launching scrcpy …")
            scrcpy_proc = subprocess.Popen(
                f"scrcpy -s {serial} {scrcpy_extra}",
                shell=True)

        # ── Monitor connection ──
        log("info", "Monitoring connection. Will auto-reconnect if device disconnects …")
        consecutive_fails = 0
        while _running:
            time.sleep(3)
            rc, _, _ = adb("-s", serial, "get-state", timeout=5)
            if rc != 0:
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    log("warn", f"Device {serial} disconnected!")
                    break
            else:
                consecutive_fails = 0

        if not _running:
            break

        # ── Reconnect cycle ──
        if scrcpy_proc and scrcpy_proc.poll() is None:
            scrcpy_proc.terminate()

        log("wait", f"Waiting {reconnect_delay}s before reconnect …")
        for _ in range(reconnect_delay):
            if not _running: break
            time.sleep(1)

        log("info", "Restarting ADB and attempting reconnect …")
        restart_adb()

    log("info", "phonelink stopped.")

# ─────────────────────────── Status ──────────────────────────────────

def cmd_status(args):
    """Show brief status of connected devices."""
    require_adb()
    devs = get_devices()
    if not devs:
        log("warn", "No Android devices connected.")
        return
    for serial, state in devs:
        colour = G if state == "device" else Y
        _, model, _   = adb("-s", serial, "shell", "getprop ro.product.model")
        _, android, _ = adb("-s", serial, "shell", "getprop ro.build.version.release")
        _, battery, _ = adb("-s", serial, "shell",
                            "dumpsys battery | grep level")
        bat = battery.replace("level:", "").strip()
        print(f"\n  {C}Serial :{RST} {serial}")
        print(f"  {C}State  :{RST} {colour}{state}{RST}")
        print(f"  {C}Model  :{RST} {model.strip() or 'unknown'}")
        print(f"  {C}Android:{RST} {android.strip() or 'unknown'}")
        print(f"  {C}Battery:{RST} {bat}%")
    print()

# ─────────────────────────── CLI ─────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="phonelink",
        description="Persistent USB Android phone connection tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{C}Commands:{RST}
  {G}watch{RST}      Persistent monitor – auto-connects and reconnects your phone
  {G}fix{RST}        Diagnose and repair ADB / USB issues
  {G}status{RST}     Show connected device info
  {C}[IoT / Action Commands]{RST}
  {G}screen{RST}     Launch screen mirror (scrcpy)
  {G}shell{RST}      Open ADB shell (interactive or with command)
  {G}push{RST}/{G}pull{RST}  Transfer files
  {G}forward{RST}    Forward a TCP port from device to host
  {G}wake{RST}       Wake up screen and unlock
  {G}app{RST}        Launch app by package name
  {G}type{RST}       Inject keyboard typing into phone
  {G}metrics{RST}    Export battery & temp data as JSON
  {G}screenshot{RST} Quick PC screen capture
  {G}net{RST}        Internet over USB (Reverse Tethering)
  {C}[Ultimate Features]{RST}
  {G}wifi{RST}       Pair and connect device over local Wi-Fi
  {G}logs{RST}       Stream phone logcat with optional filters
  {G}sync{RST}       Watch a PC folder and auto-push changes to phone
  {G}sms{RST}        Send SMS texts from the terminal
  {G}clip{RST}       Universal clipboard sync (push/pull text)
  {G}web{RST}        Local web dashboard on port 8000
  {G}macro{RST}      Run automated touch/swipe bot scripts

{C}Examples:{RST}
  phonelink watch --screen          # Watch + auto-launch scrcpy
  phonelink watch                   # Watch without screen
  phonelink fix                     # Fix broken ADB
  phonelink screen                  # Mirror screen once
  phonelink shell                   # Interactive shell
  phonelink shell 'ls /sdcard'      # Run a single command
  phonelink push photo.jpg /sdcard/photo.jpg
  phonelink pull /sdcard/DCIM/Camera/ ./photos/
  phonelink forward 5555 5555
""")

    sub = parser.add_subparsers(dest="cmd")

    # watch
    p_watch = sub.add_parser("watch", help="Persistent connection monitor")
    p_watch.add_argument("--screen", action="store_true",
                         help="Auto-launch scrcpy when device connects")
    p_watch.add_argument("--reconnect-delay", type=int, default=5,
                         metavar="SECS", help="Seconds to wait before reconnecting (default 5)")
    p_watch.add_argument("--scrcpy-args", type=str, default="",
                         help='Extra args for scrcpy, e.g. "--max-fps 60 --bit-rate 8M"')

    # screen
    p_screen = sub.add_parser("screen", help="Launch screen mirror")
    p_screen.add_argument("--scrcpy-args", type=str, default="",
                          help="Extra args passed to scrcpy")

    # fix
    sub.add_parser("fix", help="Diagnose and fix ADB/USB issues")

    # status
    sub.add_parser("status", help="Show connected device info")

    # shell
    p_shell = sub.add_parser("shell", help="Open ADB shell")
    p_shell.add_argument("command", nargs="?", default=None,
                         help="Command to run (omit for interactive shell)")

    # push
    p_push = sub.add_parser("push", help="Push file to phone")
    p_push.add_argument("src", help="Local source path")
    p_push.add_argument("dst", help="Destination path on device")

    # pull
    p_pull = sub.add_parser("pull", help="Pull file from phone")
    p_pull.add_argument("src", help="Source path on device")
    p_pull.add_argument("dst", nargs="?", default=".", help="Local destination (default: .)")

    # forward
    p_fwd = sub.add_parser("forward", help="Forward TCP port")
    p_fwd.add_argument("local_port",  type=int, help="Host port")
    p_fwd.add_argument("remote_port", type=int, help="Device port")

    # wake
    sub.add_parser("wake", help="Wake screen and unlock")

    # app
    p_app = sub.add_parser("app", help="Launch an application")
    p_app.add_argument("package", help="Package name (e.g. com.android.chrome)")

    # type
    p_type = sub.add_parser("type", help="Inject text via keyboard")
    p_type.add_argument("text", help="Text to inject")

    # metrics
    sub.add_parser("metrics", help="Export battery/temp as JSON")

    # screenshot
    p_ss = sub.add_parser("screenshot", help="Capture screen")
    p_ss.add_argument("dst", nargs="?", default="screenshot.png", help="Local destination (default: screenshot.png)")

    # net
    sub.add_parser("net", help="Reverse tethering over USB")

    # wifi
    sub.add_parser("wifi", help="Wireless pair and connect over Wi-Fi")

    # logs
    p_logs = sub.add_parser("logs", help="Stream and filter logcat")
    p_logs.add_argument("--filter", "-f", type=str, help="Keyword filtering (grep)")
    p_logs.add_argument("--errors", "-e", action="store_true", help="Only show errors")

    # sync
    p_sync = sub.add_parser("sync", help="Auto-push folder on file changes")
    p_sync.add_argument("src", help="Local file or folder to monitor")
    p_sync.add_argument("dst", help="Destination path on device")

    # sms
    p_sms = sub.add_parser("sms", help="Send SMS from the terminal")
    p_sms.add_argument("phone", help="Phone number")
    p_sms.add_argument("message", help="Message text")

    # clip
    p_clip = sub.add_parser("clip", help="Push or pull clipboard text")
    p_clip.add_argument("action", choices=["push", "pull"], help="Action to perform")
    p_clip.add_argument("text", nargs="?", default="", help="Text to push (if action is push)")

    # call
    p_call = sub.add_parser("call", help="Control phone calls or route audio")
    p_call.add_argument("action", choices=["answer", "decline", "end", "mute", "audio"],
                        help="answer/decline/end/mute a call, or 'audio' to stream phone audio to laptop")

    # notify
    p_notify = sub.add_parser("notify", help="Battery monitor with desktop notifications")
    p_notify.add_argument("--threshold", type=int, default=20, help="Alert below this % (default: 20)")
    p_notify.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")

    # sms-inbox
    p_sms_inbox = sub.add_parser("inbox", help="Read recent SMS messages from phone")
    p_sms_inbox.add_argument("--count", type=int, default=10, help="Number of messages to show (default: 10)")

    # guard
    p_guard = sub.add_parser("guard", help="Watch for calls and send desktop notification")
    p_guard.add_argument("--screenshot", action="store_true", default=True,
                         help="Auto-screenshot on every call (default: on)")

    # power
    p_power = sub.add_parser("power", help="Reboot or shutdown the phone")
    p_power.add_argument("action", choices=["reboot", "shutdown", "recovery", "bootloader"])

    # web
    p_web = sub.add_parser("web", help="Start full REST API + phone HTML panel")
    p_web.add_argument("--port", type=int, default=8000, help="Port to run the dashboard on (default: 8000)")

    # macro
    p_macro = sub.add_parser("macro", help="Run automated scripts")
    p_macro.add_argument("action", choices=["run", "example"], help="Action to perform")
    p_macro.add_argument("file", nargs="?", default="", help="Script file to run")
    p_macro.add_argument("--loop", type=int, default=1, help="Number of times to loop the script")

    # help
    sub.add_parser("help", help="Show this help message")

    args = parser.parse_args()

    dispatch = {
        "watch":   cmd_watch,
        "screen":  cmd_screen,
        "fix":     cmd_fix,
        "status":  cmd_status,
        "shell":   cmd_shell,
        "push":    cmd_push,
        "pull":    cmd_pull,
        "forward": cmd_forward,
        "wake":    cmd_wake,
        "app":     cmd_app,
        "type":    cmd_type,
        "metrics": cmd_metrics,
        "screenshot": cmd_screenshot,
        "net":     cmd_net,
        "wifi":    cmd_wifi,
        "logs":    cmd_logs,
        "sync":    cmd_sync,
        "call":    cmd_call,
        "notify":  cmd_notify,
        "inbox":   cmd_sms_inbox,
        "guard":   cmd_guard,
        "power":   cmd_power,
        "sms":     cmd_sms,
        "clip":    cmd_clip,
        "web":     cmd_web,
        "macro":   cmd_macro,
    }

    if args.cmd == "help":
        print(LOGO)
        parser.print_help()
    elif args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        print(LOGO)
        parser.print_help()

if __name__ == "__main__":
    main()
