# Antigravity Live Monitor & Workspace Hub

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Model: Gemini 3.7 Flash](https://img.shields.io/badge/Model-Gemini%203.7%20Flash-orange.svg)](https://deepmind.google/technologies/gemini/)
[![CLI: agy-cli](https://img.shields.io/badge/Built%20with-agy--cli-purple.svg)](https://github.com/)

> **A real-time HUD monitor, empirical quota capacity regression engine, and cross-project workspace hub for Google Antigravity (AGY).**
>
> *Created by **Gemini 3.7 Flash** using **`agy-cli`** (Google Antigravity CLI).*

---

## 🌟 Key Features

### 1. Reverse-Engineered Quota Regression Engine
Google does not publish hard token ceiling numbers for developer quotas. This engine solves for your exact total token limits in real time:
- **Server Slot Synchronization:** Anchors directly to the active quota reset timestamps (`reset_timestamp - 5 hours` and `reset_timestamp - 7 days`), preventing rolling-window contamination.
- **Empirical Capacity Discovery:** Correlates real disk token consumption against server percentage snapshots ($W_{\text{slot}} / \text{Fraction Used}$) to calculate your empirical pool size.
- **Persistent Self-Calibration:** Saves calibration data points to `quota_history.json` and uses running median regression to continuously refine accuracy.

### 2. 4-Tier Financial Valuations (Gemini 3.7 Flash Pricing)
Translates abstract percentage limits and token pools into concrete pay-as-you-go API dollar values:
- **1. Weighted ($2.25/M):** Blended representative consumption rate.
- **2. Input Only ($0.75/M):** Full quota value if consumed strictly as fresh prompt tokens.
- **3. Output Only ($3.75/M):** Full quota value if consumed strictly as generation and thinking tokens.
- **4. Cache Only ($0.075/M):** Full quota value if consumed strictly as cached context reads (90% cache discount).

### 3. Cross-Project Slot Tracking
### 4. Modern Frameless Desktop HUD & Autostart
- **Custom Draggable Titlebar:** Borderless dark dashboard aesthetic with `-webkit-app-region: drag` and smooth cursor-tracking movement.
- **Auto-Prime 5h Cooldown (Enabled by Default):** Background worker monitors quota status; whenever the 5-hour quota is sitting idle at 100%, it automatically sends a minimal ephemeral ping to start the 5-hour cooldown timer in advance. This unlocks a back-to-back double-burst capacity (~1.7M tokens) when starting coding sessions.
- **Detailed Multi-Unit Timers:** Resets display precise days, hours, and minutes (`e.g., Resets in 6 days, 3 hours, 21 mins`).
- **Persistent Preferences:** Pin and Auto-Prime settings are saved to `hud_config.json` and automatically restored on launch.
- **Single-Instance Enforcement:** Protected by a Windows Named Mutex (`Local\AntigravityLiveMonitor_SingleInstance_Mutex`).
- **Windows & CLI Autostart:** Automatically launches on PC boot (`shell:startup`) and hooks into Antigravity session starts (`~/.gemini/config/hooks.json`).
- **Zero Console Popups:** Runs silently in the background with `CREATE_NO_WINDOW`.

### 5. Interactive Workspace Hub (`hub.py`)
- Discovers and maps every project across your PC (from VS Code state registries and local directories).
- Lists conversations, token metrics, turn counts, and launches CLI sessions with a single keypress.

---

## 🚀 Quick Start

### 1. Requirements
- Windows 10/11
- Python 3.10+
- `agy` (Google Antigravity CLI) installed and logged in

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/ares0027/antigravity-live-monitor.git
cd antigravity-live-monitor
pip install -r requirements.txt
```

### 3. Launch the HUD Monitor
Run silently without a console window:
```bash
pythonw hud.pyw
```
Or use the launcher batch file:
```bash
launch.bat
```

### 4. Launch the Interactive Hub
```bash
python hub.py
```

---

## 📊 Rate Sheet Reference (Gemini 3.7 Flash)

| Token Type | Official API Rate | Per 1,000 Tokens (1k) |
| :--- | :---: | :---: |
| **Fresh Prompt (Input)** | **$0.75 / 1M** | `$0.00075` |
| **Context Caching (Cache)** | **$0.075 / 1M** | `$0.000075` |
| **Output & Reasoning (Thinking)** | **$3.75 / 1M** | `$0.00375` |

---

## 📜 Architecture

```text
antigravity-live-monitor/
├── hud.pyw              # Frameless PyWebView Desktop Monitor & Regression Engine
├── hub.py              # Interactive Terminal Workspace & Conversation Hub
├── launch.bat          # Silent Windows launcher
├── requirements.txt    # Python dependencies (pywebview, pythonnet)
├── LICENSE             # MIT License
└── README.md           # Documentation & Architecture Guide
```

---

## 🤖 Attribution & Authorship

This software was engineered and designed by **Gemini 3.7 Flash** using **`agy-cli`** (Google Antigravity Advanced Agentic Coding CLI).

---

## 📄 License
MIT License. Free to use, modify, and distribute for personal and commercial applications.
