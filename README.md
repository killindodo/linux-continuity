# Linux Continuity

An Apple-style continuity ecosystem between Linux PC and Android. Seamlessly transfer files, synchronize clipboards, watch and control running terminals, and mirror your PC desktop screen right from your Android phone.

**Developer**: [killindodo](https://github.com/killindodo)  
**Repository**: [https://github.com/killindodo/linux-continuity](https://github.com/killindodo/linux-continuity)

![Linux Continuity](static/icons/icon.png)

---

## Why I Built This

I wanted the seamless continuity experience that Apple has between macOS and iPhone, but for Linux and Android:
1. **Watch & Control Running Terminals**: See and control active terminal sessions, long-running scripts, server logs, or builds running on my PC directly from my phone.
2. **Live Desktop Screen Mirror**: Visually see any open window on the PC screen and control it with touch clicks and keystrokes while away.
3. **Universal Shared Clipboard**: Instantly sync clipboard between PC and phone without manually emailing or messaging links to myself.
4. **AirDrop-Style File Transfers**: Fast, wireless file dropping straight into `~/Downloads` without cables, cloud drives, or login portals.

This project delivers all of this with **zero Android app installations required**—simply open the web hub in your mobile browser or scan the desktop QR code.

---

## Features

- 📟 **Shared Interactive Terminals (Watch & Control)**:
  - Built-in `tmux` shared session multiplexing.
  - Whatever you run in a terminal on your PC is mirrored live to your phone simultaneously.
  - Multi-session switcher: switch between sessions (`main`, `work`, or create new named sessions).
  - **Running Desktop Terminals (PTS) Inspector**: view all active terminal processes running across `/dev/pts/*` on your machine (`zsh`, `python`, `gcc`, `htop`, etc.).
  - **1-Click Launch on PC**: open a terminal window on your PC screen attached to the shared session with a single tap from either desktop or phone.
  - Mobile touch helper keyboard with `ESC`, `TAB`, `Ctrl+C`, `Ctrl+Z`, and arrow keys.
- 🖱️ **Haptic Virtual Trackpad & Live Screen Mirror**:
  - Switch between Live Desktop Screen Mirror and high-response **Virtual Trackpad**.
  - 1-finger relative cursor movement with smooth acceleration.
  - 1-finger tap for Left Click, 2-finger tap for Right Click, 2-finger drag for vertical scrolling.
  - Dedicated Left, Middle, and Right Click buttons.
  - Remote Keystrokes (`Enter`, `Bksp`, `Tab`, `Esc`, `Ctrl+C`, `Super / Windows Key`, `Alt+Tab`, `Space`) + direct text input to PC.
- 🎵 **Media Player & Master Audio Control**:
  - Live **MPRIS** integration: automatically detects active playback from Spotify, VLC, YouTube, Firefox, Chrome, and MPV.
  - Displays real-time track title, artist, album, status badge, and album artwork.
  - Remote playback controls: Play/Pause, Next Track, Previous Track, Stop.
  - Master system volume slider (0% to 150%) with 1-tap presets and instant Mute toggle.
- 📊 **Real-time System & Hardware Vitals**:
  - Live CPU Load %, core count, CPU clock frequency, and CPU package temperatures (°C).
  - Memory (RAM) and Swap utilization meters.
  - Root storage (`/`) space and free GB display.
  - Thermal sensors: CPU & GPU temperatures.
  - Battery percentage and AC power charging indicator.
  - System uptime counter and 1m/5m/15m load averages.
- 🚀 **1-Click App Launcher & Power Deck**:
  - Launch PC applications straight from mobile: Terminal, File Manager (`~`), Web Browser, VS Code, and Settings.
  - System Power Management: Lock Screen, Turn Off Display (`xset dpms`), Sleep/Suspend, Reboot, and Power Off (with safety confirmations).
  - Push Desktop Notification: send custom push alerts from phone to Linux desktop via `notify-send`.
- 📋 **Universal Shared Clipboard**:
  - Live bidirectional clipboard synchronization.
  - Text copied on PC appears instantly on phone with 1-tap "Copy to Phone".
  - Text typed or pasted on phone is sent directly to the Linux X11 clipboard via `xclip`.
- 📁 **AirDrop File Drop**:
  - Send photos, documents, and videos from your phone directly to `~/Downloads` on Linux.
  - Triggers native desktop notifications on arrival.
  - Browse and download recent PC files from Linux to Android with one click.
- 📱 **Progressive Web App (PWA) & Offline Caching**:
  - Web App Manifest allows installing directly to Android home screen like a native app.
  - Built-in Service Worker for offline asset caching and instant launches.
- 🔒 **Security PIN Protection & Remote Tunnels**:
  - 4-digit PIN system protects your PC from unauthorized access on local Wi-Fi or public tunnels.
  - Integrated Cloudflare HTTPS Tunnels and Tailscale Mesh VPN support for away-from-desk access.

---

## Getting Started

### Prerequisites

Ensure Python 3, PyQt6, Tornado, tmux, and X11 utility tools are installed:

```bash
# Debian / Ubuntu / Kali
sudo apt update
sudo apt install python3 python3-pyqt6 python3-tornado tmux xdotool imagemagick xclip
```

### Installation

```bash
git clone https://github.com/killindodo/linux-continuity.git
cd linux-continuity
./install_desktop.sh
```

---

## Usage

### 1. Launch the Desktop Hub

Run via terminal or your application launcher:

```bash
continuity
```

Or run headless in the background:

```bash
python3 server.py --port 8080
```

### 2. Connect from Android

1. Ensure your Android phone is connected to the same Wi-Fi network as your PC (or use Remote Tunnel / Tailscale).
2. Point your phone camera at the QR code displayed on the desktop window (or open the displayed URL in your mobile browser, e.g., `http://192.168.x.x:8080`).
3. You now have full terminal access, screen mirroring, live clipboard sync, and file dropping!

---

## Watching & Controlling Running Terminals

To watch a command or program running on your PC from your Android phone:
1. In the desktop companion app, click **"⚡ Launch Shared Terminal"** (or in an existing terminal run `tmux new-session -A -s main`).
2. Run any command you want on your PC (e.g. `htop`, `python script.py`, build scripts, or long downloads).
3. On your phone, open the **Terminal** tab. You will see the exact same session live!
4. Any keystroke on your phone is reflected on your PC screen, and any output produced on your PC is mirrored on your phone.
5. If you want to see what is running in other non-shared terminals on your PC, tap **"📋 Running (PTS)"** to inspect active processes across all terminals.
6. Alternatively, open the **🖥️ Screen Mirror** tab to see your entire desktop screen visually!

---

## Remote Terminal Connection (When Away from PC)

When you are away from your PC (e.g., outside on 4G/5G mobile data or connected to external Wi-Fi), you have 3 powerful ways to watch and control your PC terminal remotely:

### Option 1: Mobile Web Terminal (Browser / Zero Install)
- **Cloudflare Public Tunnel**: Click **"☁️ Public Remote Tunnel"** -> **"⚡ Start Public Tunnel"** (can also be toggled directly from your phone in the Controls tab).
  - Gives you an encrypted public HTTPS URL (`https://*.trycloudflare.com`).
  - Protected by your 4-digit Security PIN.
  - Built-in 15-second WebSocket heartbeats prevent mobile cellular carrier drops and NAT timeouts.
  - Auto-reconnects with exponential backoff on network switches or screen wake.
- **Dedicated Standalone Terminal**: Open `https://<tunnel>/terminal` or `http://<tailscale-ip>:8080/terminal` for a clean, distraction-free full-screen shell that you can add directly to your Android Home Screen.

### Option 2: Tailscale Mesh VPN (Private Peer-to-Peer)
Click **"🌐 Tailscale VPN"** in the desktop app.
1. Connect your PC to Tailscale:
   ```bash
   sudo tailscale up
   ```
2. Install the free **Tailscale** app on your Android phone and sign in with the same account.
3. Open `http://<tailscale-ip>:8080` (or `http://<tailscale-ip>:8080/terminal`) in your phone browser.
4. Direct, end-to-end encrypted WireGuard connection with minimal latency.

### Option 3: Direct Mobile SSH Terminal (Termux / JuiceSSH / Termius)
If you prefer using a native terminal app on Android:
1. Connect via Tailscale mesh:
   ```bash
   ssh killindodo@100.66.109.94
   ```
2. Or attach directly into the live shared tmux session running on your PC:
   ```bash
   ssh killindodo@100.66.109.94 -t tmux new-session -A -s main
   ```
   Whatever you do in this SSH terminal is simultaneously visible on your laptop screen and the Continuity web app!

---

## Preventing Laptop Sleep While Away

To keep your Linux PC awake and connected when the lid is closed while away:

- **KDE Plasma**: System Settings -> Power Management -> When laptop lid is closed -> Select **"Turn off screen"** (instead of Sleep).
- **CLI / One-Liner**:
  ```bash
  systemd-inhibit --what=idle:sleep:handle-lid-switch --why="Remote Continuity" bash
  ```

---

## Background Autostart (Optional)

To have the Continuity server automatically start whenever you log into Linux:

```bash
systemctl --user enable --now linux-continuity
```

---

## Author

**killindodo**
- GitHub: [@killindodo](https://github.com/killindodo)
- Repository: [https://github.com/killindodo/linux-continuity](https://github.com/killindodo/linux-continuity)

---

## License

MIT License
