# 🚀 Space Shooter (Pygame)

A classic 2D vertical arcade space shooter built with Python and Pygame. Features dynamic level progression, challenging multi-phase boss encounters, responsive virtual resolution scaling, and local 2-player co-op support over TCP.

---

## ⚡ Features

- **Singleplayer Campaign**: Progressive difficulty levels with dynamic enemy spawning and scaling.
- **Boss Battles**: Multi-phase encounters with custom bullet patterns, enraged states, and minion spawning.
- **Adaptive Display**: Virtual Canvas (412x915) with automatic monitor resolution detection to fit any screen without distortion.
- **Co-op Multiplayer**: 2-player local network (LAN) co-op mode based on an integrated host-client architecture.
- **Settings & Persistence**: In-game audio sliders, custom keybinding remapping, auto-fire, screen shake, and FPS counter saved automatically.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.8+
- Install dependencies via [requirements.txt](file:///d:/Working/game-project/requirements.txt):
  ```powershell
  pip install -r requirements.txt
  ```

### 2. Launch Singleplayer
Run the main script directly from the project directory:
```powershell
python "game project/main.py"
```

### 3. Run Co-op Multiplayer
Launch two game instances:
1. **Host (Player 1)**: Select **"Create Co-op Room"** (`H`) in the main menu.
2. **Client (Player 2)**: Select **"Join Co-op Room"** (`J`) in the main menu, enter the host's IP address (default `127.0.0.1` on the same machine), and press `Enter`.

---

## 🎮 Controls

Default keybindings (fully customizable in the in-game Settings menu):

| Action | Default Key |
| :--- | :--- |
| **Move** | Arrow keys (`↑`, `↓`, `←`, `→`) |
| **Fire** | `Space` |
| **Settings / Pause** | `P` or click the Gear icon |
| **Back / Exit** | `Esc` |

---

## 👥 Contributors

- **Phan Hữu Gia Huy** ([@Aidesx](https://github.com/Aidesx)) - Core gameplay, original project development, assets integration, and logic refactoring.


---
