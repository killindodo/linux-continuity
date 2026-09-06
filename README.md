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
- 🖥️ **Live Desktop Screen Mirror & Remote Control**:
  - Live low-latency desktop screen capture streamed directly to your mobile browser.
  - Selectable refresh rates: Live (1s), 2s, 4s, or Manual refresh.
  - **Interactive Touch-to-Click**: Tap anywhere on the phone screen to simulate native mouse clicks on the PC desktop (supports Left Click, Right Click, and Double Click).
  - **Remote Keystroke & Typing Controller**: Quick keys (`Enter`, `Bksp`, `Tab`, `Esc`, `Ctrl+C`, `Super / Windows Key`, `Alt+Tab`, `Space`) plus a direct text input field to type into any active desktop window.
- 📋 **Universal Shared Clipboard**:
  - Live bidirectional clipboard synchronization.
  - Text copied on PC appears instantly on phone with 1-tap "Copy to Phone".
  - Text typed or pasted on phone is sent directly to the Linux X11 clipboard via `xclip`.
- 📁 **AirDrop File Drop**:
  - Send photos, documents, and videos from your phone directly to `~/Downloads` on Linux.
  - Triggers native desktop notifications on arrival.
  - Browse and download recent PC files from Linux to Android with one click.
- ⚡ **Desktop Companion & Mobile Controls**:
  - Quick actions from mobile: Lock screen, desktop audio mute, ping PC, open terminal on PC.
  - Desktop companion app with auto-generated QR code for instant camera pairing.
  - System tray icon with quick links and downloads folder shortcut.
- 🔒 **Security PIN Protection**:
  - 4-digit PIN system protects your PC from unauthorized access on local Wi-Fi or public tunnels.

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

## Remote Access (When Away from PC)

When you are away from your PC (e.g., outside on 4G/5G mobile data or connected to different Wi-Fi networks), you can connect remotely using either of two built-in methods:

### Method A: Cloudflare Public Tunnel (1-Click, Zero Config)
Click **"☁️ Public Remote Tunnel"** -> **"⚡ Start Public Tunnel"** in the desktop app.
- Generates an encrypted public HTTPS URL (`https://*.trycloudflare.com`).
- Works worldwide on cellular data or any external Wi-Fi.
- Accessible from any browser with zero client app installation required on your phone.
- Protected by your 4-digit Security PIN.

### Method B: Tailscale Mesh VPN (Private Peer-to-Peer)
Click **"🌐 Tailscale VPN"** in the desktop app.
1. Connect your PC to Tailscale:
   ```bash
   sudo tailscale up
   ```
2. Install the free **Tailscale** app on your Android phone and sign in with the same account.
3. Open `http://<tailscale-ip>:8080` in your phone browser.
4. Enjoy a direct, end-to-end encrypted WireGuard connection anywhere in the world.

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
