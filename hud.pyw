import os
import sys
import re
import json
import glob
import time
import datetime
import threading
import subprocess
import ctypes
import webview

USER_HOME = os.path.expanduser("~")
AGY_CLI_BRAIN = os.path.join(USER_HOME, ".agy", "antigravity", "brain")
CLI_BRAIN = os.path.join(USER_HOME, ".gemini", "antigravity-cli", "brain")
DESKTOP_BRAIN = os.path.join(USER_HOME, ".gemini", "antigravity", "brain")
BRAIN_DIRS = [AGY_CLI_BRAIN, CLI_BRAIN, DESKTOP_BRAIN]
QUOTA_HISTORY_FILE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "quota_history.json")
HUD_CONFIG_FILE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "hud_config.json")
AGY_EXE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "agy.exe")

CREATE_NO_WINDOW = 0x08000000

# Base Reference Rates (Gemini 3.8 Flash & Third-Party Baseline)
GEMINI_PRICE_IN = 0.75       # $0.75 / 1M
GEMINI_PRICE_CACHE = 0.075   # $0.075 / 1M
GEMINI_PRICE_OUT = 3.75      # $3.75 / 1M
GEMINI_PRICE_WEIGHTED = 2.25 # Blended weighted rate

TP_PRICE_IN = 3.00           # $3.00 / 1M
TP_PRICE_CACHE = 0.30        # $0.30 / 1M
TP_PRICE_OUT = 15.00         # $15.00 / 1M
TP_PRICE_WEIGHTED = 6.00     # Blended weighted rate

# Comprehensive Antigravity Model Catalog (Empirically Calibrated Quota Burn Multipliers, Tok/s Speeds & API Valuation Rates)
# weight: empirical relative quota consumption multiplier against the pool's 1.0x baseline model
MODEL_CATALOG = {
    # Gemini 4 Argon Family (Empirical: ~2.0x-2.6x relative burn, 127-138 tok/s median, 420-430 tok/s burst)
    "Gemini 4 Argon (High)": {
        "pool": "gemini", "weight": 2.6, "in": 2.50, "cache": 0.25, "out": 12.00, "weighted": 6.00, "avg_step_base": 2400, "speed_tok_s": 138.0
    },
    "Gemini 4 Argon (Medium)": {
        "pool": "gemini", "weight": 2.0, "in": 1.50, "cache": 0.15, "out": 8.00, "weighted": 4.25, "avg_step_base": 2100, "speed_tok_s": 127.0
    },
    "Gemini 4 Argon (Low)": {
        "pool": "gemini", "weight": 1.4, "in": 1.25, "cache": 0.125, "out": 6.00, "weighted": 3.20, "avg_step_base": 1800, "speed_tok_s": 145.0
    },
    # Gemini 3.1 Pro Family (Historical + Subagent Pro)
    "Gemini 3.1 Pro (High)": {
        "pool": "gemini", "weight": 2.5, "in": 2.00, "cache": 0.20, "out": 10.00, "weighted": 5.00, "avg_step_base": 2200, "speed_tok_s": 115.0
    },
    "Gemini 3.1 Pro (Low)": {
        "pool": "gemini", "weight": 1.4, "in": 1.25, "cache": 0.125, "out": 6.00, "weighted": 3.00, "avg_step_base": 1800, "speed_tok_s": 130.0
    },
    # Gemini 3.8 Flash Family (Empirical: Low=0.45x @ 231 tok/s [27.96M 5h], Med=1.0x @ 222.8 tok/s [11.62M 5h])
    "Gemini 3.8 Flash (High)": {
        "pool": "gemini", "weight": 1.15, "in": 0.75, "cache": 0.075, "out": 3.75, "weighted": 2.25, "avg_step_base": 1500, "speed_tok_s": 218.0
    },
    "Gemini 3.8 Flash (Medium)": {
        "pool": "gemini", "weight": 1.0, "in": 0.50, "cache": 0.05, "out": 2.50, "weighted": 1.50, "avg_step_base": 1350, "speed_tok_s": 222.8
    },
    "Gemini 3.8 Flash (Low)": {
        "pool": "gemini", "weight": 0.45, "in": 0.35, "cache": 0.035, "out": 1.50, "weighted": 0.95, "avg_step_base": 1100, "speed_tok_s": 231.0
    },
    "Gemini 3.8 Flash (Subagent)": {
        "pool": "gemini", "weight": 0.85, "in": 0.50, "cache": 0.05, "out": 2.50, "weighted": 1.50, "avg_step_base": 1200, "speed_tok_s": 225.0
    },
    # Third-Party Shared Pool (Empirical: 5h pool = 4.18M Sonnet-Med eff tokens, Weekly pool = 2.0x 5h pool = 8.36M eff tokens)
    "Claude Opus 5.5 (High)": {
        "pool": "tp", "weight": 2.5, "in": 15.00, "cache": 1.50, "out": 75.00, "weighted": 30.00, "avg_step_base": 2400, "speed_tok_s": 100.3
    },
    "Claude Opus 5.5 (Medium)": {
        "pool": "tp", "weight": 2.5, "in": 15.00, "cache": 1.50, "out": 75.00, "weighted": 30.00, "avg_step_base": 2100, "speed_tok_s": 98.6
    },
    "Claude Opus 5.5 (Low)": {
        "pool": "tp", "weight": 1.9, "in": 15.00, "cache": 1.50, "out": 75.00, "weighted": 30.00, "avg_step_base": 1800, "speed_tok_s": 93.6
    },
    "Claude Sonnet 5.5 (High)": {
        "pool": "tp", "weight": 1.25, "in": 3.00, "cache": 0.30, "out": 15.00, "weighted": 6.00, "avg_step_base": 2000, "speed_tok_s": 109.5
    },
    "Claude Sonnet 5.5 (Medium)": {
        "pool": "tp", "weight": 1.0, "in": 3.00, "cache": 0.30, "out": 15.00, "weighted": 6.00, "avg_step_base": 1750, "speed_tok_s": 103.7
    },
    "Claude Sonnet 5.5 (Low)": {
        "pool": "tp", "weight": 1.0, "in": 3.00, "cache": 0.30, "out": 15.00, "weighted": 6.00, "avg_step_base": 1500, "speed_tok_s": 101.3
    },
    "Claude Sonnet 4.6 (Thinking)": {
        "pool": "tp", "weight": 1.25, "in": 3.00, "cache": 0.30, "out": 15.00, "weighted": 6.00, "avg_step_base": 2000, "speed_tok_s": 105.0
    },
    "GPT-OSS 120B (Medium)": {
        "pool": "tp", "weight": 0.2, "in": 0.80, "cache": 0.08, "out": 3.20, "weighted": 1.80, "avg_step_base": 1400, "speed_tok_s": 105.8
    },
}

# Primary selectable models shown when "All Models" view is selected
PRIMARY_SELECTABLE_MODELS = [
    "Gemini 4 Argon (High)",
    "Gemini 4 Argon (Medium)",
    "Gemini 4 Argon (Low)",
    "Gemini 3.8 Flash (High)",
    "Gemini 3.8 Flash (Medium)",
    "Gemini 3.8 Flash (Low)",
    "Claude Opus 5.5 (High)",
    "Claude Opus 5.5 (Medium)",
    "Claude Opus 5.5 (Low)",
    "Claude Sonnet 5.5 (High)",
    "Claude Sonnet 5.5 (Medium)",
    "Claude Sonnet 5.5 (Low)",
    "GPT-OSS 120B (Medium)",
]


def get_model_spec(model_name: str) -> dict:
    if model_name in MODEL_CATALOG:
        return MODEL_CATALOG[model_name]
    low = model_name.lower()
    if "claude" in low or "gpt" in low or "opus" in low or "sonnet" in low:
        if "opus" in low:
            w = 2.5 if ("high" in low or "medium" in low or "thinking" in low) else 1.9
            return {"pool": "tp", "weight": w, "in": 15.0, "cache": 1.5, "out": 75.0, "weighted": 30.0, "avg_step_base": 2200, "speed_tok_s": 98.6}
        if "gpt" in low:
            return {"pool": "tp", "weight": 0.2, "in": 0.80, "cache": 0.08, "out": 3.20, "weighted": 1.80, "avg_step_base": 1400, "speed_tok_s": 105.8}
        w = 1.25 if ("high" in low or "thinking" in low) else 1.0
        return {"pool": "tp", "weight": w, "in": 3.0, "cache": 0.30, "out": 15.0, "weighted": 6.0, "avg_step_base": 1800, "speed_tok_s": 103.7}
    if "argon" in low:
        w = 2.6 if "high" in low else (1.4 if "low" in low else 2.0)
        return {"pool": "gemini", "weight": w, "in": 1.50, "cache": 0.15, "out": 8.00, "weighted": 4.25, "avg_step_base": 2100, "speed_tok_s": 132.0}
    if "pro" in low:
        w = 2.5 if "high" in low else 1.4
        return {"pool": "gemini", "weight": w, "in": 2.00, "cache": 0.20, "out": 10.00, "weighted": 5.00, "avg_step_base": 2000, "speed_tok_s": 120.0}
    w = 0.45 if ("low" in low or "lite" in low) else (1.0 if ("medium" in low or "subagent" in low) else 1.15)
    return {"pool": "gemini", "weight": w, "in": 0.75, "cache": 0.075, "out": 3.75, "weighted": 2.25, "avg_step_base": 1500, "speed_tok_s": 225.0}


# Win32 Native Setup
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.SetWindowPos.restype = ctypes.c_bool

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


def load_hud_config():
    default_config = {
        "pinned": True,
        "auto_prime": True,
        "global_yolo": True,
        "tp_expanded": False,
        "models_show_all": True,
        "theme": "oled",
        "active_tab": "5h",
        "last_w": 550,
        "last_h": 790
    }
    if os.path.exists(HUD_CONFIG_FILE):
        try:
            with open(HUD_CONFIG_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    default_config.update(d)
        except Exception:
            pass
    default_config["is_compact"] = False
    return default_config


def save_hud_config(config_dict):
    try:
        os.makedirs(os.path.dirname(HUD_CONFIG_FILE), exist_ok=True)
        to_save = dict(config_dict)
        to_save.pop("is_compact", None)
        with open(HUD_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2)
    except Exception:
        pass


def get_hud_hwnd():
    my_pid = os.getpid()
    hwnds = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, lparam):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == my_pid and user32.IsWindowVisible(hwnd):
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            if rect[2] - rect[0] > 30 and rect[3] - rect[1] > 20:
                hwnds.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return hwnds[0] if hwnds else None


def estimate_tokens(text):
    if not text:
        return 0
    return max(1, int(len(text) / 3.8))


def format_token_short(n: int) -> str:
    n = max(0, int(n))
    if n >= 1_000_000:
        return f"{n / 1_000_000.0:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000.0:.0f}k" if n >= 10_000 else f"{n / 1_000.0:.1f}k"
    return str(n)


HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Antigravity Live Monitor</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    :root {
      --bg-main: #0D0E12;
      --bg-titlebar: #12141A;
      --bg-card: #16181D;
      --bg-subcard: #1C1F26;
      --border-card: #2A2E39;
      --border-outer: #333846;
      --text-main: #FFFFFF;
      --text-muted: #94A3B8;
      --text-dim: #64748B;
      --accent-gemini: #10B981;
      --accent-tp: #A855F7;
      --accent-warn: #F59E0B;
      --accent-yolo: #EF4444;
      --ring-bg: #23272F;
    }

    [data-theme="oled"] {
      --bg-main: #000000;
      --bg-titlebar: #080808;
      --bg-card: #0D0D0D;
      --bg-subcard: #161616;
      --border-card: #383838;
      --border-outer: #525252;
      --text-main: #FFFFFF;
      --text-muted: #E2E8F0;
      --text-dim: #94A3B8;
      --accent-gemini: #00FF88;
      --accent-tp: #D946EF;
      --accent-warn: #FFCC00;
      --accent-yolo: #FF3B30;
      --ring-bg: #262626;
    }

    [data-theme="amber"] {
      --bg-main: #120E08;
      --bg-titlebar: #1A130B;
      --bg-card: #20180E;
      --bg-subcard: #2A2013;
      --border-card: #42321D;
      --border-outer: #5E4627;
      --text-main: #FFF7ED;
      --text-muted: #FDBA74;
      --text-dim: #D97706;
      --accent-gemini: #34D399;
      --accent-tp: #F472B6;
      --accent-warn: #FBBF24;
      --accent-yolo: #F87171;
      --ring-bg: #332414;
    }

    [data-theme="nordic"] {
      --bg-main: #0B1120;
      --bg-titlebar: #0F172A;
      --bg-card: #151F38;
      --bg-subcard: #1E293B;
      --border-card: #334155;
      --border-outer: #475569;
      --text-main: #F8FAFC;
      --text-muted: #CBD5E1;
      --text-dim: #94A3B8;
      --accent-gemini: #38BDF8;
      --accent-tp: #A5B4FC;
      --accent-warn: #FCD34D;
      --accent-yolo: #FB7185;
      --ring-bg: #1E293B;
    }

    [data-theme="light"] {
      --bg-main: #F8FAFC;
      --bg-titlebar: #F1F5F9;
      --bg-card: #FFFFFF;
      --bg-subcard: #F1F5F9;
      --border-card: #CBD5E1;
      --border-outer: #94A3B8;
      --text-main: #0F172A;
      --text-muted: #334155;
      --text-dim: #64748B;
      --accent-gemini: #059669;
      --accent-tp: #7C3AED;
      --accent-warn: #D97706;
      --accent-yolo: #DC2626;
      --ring-bg: #E2E8F0;
    }

    ::-webkit-scrollbar {
      display: none;
      width: 0;
      height: 0;
    }
    html, body, #mainContent {
      -ms-overflow-style: none;
      scrollbar-width: none;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--bg-main);
      color: var(--text-main);
      margin: 0;
      padding: 0;
      user-select: none;
      overflow: hidden;
      height: 100vh;
      width: 100vw;
      position: relative;
    }
    .mono {
      font-family: ui-monospace, SFMono-Regular, "Cascadia Code", "JetBrains Mono", Menlo, Consolas, monospace;
    }
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border-card);
    }
    .card-row {
      border-bottom: 1px solid var(--border-card);
    }
    .card-row:last-child {
      border-bottom: none;
    }
    .subcard {
      background: var(--bg-subcard);
      border: 1px solid var(--border-card);
    }
    .ring-bg { stroke: var(--ring-bg); }
    .ring-progress-emerald {
      stroke: var(--accent-gemini);
      transition: stroke-dashoffset 0.4s ease;
      transform: rotate(-90deg);
      transform-origin: 50% 50%;
    }
    .ring-progress-purple {
      stroke: var(--accent-tp);
      transition: stroke-dashoffset 0.4s ease;
      transform: rotate(-90deg);
      transform-origin: 50% 50%;
    }
    .drag-handle {
      cursor: grab;
    }
    .drag-handle:active {
      cursor: grabbing;
    }

    .resizer-r {
      position: absolute;
      right: 0;
      top: 0;
      bottom: 0;
      width: 6px;
      cursor: ew-resize;
      z-index: 999;
    }
    .resizer-b {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 6px;
      cursor: ns-resize;
      z-index: 999;
    }
    .resizer-corner {
      position: absolute;
      right: 0;
      bottom: 0;
      width: 12px;
      height: 12px;
      cursor: nwse-resize;
      z-index: 1000;
    }
    .corner-grip {
      position: absolute;
      right: 3px;
      bottom: 3px;
      font-size: 9px;
      line-height: 1;
      opacity: 0.4;
      pointer-events: none;
      color: var(--text-dim);
    }
  </style>
