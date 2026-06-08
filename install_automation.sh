#!/bin/bash
set -e

# Make python tool and trigger script executable
chmod +x phonelink.py
chmod +x trigger_autowifi.sh

echo "[*] Setting up Systemd user services..."
mkdir -p ~/.config/systemd/user
cp phonelink-web.service ~/.config/systemd/user/
cp phonelink-autowifi.service ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable phonelink-web.service
systemctl --user restart phonelink-web.service

echo "[*] Systemd setup complete. PhoneLink Web is now running automatically in the background!"

echo ""
echo "[*] Setting up UDEV rules for plug-and-play Wi-Fi ADB..."
if ! command -v sudo &> /dev/null; then
    echo "Requires root for udev, but sudo not found."
    exit 1
fi

sudo bash -c "cat > /etc/udev/rules.d/99-phonelink-wifi.rules << 'EOF'
ACTION==\"add\", SUBSYSTEM==\"usb\", ENV{ID_USB_INTERFACES}==\"*ff4201*\", RUN+=\"/usr/bin/sudo -u mal4crypt404 /home/mal4crypt404/phonelink/phonelink/trigger_autowifi.sh\"
EOF"

sudo chmod 644 /etc/udev/rules.d/99-phonelink-wifi.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "[✓] UDEV rules successfully installed!"
echo ""
echo "🔥 You're all set! "
echo '  1. phonelink web is ALWAYS running on http://localhost:8000 (and LAN).'
echo '  2. Simply plug in your phone over USB, wait a few seconds, and unplug it.'
echo '     It will automatically be connected over Wi-Fi!'
