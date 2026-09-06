#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_EXEC="$SCRIPT_DIR/app.py"
ICON_PATH="$SCRIPT_DIR/static/icons/icon.png"

echo "[*] Setting up Linux Continuity Desktop Integration..."

# 1. CLI Shortcut
mkdir -p "$HOME/.local/bin"
ln -sf "$APP_EXEC" "$HOME/.local/bin/continuity"
echo "[+] Created CLI command: ~/.local/bin/continuity"

# 2. Desktop Launcher
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat << EOF > "$DESKTOP_DIR/linux-continuity.desktop"
[Desktop Entry]
Name=Linux Continuity
GenericName=PC to Android Bridge
Comment=AirDrop file transfer, shared clipboard, and terminal control (by killindodo)
Exec=$APP_EXEC
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=Network;Utility;System;
Keywords=continuity;airdrop;clipboard;terminal;android;kdeconnect;
StartupNotify=true
EOF

chmod +x "$DESKTOP_DIR/linux-continuity.desktop"
echo "[+] Created application entry: $DESKTOP_DIR/linux-continuity.desktop"

# 3. Optional Desktop shortcut
if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_DIR/linux-continuity.desktop" "$HOME/Desktop/"
    chmod +x "$HOME/Desktop/linux-continuity.desktop"
    echo "[+] Created shortcut on ~/Desktop"
fi

# 4. Optional Systemd User Service (for headless/background boot auto-start)
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"
cat << EOF > "$SYSTEMD_USER_DIR/linux-continuity.service"
[Unit]
Description=Linux Continuity Hub Server (by killindodo)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $SCRIPT_DIR/server.py --port 8080
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

echo "[+] Created systemd user unit: $SYSTEMD_USER_DIR/linux-continuity.service"
echo "[*] (To auto-start server on login without opening window: systemctl --user enable --now linux-continuity)"

# 5. Fix KDE Connect DBus service if needed
mkdir -p "$HOME/.local/share/dbus-1/services"
if [ -f "/usr/share/dbus-1/services/org.kde.kdeconnect.service.original" ] && [ ! -f "$HOME/.local/share/dbus-1/services/org.kde.kdeconnect.service" ]; then
    cp /usr/share/dbus-1/services/org.kde.kdeconnect.service.original "$HOME/.local/share/dbus-1/services/org.kde.kdeconnect.service"
    echo "[+] Activated user D-Bus service for KDE Connect"
fi

echo ""
echo "=========================================================="
echo " [✓] Linux Continuity Hub successfully installed!"
echo " Launch it via application menu or by running 'continuity'."
echo "=========================================================="