</head>
<body id="bodyRoot" data-theme="oled" class="flex flex-col h-screen w-screen box-border antialiased rounded-2xl shadow-2xl overflow-hidden" style="border: 1px solid var(--border-outer);">

  <!-- RESIZE HANDLES -->
  <div id="resizeRight" class="resizer-r"></div>
  <div id="resizeBottom" class="resizer-b"></div>
  <div id="resizeCorner" class="resizer-corner" title="Drag to Resize Window">
    <span class="corner-grip">◿</span>
  </div>

  <!-- 0. SLEEK CUSTOM TITLEBAR -->
  <div id="titlebar" ondblclick="toggleCompactMode()" class="drag-handle flex items-center justify-between px-3 select-none flex-shrink-0 transition-all duration-150 relative" style="background: var(--bg-titlebar); border-bottom: 1px solid var(--border-card); height: 42px;" title="Double-click anywhere to toggle ultra-minimal 1-line bar">
    
    <div id="fullHeaderLeft" class="flex items-center gap-2">
      <div class="w-3 h-3 rounded-full animate-pulse flex-shrink-0" style="background: var(--accent-gemini);"></div>
      <span class="text-sm font-bold tracking-wide mono" style="color: var(--text-main);">Antigravity Live Monitor</span>
    </div>

    <div id="fullControls" class="flex items-center gap-1.5" onclick="event.stopPropagation()">
      <!-- Force Sync Button -->
      <button onclick="triggerSync()" id="syncBtn" class="p-1 px-1.5 rounded-md transition text-xs mono cursor-pointer font-bold" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--text-main);" title="Force Refresh Official Quota">
        ↻
      </button>

      <!-- Collapse Button -->
      <button onclick="toggleCompactMode()" class="p-1 px-1.5 rounded-md transition text-xs mono cursor-pointer font-bold" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--text-main);" title="Collapse to 1-Line Mini Bar">
        ⛶
      </button>

      <!-- Global YOLO Mode Toggle -->
      <button onclick="toggleYolo()" id="yoloBtn" class="px-2 py-0.5 rounded-md border flex items-center gap-1 text-[11px] mono cursor-pointer font-bold" style="background: rgba(239, 68, 68, 0.2); border-color: var(--accent-yolo); color: var(--accent-yolo);" title="Global YOLO Mode (Auto-Approve All Permissions)">
        <span id="yoloDot" class="w-1.5 h-1.5 rounded-full animate-pulse" style="background: var(--accent-yolo);"></span>
        <span id="yoloText">YOLO</span>
      </button>

      <!-- Auto-Prime Toggle -->
      <button onclick="togglePrime()" id="primeBtn" class="px-2 py-0.5 rounded-md border flex items-center gap-1 text-[11px] mono cursor-pointer font-bold" style="background: rgba(245, 158, 11, 0.2); border-color: var(--accent-warn); color: var(--accent-warn);" title="Auto-Prime Dual Cooldowns (Gemini + Claude/GPT)">
        <span id="primeDot" class="w-1.5 h-1.5 rounded-full animate-pulse" style="background: var(--accent-warn);"></span>
        <span id="primeText">PRIME</span>
      </button>

      <!-- Always on Top Toggle -->
      <button onclick="togglePin()" id="pinBtn" class="px-2 py-0.5 rounded-md border flex items-center gap-1 text-[11px] mono cursor-pointer font-bold" style="background: rgba(16, 185, 129, 0.2); border-color: var(--accent-gemini); color: var(--accent-gemini);" title="Always on Top">
        <span id="pinDot" class="w-1.5 h-1.5 rounded-full" style="background: var(--accent-gemini);"></span>
        <span id="pinText">PIN</span>
      </button>

      <!-- Minimize -->
      <button onclick="minimizeWindow()" class="p-1 px-1.5 rounded-md transition text-xs mono cursor-pointer font-bold" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--text-main);" title="Minimize">
        −
      </button>

      <!-- Close -->
      <button onclick="closeWindow()" class="p-1 px-1.5 rounded-md transition text-xs mono cursor-pointer font-bold" style="background: rgba(239, 68, 68, 0.2); border: 1px solid var(--accent-yolo); color: var(--accent-yolo);" title="Close">
        ✕
      </button>
    </div>

    <!-- PURE MINIMALIST COMPACT STRIP -->
    <div id="compactBar" class="hidden w-full h-full flex items-center justify-around px-2">
      <div class="flex items-center gap-1.5" title="Gemini Weekly Limit Remaining">
        <svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 36 36">
          <path class="ring-bg" stroke-width="4.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
          <path id="miniGWRing" class="ring-progress-emerald" stroke-width="4.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
        </svg>
        <span class="mono text-xs font-black tracking-tight" style="color: var(--accent-gemini);" id="miniGWPct">--%</span>
        <span class="text-[10px] mono font-bold" style="color: var(--text-dim);">W</span>
      </div>

      <div class="w-px h-3.5" style="background: var(--border-card);"></div>

      <div class="flex items-center gap-1.5" title="Gemini 5-Hour Limit Remaining">
        <svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 36 36">
          <path class="ring-bg" stroke-width="4.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
          <path id="miniG5Ring" class="ring-progress-emerald" stroke-width="4.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
        </svg>
        <span class="mono text-xs font-black tracking-tight" style="color: var(--accent-warn);" id="miniG5Pct">--%</span>
        <span class="text-[10px] mono font-bold" style="color: var(--text-dim);">5h</span>
      </div>
    </div>

  </div>

  <!-- MAIN SCROLLABLE CONTENT -->
  <div id="mainContent" class="p-3.5 space-y-3 flex-1 overflow-y-auto">

    <!-- 1. GEMINI MODELS SECTION -->
    <div>
      <div class="flex items-center justify-between mb-1.5 px-1">
        <h2 class="text-xs font-bold tracking-tight uppercase flex items-center gap-1.5" style="color: var(--accent-gemini);">
          <span class="w-2.5 h-2.5 rounded-full inline-block" style="background: var(--accent-gemini);"></span>
          Gemini Quota Pool (Argon · Pro · Flash)
        </h2>
        <span class="text-[11px] mono font-semibold" style="color: var(--text-muted);" id="activeModelHeaderBadge">Active: Gemini 4 Argon</span>
      </div>

      <div class="card rounded-2xl overflow-hidden shadow-lg">

        <!-- Gemini Weekly Limit -->
        <div class="p-3 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-sm font-bold" style="color: var(--text-main);">Weekly Limit Remaining</span>
                <span class="text-sm font-bold mono" style="color: var(--accent-gemini);" id="geminiWeeklyRemain">~--M left</span>
              </div>
              <div class="text-xs mt-0.5 mono font-medium" style="color: var(--text-muted);" id="geminiWeeklyDesc">Resets in --</div>
            </div>
            <div class="flex items-center gap-2.5 flex-shrink-0">
              <span class="mono text-sm font-bold" style="color: var(--text-main);" id="geminiWeeklyPct">--%</span>
              <svg class="w-7 h-7" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="geminiWeeklyRing" class="ring-progress-emerald" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <!-- 4-Value Matrix -->
          <div class="grid grid-cols-4 gap-1.5 mt-2 text-[10px] mono">
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">1. Weighted</span>
              <span class="font-bold text-xs" style="color: var(--accent-gemini);" id="gwValWeighted">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">2. Input</span>
              <span class="font-bold text-xs" style="color: var(--text-main);" id="gwValInput">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">3. Output</span>
              <span class="font-bold text-xs" style="color: var(--accent-tp);" id="gwValOutput">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">4. Cache</span>
              <span class="font-bold text-xs" style="color: var(--accent-warn);" id="gwValCache">$0.00</span>
            </div>
          </div>
        </div>

        <!-- Gemini Five Hour Limit -->
        <div class="p-3 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-sm font-bold" style="color: var(--text-main);">Five Hour Limit Remaining</span>
                <span class="text-sm font-bold mono" style="color: var(--accent-warn);" id="gemini5hRemain">~--k left</span>
              </div>
              <div class="text-xs mt-0.5 mono font-medium" style="color: var(--text-muted);" id="gemini5hDesc">Resets in --</div>
            </div>
            <div class="flex items-center gap-2.5 flex-shrink-0">
              <span class="mono text-sm font-bold" style="color: var(--text-main);" id="gemini5hPct">--%</span>
              <svg class="w-7 h-7" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="gemini5hRing" class="ring-progress-emerald" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <!-- 4-Value Matrix -->
          <div class="grid grid-cols-4 gap-1.5 mt-2 text-[10px] mono">
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">1. Weighted</span>
              <span class="font-bold text-xs" style="color: var(--accent-gemini);" id="gfValWeighted">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">2. Input</span>
              <span class="font-bold text-xs" style="color: var(--text-main);" id="gfValInput">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">3. Output</span>
              <span class="font-bold text-xs" style="color: var(--accent-tp);" id="gfValOutput">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">4. Cache</span>
              <span class="font-bold text-xs" style="color: var(--accent-warn);" id="gfValCache">$0.00</span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- 2. CLAUDE & GPT THIRD-PARTY SECTION (COLLAPSIBLE) -->
    <div>
      <div onclick="toggleTpDetails()" class="card rounded-xl p-2.5 shadow-md flex items-center justify-between text-xs mono cursor-pointer transition">
        <div class="flex items-center gap-2">
          <span class="inline-block w-2.5 h-2.5 rounded-full" style="background: var(--accent-tp);" id="tpDot"></span>
          <span class="font-bold text-xs" style="color: var(--text-main);" id="tpSummary">Claude & GPT: 100% Weekly · 100% 5h</span>
        </div>
        <div class="flex items-center gap-2 text-xs font-semibold" style="color: var(--text-muted);">
          <span id="tpDetail">Details</span>
          <span id="tpArrow" class="text-xs transition-transform duration-200">▼</span>
        </div>
      </div>

      <div id="tpDetailsContainer" class="hidden mt-2 card rounded-2xl overflow-hidden shadow-lg">

        <!-- Claude Weekly Limit -->
        <div class="p-3 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-sm font-bold" style="color: var(--text-main);">Weekly Limit Remaining</span>
                <span class="text-sm font-bold mono" style="color: var(--accent-tp);" id="tpWeeklyRemain">~--M left</span>
              </div>
              <div class="text-xs mt-0.5 mono font-medium" style="color: var(--text-muted);" id="tpWeeklyDesc">Resets in --</div>
            </div>
            <div class="flex items-center gap-2.5 flex-shrink-0">
              <span class="mono text-sm font-bold" style="color: var(--text-main);" id="tpWeeklyPct">--%</span>
              <svg class="w-7 h-7" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="tpWeeklyRing" class="ring-progress-purple" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <div class="grid grid-cols-4 gap-1.5 mt-2 text-[10px] mono">
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">1. Weighted</span>
              <span class="font-bold text-xs" style="color: var(--accent-tp);" id="tpwValWeighted">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">2. Input</span>
              <span class="font-bold text-xs" style="color: var(--text-main);" id="tpwValInput">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">3. Output</span>
              <span class="font-bold text-xs" style="color: var(--accent-tp);" id="tpwValOutput">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">4. Cache</span>
              <span class="font-bold text-xs" style="color: var(--accent-warn);" id="tpwValCache">$0.00</span>
            </div>
          </div>
        </div>

        <!-- Claude Five Hour Limit -->
        <div class="p-3 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-sm font-bold" style="color: var(--text-main);">Five Hour Limit Remaining</span>
                <span class="text-sm font-bold mono" style="color: var(--accent-warn);" id="tp5hRemain">~--k left</span>
              </div>
              <div class="text-xs mt-0.5 mono font-medium" style="color: var(--text-muted);" id="tp5hDesc">Resets in --</div>
            </div>
            <div class="flex items-center gap-2.5 flex-shrink-0">
              <span class="mono text-sm font-bold" style="color: var(--text-main);" id="tp5hPct">--%</span>
              <svg class="w-7 h-7" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="tp5hRing" class="ring-progress-purple" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <div class="grid grid-cols-4 gap-1.5 mt-2 text-[10px] mono">
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">1. Weighted</span>
              <span class="font-bold text-xs" style="color: var(--accent-tp);" id="tpfValWeighted">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">2. Input</span>
              <span class="font-bold text-xs" style="color: var(--text-main);" id="tpfValInput">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">3. Output</span>
              <span class="font-bold text-xs" style="color: var(--accent-tp);" id="tpfValOutput">$0.00</span>
            </div>
            <div class="subcard p-1.5 rounded-lg text-center">
              <span class="block text-[9px] font-semibold" style="color: var(--text-dim);">4. Cache</span>
              <span class="font-bold text-xs" style="color: var(--accent-warn);" id="tpfValCache">$0.00</span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- 3. CURRENT ACTIVE QUOTA SLOT USAGE -->
    <div class="card rounded-2xl p-3 shadow-lg space-y-2.5">
      
      <!-- Slot Selector Tabs -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-1.5 p-0.5 rounded-lg border text-xs mono" style="background: var(--bg-subcard); border-color: var(--border-card);">
          <button id="tab5h" onclick="switchTab('5h')" class="px-3 py-1 rounded-md font-bold transition cursor-pointer" style="background: var(--border-card); color: var(--text-main);">Current 5h Slot</button>
          <button id="tabWeekly" onclick="switchTab('weekly')" class="px-3 py-1 rounded-md font-bold transition cursor-pointer" style="color: var(--text-muted);">Current Weekly Slot</button>
        </div>
        <span class="mono text-sm font-bold" style="color: var(--accent-gemini);" id="curSlotCost">Total Spent: $0.0000</span>
      </div>

      <!-- Model Category Breakdown Sub-bars -->
      <div class="grid grid-cols-2 gap-2 text-xs mono">
        <div class="subcard p-2 rounded-lg">
          <div class="flex justify-between font-bold" style="color: var(--text-main);">
            <span>Gemini Spent:</span>
            <span style="color: var(--accent-gemini);" id="geminiSlotCost">$0.0000</span>
          </div>
          <div class="text-[11px] mt-0.5 font-medium" style="color: var(--text-muted);" id="geminiSlotTokens">0 tokens</div>
        </div>
        <div class="subcard p-2 rounded-lg">
          <div class="flex justify-between font-bold" style="color: var(--text-main);">
            <span>Claude/GPT Spent:</span>
            <span style="color: var(--accent-tp);" id="tpSlotCost">$0.0000</span>
          </div>
          <div class="text-[11px] mt-0.5 font-medium" style="color: var(--text-muted);" id="tpSlotTokens">0 tokens</div>
        </div>
      </div>

      <!-- Live Exact Token & Cost Breakdown Grid -->
      <div class="grid grid-cols-3 gap-2">
        <div class="subcard p-2 rounded-xl text-center">
          <div class="text-[10px] uppercase font-bold tracking-wider" style="color: var(--text-dim);">Fresh In</div>
          <div class="mono text-sm font-bold mt-0.5" style="color: var(--text-main);" id="statIn">0k</div>
          <div class="mono text-[11px] font-bold" style="color: var(--accent-gemini);" id="statInCost">($0.0000)</div>
        </div>
        <div class="subcard p-2 rounded-xl text-center">
          <div class="text-[10px] uppercase font-bold tracking-wider" style="color: var(--text-dim);">Total Out</div>
          <div class="mono text-sm font-bold mt-0.5" style="color: var(--text-main);" id="statOut">0k</div>
          <div class="mono text-[11px] font-bold" style="color: var(--accent-tp);" id="statOutCost">($0.0000)</div>
        </div>
        <div class="subcard p-2 rounded-xl text-center">
          <div class="text-[10px] uppercase font-bold tracking-wider" style="color: var(--text-dim);">Cache Read</div>
          <div class="mono text-sm font-bold mt-0.5" style="color: var(--text-main);" id="statCache">0k</div>
          <div class="mono text-[11px] font-bold" style="color: var(--accent-warn);" id="statCacheCost">($0.0000)</div>
        </div>
      </div>

      <!-- 4. PER-MODEL USAGE & REMAINING QUOTA ESTIMATOR -->
      <div class="pt-2 border-t space-y-2" style="border-color: var(--border-card);">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5">
            <span class="text-xs font-bold uppercase tracking-tight" style="color: var(--text-main);">Per-Model Usage & Remaining</span>
            <span class="text-[10px] mono px-1.5 py-0.5 rounded font-bold" style="background: var(--bg-subcard); color: var(--text-muted); border: 1px solid var(--border-card);" id="modelSlotLabel">5h Window</span>
          </div>
          <button onclick="toggleModelsShowAll()" id="modelsFilterBtn" class="px-2 py-0.5 rounded text-[10px] mono font-bold cursor-pointer transition" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--accent-gemini);" title="Toggle between active models and all Antigravity models">
            Showing: All Models
          </button>
        </div>

        <div id="perModelTable" class="space-y-1.5">
          <!-- Populated dynamically by refreshData() -->
        </div>
      </div>

      <!-- Current Session Context Sub-pill -->
      <div class="pt-1.5 border-t flex justify-between items-center text-[11px] mono font-medium" style="border-color: var(--border-card); color: var(--text-muted);">
        <span id="wsName">Active: Workspace</span>
        <span id="sessionTokens">Current Chat: 0 tokens (0 turns)</span>
      </div>
    </div>

  </div>

  <!-- FOOTER STATUS & THEME SELECTOR -->
  <div id="footerStatus" class="flex items-center justify-between px-3.5 py-2 border-t text-xs mono font-semibold flex-shrink-0" style="background: var(--bg-titlebar); border-color: var(--border-card);">
    <div class="flex items-center gap-3">
      <span class="flex items-center gap-1.5" style="color: var(--text-muted);">
        <span class="inline-block w-2 h-2 rounded-full" style="background: var(--accent-gemini);"></span>
        <span id="syncPoints">Engine Synchronized (1s)</span>
      </span>

      <div class="flex items-center gap-1">
        <span style="color: var(--text-dim);">🎨</span>
        <select id="themeSelect" onchange="changeTheme(this.value)" class="border rounded px-1.5 py-0.5 text-xs mono cursor-pointer outline-none font-bold" style="background: var(--bg-subcard); border-color: var(--border-card); color: var(--text-main);">
          <option value="oled">High-Contrast OLED</option>
          <option value="dark">Onyx Dark</option>
          <option value="amber">Warm Amber (Eye-Care)</option>
          <option value="nordic">Nordic Frost</option>
          <option value="light">Paper Light</option>
        </select>
      </div>
    </div>

    <span id="timestamp" style="color: var(--text-dim);">--:--:--</span>
  </div>

  <script>
    let activeTab = '5h';
    let isPinned = true;
    let isAutoPrime = true;
    let isGlobalYolo = true;
    let isTpExpanded = false;
    let modelsShowAll = true;
    let isCompact = false;
    let currentTheme = 'oled';
    let isDragging = false;
    let startX = 0, startY = 0;

    let isResizing = false;
    let resizeDir = '';
    let resizeStartX = 0, resizeStartY = 0;
    let initialW = 0, initialH = 0;

    function setupDragAndResize() {
      const tb = document.getElementById('titlebar');
      if (tb) {
        tb.addEventListener('mousedown', (e) => {
          if (e.target.closest('button') || e.target.closest('select') || e.target.closest('input') || e.target.classList.contains('resizer-corner') || e.target.classList.contains('resizer-r') || e.target.classList.contains('resizer-b')) return;
          if (e.button === 0) {
            isDragging = true;
            startX = e.screenX;
            startY = e.screenY;
          }
        });
      }

      const rRight = document.getElementById('resizeRight');
      const rBottom = document.getElementById('resizeBottom');
      const rCorner = document.getElementById('resizeCorner');

      function startResize(e, dir) {
        e.stopPropagation();
        e.preventDefault();
        isResizing = true;
        resizeDir = dir;
        resizeStartX = e.screenX;
        resizeStartY = e.screenY;
        initialW = window.outerWidth || window.innerWidth;
        initialH = window.outerHeight || window.innerHeight;
      }

      if (rRight) rRight.addEventListener('mousedown', (e) => startResize(e, 'e'));
      if (rBottom) rBottom.addEventListener('mousedown', (e) => startResize(e, 's'));
      if (rCorner) rCorner.addEventListener('mousedown', (e) => startResize(e, 'se'));

      window.addEventListener('mousemove', (e) => {
        if (isDragging) {
          const dx = e.screenX - startX;
          const dy = e.screenY - startY;
          if (dx !== 0 || dy !== 0) {
            startX = e.screenX;
            startY = e.screenY;
            if (window.pywebview && window.pywebview.api) {
              window.pywebview.api.move_by(dx, dy);
            }
          }
        } else if (isResizing) {
          const dx = e.screenX - resizeStartX;
          const dy = e.screenY - resizeStartY;
          let nw = initialW;
          let nh = initialH;

          if (resizeDir.includes('e')) nw = initialW + dx;
          if (resizeDir.includes('s')) nh = initialH + dy;

          if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.resize_window(nw, nh);
          }
        }
      });

      window.addEventListener('mouseup', () => {
        isDragging = false;
        isResizing = false;
      });
    }

    function applyCompactVisual(compact) {
      isCompact = compact;
      const fullHeaderLeft = document.getElementById('fullHeaderLeft');
      const fullControls = document.getElementById('fullControls');
      const compactBar = document.getElementById('compactBar');
      const mainContent = document.getElementById('mainContent');
      const footerStatus = document.getElementById('footerStatus');
      const titlebar = document.getElementById('titlebar');

      if (isCompact) {
        if (fullHeaderLeft) fullHeaderLeft.classList.add('hidden');
        if (fullControls) fullControls.classList.add('hidden');
        if (compactBar) compactBar.classList.remove('hidden');
        if (mainContent) mainContent.classList.add('hidden');
        if (footerStatus) footerStatus.classList.add('hidden');
        if (titlebar) {
          titlebar.style.borderBottom = 'none';
          titlebar.style.height = '100%';
        }
      } else {
        if (fullHeaderLeft) fullHeaderLeft.classList.remove('hidden');
        if (fullControls) fullControls.classList.remove('hidden');
        if (compactBar) compactBar.classList.add('hidden');
        if (mainContent) mainContent.classList.remove('hidden');
        if (footerStatus) footerStatus.classList.remove('hidden');
        if (titlebar) {
          titlebar.style.borderBottom = '1px solid var(--border-card)';
          titlebar.style.height = '42px';
        }
      }
    }

    async function toggleCompactMode() {
      isCompact = !isCompact;
      applyCompactVisual(isCompact);
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.set_compact_mode(isCompact);
      }
    }

    function applyThemeVisual(themeName) {
      currentTheme = themeName || 'oled';
      document.body.setAttribute('data-theme', currentTheme);
      const sel = document.getElementById('themeSelect');
      if (sel) sel.value = currentTheme;
    }

    async function changeTheme(themeName) {
      applyThemeVisual(themeName);
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.set_theme(themeName);
      }
    }

    function toggleTpDetails() {
      isTpExpanded = !isTpExpanded;
      applyTpExpanded(isTpExpanded);
      if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.set_tp_expanded(isTpExpanded);
      }
    }

    function applyTpExpanded(expanded) {
      isTpExpanded = expanded;
      const container = document.getElementById('tpDetailsContainer');
      const arrow = document.getElementById('tpArrow');
      if (container && arrow) {
        if (isTpExpanded) {
          container.classList.remove('hidden');
          arrow.style.transform = 'rotate(180deg)';
        } else {
          container.classList.add('hidden');
          arrow.style.transform = 'rotate(0deg)';
        }
      }
    }

    function applyModelsShowAll(showAll) {
      modelsShowAll = showAll;
      const btn = document.getElementById('modelsFilterBtn');
      if (btn) {
        btn.textContent = modelsShowAll ? 'Showing: All Models' : 'Showing: Used Only';
        btn.style.color = modelsShowAll ? 'var(--accent-gemini)' : 'var(--accent-warn)';
      }
    }

    async function toggleModelsShowAll() {
      modelsShowAll = !modelsShowAll;
      applyModelsShowAll(modelsShowAll);
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.set_models_show_all(modelsShowAll);
      }
      refreshData();
    }

    function applyYoloVisual(enabled) {
      isGlobalYolo = enabled;
      const dot = document.getElementById('yoloDot');
      const text = document.getElementById('yoloText');
      const btn = document.getElementById('yoloBtn');
      if (isGlobalYolo) {
        dot.className = 'w-1.5 h-1.5 rounded-full animate-pulse';
        dot.style.background = 'var(--accent-yolo)';
        btn.style.background = 'rgba(239, 68, 68, 0.2)';
        btn.style.borderColor = 'var(--accent-yolo)';
        btn.style.color = 'var(--accent-yolo)';
        text.textContent = 'YOLO';
        btn.title = 'Global YOLO Mode (Enabled - Auto-Approve All Permissions)';
      } else {
        dot.className = 'w-1.5 h-1.5 rounded-full';
        dot.style.background = 'var(--text-dim)';
        btn.style.background = 'var(--bg-subcard)';
        btn.style.borderColor = 'var(--border-card)';
        btn.style.color = 'var(--text-muted)';
        text.textContent = 'YOLO: OFF';
        btn.title = 'Global YOLO Mode (Disabled - Standard Permission Prompts)';
      }
    }

    function applyPrimeVisual(enabled) {
      isAutoPrime = enabled;
      const dot = document.getElementById('primeDot');
      const text = document.getElementById('primeText');
      const btn = document.getElementById('primeBtn');
      if (isAutoPrime) {
        dot.className = 'w-1.5 h-1.5 rounded-full animate-pulse';
        dot.style.background = 'var(--accent-warn)';
        btn.style.background = 'rgba(245, 158, 11, 0.2)';
        btn.style.borderColor = 'var(--accent-warn)';
        btn.style.color = 'var(--accent-warn)';
        text.textContent = 'PRIME';
        btn.title = 'Auto-Prime Dual Cooldowns (Enabled)';
      } else {
        dot.className = 'w-1.5 h-1.5 rounded-full';
        dot.style.background = 'var(--text-dim)';
        btn.style.background = 'var(--bg-subcard)';
        btn.style.borderColor = 'var(--border-card)';
        btn.style.color = 'var(--text-muted)';
        text.textContent = 'PRIME: OFF';
        btn.title = 'Auto-Prime Dual Cooldowns (Disabled)';
      }
    }

    function applyPinVisual(pinned) {
      isPinned = pinned;
      const dot = document.getElementById('pinDot');
      const text = document.getElementById('pinText');
      const btn = document.getElementById('pinBtn');
      if (isPinned) {
        dot.className = 'w-1.5 h-1.5 rounded-full';
        dot.style.background = 'var(--accent-gemini)';
        btn.style.background = 'rgba(16, 185, 129, 0.2)';
        btn.style.borderColor = 'var(--accent-gemini)';
        btn.style.color = 'var(--accent-gemini)';
        text.textContent = 'PIN';
        btn.title = 'Always on Top (Enabled)';
      } else {
        dot.className = 'w-1.5 h-1.5 rounded-full';
        dot.style.background = 'var(--text-dim)';
        btn.style.background = 'var(--bg-subcard)';
        btn.style.borderColor = 'var(--border-card)';
        btn.style.color = 'var(--text-muted)';
        text.textContent = 'UNPIN';
        btn.title = 'Always on Top (Disabled)';
      }
    }

    function switchTab(tab) {
      activeTab = tab;
      const t5 = document.getElementById('tab5h');
      const tw = document.getElementById('tabWeekly');
      const lbl = document.getElementById('modelSlotLabel');
      if (tab === '5h') {
        t5.style.background = 'var(--border-card)';
        t5.style.color = 'var(--text-main)';
        tw.style.background = 'transparent';
        tw.style.color = 'var(--text-muted)';
        if (lbl) lbl.textContent = '5h Window';
      } else {
        tw.style.background = 'var(--border-card)';
        tw.style.color = 'var(--text-main)';
        t5.style.background = 'transparent';
        t5.style.color = 'var(--text-muted)';
        if (lbl) lbl.textContent = '7-Day Weekly';
      }
      refreshData();
    }

    async function toggleYolo() {
      if (window.pywebview && window.pywebview.api) {
        try {
          const newState = await window.pywebview.api.toggle_global_yolo();
          applyYoloVisual(newState);
        } catch (e) {
          console.error(e);
        }
      }
    }

    async function togglePrime() {
      if (window.pywebview && window.pywebview.api) {
        try {
          const newState = await window.pywebview.api.toggle_auto_prime();
          applyPrimeVisual(newState);
        } catch (e) {
          console.error(e);
        }
      }
    }

    async function togglePin() {
      if (window.pywebview && window.pywebview.api) {
        try {
          const newState = await window.pywebview.api.toggle_on_top();
          applyPinVisual(newState);
        } catch (e) {
          console.error(e);
        }
      }
    }

    function minimizeWindow() {
      if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.minimize();
      }
    }

    function closeWindow() {
      if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.close();
      }
    }

    function updateRing(elementId, percent) {
      const el = document.getElementById(elementId);
      if (el) {
        const offset = 100 - Math.min(100, Math.max(0, percent));
        el.setAttribute('stroke-dashoffset', offset);
      }
    }

    function fmtTok(n) {
      if (!n || n <= 0) return '0';
      if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
      if (n >= 10000) return (n / 1000).toFixed(0) + 'k';
      if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
      return n.toString();
    }

    async function triggerSync() {
      const btn = document.getElementById('syncBtn');
      if (btn) btn.textContent = '...';
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.force_sync();
        await refreshData();
      }
      setTimeout(() => { if (btn) btn.textContent = '↻'; }, 800);
    }

    function renderPerModelTable(d) {
      const container = document.getElementById('perModelTable');
      if (!container) return;
      const rows = (activeTab === '5h') ? (d.models_5h || []) : (d.models_weekly || []);
      const filtered = modelsShowAll ? rows : rows.filter(r => r.steps > 0 || r.is_active);

      if (!filtered.length) {
        container.innerHTML = '<div class="subcard p-2 rounded-lg text-center text-xs mono" style="color: var(--text-dim);">No model usage in this window yet.</div>';
        return;
      }

      let html = '';
      for (const m of filtered) {
        const isGem = m.pool === 'gemini';
        const dotColor = isGem ? 'var(--accent-gemini)' : 'var(--accent-tp)';
        const borderStyle = m.is_active ? `border: 1px solid ${dotColor};` : '';
        const activeTag = m.is_active
          ? `<span class="px-1.5 py-0.2 rounded text-[9px] font-black uppercase" style="background: rgba(16, 185, 129, 0.2); color: ${dotColor};">ACTIVE</span>`
          : '';
        const usedText = m.steps > 0
          ? `<span style="color: var(--text-main); font-weight: 700;">${m.steps} steps</span> · In: ${fmtTok(m.in_tokens)} · Out: ${fmtTok(m.out_tokens)} · Cache: ${fmtTok(m.cache_tokens)} <span style="color: ${dotColor}; font-weight: 700;">($${m.cost.toFixed(3)})</span>`
          : `<span style="color: var(--text-dim);">0 steps used in this slot</span>`;

        const bottleneckColor = (m.bottleneck === 'weekly') ? 'var(--accent-warn)' : dotColor;

        html += `
          <div class="subcard p-2 rounded-xl text-[11px] mono space-y-1" style="${borderStyle}">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="w-2 h-2 rounded-full flex-shrink-0" style="background: ${dotColor};"></span>
                <span class="font-bold text-xs" style="color: var(--text-main);">${m.name}</span>
                <span class="px-1 rounded text-[9px] font-bold" style="background: var(--bg-card); color: var(--text-dim); border: 1px solid var(--border-card);" title="Empirical Quota Burn Multiplier">${m.weight}x</span>
                <span class="px-1 rounded text-[9px] font-bold" style="background: var(--bg-card); color: var(--text-muted); border: 1px solid var(--border-card);" title="Empirically Benchmarked Median Output Speed">${Math.round(m.speed_tok_s || 100)} tok/s</span>
                ${activeTag}
              </div>
              <div class="text-right flex items-center gap-1.5">
                <span class="font-bold text-xs" style="color: ${bottleneckColor};" title="Effective Remaining Capacity (min of 5h vs Weekly pool for this model)">~${m.est_eff_remain_str} left</span>
                <span class="text-[10px]" style="color: var(--text-muted);" title="Estimated Remaining Turns/Steps on this model">(~${m.est_steps_left} steps)</span>
              </div>
            </div>
            <div class="flex items-center justify-between text-[10px]" style="color: var(--text-muted);">
              <div>${usedText}</div>
              <div class="flex-shrink-0" style="color: var(--text-dim);">
                5h: <span style="color: var(--text-muted);">${m.est_5h_remain_str}</span> · W: <span style="color: var(--text-muted);">${m.est_weekly_remain_str}</span>
              </div>
            </div>
          </div>
        `;
      }
      container.innerHTML = html;
    }

    async function refreshData() {
      if (window.pywebview && window.pywebview.api) {
        try {
          const d = await window.pywebview.api.get_metrics();
          if (!d) return;

          if (d.active_model) {
            const hdr = document.getElementById('activeModelHeaderBadge');
            if (hdr) hdr.textContent = 'Active: ' + d.active_model;
          }

          // 1. Gemini Weekly
          document.getElementById('geminiWeeklyPct').textContent = d.gemini_weekly_pct + '%';
          document.getElementById('geminiWeeklyDesc').textContent = d.gemini_weekly_desc;
          document.getElementById('geminiWeeklyRemain').textContent = '~' + d.gemini_est_weekly_remain_str + ' left';
          updateRing('geminiWeeklyRing', d.gemini_weekly_pct);

          document.getElementById('miniGWPct').textContent = d.gemini_weekly_pct + '%';
          updateRing('miniGWRing', d.gemini_weekly_pct);

          document.getElementById('gwValWeighted').textContent = '$' + d.gw_cost_weighted.toFixed(2);
          document.getElementById('gwValInput').textContent = '$' + d.gw_cost_in.toFixed(2);
          document.getElementById('gwValOutput').textContent = '$' + d.gw_cost_out.toFixed(2);
          document.getElementById('gwValCache').textContent = '$' + d.gw_cost_cache.toFixed(2);

          // 2. Gemini 5-Hour
          document.getElementById('gemini5hPct').textContent = d.gemini_5h_pct + '%';
          document.getElementById('gemini5hDesc').textContent = d.gemini_5h_desc;
          document.getElementById('gemini5hRemain').textContent = '~' + d.gemini_est_5h_remain_str + ' left';
          updateRing('gemini5hRing', d.gemini_5h_pct);

          document.getElementById('miniG5Pct').textContent = d.gemini_5h_pct + '%';
          updateRing('miniG5Ring', d.gemini_5h_pct);

          document.getElementById('gfValWeighted').textContent = '$' + d.gf_cost_weighted.toFixed(2);
          document.getElementById('gfValInput').textContent = '$' + d.gf_cost_in.toFixed(2);
          document.getElementById('gfValOutput').textContent = '$' + d.gf_cost_out.toFixed(2);
          document.getElementById('gfValCache').textContent = '$' + d.gf_cost_cache.toFixed(2);

          // 3. Claude & GPT Summary & Details
          document.getElementById('tpSummary').textContent = 'Claude & GPT: ' + d.tp_weekly_pct + '% Weekly · ' + d.tp_5h_pct + '% 5h';
          
          document.getElementById('tpWeeklyPct').textContent = d.tp_weekly_pct + '%';
          document.getElementById('tpWeeklyDesc').textContent = d.tp_weekly_desc;
          document.getElementById('tpWeeklyRemain').textContent = '~' + d.tp_est_weekly_remain_str + ' left';
          updateRing('tpWeeklyRing', d.tp_weekly_pct);

          document.getElementById('tpwValWeighted').textContent = '$' + d.tpw_cost_weighted.toFixed(2);
          document.getElementById('tpwValInput').textContent = '$' + d.tpw_cost_in.toFixed(2);
          document.getElementById('tpwValOutput').textContent = '$' + d.tpw_cost_out.toFixed(2);
          document.getElementById('tpwValCache').textContent = '$' + d.tpw_cost_cache.toFixed(2);

          // 4. Claude & GPT 5-Hour
          document.getElementById('tp5hPct').textContent = d.tp_5h_pct + '%';
          document.getElementById('tp5hDesc').textContent = d.tp_5h_desc;
          document.getElementById('tp5hRemain').textContent = '~' + d.tp_est_5h_remain_str + ' left';
          updateRing('tp5hRing', d.tp_5h_pct);

          document.getElementById('tpfValWeighted').textContent = '$' + d.tpf_cost_weighted.toFixed(2);
          document.getElementById('tpfValInput').textContent = '$' + d.tpf_cost_in.toFixed(2);
          document.getElementById('tpfValOutput').textContent = '$' + d.tpf_cost_out.toFixed(2);
          document.getElementById('tpfValCache').textContent = '$' + d.tpf_cost_cache.toFixed(2);

          // 5. Active Slot Breakdown (5h vs Weekly)
          const in_tok = (activeTab === '5h') ? d.slot5_in : d.slotW_in;
          const out_tok = (activeTab === '5h') ? d.slot5_out : d.slotW_out;
          const cache_tok = (activeTab === '5h') ? d.slot5_cache : d.slotW_cache;
          const tot_c = (activeTab === '5h') ? d.slot5_total_cost : d.slotW_total_cost;
          const in_c = (activeTab === '5h') ? d.slot5_in_cost : d.slotW_in_cost;
          const out_c = (activeTab === '5h') ? d.slot5_out_cost : d.slotW_out_cost;
          const cache_c = (activeTab === '5h') ? d.slot5_cache_cost : d.slotW_cache_cost;

          const g_cost = (activeTab === '5h') ? d.slot5_gemini_cost : d.slotW_gemini_cost;
          const g_tokens = (activeTab === '5h') ? d.slot5_gemini_tokens : d.slotW_gemini_tokens;
          const tp_cost = (activeTab === '5h') ? d.slot5_tp_cost : d.slotW_tp_cost;
          const tp_tokens = (activeTab === '5h') ? d.slot5_tp_tokens : d.slotW_tp_tokens;

          document.getElementById('curSlotCost').textContent = 'Total Spent: $' + tot_c.toFixed(4);
          document.getElementById('geminiSlotCost').textContent = '$' + g_cost.toFixed(4);
          document.getElementById('geminiSlotTokens').textContent = fmtTok(g_tokens) + ' fresh+out';
          document.getElementById('tpSlotCost').textContent = '$' + tp_cost.toFixed(4);
          document.getElementById('tpSlotTokens').textContent = fmtTok(tp_tokens) + ' fresh+out';

          document.getElementById('statIn').textContent = fmtTok(in_tok);
          document.getElementById('statInCost').textContent = '($' + in_c.toFixed(4) + ')';

          document.getElementById('statOut').textContent = fmtTok(out_tok);
          document.getElementById('statOutCost').textContent = '($' + out_c.toFixed(4) + ')';

          document.getElementById('statCache').textContent = fmtTok(cache_tok);
          document.getElementById('statCacheCost').textContent = '($' + cache_c.toFixed(4) + ')';

          renderPerModelTable(d);

          document.getElementById('wsName').textContent = 'Active: ' + d.workspace;
          document.getElementById('sessionTokens').textContent = 'Chat: ' + fmtTok(d.session_total_tokens) + ' tok (' + d.turns + ' turns)';
          document.getElementById('syncPoints').textContent = 'Synced · ' + d.sample_count + ' cal pts';

          const now = new Date();
          document.getElementById('timestamp').textContent = now.toTimeString().split(' ')[0];
        } catch (err) {
          console.error(err);
        }
      }
    }

    async function init() {
      setupDragAndResize();
      if (window.pywebview && window.pywebview.api) {
        try {
          const cfg = await window.pywebview.api.get_config();
          if (cfg) {
            if (cfg.theme) applyThemeVisual(cfg.theme);
            if (typeof cfg.pinned === 'boolean') applyPinVisual(cfg.pinned);
            if (typeof cfg.auto_prime === 'boolean') applyPrimeVisual(cfg.auto_prime);
            if (typeof cfg.global_yolo === 'boolean') applyYoloVisual(cfg.global_yolo);
            if (typeof cfg.tp_expanded === 'boolean') applyTpExpanded(cfg.tp_expanded);
            if (typeof cfg.models_show_all === 'boolean') applyModelsShowAll(cfg.models_show_all);
          }
        } catch(e) {}
      }
      refreshData();
      setInterval(refreshData, 1000);
    }

    window.addEventListener('pywebviewready', init);
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 100));
  </script>
