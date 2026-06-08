#!/usr/bin/env bash
# install.sh – Install phonelink system-wide
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="/usr/local/bin/phonelink"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║    phonelink installer           ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# Copy the main script
sudo cp "$SCRIPT_DIR/phonelink.py" "$TARGET"
sudo chmod +x "$TARGET"

# Ensure shebang points to the right python3
PYTHON=$(which python3)
sudo sed -i "1s|.*|#!${PYTHON}|" "$TARGET"

echo "  [✓] phonelink installed to $TARGET"

# Make sure adb is installed
if ! command -v adb &>/dev/null; then
  echo "  [!] adb not found. Installing android-tools-adb …"
  sudo apt-get install -y android-tools-adb 2>/dev/null || true
fi

# Make sure scrcpy is installed
if ! command -v scrcpy &>/dev/null; then
  echo "  [!] scrcpy not found. Installing …"
  sudo apt-get install -y scrcpy 2>/dev/null || \
    sudo snap install scrcpy 2>/dev/null || true
fi

# Make sure ffmpeg is installed for media streaming
if ! command -v ffmpeg &>/dev/null; then
  echo "  [!] ffmpeg not found. Installing …"
  sudo apt-get install -y ffmpeg 2>/dev/null || true
fi

# Make sure xrandr is installed for Brightness adjuster
if ! command -v xrandr &>/dev/null; then
  echo "  [!] xrandr not found. Installing x11-xserver-utils …"
  sudo apt-get install -y x11-xserver-utils 2>/dev/null || true
fi

# Apply udev rules so ADB survives reboots
UDEV_FILE="/etc/udev/rules.d/51-android.rules"
if [ ! -f "$UDEV_FILE" ]; then
  echo "  [~] Applying Android udev rules (needs sudo) …"
  phonelink fix 2>/dev/null || true
else
  echo "  [✓] udev rules already present"
fi

# Add user to plugdev group (required for USB permission)
if ! groups "$USER" | grep -q plugdev; then
  echo "  [~] Adding $USER to plugdev group …"
  sudo usermod -aG plugdev "$USER"
  echo "  [!] Log out and back in for group change to take effect."
fi

echo ""
echo "  phonelink is ready! Try:"
echo "    phonelink --help"
echo "    phonelink fix        # diagnose ADB issues"
echo "    phonelink watch      # persistent monitor"
echo "    phonelink watch --screen   # mirror your screen"
echo ""
