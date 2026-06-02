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
    rc, out, err = adb("-s", serial, "shell", "monkey", "-p", args.package, "-c", "android.intent.category.LAUNCHER", "1")
    if rc == 0:
        log("ok", f"Launched {args.package}")
    else:
        log("err", f"Failed to launch app: {err}")

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
    
    # temperature can be returned in tenths of a degree
    temp_c = float(bat_data.get('temperature', 0)) / 10.0
    level = int(bat_data.get('level', 0))
    status = bat_data.get('status', 'unknown')
    
    metrics = {
        "status": "success",
        "device": serial,
        "battery_level_pct": level,
        "battery_temp_c": temp_c,
        "charging_status": status
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
    }

    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        print(LOGO)
        parser.print_help()

if __name__ == "__main__":
    main()