</body>
</html>
"""


class MetricsEngine:
    def __init__(self):
        self.history = self.load_history()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        self.five_h_start_dt = now_utc - datetime.timedelta(hours=5)
        self.weekly_start_dt = now_utc - datetime.timedelta(days=7)
        self.tp_five_h_start_dt = now_utc - datetime.timedelta(hours=5)
        self.tp_weekly_start_dt = now_utc - datetime.timedelta(days=7)
        self.gemini_5h_reset_dt = None
        self.tp_5h_reset_dt = None
        self.last_cal_save_ts = 0.0

        self.cached_metrics = {
            "active_model": "Gemini 4 Argon (Medium)",
            # Gemini Models
            "gemini_weekly_pct": 30,
            "gemini_weekly_desc": "Synchronizing...",
            "gemini_5h_pct": 94,
            "gemini_5h_desc": "Synchronizing...",
            "gemini_est_5h_remain_str": "810k",
            "gf_cost_weighted": 1.82,
            "gf_cost_in": 0.61,
            "gf_cost_out": 3.04,
            "gf_cost_cache": 0.06,
            "gemini_est_weekly_remain_str": "2.43M",
            "gw_cost_weighted": 5.46,
            "gw_cost_in": 1.82,
            "gw_cost_out": 9.10,
            "gw_cost_cache": 0.18,

            # Claude & GPT Models
            "tp_weekly_pct": 100,
            "tp_weekly_desc": "Synchronizing...",
            "tp_5h_pct": 100,
            "tp_5h_desc": "Synchronizing...",
            "tp_est_5h_remain_str": "250k",
            "tpf_cost_weighted": 1.50,
            "tpf_cost_in": 0.75,
            "tpf_cost_out": 3.75,
            "tpf_cost_cache": 0.08,
            "tp_est_weekly_remain_str": "1.50M",
            "tpw_cost_weighted": 9.00,
            "tpw_cost_in": 4.50,
            "tpw_cost_out": 22.50,
            "tpw_cost_cache": 0.45,

            "sample_count": len(self.history.get("samples_5h", [])),
            "workspace": "Active Workspace",
            "turns": 0,
            "session_total_tokens": 0,

            # Exact Slot Breakdown
            "slot5_in": 0,
            "slot5_out": 0,
            "slot5_cache": 0,
            "slot5_in_cost": 0.0,
            "slot5_out_cost": 0.0,
            "slot5_cache_cost": 0.0,
            "slot5_total_cost": 0.0,
            "slot5_gemini_cost": 0.0,
            "slot5_gemini_tokens": 0,
            "slot5_tp_cost": 0.0,
            "slot5_tp_tokens": 0,

            "slotW_in": 0,
            "slotW_out": 0,
            "slotW_cache": 0,
            "slotW_in_cost": 0.0,
            "slotW_out_cost": 0.0,
            "slotW_cache_cost": 0.0,
            "slotW_total_cost": 0.0,
            "slotW_gemini_cost": 0.0,
            "slotW_gemini_tokens": 0,
            "slotW_tp_cost": 0.0,
            "slotW_tp_tokens": 0,

            # Per-Model Breakdown & Remaining Estimations
            "models_5h": [],
            "models_weekly": []
        }
        self.running = True
        self.start_worker()

    def load_history(self):
        if os.path.exists(QUOTA_HISTORY_FILE):
            try:
                with open(QUOTA_HISTORY_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, dict):
                        d.setdefault("samples_5h", [])
                        d.setdefault("samples_weekly", [])
                        d.setdefault("samples_tp_5h", [])
                        d.setdefault("samples_tp_weekly", [])
                        return d
            except Exception:
                pass
        return {"samples_5h": [], "samples_weekly": [], "samples_tp_5h": [], "samples_tp_weekly": []}

    def save_history(self):
        try:
            with open(QUOTA_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass

    def start_worker(self):
        t_disk = threading.Thread(target=self._disk_worker_loop, daemon=True)
        t_disk.start()

        t_usage = threading.Thread(target=self._usage_worker_loop, daemon=True)
        t_usage.start()

    def _usage_worker_loop(self):
        while self.running:
            try:
                self.query_official_usage()
            except Exception:
                pass
            time.sleep(45.0)

    def query_official_usage(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            # IMPORTANT: Do NOT pass --disable-slash-commands so /usage executes natively in ~4s
            cmd = [AGY_EXE if os.path.exists(AGY_EXE) else "agy", "-p", "/usage"]
            out = subprocess.check_output(
                cmd,
                stdin=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=18,
                startupinfo=si,
                creationflags=CREATE_NO_WINDOW
            )

            now = datetime.datetime.now(datetime.timezone.utc)
            for line in out.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 4:
                    group, metric, pct_str, reset_iso = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
                    pct = int(pct_str.replace("%", "").strip())
                    reset_dt = datetime.datetime.fromisoformat(reset_iso.replace("Z", "+00:00"))
                    diff_secs = max(0, int((reset_dt - now).total_seconds()))

                    days = diff_secs // 86400
                    hours = (diff_secs % 86400) // 3600
                    mins = (diff_secs % 3600) // 60

                    if days > 0:
                        d_txt = f"{days} day" if days == 1 else f"{days} days"
                        h_txt = f"{hours} hour" if hours == 1 else f"{hours} hours"
                        m_txt = f"{mins} min" if mins == 1 else f"{mins} mins"
                        time_txt = f"{d_txt}, {h_txt}, {m_txt}"
                    elif hours > 0:
                        h_txt = f"{hours} hour" if hours == 1 else f"{hours} hours"
                        m_txt = f"{mins} min" if mins == 1 else f"{mins} mins"
                        time_txt = f"{h_txt}, {m_txt}"
                    else:
                        m_txt = f"{mins} min" if mins == 1 else f"{mins} mins"
                        time_txt = f"{m_txt}"

                    short_desc = f"Resets in {time_txt}"

                    if "Gemini" in group:
                        if "Weekly" in metric:
                            self.cached_metrics["gemini_weekly_pct"] = pct
                            self.cached_metrics["gemini_weekly_desc"] = short_desc
                            self.weekly_start_dt = reset_dt - datetime.timedelta(days=7)
                        elif "Five Hour" in metric:
                            self.cached_metrics["gemini_5h_pct"] = pct
                            self.cached_metrics["gemini_5h_desc"] = short_desc
                            self.five_h_start_dt = reset_dt - datetime.timedelta(hours=5)
                            self.gemini_5h_reset_dt = reset_dt
                    elif "Claude" in group or "GPT" in group:
                        if "Weekly" in metric:
                            self.cached_metrics["tp_weekly_pct"] = pct
                            self.cached_metrics["tp_weekly_desc"] = short_desc
                            self.tp_weekly_start_dt = reset_dt - datetime.timedelta(days=7)
                        elif "Five Hour" in metric:
                            self.cached_metrics["tp_5h_pct"] = pct
                            self.cached_metrics["tp_5h_desc"] = short_desc
                            self.tp_five_h_start_dt = reset_dt - datetime.timedelta(hours=5)
                            self.tp_5h_reset_dt = reset_dt

            self._update_pool_valuations()
        except Exception:
            pass

    def _update_pool_valuations(self):
        learned_5h_cap = self.compute_learned_cap(self.history.get("samples_5h", []), default=1350000)
        learned_weekly_cap = self.compute_learned_cap(self.history.get("samples_weekly", []), default=8083900)
        learned_tp_5h_cap = self.compute_learned_cap(self.history.get("samples_tp_5h", []), default=255000)
        learned_tp_weekly_cap = self.compute_learned_cap(self.history.get("samples_tp_weekly", []), default=510000)

        # 1. Gemini Pool Remaining (1.0x Flash-Equivalent Base Units)
        cur_g_5h = self.cached_metrics["gemini_5h_pct"]
        est_g_5h_rem = int(learned_5h_cap * (cur_g_5h / 100.0))
        self.cached_metrics["gemini_est_5h_remain_str"] = format_token_short(est_g_5h_rem)
        self.cached_metrics["gf_cost_weighted"] = (est_g_5h_rem / 1000000.0) * GEMINI_PRICE_WEIGHTED
        self.cached_metrics["gf_cost_in"] = (est_g_5h_rem / 1000000.0) * GEMINI_PRICE_IN
        self.cached_metrics["gf_cost_out"] = (est_g_5h_rem / 1000000.0) * GEMINI_PRICE_OUT
        self.cached_metrics["gf_cost_cache"] = (est_g_5h_rem / 1000000.0) * GEMINI_PRICE_CACHE

        cur_g_weekly = self.cached_metrics["gemini_weekly_pct"]
        est_g_w_rem = int(learned_weekly_cap * (cur_g_weekly / 100.0))
        self.cached_metrics["gemini_est_weekly_remain_str"] = format_token_short(est_g_w_rem)
        self.cached_metrics["gw_cost_weighted"] = (est_g_w_rem / 1000000.0) * GEMINI_PRICE_WEIGHTED
        self.cached_metrics["gw_cost_in"] = (est_g_w_rem / 1000000.0) * GEMINI_PRICE_IN
        self.cached_metrics["gw_cost_out"] = (est_g_w_rem / 1000000.0) * GEMINI_PRICE_OUT
        self.cached_metrics["gw_cost_cache"] = (est_g_w_rem / 1000000.0) * GEMINI_PRICE_CACHE

        # 2. Claude & GPT Third-Party Pool Remaining (1.0x Sonnet-Equivalent Base Units)
        cur_tp_5h = self.cached_metrics["tp_5h_pct"]
        est_tp_5h_rem = int(learned_tp_5h_cap * (cur_tp_5h / 100.0))
        self.cached_metrics["tp_est_5h_remain_str"] = format_token_short(est_tp_5h_rem)
        self.cached_metrics["tpf_cost_weighted"] = (est_tp_5h_rem / 1000000.0) * TP_PRICE_WEIGHTED
        self.cached_metrics["tpf_cost_in"] = (est_tp_5h_rem / 1000000.0) * TP_PRICE_IN
        self.cached_metrics["tpf_cost_out"] = (est_tp_5h_rem / 1000000.0) * TP_PRICE_OUT
        self.cached_metrics["tpf_cost_cache"] = (est_tp_5h_rem / 1000000.0) * TP_PRICE_CACHE

        cur_tp_weekly = self.cached_metrics["tp_weekly_pct"]
        est_tp_w_rem = int(learned_tp_weekly_cap * (cur_tp_weekly / 100.0))
        self.cached_metrics["tp_est_weekly_remain_str"] = format_token_short(est_tp_w_rem)
        self.cached_metrics["tpw_cost_weighted"] = (est_tp_w_rem / 1000000.0) * TP_PRICE_WEIGHTED
        self.cached_metrics["tpw_cost_in"] = (est_tp_w_rem / 1000000.0) * TP_PRICE_IN
        self.cached_metrics["tpw_cost_out"] = (est_tp_w_rem / 1000000.0) * TP_PRICE_OUT
        self.cached_metrics["tpw_cost_cache"] = (est_tp_w_rem / 1000000.0) * TP_PRICE_CACHE

        self.cached_metrics["sample_count"] = len(self.history.get("samples_5h", []))

    def compute_learned_cap(self, samples, default):
        if not samples:
            return default
        caps = [s["implied_cap"] for s in samples if s.get("implied_cap", 0) > 10000]
        if not caps:
            return default
        caps.sort()
        mid = len(caps) // 2
        return caps[mid]

    def _build_subagent_map(self, all_logs):
        subagent_map = {}
        for _, log_path in all_logs:
            cur_model = None
            pending_subagents = []
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as fp:
                    for line in fp:
                        if not line.strip():
                            continue
                        if "Model Selection" not in line and "invoke_subagent" not in line and "Created the following subagents" not in line:
                            continue
                        try:
                            d = json.loads(line)
                        except Exception:
                            continue
                        c = str(d.get("content", ""))
                        if d.get("type") == "USER_INPUT" and "<USER_SETTINGS_CHANGE>" in c and "Model Selection" in c:
                            m = re.search(r"Model Selection`?\s+from\s+.*?\s+to\s+([^\.\n`]+)\.\s+No need", c)
                            if m:
                                cur_model = m.group(1).strip()
                        for tc in d.get("tool_calls") or []:
                            if tc.get("name") == "invoke_subagent":
                                raw_subs = (tc.get("args") or {}).get("Subagents", "")
                                try:
                                    subs = raw_subs if isinstance(raw_subs, list) else json.loads(str(raw_subs))
                                    if isinstance(subs, list):
                                        for s in subs:
                                            if isinstance(s, dict):
                                                pending_subagents.append(s.get("Model", "inherit"))
                                except Exception:
                                    pass
                        if "Created the following subagents:" in c:
                            cids = re.findall(r'"conversationId":\s*"([a-f0-9\-]+)"', c)
                            for idx, cid in enumerate(cids):
                                sm = pending_subagents[idx] if idx < len(pending_subagents) else "inherit"
                                subagent_map[cid] = (sm, cur_model or "Gemini 4 Argon (Medium)")
                            pending_subagents = []
            except Exception:
                pass
        return subagent_map

    def calculate_slot(self, start_dt, subagent_map=None, all_logs=None):
        start_ts = start_dt.timestamp()

        if all_logs is None:
            all_logs = []
            for b in BRAIN_DIRS:
                if os.path.exists(b):
                    for f in glob.glob(os.path.join(b, "*", ".system_generated", "logs", "transcript.jsonl")):
                        try:
                            mt = os.path.getmtime(f)
                            if mt >= start_ts:
                                all_logs.append((mt, f))
                        except Exception:
                            pass
            all_logs.sort(key=lambda x: x[0], reverse=True)
        else:
            all_logs = [item for item in all_logs if item[0] >= start_ts]

        if subagent_map is None:
            subagent_map = self._build_subagent_map(all_logs)

        total_in = 0
        total_out = 0
        total_cache = 0
        total_in_cost = 0.0
        total_out_cost = 0.0
        total_cache_cost = 0.0
        gemini_tokens = 0
        gemini_cost = 0.0
        gemini_base_units = 0
        gemini_legacy_units = 0
        tp_tokens = 0
        tp_cost = 0.0
        tp_base_units = 0
        tp_legacy_units = 0
        legacy_weighted_units = 0

        by_model = {}

        bench_tag_models = {
            "BENCH_phase1_flash_low": "Gemini 3.8 Flash (Low)",
            "BENCH_phase2_flash_medium": "Gemini 3.8 Flash (Medium)",
            "BENCH_phase3_flash_high": "Gemini 3.8 Flash (High)",
            "BENCH_phase4_argon_low": "Gemini 4 Argon (Low)",
            "BENCH_phase5_argon_medium": "Gemini 4 Argon (Medium)",
            "BENCH_phase6_argon_medium": "Gemini 4 Argon (Medium)",
            "BENCH_phase7_argon_high": "Gemini 4 Argon (High)",
            "BENCH_tp1_gpt_oss_120b": "GPT-OSS 120B (Medium)",
            "BENCH_tp2_claude_sonnet_55_low": "Claude Sonnet 5.5 (Low)",
            "BENCH_tp3_claude_sonnet_55_medium": "Claude Sonnet 5.5 (Medium)",
            "BENCH_tp4_claude_sonnet_55_high": "Claude Sonnet 5.5 (High)",
            "BENCH_tp5_claude_opus_55_low": "Claude Opus 5.5 (Low)",
            "BENCH_tp6_claude_opus_55_medium": "Claude Opus 5.5 (Medium)",
            "BENCH_tp7_claude_opus_55_high": "Claude Opus 5.5 (High)",
        }

        for _, log_path in all_logs:
            conv_id = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(log_path))))
            cur_model = None
            if conv_id in subagent_map:
                sm, parent_m = subagent_map[conv_id]
                if sm == "flash":
                    cur_model = "Gemini 3.8 Flash (Subagent)"
                elif sm == "flash_lite":
                    cur_model = "Gemini 3.8 Flash (Low)"
                elif sm == "pro":
                    cur_model = "Gemini 4 Argon (High)"
                else:
                    cur_model = parent_m

            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as fp:
                    for line in fp:
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except Exception:
                            continue

                        t = data.get("type", "")
                        c = str(data.get("content", ""))
                        if t == "USER_INPUT":
                            if "<USER_SETTINGS_CHANGE>" in c and "Model Selection" in c:
                                m = re.search(r"Model Selection`?\s+from\s+.*?\s+to\s+([^\.\n`]+)\.\s+No need", c)
                                if m:
                                    cur_model = m.group(1).strip()
                            elif "BENCH_" in c:
                                for btag, bmod in bench_tag_models.items():
                                    if btag in c:
                                        cur_model = bmod
                                        break
                        if data.get("modelName"):
                            cur_model = str(data.get("modelName")).strip()
                        elif data.get("model"):
                            cur_model = str(data.get("model")).strip()

                        if "created_at" not in data:
                            continue
                        try:
                            dt = datetime.datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
                        except Exception:
                            continue

                        if dt < start_dt:
                            continue

                        model_key = cur_model or "Gemini 3.8 Flash (High)"
                        spec = get_model_spec(model_key)

                        # Maintain legacy content heuristic separated by pool for quota_history.json compatibility
                        if t in ["USER_INPUT", "CODE_ACTION", "RUN_COMMAND", "GENERIC", "TOOL_RESULT"]:
                            lw = int(estimate_tokens(c) * spec["weight"])
                            legacy_weighted_units += lw
                            if spec["pool"] == "tp":
                                tp_legacy_units += lw
                            else:
                                gemini_legacy_units += lw
                        elif t in ["PLANNER_RESPONSE", "MODEL"]:
                            legacy_tok = estimate_tokens(c) + estimate_tokens(str(data.get("thinking", "")))
                            lw = int(legacy_tok * spec["weight"])
                            legacy_weighted_units += lw
                            if spec["pool"] == "tp":
                                tp_legacy_units += lw
                            else:
                                gemini_legacy_units += lw

                            # Extract exact server-reported telemetry tokens
                            if "input_tokens" in data or "output_tokens" in data:
                                in_tok = int(data.get("input_tokens", 0) or 0)
                                cache_tok = int(data.get("cache_read_tokens", 0) or data.get("cached_content_token_count", 0) or 0)
                                out_tok = int(data.get("output_tokens", 0) or 0)
                            else:
                                in_tok = estimate_tokens(c)
                                cache_tok = 0
                                out_tok = legacy_tok

                            step_in_cost = (in_tok / 1_000_000.0) * spec["in"]
                            step_cache_cost = (cache_tok / 1_000_000.0) * spec["cache"]
                            step_out_cost = (out_tok / 1_000_000.0) * spec["out"]
                            step_total_cost = step_in_cost + step_cache_cost + step_out_cost

                            # Effective cache-discounted tokens (90% discount on cached reads) & 1.0x pool base units
                            step_eff_tokens = in_tok + out_tok + int(cache_tok * 0.1)
                            step_base_units = int(step_eff_tokens * spec["weight"])

                            total_in += in_tok
                            total_cache += cache_tok
                            total_out += out_tok
                            total_in_cost += step_in_cost
                            total_cache_cost += step_cache_cost
                            total_out_cost += step_out_cost

                            if spec["pool"] == "tp":
                                tp_tokens += (in_tok + out_tok)
                                tp_cost += step_total_cost
                                tp_base_units += step_base_units
                            else:
                                gemini_tokens += (in_tok + out_tok)
                                gemini_cost += step_total_cost
                                gemini_base_units += step_base_units

                            m_entry = by_model.setdefault(model_key, {
                                "name": model_key,
                                "pool": spec["pool"],
                                "weight": spec["weight"],
                                "steps": 0,
                                "in_tokens": 0,
                                "cache_tokens": 0,
                                "out_tokens": 0,
                                "base_units": 0,
                                "cost": 0.0,
                            })
                            m_entry["steps"] += 1
                            m_entry["in_tokens"] += in_tok
                            m_entry["cache_tokens"] += cache_tok
                            m_entry["out_tokens"] += out_tok
                            m_entry["base_units"] += step_base_units
                            m_entry["cost"] += step_total_cost
            except Exception:
                pass

        return {
            "in": total_in,
            "out": total_out,
            "cache": total_cache,
            "total_tokens": total_in + total_out,
            "in_cost": total_in_cost,
            "out_cost": total_out_cost,
            "cache_cost": total_cache_cost,
            "total_cost": total_in_cost + total_out_cost + total_cache_cost,
            "gemini_tokens": gemini_tokens,
            "gemini_cost": gemini_cost,
            "gemini_base_units": gemini_base_units,
            "gemini_legacy_units": gemini_legacy_units,
            "tp_tokens": tp_tokens,
            "tp_cost": tp_cost,
            "tp_base_units": tp_base_units,
            "tp_legacy_units": tp_legacy_units,
            "legacy_weighted_units": legacy_weighted_units,
            "by_model": by_model,
        }

    def _append_cal_sample(self, key: str, used_units: int, pct_used: int, min_pct: int = 5, max_pct: int = 98, extra: dict = None) -> bool:
        if used_units <= 0 or pct_used < min_pct or pct_used > max_pct:
            return False
        implied_cap = int(used_units / (pct_used / 100.0))
        if implied_cap <= 10000:
            return False
        samples = self.history.setdefault(key, [])
        if samples:
            last = samples[-1]
            # Avoid duplicate consecutive samples when neither pct_used nor used_units moved significantly
            if last.get("pct_used") == pct_used and abs(int(last.get("used", 0)) - used_units) < 250:
                return False
        entry = {
            "ts": time.time(),
            "used": int(used_units),
            "pct_used": int(pct_used),
            "implied_cap": int(implied_cap),
        }
        if extra:
            entry.update(extra)
        samples.append(entry)
        if len(samples) > 600:
            del samples[:-600]
        return True

    def _record_calibration_samples(self, w5, wWeek, w5_tp, wWeek_tp):
        if self.gemini_5h_reset_dt is None:
            return
        now_ts = time.time()
        changed = False

        g5_pct_used = 100 - int(self.cached_metrics.get("gemini_5h_pct", 100))
        gw_pct_used = 100 - int(self.cached_metrics.get("gemini_weekly_pct", 100))
        tp5_pct_used = 100 - int(self.cached_metrics.get("tp_5h_pct", 100))
        tpw_pct_used = 100 - int(self.cached_metrics.get("tp_weekly_pct", 100))

        # Check if percentage changed on 5h pool (record immediately) or periodic 30s interval
        samples_5h = self.history.get("samples_5h", [])
        last_g5_pct = samples_5h[-1].get("pct_used") if samples_5h else None
        pct_jumped = (last_g5_pct != g5_pct_used)

        if not pct_jumped and (now_ts - self.last_cal_save_ts) < 30.0:
            return

        if self._append_cal_sample(
            "samples_5h",
            w5["gemini_legacy_units"],
            g5_pct_used,
            min_pct=5,
            max_pct=98,
            extra={
                "server_base_units": w5["gemini_base_units"],
                "raw_tokens": w5["gemini_tokens"],
                "cache_tokens": w5["cache"],
                "cost_usd": round(w5["gemini_cost"], 4),
            },
        ):
            changed = True

        if self._append_cal_sample(
            "samples_weekly",
            wWeek["gemini_legacy_units"],
            gw_pct_used,
            min_pct=2,
            max_pct=98,
            extra={
                "server_base_units": wWeek["gemini_base_units"],
                "raw_tokens": wWeek["gemini_tokens"],
                "cost_usd": round(wWeek["gemini_cost"], 4),
            },
        ):
            changed = True

        if self._append_cal_sample(
            "samples_tp_5h",
            w5_tp["tp_legacy_units"],
            tp5_pct_used,
            min_pct=5,
            max_pct=98,
            extra={
                "server_base_units": w5_tp["tp_base_units"],
                "raw_tokens": w5_tp["tp_tokens"],
                "cost_usd": round(w5_tp["tp_cost"], 4),
            },
        ):
            changed = True

        if self._append_cal_sample(
            "samples_tp_weekly",
            wWeek_tp["tp_legacy_units"],
            tpw_pct_used,
            min_pct=2,
            max_pct=98,
            extra={
                "server_base_units": wWeek_tp["tp_base_units"],
                "raw_tokens": wWeek_tp["tp_tokens"],
                "cost_usd": round(wWeek_tp["tp_cost"], 4),
            },
        ):
            changed = True

        if changed:
            self.last_cal_save_ts = now_ts
            self.save_history()

    def _build_model_rows(self, by_model_dict, active_model_name):
        learned_g_5h = self.compute_learned_cap(self.history.get("samples_5h", []), default=1350000)
        learned_g_w = self.compute_learned_cap(self.history.get("samples_weekly", []), default=8083900)
        learned_tp_5h = self.compute_learned_cap(self.history.get("samples_tp_5h", []), default=255000)
        learned_tp_w = self.compute_learned_cap(self.history.get("samples_tp_weekly", []), default=510000)

        g_5h_rem_base = learned_g_5h * (self.cached_metrics["gemini_5h_pct"] / 100.0)
        g_w_rem_base = learned_g_w * (self.cached_metrics["gemini_weekly_pct"] / 100.0)
        tp_5h_rem_base = learned_tp_5h * (self.cached_metrics["tp_5h_pct"] / 100.0)
        tp_w_rem_base = learned_tp_w * (self.cached_metrics["tp_weekly_pct"] / 100.0)

        all_model_names = []
        for m_name in by_model_dict.keys():
            if m_name not in all_model_names:
                all_model_names.append(m_name)
        if active_model_name and active_model_name not in all_model_names:
            all_model_names.append(active_model_name)
        for m_name in PRIMARY_SELECTABLE_MODELS:
            if m_name not in all_model_names:
                all_model_names.append(m_name)

        rows = []
        for m_name in all_model_names:
            spec = get_model_spec(m_name)
            usage = by_model_dict.get(m_name, {
                "steps": 0, "in_tokens": 0, "cache_tokens": 0, "out_tokens": 0, "cost": 0.0
            })
            w = max(0.1, float(spec["weight"]))
            if spec["pool"] == "gemini":
                rem_5h = int(g_5h_rem_base / w)
                rem_w = int(g_w_rem_base / w)
            else:
                rem_5h = int(tp_5h_rem_base / w)
                rem_w = int(tp_w_rem_base / w)

            eff_rem = min(rem_5h, rem_w)
            bottleneck = "weekly" if rem_w < rem_5h else "5h"
            avg_step = spec.get("avg_step_base", 1800)
            est_steps_left = max(0, int(eff_rem / avg_step))

            rows.append({
                "name": m_name,
                "pool": spec["pool"],
                "weight": spec["weight"],
                "speed_tok_s": spec.get("speed_tok_s", 100.0),
                "is_active": (m_name == active_model_name),
                "steps": usage["steps"],
                "in_tokens": usage["in_tokens"],
                "cache_tokens": usage["cache_tokens"],
                "out_tokens": usage["out_tokens"],
                "cost": usage["cost"],
                "est_5h_remain_str": format_token_short(rem_5h),
                "est_weekly_remain_str": format_token_short(rem_w),
                "est_eff_remain_str": format_token_short(eff_rem),
                "est_steps_left": est_steps_left,
                "bottleneck": bottleneck,
            })

        # Sort: Active model first, then models with usage > 0 (by steps desc), then catalog order
        rows.sort(key=lambda r: (
            0 if r["is_active"] else (1 if r["steps"] > 0 else 2),
            -r["steps"],
            0 if r["pool"] == "gemini" else 1,
            -r["weight"]
        ))
        return rows

    def _disk_worker_loop(self):
        while self.running:
            try:
                self._compute_disk_metrics()
            except Exception:
                pass
            time.sleep(1.5)

    def _compute_disk_metrics(self):
        # Gather all transcript logs modified within the last 8 days
        cutoff_ts = min(self.weekly_start_dt.timestamp(), self.tp_weekly_start_dt.timestamp()) - 86400
        all_logs = []
        for b in BRAIN_DIRS:
            if os.path.exists(b):
                for f in glob.glob(os.path.join(b, "*", ".system_generated", "logs", "transcript.jsonl")):
                    try:
                        mtime = os.path.getmtime(f)
                        if mtime >= cutoff_ts:
                            all_logs.append((mtime, f))
                    except Exception:
                        pass

        all_logs.sort(key=lambda x: x[0], reverse=True)
        subagent_map = self._build_subagent_map(all_logs)

        # Active Session Context & Active Model Detection (skip subagents and /usage or auto-prime pings)
        active_model_name = self.cached_metrics.get("active_model", "Gemini 4 Argon (Medium)")
        for _, cand_log in all_logs:
            cand_id = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(cand_log))))
            if cand_id in subagent_map:
                continue
            in_tokens = 0
            out_tokens = 0
            turns = 0
            ws_name = None
            session_model = None
            is_ping = False

            try:
                with open(cand_log, "r", encoding="utf-8", errors="ignore") as fp:
                    for line in fp:
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except Exception:
                            continue

                        t = data.get("type", "")
                        c = str(data.get("content", ""))
                        if turns == 0 and t == "USER_INPUT":
                            if (
                                "<USER_REQUEST>\n/usage\n</USER_REQUEST>" in c
                                or "<USER_REQUEST>\n1\n</USER_REQUEST>" in c
                                or "Benchmark Nonce " in c
                                or "[Benchmark ID:" in c
                            ):
                                is_ping = True
                                break

                        if t == "USER_INPUT" and "<USER_SETTINGS_CHANGE>" in c and "Model Selection" in c:
                            m = re.search(r"Model Selection`?\s+from\s+.*?\s+to\s+([^\.\n`]+)\.\s+No need", c)
                            if m:
                                session_model = m.group(1).strip()


                        t = data.get("type", "")
                        if t == "USER_INPUT":
                            turns += 1
                        elif t in ["PLANNER_RESPONSE", "MODEL"]:
                            if "input_tokens" in data or "output_tokens" in data:
                                in_tokens += int(data.get("input_tokens", 0) or 0)
                                out_tokens += int(data.get("output_tokens", 0) or 0)
                            else:
                                out_tokens += estimate_tokens(c) + estimate_tokens(str(data.get("thinking", "")))

                        if not ws_name and data.get("tool_calls"):
                            for tc in data["tool_calls"]:
                                args = tc.get("args") or tc.get("arguments") or {}
                                for _, v in args.items():
                                    if isinstance(v, str):
                                        val = v.replace("/", "\\").strip('"\'')
                                        if not (".gemini\\" in val.lower() or "brain\\" in val.lower()):
                                            p = val if os.path.isdir(val) else os.path.dirname(val)
                                            if p and len(p) > 3:
                                                ws_name = os.path.basename(p) or p
                                                break
                                if ws_name:
                                    break
            except Exception:
                continue

            if is_ping or turns == 0:
                continue

            if session_model:
                active_model_name = session_model
            self.cached_metrics["active_model"] = active_model_name
            self.cached_metrics["workspace"] = ws_name or "Active Workspace"
            self.cached_metrics["turns"] = turns
            self.cached_metrics["session_total_tokens"] = in_tokens + out_tokens
            break

        # 1. 5-Hour Slot Metrics (Gemini & Third-Party anchored to their respective reset timestamps)
        w5 = self.calculate_slot(self.five_h_start_dt, subagent_map=subagent_map, all_logs=all_logs)
        if abs((self.tp_five_h_start_dt - self.five_h_start_dt).total_seconds()) > 60:
            w5_tp = self.calculate_slot(self.tp_five_h_start_dt, subagent_map=subagent_map, all_logs=all_logs)
        else:
            w5_tp = w5

        self.cached_metrics["slot5_in"] = w5["in"]
        self.cached_metrics["slot5_out"] = w5["out"]
        self.cached_metrics["slot5_cache"] = w5["cache"]
        self.cached_metrics["slot5_in_cost"] = w5["in_cost"]
        self.cached_metrics["slot5_out_cost"] = w5["out_cost"]
        self.cached_metrics["slot5_cache_cost"] = w5["cache_cost"]
        self.cached_metrics["slot5_total_cost"] = w5["gemini_cost"] + w5_tp["tp_cost"]
        self.cached_metrics["slot5_gemini_cost"] = w5["gemini_cost"]
        self.cached_metrics["slot5_gemini_tokens"] = w5["gemini_tokens"]
        self.cached_metrics["slot5_tp_cost"] = w5_tp["tp_cost"]
        self.cached_metrics["slot5_tp_tokens"] = w5_tp["tp_tokens"]

        # 2. Weekly Slot Metrics (Gemini & Third-Party anchored to their respective reset timestamps)
        wWeek = self.calculate_slot(self.weekly_start_dt, subagent_map=subagent_map, all_logs=all_logs)
        if abs((self.tp_weekly_start_dt - self.weekly_start_dt).total_seconds()) > 60:
            wWeek_tp = self.calculate_slot(self.tp_weekly_start_dt, subagent_map=subagent_map, all_logs=all_logs)
        else:
            wWeek_tp = wWeek

        self.cached_metrics["slotW_in"] = wWeek["in"]
        self.cached_metrics["slotW_out"] = wWeek["out"]
        self.cached_metrics["slotW_cache"] = wWeek["cache"]
        self.cached_metrics["slotW_in_cost"] = wWeek["in_cost"]
        self.cached_metrics["slotW_out_cost"] = wWeek["out_cost"]
        self.cached_metrics["slotW_cache_cost"] = wWeek["cache_cost"]
        self.cached_metrics["slotW_total_cost"] = wWeek["gemini_cost"] + wWeek_tp["tp_cost"]
        self.cached_metrics["slotW_gemini_cost"] = wWeek["gemini_cost"]
        self.cached_metrics["slotW_gemini_tokens"] = wWeek["gemini_tokens"]
        self.cached_metrics["slotW_tp_cost"] = wWeek_tp["tp_cost"]
        self.cached_metrics["slotW_tp_tokens"] = wWeek_tp["tp_tokens"]

        # Merge per-model dictionaries when TP window differs from Gemini window
        by_model_5h = {k: v for k, v in w5["by_model"].items() if v.get("pool") != "tp"}
        for k, v in w5_tp["by_model"].items():
            if v.get("pool") == "tp":
                by_model_5h[k] = v

        by_model_w = {k: v for k, v in wWeek["by_model"].items() if v.get("pool") != "tp"}
        for k, v in wWeek_tp["by_model"].items():
            if v.get("pool") == "tp":
                by_model_w[k] = v

        # 3. Record empirical calibration samples & build model rows
        self._record_calibration_samples(w5, wWeek, w5_tp, wWeek_tp)
        self.cached_metrics["models_5h"] = self._build_model_rows(by_model_5h, active_model_name)
        self.cached_metrics["models_weekly"] = self._build_model_rows(by_model_w, active_model_name)
        self._update_pool_valuations()



class AutoPrimerWorker(threading.Thread):
    def __init__(self, engine, config):
        super().__init__(daemon=True)
        self.engine = engine
        self.config = config
        self.running = True
        self.last_gemini_prime = 0
        self.last_tp_prime = 0

    def run(self):
        while self.running:
            try:
                if self.config.get("auto_prime", True):
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    now_ts = time.time()

                    if self.engine.gemini_5h_reset_dt is not None:
                        gemini_rem_secs = (self.engine.gemini_5h_reset_dt - now_utc).total_seconds()
                        if gemini_rem_secs <= 0 and (now_ts - self.last_gemini_prime) > 180:
                            self.last_gemini_prime = now_ts
                            self.trigger_gemini_prime()

                    if self.engine.tp_5h_reset_dt is not None:
                        tp_rem_secs = (self.engine.tp_5h_reset_dt - now_utc).total_seconds()
                        if tp_rem_secs <= 0 and (now_ts - self.last_tp_prime) > 180:
                            self.last_tp_prime = now_ts
                            self.trigger_tp_prime()
            except Exception:
                pass
            time.sleep(15.0)

    def trigger_gemini_prime(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            cmd = [
                AGY_EXE if os.path.exists(AGY_EXE) else "agy",
                "-p", "1",
                "--model", "Gemini 3.8 Flash (Low)",
                "--disable-slash-commands",
                "--dangerously-skip-permissions"
            ]
            subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=si,
                creationflags=CREATE_NO_WINDOW,
                timeout=20
            )
            time.sleep(3.0)
            self.engine.query_official_usage()
        except Exception:
            pass

    def trigger_tp_prime(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            cmd = [
                AGY_EXE if os.path.exists(AGY_EXE) else "agy",
                "-p", "1",
                "--model", "GPT-OSS 120B (Medium)",
                "--disable-slash-commands",
                "--dangerously-skip-permissions"
            ]
            subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=si,
                creationflags=CREATE_NO_WINDOW,
                timeout=20
            )
            time.sleep(3.0)
            self.engine.query_official_usage()
        except Exception:
            pass


class Api:
    def __init__(self, engine, config):
        self.engine = engine
        self.config = config
        self.window = None
        self.is_on_top = config.get("pinned", True)
        self.is_auto_prime = config.get("auto_prime", True)
        self.is_global_yolo = config.get("global_yolo", True)
        self.is_tp_expanded = config.get("tp_expanded", False)
        self.models_show_all = config.get("models_show_all", True)
        self.is_compact = False
        self.current_theme = config.get("theme", "oled")

        self.last_expanded_w = config.get("last_w", 550)
        self.last_expanded_h = config.get("last_h", 820 if self.is_tp_expanded else 790)

    def set_window(self, window):
        self.window = window

    def get_config(self):
        return self.config

    def get_metrics(self):
        return self.engine.cached_metrics

    def force_sync(self):
        self.engine.query_official_usage()
        return True

    def move_by(self, dx, dy):
        hwnd = get_hud_hwnd()
        if hwnd:
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            cur_x = rect[0]
            cur_y = rect[1]
            user32.SetWindowPos(hwnd, 0, cur_x + dx, cur_y + dy, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        elif self.window:
            try:
                self.window.move(self.window.x + dx, self.window.y + dy)
            except Exception:
                pass

    def resize_window(self, new_w, new_h):
        min_w = 160 if self.is_compact else 380
        min_h = 30 if self.is_compact else 320
        target_w = max(min_w, int(new_w))
        target_h = max(min_h, int(new_h))

        if not self.is_compact:
            self.last_expanded_w = target_w
            self.last_expanded_h = target_h
            self.config["last_w"] = target_w
            self.config["last_h"] = target_h
            save_hud_config(self.config)

        hwnd = get_hud_hwnd()
        if hwnd:
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            cur_x = rect[0]
            cur_y = rect[1]
            user32.SetWindowPos(hwnd, 0, cur_x, cur_y, target_w, target_h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        elif self.window:
            try:
                self.window.resize(target_w, target_h)
            except Exception:
                pass
        return True

    def set_compact_mode(self, is_compact):
        hwnd = get_hud_hwnd()
        if hwnd and not self.is_compact:
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            cur_w = rect[2] - rect[0]
            cur_h = rect[3] - rect[1]
            if cur_w > 300 and cur_h > 200:
                self.last_expanded_w = cur_w
                self.last_expanded_h = cur_h

        self.is_compact = is_compact

        if hwnd:
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            cur_x = rect[0]
            cur_y = rect[1]
            if is_compact:
                w, h = 205, 34
            else:
                w = max(520, self.last_expanded_w)
                min_safe_h = 820 if self.is_tp_expanded else 760
                h = max(min_safe_h, self.last_expanded_h)
            user32.SetWindowPos(hwnd, 0, cur_x, cur_y, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        elif self.window:
            try:
                if is_compact:
                    self.window.resize(205, 34)
                else:
                    w = max(520, self.last_expanded_w)
                    min_safe_h = 820 if self.is_tp_expanded else 760
                    h = max(min_safe_h, self.last_expanded_h)
                    self.window.resize(w, h)
            except Exception:
                pass
        return self.is_compact

    def set_tp_expanded(self, expanded):
        self.is_tp_expanded = expanded
        self.config["tp_expanded"] = self.is_tp_expanded
        save_hud_config(self.config)
        return self.is_tp_expanded

    def set_models_show_all(self, show_all):
        self.models_show_all = bool(show_all)
        self.config["models_show_all"] = self.models_show_all
        save_hud_config(self.config)
        return self.models_show_all

    def set_theme(self, theme_name):
        self.current_theme = theme_name
        self.config["theme"] = theme_name
        save_hud_config(self.config)
        return self.current_theme

    def toggle_global_yolo(self):
        self.is_global_yolo = not self.is_global_yolo
        self.config["global_yolo"] = self.is_global_yolo
        save_hud_config(self.config)
        return self.is_global_yolo

    def toggle_auto_prime(self):
        self.is_auto_prime = not self.is_auto_prime
        self.config["auto_prime"] = self.is_auto_prime
        save_hud_config(self.config)
        return self.is_auto_prime

    def toggle_on_top(self):
        self.is_on_top = not self.is_on_top
        self.config["pinned"] = self.is_on_top
        save_hud_config(self.config)
        
        hwnd = get_hud_hwnd()
        if hwnd:
            flag = HWND_TOPMOST if self.is_on_top else HWND_NOTOPMOST
            user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        return self.is_on_top

    def minimize(self):
        hwnd = get_hud_hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, 6)
        elif self.window:
            try:
                self.window.minimize()
            except Exception:
                pass

    def close(self):
        if self.window:
            threading.Thread(target=self.window.destroy, daemon=True).start()


def main():
    mutex_name = "Global\\AntigravityHUD_SingleInstance_Mutex"
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:
        sys.exit(0)

    start_minimized = ("--minimized" in sys.argv) or ("-m" in sys.argv)
    config = load_hud_config()

    engine = MetricsEngine()
    primer = AutoPrimerWorker(engine, config)
    primer.start()

    api = Api(engine, config)

    is_tp = config.get("tp_expanded", False)
    init_w = config.get("last_w", 550)
    init_h = config.get("last_h", 820 if is_tp else 790)

    window = webview.create_window(
        title="Antigravity Live Monitor",
        html=HTML_CONTENT,
        js_api=api,
        width=init_w,
        height=init_h,
        frameless=True,
        on_top=config.get("pinned", True),
        minimized=start_minimized,
        resizable=True,
        background_color="#000000"
    )
    api.set_window(window)

    def on_startup():
        if start_minimized:
            for _ in range(25):
                hwnd = get_hud_hwnd()
                if hwnd:
                    # SW_SHOWMINNOACTIVE = 7 (minimizes to taskbar without stealing focus)
                    user32.ShowWindow(hwnd, 7)
                    break
                time.sleep(0.08)

    webview.start(on_startup)


if __name__ == "__main__":
    main()

