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
TRANSCRIPT_CACHE_FILE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "transcript_cache.json")
HUD_CONFIG_FILE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "hud_config.json")
QUOTA_PACE_FILE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "quota_pace_status.json")
AGY_EXE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "agy.exe")
SILENT_RUNNER_EXE = os.path.join(USER_HOME, ".gemini", "bin", "silent_mcp_runner.exe")
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

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
    # Gemini 4 Carbon Family
    "Gemini 4 Carbon (High)": {
        "pool": "gemini", "weight": 1.75, "in": 2.50, "cache": 0.25, "out": 12.00, "weighted": 6.00, "avg_step_base": 2000, "speed_tok_s": 135.0
    },
    "Gemini 4 Carbon (Medium)": {
        "pool": "gemini", "weight": 1.35, "in": 1.50, "cache": 0.15, "out": 8.00, "weighted": 4.25, "avg_step_base": 1650, "speed_tok_s": 142.0
    },
    "Gemini 4 Carbon (Low)": {
        "pool": "gemini", "weight": 1.05, "in": 1.25, "cache": 0.125, "out": 6.00, "weighted": 3.20, "avg_step_base": 1400, "speed_tok_s": 150.0
    },
    # Gemini 4 Hydrogen Family
    "Gemini 4 Hydrogen (XHigh)": {
        "pool": "gemini", "weight": 2.10, "in": 3.00, "cache": 0.30, "out": 15.00, "weighted": 7.50, "avg_step_base": 2200, "speed_tok_s": 115.0
    },
    "Gemini 4 Hydrogen (High)": {
        "pool": "gemini", "weight": 1.55, "in": 2.00, "cache": 0.20, "out": 10.00, "weighted": 5.00, "avg_step_base": 1850, "speed_tok_s": 128.0
    },
    "Gemini 4 Hydrogen (Medium)": {
        "pool": "gemini", "weight": 1.25, "in": 1.25, "cache": 0.125, "out": 6.00, "weighted": 3.50, "avg_step_base": 1600, "speed_tok_s": 140.0
    },
    "Gemini 4 Hydrogen (Low)": {
        "pool": "gemini", "weight": 0.95, "in": 0.90, "cache": 0.09, "out": 4.50, "weighted": 2.50, "avg_step_base": 1350, "speed_tok_s": 155.0
    },
    # Gemini 4 Argon Family (Empirical: ~2.0x-2.6x relative burn, 127-138 tok/s median, 420-430 tok/s burst)
    "Gemini 4 Argon (High)": {
        "pool": "gemini", "weight": 1.70, "in": 2.50, "cache": 0.25, "out": 12.00, "weighted": 6.00, "avg_step_base": 2000, "speed_tok_s": 138.0
    },
    "Gemini 4 Argon (Medium)": {
        "pool": "gemini", "weight": 1.34, "in": 1.50, "cache": 0.15, "out": 8.00, "weighted": 4.25, "avg_step_base": 1650, "speed_tok_s": 127.0
    },
    "Gemini 4 Argon (Low)": {
        "pool": "gemini", "weight": 1.05, "in": 1.25, "cache": 0.125, "out": 6.00, "weighted": 3.20, "avg_step_base": 1400, "speed_tok_s": 145.0
    },
    # Gemini 3.1 Pro Family (Historical + Subagent Pro)
    "Gemini 3.1 Pro (High)": {
        "pool": "gemini", "weight": 1.65, "in": 2.00, "cache": 0.20, "out": 10.00, "weighted": 5.00, "avg_step_base": 1900, "speed_tok_s": 115.0
    },
    "Gemini 3.1 Pro (Low)": {
        "pool": "gemini", "weight": 1.05, "in": 1.25, "cache": 0.125, "out": 6.00, "weighted": 3.00, "avg_step_base": 1400, "speed_tok_s": 130.0
    },
    # Gemini 3.8 Flash Family (1.00x Baseline = Flash High [862k 5h / 8.08M wk legacy units]; Med=0.87x, Low=0.45x)
    "Gemini 3.8 Flash (High)": {
        "pool": "gemini", "weight": 1.00, "in": 0.75, "cache": 0.075, "out": 3.75, "weighted": 2.25, "avg_step_base": 1350, "speed_tok_s": 218.0
    },
    "Gemini 3.8 Flash (Medium)": {
        "pool": "gemini", "weight": 0.87, "in": 0.50, "cache": 0.05, "out": 2.50, "weighted": 1.50, "avg_step_base": 1200, "speed_tok_s": 222.8
    },
    "Gemini 3.8 Flash (Low)": {
        "pool": "gemini", "weight": 0.45, "in": 0.35, "cache": 0.035, "out": 1.50, "weighted": 0.95, "avg_step_base": 950, "speed_tok_s": 231.0
    },
    "Gemini 3.8 Flash (Subagent)": {
        "pool": "gemini", "weight": 0.75, "in": 0.50, "cache": 0.05, "out": 2.50, "weighted": 1.50, "avg_step_base": 1100, "speed_tok_s": 225.0
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
    "Gemini 4 Carbon (High)",
    "Gemini 4 Carbon (Medium)",
    "Gemini 4 Carbon (Low)",
    "Gemini 4 Hydrogen (XHigh)",
    "Gemini 4 Hydrogen (High)",
    "Gemini 4 Hydrogen (Medium)",
    "Gemini 4 Hydrogen (Low)",
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
    if "carbon" in low:
        w = 1.75 if "high" in low else (1.05 if "low" in low else 1.35)
        return {"pool": "gemini", "weight": w, "in": 1.50, "cache": 0.15, "out": 8.00, "weighted": 4.25, "avg_step_base": 1650, "speed_tok_s": 142.0}
    if "hydrogen" in low:
        w = 2.10 if "xhigh" in low else (1.55 if "high" in low else (0.95 if "low" in low else 1.25))
        return {"pool": "gemini", "weight": w, "in": 1.25, "cache": 0.125, "out": 6.00, "weighted": 3.50, "avg_step_base": 1600, "speed_tok_s": 140.0}
    if "argon" in low:
        w = 1.70 if "high" in low else (1.05 if "low" in low else 1.34)
        return {"pool": "gemini", "weight": w, "in": 1.50, "cache": 0.15, "out": 8.00, "weighted": 4.25, "avg_step_base": 1650, "speed_tok_s": 132.0}
    if "pro" in low:
        w = 1.65 if "high" in low else 1.05
        return {"pool": "gemini", "weight": w, "in": 2.00, "cache": 0.20, "out": 10.00, "weighted": 5.00, "avg_step_base": 1800, "speed_tok_s": 120.0}
    w = 0.45 if ("low" in low or "lite" in low) else (0.87 if ("medium" in low or "subagent" in low) else 1.00)
    return {"pool": "gemini", "weight": w, "in": 0.75, "cache": 0.075, "out": 3.75, "weighted": 2.25, "avg_step_base": 1350, "speed_tok_s": 225.0}


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
        "view_mode": "minimal",
        "minimal_model": "auto",
        "theme": "oled",
        "active_tab": "5h",
        "last_w": 550,
        "last_h": 790,
        "last_x": None,
        "last_y": None,
        "font_scale_full": 1.0,
        "font_scale_mini": 1.0,
        "ctx_bars_count": 4,
        "ctx_unique_projects": False,
    }
    if os.path.exists(HUD_CONFIG_FILE):
        try:
            with open(HUD_CONFIG_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    default_config.update(d)
        except Exception:
            pass
    if default_config.get("view_mode") not in ("minimal", "verbose"):
        default_config["view_mode"] = "minimal"
    if not default_config.get("minimal_model"):
        default_config["minimal_model"] = "auto"
    default_config["is_compact"] = False
    return default_config


def save_hud_config(config_dict):
    try:
        os.makedirs(os.path.dirname(HUD_CONFIG_FILE), exist_ok=True)
        to_save = dict(config_dict)
        to_save.pop("is_compact", None)
        tmp_path = HUD_CONFIG_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2)
        os.replace(tmp_path, HUD_CONFIG_FILE)
    except Exception:
        pass


_ACTIVE_WEBVIEW_WINDOW = None


def get_hud_hwnd():
    global _ACTIVE_WEBVIEW_WINDOW
    if _ACTIVE_WEBVIEW_WINDOW is not None:
        try:
            nat = getattr(_ACTIVE_WEBVIEW_WINDOW, "native", None)
            if nat is not None and getattr(nat, "Handle", None) is not None:
                h = int(nat.Handle.ToInt64())
                if h:
                    return h
        except Exception:
            pass
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
      --font-scale: 1;
    }

    .text-sm {
      font-size: calc(14px * var(--font-scale)) !important;
      line-height: calc(19px * var(--font-scale)) !important;
    }
    .text-xs {
      font-size: calc(12px * var(--font-scale)) !important;
      line-height: calc(16px * var(--font-scale)) !important;
    }
    .text-\[11px\] {
      font-size: calc(11px * var(--font-scale)) !important;
      line-height: calc(15px * var(--font-scale)) !important;
    }
    .text-\[10px\] {
      font-size: calc(10px * var(--font-scale)) !important;
      line-height: calc(13.5px * var(--font-scale)) !important;
    }
    .text-\[9\.5px\] {
      font-size: calc(9.5px * var(--font-scale)) !important;
      line-height: calc(12px * var(--font-scale)) !important;
    }
    .text-\[9px\] {
      font-size: calc(9px * var(--font-scale)) !important;
      line-height: calc(12px * var(--font-scale)) !important;
    }
    .text-\[8px\] {
      font-size: calc(8px * var(--font-scale)) !important;
      line-height: calc(11px * var(--font-scale)) !important;
    }
    .mini-ring {
      width: calc(20px * var(--font-scale)) !important;
      height: calc(20px * var(--font-scale)) !important;
    }
    .mini-ring-dual {
      width: calc(34px * var(--font-scale)) !important;
      height: calc(34px * var(--font-scale)) !important;
    }
    .mini-divider {
      height: calc(28px * var(--font-scale)) !important;
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
    .ring-progress-timer {
      stroke: var(--accent-warn);
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
      <!-- View Mode Switcher (Minimal Default / Verbose) -->
      <div class="flex items-center p-0.5 rounded-md border text-[10px] mono font-bold" style="background: var(--bg-subcard); border-color: var(--border-card);" title="Switch between Minimal View (Model + Reset Summary) and Verbose View (Full Telemetry)">
        <button onclick="setViewMode('minimal')" id="btnModeMinimal" class="px-1.5 py-0.5 rounded cursor-pointer transition" style="background: var(--accent-gemini); color: #000000;">Min</button>
        <button onclick="setViewMode('verbose')" id="btnModeVerbose" class="px-1.5 py-0.5 rounded cursor-pointer transition" style="color: var(--text-muted);">Verb</button>
      </div>

      <!-- Force Refresh UI & Quota Button -->
      <button onclick="triggerSync()" id="syncBtn" class="p-1 px-2 rounded-md transition text-[11px] mono cursor-pointer font-bold flex items-center gap-1" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--accent-gemini);" title="Force Refresh UI & Re-query Official Antigravity Quota">
        ↻ Refresh
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

    <!-- PURE MINIMALIST COMPACT STRIP (META HEADER + CONCENTRIC CIRCLES: OUTER BLUE = QUOTA LEFT, INNER YELLOW = RESET TIMER) -->
    <div id="compactBar" class="hidden w-full h-full flex flex-col justify-center px-1.5 py-1 gap-1 min-w-0">
      <!-- Top Identity Row: Active Conversation Name + Active Model -->
      <div class="w-full flex items-center justify-between gap-1.5 pb-0.5 border-b leading-none min-w-0" style="border-color: var(--border-card);">
        <div class="flex items-center gap-1 min-w-0 flex-1">
          <span id="miniPoolDot" class="w-1.5 h-1.5 rounded-full flex-shrink-0" style="background: var(--accent-gemini);"></span>
          <span id="miniConvName" class="mono text-[9.5px] font-bold truncate min-w-0" style="color: var(--text-main);" title="Active Conversation">Detecting chat...</span>
        </div>
        <span id="miniModelName" class="mono text-[9px] font-bold flex-shrink-0 px-1.5 py-0 rounded whitespace-nowrap" style="background: var(--bg-subcard); color: var(--accent-gemini); border: 1px solid var(--border-card);" title="Active Model">--</span>
      </div>

      <!-- Bottom Metrics Row: Concentric Circles + Context/Pace + Refresh & Zoom -->
      <div class="w-full flex items-center justify-between gap-1.5 min-w-0">
      <!-- Weekly Concentric Circle: Outer Blue = Quota Left, Inner Yellow = Time Left -->
      <div class="flex flex-col items-center justify-center flex-shrink-0 leading-none" title="Weekly: Blue Outer = Quota Left · Yellow Inner = Time Left Until Reset">
        <svg class="mini-ring-dual flex-shrink-0" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20.5" class="ring-bg" stroke-width="4.2" fill="none" />
          <circle id="miniGWRing" data-circ="128.81" class="ring-progress-emerald" cx="24" cy="24" r="20.5" stroke-width="4.2" stroke-dasharray="128.81, 128.81" stroke-dashoffset="0" stroke-linecap="round" fill="none" />
          <circle cx="24" cy="24" r="14.0" class="ring-bg" stroke-width="3.6" fill="none" />
          <circle id="miniGWTimerRing" data-circ="87.96" class="ring-progress-timer" cx="24" cy="24" r="14.0" stroke-width="3.6" stroke-dasharray="87.96, 87.96" stroke-dashoffset="0" stroke-linecap="round" fill="none" />
          <text x="24" y="24.5" dominant-baseline="central" text-anchor="middle" font-size="11" font-weight="800" fill="var(--text-main)" class="mono">W</text>
        </svg>
        <div class="flex items-baseline justify-center gap-1 mt-0.5 leading-none whitespace-nowrap">
          <span class="mono text-[9.5px] font-black tracking-tight" style="color: var(--accent-gemini);" id="miniGWPct">--%</span>
          <span class="mono text-[9.5px] font-bold tracking-tight" style="color: var(--accent-warn);" id="miniWeeklyCooldown">--</span>
        </div>
      </div>

      <div class="w-px mini-divider flex-shrink-0" style="background: var(--border-card);"></div>

      <!-- 5-Hour Concentric Circle: Outer Blue = Quota Left, Inner Yellow = Time Left -->
      <div class="flex flex-col items-center justify-center flex-shrink-0 leading-none" title="5-Hour: Blue Outer = Quota Left · Yellow Inner = Time Left Until Reset">
        <svg class="mini-ring-dual flex-shrink-0" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20.5" class="ring-bg" stroke-width="4.2" fill="none" />
          <circle id="miniG5Ring" data-circ="128.81" class="ring-progress-emerald" cx="24" cy="24" r="20.5" stroke-width="4.2" stroke-dasharray="128.81, 128.81" stroke-dashoffset="0" stroke-linecap="round" fill="none" />
          <circle cx="24" cy="24" r="14.0" class="ring-bg" stroke-width="3.6" fill="none" />
          <circle id="miniG5TimerRing" data-circ="87.96" class="ring-progress-timer" cx="24" cy="24" r="14.0" stroke-width="3.6" stroke-dasharray="87.96, 87.96" stroke-dashoffset="0" stroke-linecap="round" fill="none" />
          <text x="24" y="24.5" dominant-baseline="central" text-anchor="middle" font-size="10.5" font-weight="800" fill="var(--text-main)" class="mono">5h</text>
        </svg>
        <div class="flex items-baseline justify-center gap-1 mt-0.5 leading-none whitespace-nowrap">
          <span class="mono text-[9.5px] font-black tracking-tight" style="color: var(--accent-gemini);" id="miniG5Pct">--%</span>
          <span class="mono text-[9.5px] font-bold tracking-tight" style="color: var(--accent-warn);" id="miniCooldown">--</span>
        </div>
      </div>

      <div class="w-px mini-divider flex-shrink-0" style="background: var(--border-card);"></div>

      <!-- Context & Pace Status (Stacked & Centered) -->
      <div class="flex flex-col items-center justify-center gap-0.5 flex-shrink-0" title="Active Conversation Context (Backpack Weight)">
        <span id="miniCtxWarn" class="px-1.5 py-0.2 rounded text-[9.5px] mono font-black whitespace-nowrap text-center" style="background: rgba(16, 185, 129, 0.18); color: var(--accent-gemini); border: 1px solid var(--accent-gemini);">🟢 0k</span>
        <span id="miniPaceWarn" class="hidden px-1.5 py-0 rounded text-[8px] mono font-black animate-pulse whitespace-nowrap text-center" style="background: rgba(239, 68, 68, 0.25); color: var(--accent-yolo); border: 1px solid var(--accent-yolo);" title="5h Burn Pace Depletion Alert">PACE!</span>
      </div>

      <!-- Aligned Force Refresh + Font Scale Controls (Up to 300%) -->
      <div class="flex items-stretch gap-1 flex-shrink-0" onclick="event.stopPropagation()" ondblclick="event.stopPropagation()">
        <button onclick="triggerSync()" id="miniSyncBtn" class="px-1.5 rounded text-[10px] mono font-bold cursor-pointer leading-none flex items-center justify-center" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--accent-gemini);" title="Force Refresh UI & Re-query Quota">↻</button>
        <div class="flex flex-col items-center justify-center gap-0.5">
          <button onclick="adjustFontSize(0.10)" class="px-1.5 py-0 rounded text-[9px] mono font-bold cursor-pointer leading-tight w-full text-center" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--text-main);" title="Increase Mini-Bar Icon & Font Size up to 300% (Ctrl + +)">A+</button>
          <button onclick="adjustFontSize(-0.10)" class="px-1.5 py-0 rounded text-[9px] mono font-bold cursor-pointer leading-tight w-full text-center" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--text-muted);" title="Decrease Mini-Bar Icon & Font Size (Ctrl + -)">A-</button>
        </div>
      </div>
      </div>
    </div>

  </div>

  <!-- MAIN SCROLLABLE CONTENT -->
  <div id="mainContent" class="p-3.5 space-y-3 flex-1 overflow-y-auto">

    <!-- MINIMAL VIEW (DEFAULT): CURRENT MODEL ONLY · CURRENT / LAST 3 / ALL RESETS -->
    <div id="minimalView" class="space-y-2.5">
      <!-- Active Conversation & Model Selector Card -->
      <div class="card rounded-2xl p-3 shadow-lg space-y-2">
        <div class="flex items-center justify-between gap-2 text-[10px] mono">
          <div class="flex items-center gap-1.5 min-w-0">
            <span id="minModeBadge" class="px-1.5 py-0.5 rounded font-black flex-shrink-0" style="background: rgba(16, 185, 129, 0.18); color: var(--accent-gemini); border: 1px solid var(--accent-gemini);">AUTO</span>
            <span id="minConvContext" class="truncate font-semibold" style="color: var(--text-muted);" title="Auto-detected active conversation">Detecting active conversation...</span>
          </div>
          <div class="flex items-center gap-1.5 flex-shrink-0">
            <button id="minResetAutoBtn" onclick="onMinimalModelChange('auto')" class="hidden px-1.5 py-0.5 rounded border text-[9px] mono font-bold cursor-pointer transition" style="background: rgba(245, 158, 11, 0.18); border-color: var(--accent-warn); color: var(--accent-warn);" title="Return to automatic current-conversation model detection">↺ Auto</button>
            <span id="minPoolBadge" class="px-1.5 py-0.5 rounded font-bold" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--accent-gemini);">Gemini · 1.0x</span>
          </div>
        </div>

        <div class="flex items-center justify-between gap-2">
          <select id="minimalModelSelect" onchange="onMinimalModelChange(this.value)" class="w-full border rounded-xl px-2.5 py-1.5 text-xs mono cursor-pointer outline-none font-bold" style="background: var(--bg-subcard); border-color: var(--border-card); color: var(--text-main);" title="Auto tracks your current conversation model; choose another model manually to simulate its token & $ capacity">
            <option value="auto">Auto (Detecting...)</option>
          </select>
        </div>

        <div class="flex items-center justify-between text-[10px] mono px-0.5" style="color: var(--text-dim);">
          <span id="minRateSpec">Rates: In $-- · Out $-- · Cache $-- /1M</span>
          <span id="minArchiveNote">Archive ready</span>
        </div>
      </div>

      <!-- 5-HOUR WINDOW CARD (MINIMAL) -->
      <div class="card rounded-2xl p-3 shadow-lg space-y-2">
        <div class="flex items-center justify-between gap-2 pb-1.5 border-b" style="border-color: var(--border-card);">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background: var(--accent-warn);"></span>
            <span class="text-xs font-bold uppercase tracking-tight" style="color: var(--text-main);">5-Hour Reset Window</span>
          </div>
          <div class="flex items-center gap-2">
            <span id="min5hCooldown" class="px-2 py-0.5 rounded-md text-[10px] mono font-bold" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--accent-warn);" title="Live countdown until next 5h quota reset">⏳ --</span>
            <span class="mono text-xs font-black" style="color: var(--text-main);" id="min5hPct">--%</span>
            <svg class="w-6 h-6 flex-shrink-0" viewBox="0 0 36 36">
              <path class="ring-bg" stroke-width="4" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <path id="min5hRing" class="ring-progress-emerald" stroke-width="4" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
            </svg>
          </div>
        </div>

        <div class="grid grid-cols-12 gap-1.5 px-1 text-[9px] mono font-bold uppercase" style="color: var(--text-dim);">
          <div class="col-span-3">Scope</div>
          <div class="col-span-4 text-right">Used (Tok / $)</div>
          <div class="col-span-5 text-right">Can Use Left (Tok / $)</div>
        </div>
        <div id="min5hRows" class="space-y-1.5"></div>
      </div>

      <!-- WEEKLY WINDOW CARD (MINIMAL) -->
      <div class="card rounded-2xl p-3 shadow-lg space-y-2">
        <div class="flex items-center justify-between gap-2 pb-1.5 border-b" style="border-color: var(--border-card);">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background: var(--accent-gemini);"></span>
            <span class="text-xs font-bold uppercase tracking-tight" style="color: var(--text-main);">Weekly Reset Window</span>
          </div>
          <div class="flex items-center gap-2">
            <span id="minWkCooldown" class="px-2 py-0.5 rounded-md text-[10px] mono font-bold" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--accent-gemini);" title="Live countdown until next Weekly quota reset">⏳ --</span>
            <span class="mono text-xs font-black" style="color: var(--text-main);" id="minWkPct">--%</span>
            <svg class="w-6 h-6 flex-shrink-0" viewBox="0 0 36 36">
              <path class="ring-bg" stroke-width="4" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <path id="minWkRing" class="ring-progress-emerald" stroke-width="4" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
            </svg>
          </div>
        </div>

        <div class="grid grid-cols-12 gap-1.5 px-1 text-[9px] mono font-bold uppercase" style="color: var(--text-dim);">
          <div class="col-span-3">Scope</div>
          <div class="col-span-4 text-right">Used (Tok / $)</div>
          <div class="col-span-5 text-right">Can Use Left (Tok / $)</div>
        </div>
        <div id="minWkRows" class="space-y-1.5"></div>
      </div>
    </div>

    <!-- VERBOSE VIEW: FULL TELEMETRY DASHBOARD -->
    <div id="verboseView" class="space-y-3 hidden">

    <!-- 0. MULTI-CONVERSATION CONTEXT & BACKPACK METER (VERY TOP) -->
    <div id="ctxMeterCard" class="card rounded-xl p-2.5 shadow-md space-y-2">
      <div class="flex items-center justify-between text-[10px] mono">
        <div class="flex items-center gap-1.5 font-bold uppercase tracking-tight" style="color: var(--text-muted);">
          <span>🎒 Active & Recent Backpacks</span>
          <span style="color: var(--text-dim);" class="text-[9px] font-normal">(Click row to pin to Mini-HUD)</span>
        </div>
        <div class="flex items-center gap-1">
          <button onclick="toggleCtxUniqueMode()" id="ctxUniqueBtn" class="px-1.5 py-0.5 rounded border text-[9px] mono font-bold cursor-pointer transition" style="background: var(--bg-subcard); border-color: var(--border-card); color: var(--accent-gemini);" title="Toggle between showing all recent conversations vs 1 latest conversation per project">All Chats</button>
          <button onclick="adjustCtxBarsCount(-1)" class="px-1.5 py-0.5 rounded border text-[9px] mono font-bold cursor-pointer transition" style="background: var(--bg-subcard); border-color: var(--border-card); color: var(--text-muted);" title="Show Fewer Conversation Bars">−</button>
          <span id="ctxBarsCountLabel" class="px-1 text-[9px] mono font-bold" style="color: var(--text-main);" title="Number of simultaneous conversation context bars">4 Bars</span>
          <button onclick="adjustCtxBarsCount(1)" class="px-1.5 py-0.5 rounded border text-[9px] mono font-bold cursor-pointer transition" style="background: var(--bg-subcard); border-color: var(--border-card); color: var(--text-main);" title="Show More Conversation Bars">+</button>
        </div>
      </div>

      <div id="ctxBarsContainer" class="space-y-1.5">
        <!-- Populated dynamically with N simultaneous conversation context bars -->
      </div>

      <div class="w-full h-[2px] rounded-full overflow-hidden" style="background: var(--bg-subcard);" title="Next Context Bar Refresh (2s cycle)">
        <div id="ctxReloadBar" class="h-full" style="width: 0%; background: var(--text-muted); opacity: 0.65;"></div>
      </div>
    </div>

    <!-- 1. GEMINI MODELS SECTION -->
    <div>
      <div class="flex items-center justify-between mb-1.5 px-1">
        <h2 class="text-xs font-bold tracking-tight uppercase flex items-center gap-1.5" style="color: var(--accent-gemini);">
          <span class="w-2.5 h-2.5 rounded-full inline-block" style="background: var(--accent-gemini);"></span>
          Gemini Quota Pool (Carbon · Argon · Hydrogen · Flash)
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

          <!-- 3-Window 5h Burn Pace & Depletion Guard (0->Now, Last 30m, Last 15m) -->
          <div class="mt-2.5 pt-2 border-t space-y-1.5" style="border-color: var(--border-card);">
            <div id="paceAlertBanner" class="px-2 py-1 rounded-lg text-[10px] mono font-bold flex items-center justify-between" style="background: var(--bg-subcard); border: 1px solid var(--border-card); color: var(--accent-gemini);">
              <span id="paceAlertText">✓ 5h Burn Pace Safe (Checking windows...)</span>
              <span id="paceClockSplit" style="color: var(--text-muted);">-- elapsed · -- left</span>
            </div>

            <div class="grid grid-cols-3 gap-1.5 text-[10px] mono">
              <!-- Window 1: 0 -> Current Time -->
              <div id="paceCardSlot" class="subcard p-1.5 rounded-lg space-y-0.5">
                <div class="flex items-center justify-between">
                  <span class="text-[9px] font-bold uppercase" style="color: var(--text-dim);">0→Now Slot</span>
                  <span id="paceBadgeSlot" class="px-1 rounded text-[8px] font-black" style="background: rgba(16,185,129,0.18); color: var(--accent-gemini);">SAFE</span>
                </div>
                <div class="font-bold text-[11px]" style="color: var(--text-main);" id="paceRateSlot">0.0%/hr</div>
                <div class="text-[9px]" style="color: var(--text-muted);" id="paceProjSlot">Proj: +0% vs 100% left</div>
                <div class="text-[9px] font-semibold" style="color: var(--text-dim);" id="paceEtaSlot">Runway: Safe</div>
              </div>

              <!-- Window 2: Last 30m -->
              <div id="paceCard30m" class="subcard p-1.5 rounded-lg space-y-0.5">
                <div class="flex items-center justify-between">
                  <span class="text-[9px] font-bold uppercase" style="color: var(--text-dim);">Last 30m</span>
                  <span id="paceBadge30m" class="px-1 rounded text-[8px] font-black" style="background: rgba(16,185,129,0.18); color: var(--accent-gemini);">SAFE</span>
                </div>
                <div class="font-bold text-[11px]" style="color: var(--text-main);" id="paceRate30m">0.0%/hr</div>
                <div class="text-[9px]" style="color: var(--text-muted);" id="paceProj30m">Proj: +0% vs 100% left</div>
                <div class="text-[9px] font-semibold" style="color: var(--text-dim);" id="paceEta30m">Runway: Safe</div>
              </div>

              <!-- Window 3: Last 15m -->
              <div id="paceCard15m" class="subcard p-1.5 rounded-lg space-y-0.5">
                <div class="flex items-center justify-between">
                  <span class="text-[9px] font-bold uppercase" style="color: var(--text-dim);">Last 15m</span>
                  <span id="paceBadge15m" class="px-1 rounded text-[8px] font-black" style="background: rgba(16,185,129,0.18); color: var(--accent-gemini);">SAFE</span>
                </div>
                <div class="font-bold text-[11px]" style="color: var(--text-main);" id="paceRate15m">0.0%/hr</div>
                <div class="text-[9px]" style="color: var(--text-muted);" id="paceProj15m">Proj: +0% vs 100% left</div>
                <div class="text-[9px] font-semibold" style="color: var(--text-dim);" id="paceEta15m">Runway: Safe</div>
              </div>
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
          <span id="tpHeaderCooldown" class="text-[10px] mono font-bold" style="color: var(--accent-tp);"></span>
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
    </div>

    </div><!-- end #verboseView -->

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

      <!-- Font Size Adjuster (Full View) -->
      <div class="flex items-center gap-1" title="Adjust HUD Font Scale (or use Ctrl + MouseWheel / Ctrl + +/-)">
        <button onclick="adjustFontSize(-0.08)" class="px-1.5 py-0.5 rounded border text-[10px] mono font-bold cursor-pointer transition" style="background: var(--bg-subcard); border-color: var(--border-card); color: var(--text-muted);" title="Smaller Font (Ctrl + -)">A-</button>
        <button onclick="resetFontSize()" id="fontScaleLabel" class="px-1.5 py-0.5 rounded border text-[10px] mono font-bold cursor-pointer transition" style="background: var(--bg-subcard); border-color: var(--border-card); color: var(--accent-gemini);" title="Click to Reset Font Size to 100% (Ctrl + 0)">100%</button>
        <button onclick="adjustFontSize(0.08)" class="px-1.5 py-0.5 rounded border text-[10px] mono font-bold cursor-pointer transition" style="background: var(--bg-subcard); border-color: var(--border-card); color: var(--text-main);" title="Larger Font (Ctrl + +)">A+</button>
      </div>
    </div>

    <span id="timestamp" style="color: var(--text-dim);">--:--:--</span>
  </div>

  <script>
    let activeTab = '5h';
    let viewMode = 'minimal';
    let minimalModelPref = 'auto';
    let lastMetrics = null;
    let isPinned = true;
    let isAutoPrime = true;
    let isGlobalYolo = true;
    let isTpExpanded = false;
    let modelsShowAll = true;
    let isCompact = false;
    let currentTheme = 'oled';
    let fontScaleFull = 1.0;
    let fontScaleMini = 1.0;
    let ctxBarsCount = 4;
    let ctxUniqueProjects = false;
    let pinnedSessionId = null;
    let lastTopSessionMtime = 0;
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
        if (isDragging && window.pywebview && window.pywebview.api && window.pywebview.api.save_window_pos) {
          window.pywebview.api.save_window_pos();
        }
        isDragging = false;
        isResizing = false;
      });

      window.addEventListener('wheel', (e) => {
        if (e.ctrlKey) {
          e.preventDefault();
          const delta = e.deltaY < 0 ? 0.06 : -0.06;
          adjustFontSize(delta);
        }
      }, { passive: false });

      window.addEventListener('keydown', (e) => {
        if (e.ctrlKey) {
          if (e.key === '=' || e.key === '+') {
            e.preventDefault();
            adjustFontSize(0.08);
          } else if (e.key === '-' || e.key === '_') {
            e.preventDefault();
            adjustFontSize(-0.08);
          } else if (e.key === '0') {
            e.preventDefault();
            resetFontSize();
          }
        }
      });
    }

    function applyFontScaleVisual() {
      const activeScale = isCompact ? fontScaleMini : fontScaleFull;
      document.documentElement.style.setProperty('--font-scale', activeScale.toFixed(3));
      const lbl = document.getElementById('fontScaleLabel');
      if (lbl) {
        lbl.textContent = Math.round(fontScaleFull * 100) + '%';
      }
    }

    async function adjustFontSize(delta) {
      if (isCompact) {
        fontScaleMini = Math.min(3.0, Math.max(0.75, Math.round((fontScaleMini + delta) * 100) / 100));
        applyFontScaleVisual();
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_font_scale('mini', fontScaleMini);
        }
      } else {
        fontScaleFull = Math.min(3.0, Math.max(0.75, Math.round((fontScaleFull + delta) * 100) / 100));
        applyFontScaleVisual();
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_font_scale('full', fontScaleFull);
        }
      }
    }

    async function resetFontSize() {
      if (isCompact) {
        fontScaleMini = 1.0;
        applyFontScaleVisual();
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_font_scale('mini', 1.0);
        }
      } else {
        fontScaleFull = 1.0;
        applyFontScaleVisual();
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_font_scale('full', 1.0);
        }
      }
    }

    function applyCtxBarPrefsVisual() {
      const cntLbl = document.getElementById('ctxBarsCountLabel');
      if (cntLbl) {
        cntLbl.textContent = ctxBarsCount + (ctxBarsCount === 1 ? ' Bar' : ' Bars');
      }
      const uBtn = document.getElementById('ctxUniqueBtn');
      if (uBtn) {
        uBtn.textContent = ctxUniqueProjects ? '1 / Project' : 'All Chats';
        uBtn.style.color = ctxUniqueProjects ? 'var(--accent-warn)' : 'var(--accent-gemini)';
      }
    }

    async function adjustCtxBarsCount(delta) {
      ctxBarsCount = Math.min(8, Math.max(1, ctxBarsCount + delta));
      applyCtxBarPrefsVisual();
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.set_ctx_bars_prefs(ctxBarsCount, ctxUniqueProjects);
      }
      refreshData();
    }

    async function toggleCtxUniqueMode() {
      ctxUniqueProjects = !ctxUniqueProjects;
      applyCtxBarPrefsVisual();
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.set_ctx_bars_prefs(ctxBarsCount, ctxUniqueProjects);
      }
      refreshData();
    }

    function selectPinnedSession(cid) {
      pinnedSessionId = (pinnedSessionId === cid) ? null : cid;
      refreshData();
    }

    function updateCompactMeta(d, targetMini) {
      const convEl = document.getElementById('miniConvName');
      const modelEl = document.getElementById('miniModelName');
      const dotEl = document.getElementById('miniPoolDot');
      const m = (d && d.minimal) || {};

      const convProject = (targetMini && targetMini.project) || m.conv_project || '';
      const rawTitle = (targetMini && (targetMini.title || targetMini.topic)) || m.conv_title || '';
      const convDisplay = rawTitle || convProject || 'Active Chat';
      const convTip = (convProject && rawTitle && rawTitle !== convProject)
        ? `[${convProject}] ${rawTitle}`
        : convDisplay;

      const modelName = (targetMini && targetMini.session_model) || m.detected_model || (d && d.active_model) || 'Gemini';
      const isTp = /claude|gpt|opus|sonnet|oss/i.test(modelName);
      const poolAccent = isTp ? 'var(--accent-tp)' : 'var(--accent-gemini)';

      if (convEl) {
        convEl.textContent = convDisplay;
        convEl.title = 'Conversation: ' + convTip;
      }
      if (modelEl) {
        modelEl.textContent = modelName;
        modelEl.style.color = poolAccent;
        modelEl.title = 'Active Model: ' + modelName;
      }
      if (dotEl) {
        dotEl.style.background = poolAccent;
      }
    }

    function renderContextBars(d) {
      const container = document.getElementById('ctxBarsContainer');
      const miniCtx = document.getElementById('miniCtxWarn');
      const allSessions = d.recent_sessions || [];
      if (!container) return;

      if (allSessions.length > 0) {
        const newestMtime = allSessions[0].mtime || 0;
        if (lastTopSessionMtime > 0 && newestMtime > lastTopSessionMtime + 0.5) {
          pinnedSessionId = null;
        }
        lastTopSessionMtime = newestMtime;
      }

      let filtered = [];
      if (ctxUniqueProjects) {
        const seenProj = new Set();
        for (const s of allSessions) {
          const key = s.project || s.id;
          if (!seenProj.has(key)) {
            seenProj.add(key);
            filtered.push(s);
          }
        }
      } else {
        filtered = allSessions.slice();
      }

      const shown = filtered.slice(0, ctxBarsCount);
      const targetMini = (pinnedSessionId && allSessions.find(s => s.id === pinnedSessionId)) || shown[0] || allSessions[0] || null;
      updateCompactMeta(d, targetMini);

      if (!shown.length) {
        container.innerHTML = '<div class="subcard p-2 rounded-lg text-center text-[10px] mono" style="color: var(--text-dim);">No active conversations detected yet.</div>';
        return;
      }

      if (miniCtx && targetMini) {
        const st = targetMini.status || 'safe';
        const tokStr = fmtTok(targetMini.ctx_tokens || 0);
        const mult = (targetMini.mult || 1.0).toFixed(1);
        if (st === 'cold') {
          miniCtx.classList.remove('hidden');
          miniCtx.classList.add('animate-pulse');
          miniCtx.style.background = 'rgba(56, 189, 248, 0.22)';
          miniCtx.style.color = '#38BDF8';
          miniCtx.style.borderColor = '#38BDF8';
          miniCtx.textContent = '❄️ ' + tokStr;
          miniCtx.title = targetMini.project + ' — COLD CACHE (' + tokStr + ' ctx · ' + targetMini.idle_str + '): Start new chat with resume!';
        } else if (st === 'critical') {
          miniCtx.classList.remove('hidden');
          miniCtx.classList.add('animate-pulse');
          miniCtx.style.background = 'rgba(239, 68, 68, 0.25)';
          miniCtx.style.color = 'var(--accent-yolo)';
          miniCtx.style.borderColor = 'var(--accent-yolo)';
          miniCtx.textContent = '🔴 ' + tokStr + '!';
          miniCtx.title = targetMini.project + ' — HEAVY (' + tokStr + ' · ' + mult + 'x/step): Run /compact or handoff!';
        } else if (st === 'warn') {
          miniCtx.classList.remove('hidden', 'animate-pulse');
          miniCtx.style.background = 'rgba(245, 158, 11, 0.22)';
          miniCtx.style.color = 'var(--accent-warn)';
          miniCtx.style.borderColor = 'var(--accent-warn)';
          miniCtx.textContent = '🟡 ' + tokStr;
          miniCtx.title = targetMini.project + ' — WARM (' + tokStr + ' · ' + mult + 'x/step): /compact after current task.';
        } else {
          miniCtx.classList.remove('hidden', 'animate-pulse');
          miniCtx.style.background = 'rgba(16, 185, 129, 0.18)';
          miniCtx.style.color = 'var(--accent-gemini)';
          miniCtx.style.borderColor = 'var(--accent-gemini)';
          miniCtx.textContent = '🟢 ' + tokStr;
          miniCtx.title = targetMini.project + ' — LIGHT (' + tokStr + ' · ' + mult + 'x/step): Optimal efficiency.';
        }
      }

      let html = '';
      for (let i = 0; i < shown.length; i++) {
        const s = shown[i];
        const st = s.status || 'safe';
        const ctxTok = s.ctx_tokens || 0;
        const mult = (s.mult || 1.0).toFixed(1);
        const pct = Math.min(100, Math.max(4, Math.round((ctxTok / 170000) * 100)));
        const isPinnedRow = (pinnedSessionId === s.id) || (!pinnedSessionId && i === 0);

        let barColor = 'var(--accent-gemini)';
        let badgeBg = 'rgba(16, 185, 129, 0.18)';
        let badgeCol = 'var(--accent-gemini)';
        let badgeTxt = '🟢 LIGHT ' + mult + 'x';
        let tipTxt = 'Fresh context (' + fmtTok(ctxTok) + ' tokens). Safe to continue.';

        if (st === 'cold') {
          barColor = '#38BDF8';
          badgeBg = 'rgba(56, 189, 248, 0.22)';
          badgeCol = '#38BDF8';
          badgeTxt = '❄️ COLD ' + mult + 'x · NEW CHAT!';
          tipTxt = 'Idle ' + s.idle_str + ' with ' + fmtTok(ctxTok) + ' context! Server cache expired — start a new chat and type "resume" instead of waking this chat.';
        } else if (st === 'critical') {
          barColor = 'var(--accent-yolo)';
          badgeBg = 'rgba(239, 68, 68, 0.24)';
          badgeCol = 'var(--accent-yolo)';
          badgeTxt = '🔴 HEAVY ' + mult + 'x · COMPACT!';
          tipTxt = 'Near 170k ceiling (' + mult + 'x quota cost per step). Run /compact or "handoff time" now!';
        } else if (st === 'warn') {
          barColor = 'var(--accent-warn)';
          badgeBg = 'rgba(245, 158, 11, 0.22)';
          badgeCol = 'var(--accent-warn)';
          badgeTxt = '🟡 WARM ' + mult + 'x · /compact';
          tipTxt = 'Warm context (' + fmtTok(ctxTok) + ' = ' + mult + 'x/step). Finish current task then run /compact.';
        }

        const borderStyle = isPinnedRow
          ? `border: 1px solid ${barColor};`
          : 'border: 1px solid var(--border-card);';

        const convTitle = s.title || s.topic || '';
        const topicHtml = convTitle
          ? `<span class="truncate" style="color: var(--text-muted); max-width: 175px;">${convTitle}</span><span style="color: var(--text-dim);">·</span>`
          : '';
        const fullTip = (convTitle ? `[${s.project}] ${convTitle} — ` : '') + tipTxt;

        html += `
          <div onclick="selectPinnedSession('${s.id}')" class="subcard px-2 py-1.5 rounded-lg space-y-1 cursor-pointer transition" style="${borderStyle}" title="${fullTip.replace(/"/g, '&quot;')}">
            <div class="flex items-center justify-between text-[10px] mono gap-1.5">
              <div class="flex items-center gap-1.5 truncate">
                <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" style="background: ${barColor};"></span>
                <span class="font-bold flex-shrink-0" style="color: var(--text-main);">${s.project}</span>
                <span style="color: var(--text-dim);">·</span>
                ${topicHtml}
                <span class="flex-shrink-0" style="color: var(--text-dim);">${fmtTok(ctxTok)} (${s.steps} stp · ${s.idle_str})</span>
              </div>
              <span class="px-1.5 py-0.2 rounded text-[9px] mono font-black flex-shrink-0" style="background: ${badgeBg}; color: ${badgeCol};">${badgeTxt}</span>
            </div>
            <div class="w-full h-1 rounded-full overflow-hidden" style="background: var(--bg-card);">
              <div class="h-full transition-all duration-300" style="width: ${pct}%; background: ${barColor};"></div>
            </div>
          </div>
        `;
      }
      container.innerHTML = html;
    }

    function applyCompactVisual(compact) {
      isCompact = compact;
      applyFontScaleVisual();
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
          titlebar.style.paddingLeft = '6px';
          titlebar.style.paddingRight = '6px';
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
          titlebar.style.paddingLeft = '';
          titlebar.style.paddingRight = '';
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

    function applyTabVisual(tab) {
      activeTab = (tab === 'weekly') ? 'weekly' : '5h';
      const t5 = document.getElementById('tab5h');
      const tw = document.getElementById('tabWeekly');
      const lbl = document.getElementById('modelSlotLabel');
      if (!t5 || !tw) return;
      if (activeTab === '5h') {
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
    }

    async function switchTab(tab) {
      applyTabVisual(tab);
      if (window.pywebview && window.pywebview.api && window.pywebview.api.set_active_tab) {
        try { await window.pywebview.api.set_active_tab(activeTab); } catch (e) {}
      }
      refreshData();
    }

    function applyViewModeVisual(mode) {
      viewMode = (mode === 'verbose') ? 'verbose' : 'minimal';
      const minV = document.getElementById('minimalView');
      const verbV = document.getElementById('verboseView');
      const bMin = document.getElementById('btnModeMinimal');
      const bVerb = document.getElementById('btnModeVerbose');
      if (viewMode === 'minimal') {
        if (minV) minV.classList.remove('hidden');
        if (verbV) verbV.classList.add('hidden');
        if (bMin) { bMin.style.background = 'var(--accent-gemini)'; bMin.style.color = '#000000'; }
        if (bVerb) { bVerb.style.background = 'transparent'; bVerb.style.color = 'var(--text-muted)'; }
      } else {
        if (minV) minV.classList.add('hidden');
        if (verbV) verbV.classList.remove('hidden');
        if (bVerb) { bVerb.style.background = 'var(--accent-gemini)'; bVerb.style.color = '#000000'; }
        if (bMin) { bMin.style.background = 'transparent'; bMin.style.color = 'var(--text-muted)'; }
      }
    }

    async function setViewMode(mode) {
      applyViewModeVisual(mode);
      if (window.pywebview && window.pywebview.api && window.pywebview.api.set_view_mode) {
        try { await window.pywebview.api.set_view_mode(viewMode); } catch (e) {}
      }
    }

    async function onMinimalModelChange(val) {
      minimalModelPref = val || 'auto';
      if (window.pywebview && window.pywebview.api && window.pywebview.api.set_minimal_model) {
        try { await window.pywebview.api.set_minimal_model(minimalModelPref); } catch (e) {}
      }
      refreshData();
    }

    let lastAvailModelsSig = '';
    function fmtUsd(v) {
      const n = Number(v || 0);
      if (n >= 100) return '$' + n.toFixed(0);
      if (n >= 10) return '$' + n.toFixed(1);
      return '$' + n.toFixed(2);
    }

    function fmtCountdownParts(resetTs) {
      if (!resetTs) return null;
      const diff = Math.max(0, Math.floor(resetTs - Date.now() / 1000));
      const d = Math.floor(diff / 86400);
      const h = Math.floor((diff % 86400) / 3600);
      const m = Math.floor((diff % 3600) / 60);
      const s = diff % 60;
      const pad = (x) => String(x).padStart(2, '0');
      const dt = new Date(resetTs * 1000);
      const hhmm = pad(dt.getHours()) + ':' + pad(dt.getMinutes());
      const monDay = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      const clock = (d > 0) ? (monDay + ' ' + hhmm) : hhmm;
      if (diff <= 0) {
        return { full: 'Resetting now · ' + clock, compact: '0m', verbose: 'Resetting now · (' + clock + ')' };
      }
      if (d > 0) {
        return {
          full: `⏳ ${d}d ${pad(h)}h ${pad(m)}m · ${clock}`,
          compact: `${d}d${pad(h)}h`,
          verbose: `Resets in ${d}d ${pad(h)}h ${pad(m)}m · ${clock}`
        };
      }
      if (h > 0) {
        return {
          full: `⏳ ${h}h ${pad(m)}m ${pad(s)}s · ${clock}`,
          compact: `${h}h${pad(m)}m`,
          verbose: `Resets in ${h}h ${pad(m)}m ${pad(s)}s · ${clock}`
        };
      }
      return {
        full: `⏳ ${m}m ${pad(s)}s · ${clock}`,
        compact: `${m}m${pad(s)}s`,
        verbose: `Resets in ${m}m ${pad(s)}s · ${clock}`
      };
    }

    function updateLiveCooldowns() {
      if (!lastMetrics) return;
      const d = lastMetrics;
      const gw = fmtCountdownParts(d.gemini_weekly_reset_ts);
      const g5 = fmtCountdownParts(d.gemini_5h_reset_ts);
      const tpw = fmtCountdownParts(d.tp_weekly_reset_ts);
      const tp5 = fmtCountdownParts(d.tp_5h_reset_ts);

      if (gw) {
        const el = document.getElementById('geminiWeeklyDesc');
        if (el) el.textContent = gw.verbose;
        const mwc = document.getElementById('miniWeeklyCooldown');
        if (mwc) mwc.textContent = gw.compact;
        const wkRemSecs = Math.max(0, d.gemini_weekly_reset_ts - Date.now() / 1000);
        const wkTimerPct = Math.min(100, Math.max(0, (wkRemSecs / 604800) * 100));
        updateRing('miniGWTimerRing', wkTimerPct);
      }
      if (g5) {
        const el = document.getElementById('gemini5hDesc');
        if (el) el.textContent = g5.verbose;
        const mc = document.getElementById('miniCooldown');
        if (mc) mc.textContent = g5.compact;
        const h5RemSecs = Math.max(0, d.gemini_5h_reset_ts - Date.now() / 1000);
        const h5TimerPct = Math.min(100, Math.max(0, (h5RemSecs / 18000) * 100));
        updateRing('miniG5TimerRing', h5TimerPct);
      }
      if (tpw) {
        const el = document.getElementById('tpWeeklyDesc');
        if (el) el.textContent = tpw.verbose;
      }
      if (tp5) {
        const el = document.getElementById('tp5hDesc');
        if (el) el.textContent = tp5.verbose;
        const hEl = document.getElementById('tpHeaderCooldown');
        if (hEl) hEl.textContent = tp5.compact ? ('⏳ ' + tp5.compact) : '';
      }

      const mm = d.minimal;
      if (mm) {
        const m5 = mm.h5 && mm.h5.reset_ts ? fmtCountdownParts(mm.h5.reset_ts) : null;
        const mw = mm.weekly && mm.weekly.reset_ts ? fmtCountdownParts(mm.weekly.reset_ts) : null;
        const el5 = document.getElementById('min5hCooldown');
        const elw = document.getElementById('minWkCooldown');
        if (el5 && m5) el5.textContent = m5.full;
        if (elw && mw) elw.textContent = mw.full;
      }
    }

    function renderMinimalScopeRows(containerId, scopes, isTpPool) {
      const el = document.getElementById(containerId);
      if (!el || !scopes) return;
      const accentUsed = isTpPool ? 'var(--accent-tp)' : 'var(--accent-warn)';
      const accentRem = isTpPool ? 'var(--accent-tp)' : 'var(--accent-gemini)';
      const defs = [
        { key: 'current', title: 'Current' },
        { key: 'last3', title: 'Last 3 Resets' },
        { key: 'all', title: 'All Resets' },
      ];
      let html = '';
      for (const item of defs) {
        const sc = scopes[item.key];
        if (!sc) continue;
        const nRes = sc.resets_count || 0;
        let usedSub = '';
        if (item.key === 'current') {
          usedSub = `${sc.steps || 0} stp · +${fmtTok(sc.used_cache_tokens || 0)} cache`;
        } else {
          usedSub = `avg ${fmtTok(sc.used_avg_tokens || 0)} · ${fmtUsd(sc.used_avg_usd || 0)} (${nRes}r)`;
        }
        const remSub = (item.key === 'current')
          ? `~${sc.rem_steps || 0} stp · cap ${fmtTok(sc.cap_tokens || 0)} (${fmtUsd(sc.cap_usd || 0)})`
          : `cap ${fmtTok(sc.cap_tokens || 0)} (${fmtUsd(sc.cap_usd || 0)}) · ${sc.cap_source || ''}`;

        html += `
          <div class="subcard px-2 py-1.5 rounded-xl grid grid-cols-12 gap-1.5 items-center text-[11px] mono">
            <div class="col-span-3">
              <div class="font-bold text-[11px]" style="color: var(--text-main);">${item.title}</div>
              <div class="text-[9px]" style="color: var(--text-dim);">${item.key === 'current' ? 'Active cycle' : (nRes + ' cycles')}</div>
            </div>
            <div class="col-span-4 text-right">
              <div class="font-bold" style="color: var(--text-main);">${fmtTok(sc.used_tokens || 0)} <span style="color: ${accentUsed};">· ${fmtUsd(sc.used_usd || 0)}</span></div>
              <div class="text-[9px] truncate" style="color: var(--text-muted);">${usedSub}</div>
            </div>
            <div class="col-span-5 text-right">
              <div class="font-bold" style="color: var(--text-main);">~${fmtTok(sc.rem_tokens || 0)} <span style="color: ${accentRem};">· ~${fmtUsd(sc.rem_usd || 0)}</span></div>
              <div class="text-[9px] truncate" style="color: var(--text-muted);">${remSub}</div>
            </div>
          </div>
        `;
      }
      el.innerHTML = html;
    }

    function renderMinimalView(d) {
      const m = d.minimal;
      if (!m) return;

      const sel = document.getElementById('minimalModelSelect');
      const avail = d.available_models || [];
      const sig = avail.join('|');
      if (sel && sig !== lastAvailModelsSig) {
        lastAvailModelsSig = sig;
        let opts = `<option value="auto">Auto (Detected: ${m.detected_model})</option>`;
        for (const nm of avail) {
          opts += `<option value="${nm.replace(/"/g, '&quot;')}">${nm}</option>`;
        }
        sel.innerHTML = opts;
      }
      if (sel) {
        if (sel.options && sel.options.length > 0) {
          sel.options[0].textContent = 'Auto (Detected: ' + (m.detected_model || '...') + ')';
        }
        const desiredVal = m.is_manual ? m.target_model : 'auto';
        if (document.activeElement !== sel && sel.value !== desiredVal) {
          sel.value = desiredVal;
        }
      }

      const modeBadge = document.getElementById('minModeBadge');
      const resetAutoBtn = document.getElementById('minResetAutoBtn');
      const convCtx = document.getElementById('minConvContext');
      const poolBadge = document.getElementById('minPoolBadge');
      const rateSpec = document.getElementById('minRateSpec');
      const archNote = document.getElementById('minArchiveNote');

      if (m.is_manual) {
        if (modeBadge) {
          modeBadge.textContent = 'MANUAL';
          modeBadge.style.background = 'rgba(245, 158, 11, 0.20)';
          modeBadge.style.color = 'var(--accent-warn)';
          modeBadge.style.borderColor = 'var(--accent-warn)';
        }
        if (resetAutoBtn) resetAutoBtn.classList.remove('hidden');
        if (convCtx) convCtx.textContent = 'Viewing: ' + m.target_model + ' (Detected: ' + m.detected_model + ')';
      } else {
        if (modeBadge) {
          modeBadge.textContent = 'AUTO';
          modeBadge.style.background = 'rgba(16, 185, 129, 0.18)';
          modeBadge.style.color = 'var(--accent-gemini)';
          modeBadge.style.borderColor = 'var(--accent-gemini)';
        }
        if (resetAutoBtn) resetAutoBtn.classList.add('hidden');
        const cTitle = m.conv_title ? (' · ' + m.conv_title) : '';
        if (convCtx) convCtx.textContent = (m.conv_project || 'Active Chat') + cTitle;
      }

      const isTp = (m.pool === 'tp');
      if (poolBadge) {
        poolBadge.textContent = (isTp ? 'Claude/GPT · ' : 'Gemini · ') + Number(m.weight || 1.0).toFixed(2) + 'x';
        poolBadge.style.color = isTp ? 'var(--accent-tp)' : 'var(--accent-gemini)';
      }
      if (rateSpec) {
        rateSpec.textContent = `Rates: In $${Number(m.price_in || 0).toFixed(2)} · Out $${Number(m.price_out || 0).toFixed(2)} · Cache $${Number(m.price_cache || 0).toFixed(3)} /1M`;
      }
      if (archNote) {
        archNote.textContent = m.archive_hydrated
          ? `${m.archive_total_files || 0} logs cached`
          : `Indexing ${m.archive_cached_files || 0}/${m.archive_total_files || 0} logs...`;
      }

      if (m.h5) {
        const p5 = document.getElementById('min5hPct');
        if (p5) p5.textContent = (m.h5.pct_rem ?? '--') + '% left';
        updateRing('min5hRing', m.h5.pct_rem ?? 100);
        renderMinimalScopeRows('min5hRows', m.h5.scopes, isTp);
      }
      if (m.weekly) {
        const pw = document.getElementById('minWkPct');
        if (pw) pw.textContent = (m.weekly.pct_rem ?? '--') + '% left';
        updateRing('minWkRing', m.weekly.pct_rem ?? 100);
        renderMinimalScopeRows('minWkRows', m.weekly.scopes, isTp);
      }
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
        const circ = parseFloat(el.dataset.circ || '100');
        const clamped = Math.min(100, Math.max(0, Number(percent) || 0));
        const offset = circ * (1 - clamped / 100);
        el.setAttribute('stroke-dashoffset', offset.toFixed(2));
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
      const mBtn = document.getElementById('miniSyncBtn');
      if (btn) btn.textContent = '↻ ...';
      if (mBtn) mBtn.textContent = '…';
      try {
        lastAvailModelsSig = '';
        if (window.pywebview && window.pywebview.api) {
          const fresh = await window.pywebview.api.force_sync();
          if (fresh && typeof fresh === 'object') {
            lastMetrics = fresh;
          }
          await refreshData();
        }
      } catch (e) {
        console.error(e);
      }
      setTimeout(() => {
        if (btn) btn.textContent = '↻ Refresh';
        if (mBtn) mBtn.textContent = '↻';
      }, 650);
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

    function applyPaceWindowCard(suffix, w, remPct) {
      const card = document.getElementById('paceCard' + suffix);
      const badge = document.getElementById('paceBadge' + suffix);
      const rateEl = document.getElementById('paceRate' + suffix);
      const projEl = document.getElementById('paceProj' + suffix);
      const etaEl = document.getElementById('paceEta' + suffix);
      if (!card || !w) return;

      const isWarn = Boolean(w.warn);
      const isCrit = Boolean(w.critical);
      const accent = isCrit ? 'var(--accent-yolo)' : (isWarn ? 'var(--accent-warn)' : 'var(--accent-gemini)');
      const bgBadge = isCrit ? 'rgba(239,68,68,0.22)' : (isWarn ? 'rgba(245,158,11,0.22)' : 'rgba(16,185,129,0.18)');

      card.style.border = (isWarn || isCrit) ? ('1px solid ' + accent) : '1px solid var(--border-card)';
      if (badge) {
        badge.style.background = bgBadge;
        badge.style.color = accent;
        badge.textContent = isCrit ? 'DEPLETES!' : (isWarn ? 'WARN' : 'SAFE');
      }
      if (rateEl) {
        rateEl.textContent = w.rate_pct_hr.toFixed(1) + '%/hr (' + w.used_pct.toFixed(1) + '%)';
        rateEl.style.color = (isWarn || isCrit) ? accent : 'var(--text-main)';
      }
      if (projEl) {
        projEl.textContent = 'Proj: +' + Math.round(w.proj_rem_burn_pct) + '% vs ' + remPct + '% left';
      }
      if (etaEl) {
        etaEl.textContent = w.runway_label || 'Runway: Safe';
        etaEl.style.color = (isWarn || isCrit) ? accent : 'var(--text-dim)';
      }
    }

    function renderPaceMonitor(d) {
      const p = d.pace_5h;
      if (!p) return;

      const banner = document.getElementById('paceAlertBanner');
      const alertText = document.getElementById('paceAlertText');
      const clockSplit = document.getElementById('paceClockSplit');
      const miniWarn = document.getElementById('miniPaceWarn');

      if (clockSplit) {
        clockSplit.textContent = p.elapsed_str + ' in · ' + p.left_str + ' left';
      }

      if (banner && alertText) {
        if (p.any_warning) {
          const isCrit = Boolean(p.any_critical);
          const col = isCrit ? 'var(--accent-yolo)' : 'var(--accent-warn)';
          banner.style.background = isCrit ? 'rgba(239, 68, 68, 0.16)' : 'rgba(245, 158, 11, 0.16)';
          banner.style.borderColor = col;
          banner.style.color = col;
          alertText.textContent = p.headline || '⚠️ 5h Pace Alert: Projected to deplete before reset!';
          if (miniWarn) {
            miniWarn.classList.remove('hidden');
            miniWarn.title = p.headline || '5h Burn Pace Alert';
          }
        } else {
          banner.style.background = 'var(--bg-subcard)';
          banner.style.borderColor = 'var(--border-card)';
          banner.style.color = 'var(--accent-gemini)';
          alertText.textContent = p.headline || '✓ 5h Pace Safe across Slot, 30m & 15m windows';
          if (miniWarn) miniWarn.classList.add('hidden');
        }
      }

      applyPaceWindowCard('Slot', p.slot, d.gemini_5h_pct);
      applyPaceWindowCard('30m', p.w30m, d.gemini_5h_pct);
      applyPaceWindowCard('15m', p.w15m, d.gemini_5h_pct);
    }

    async function refreshData() {
      if (window.pywebview && window.pywebview.api) {
        try {
          const d = await window.pywebview.api.get_metrics();
          if (!d) return;
          lastMetrics = d;

          renderMinimalView(d);

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

          renderPaceMonitor(d);

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
          renderContextBars(d);
          updateLiveCooldowns();

          document.getElementById('syncPoints').textContent = 'Synced · ' + d.sample_count + ' cal pts';

          const now = new Date();
          document.getElementById('timestamp').textContent = now.toTimeString().split(' ')[0];
        } catch (err) {
          console.error(err);
        }
      }
    }

    let hudInitDone = false;
    const RELOAD_INTERVAL_MS = 2000;
    let lastReloadTs = performance.now();
    let lastCooldownTickTs = 0;
    let isRefreshing = false;

    function tickReloadBar(now) {
      const bar = document.getElementById('ctxReloadBar');
      const elapsed = now - lastReloadTs;
      const pct = Math.min(100, Math.max(0, (elapsed / RELOAD_INTERVAL_MS) * 100));
      if (bar) {
        bar.style.width = pct.toFixed(1) + '%';
        bar.style.background = pct >= 96 ? 'var(--accent-gemini)' : 'var(--text-muted)';
        bar.style.opacity = pct >= 96 ? '1' : '0.65';
      }
      if (now - lastCooldownTickTs >= 1000) {
        lastCooldownTickTs = now;
        updateLiveCooldowns();
      }
      if (elapsed >= RELOAD_INTERVAL_MS && !isRefreshing) {
        isRefreshing = true;
        lastReloadTs = now;
        refreshData().finally(() => {
          isRefreshing = false;
          lastReloadTs = performance.now();
        });
      }
      requestAnimationFrame(tickReloadBar);
    }

    async function init() {
      if (hudInitDone) return;
      hudInitDone = true;
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
            if (cfg.active_tab) applyTabVisual(cfg.active_tab);
            if (cfg.minimal_model) minimalModelPref = cfg.minimal_model;
            applyViewModeVisual(cfg.view_mode || 'minimal');
            if (typeof cfg.font_scale_full === 'number') fontScaleFull = cfg.font_scale_full;
            if (typeof cfg.font_scale_mini === 'number') fontScaleMini = cfg.font_scale_mini;
            if (typeof cfg.ctx_bars_count === 'number') ctxBarsCount = cfg.ctx_bars_count;
            if (typeof cfg.ctx_unique_projects === 'boolean') ctxUniqueProjects = cfg.ctx_unique_projects;
            applyFontScaleVisual();
            applyCtxBarPrefsVisual();
          }
        } catch(e) {}
      }
      await refreshData();
      lastReloadTs = performance.now();
      requestAnimationFrame(tickReloadBar);
    }

    window.addEventListener('pywebviewready', init);
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 100));
  </script>
</body>
</html>
"""


class MetricsEngine:
    def __init__(self, config=None):
        self.config = config if isinstance(config, dict) else {}
        self.history = self.load_history()
        self._step_cache_lock = threading.Lock()
        self._step_cache = self.load_step_cache()
        self._archive_hydrated = False
        self._archive_total_files = 0
        self._archive_cached_files = 0
        self._last_w5 = {}
        self._last_wWeek = {}
        self._last_by_model_5h = {}
        self._last_by_model_w = {}

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        self.five_h_start_dt = now_utc - datetime.timedelta(hours=5)
        self.weekly_start_dt = now_utc - datetime.timedelta(days=7)
        self.tp_five_h_start_dt = now_utc - datetime.timedelta(hours=5)
        self.tp_weekly_start_dt = now_utc - datetime.timedelta(days=7)
        self.gemini_5h_reset_dt = None
        self.gemini_weekly_reset_dt = None
        self.tp_5h_reset_dt = None
        self.tp_weekly_reset_dt = None
        self.last_cal_save_ts = 0.0

        self.cached_metrics = {
            "active_model": "Gemini 4 Argon (Medium)",
            "active_conv_title": "",
            "active_conv_project": "Active Workspace",
            "available_models": list(PRIMARY_SELECTABLE_MODELS),
            "gemini_5h_reset_ts": None,
            "gemini_weekly_reset_ts": None,
            "tp_5h_reset_ts": None,
            "tp_weekly_reset_ts": None,
            "minimal": {},
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
            "session_context_tokens": 0,
            "session_steps": 0,
            "session_step_mult": 1.0,
            "session_idle_mins": 0.0,
            "session_ctx_status": "safe",
            "recent_sessions": [],

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
        self._conv_parse_cache = {}
        self._seed_reset_caps_from_samples()
        self._hydrate_from_last_usage()
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
                        d.setdefault("reset_caps", {"g_5h": {}, "g_weekly": {}, "tp_5h": {}, "tp_weekly": {}})
                        d.setdefault("last_usage", {})
                        return d
            except Exception:
                pass
        return {
            "samples_5h": [],
            "samples_weekly": [],
            "samples_tp_5h": [],
            "samples_tp_weekly": [],
            "reset_caps": {"g_5h": {}, "g_weekly": {}, "tp_5h": {}, "tp_weekly": {}},
            "last_usage": {},
        }

    def save_history(self):
        try:
            os.makedirs(os.path.dirname(QUOTA_HISTORY_FILE), exist_ok=True)
            tmp_path = QUOTA_HISTORY_FILE + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
            os.replace(tmp_path, QUOTA_HISTORY_FILE)
        except Exception:
            pass

    def load_step_cache(self):
        if os.path.exists(TRANSCRIPT_CACHE_FILE):
            try:
                with open(TRANSCRIPT_CACHE_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, dict):
                        return d
            except Exception:
                pass
        return {}

    def save_step_cache(self):
        try:
            with self._step_cache_lock:
                os.makedirs(os.path.dirname(TRANSCRIPT_CACHE_FILE), exist_ok=True)
                tmp_path = TRANSCRIPT_CACHE_FILE + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._step_cache, f)
                os.replace(tmp_path, TRANSCRIPT_CACHE_FILE)
        except Exception:
            pass

    @staticmethod
    def _median_num(vals, default=0.0):
        clean = sorted(v for v in vals if v is not None and v > 0)
        if not clean:
            return default
        return clean[len(clean) // 2]

    def _seed_reset_caps_from_samples(self):
        rcaps = self.history.setdefault("reset_caps", {})
        mapping = [
            ("samples_5h", "g_5h", 5),
            ("samples_weekly", "g_weekly", 2),
            ("samples_tp_5h", "tp_5h", 5),
            ("samples_tp_weekly", "tp_weekly", 2),
        ]
        changed = False
        for samp_key, cap_key, min_pct in mapping:
            bucket_map = rcaps.setdefault(cap_key, {})
            samples = self.history.get(samp_key, [])
            if not samples:
                continue
            clusters = []
            cur = []
            prev_used = None
            for s in samples:
                u = float(s.get("used", 0) or 0)
                if prev_used is not None and u + 0.05 < prev_used and cur:
                    clusters.append(cur)
                    cur = []
                cur.append(s)
                prev_used = u
            if cur:
                clusters.append(cur)

            for cl in clusters:
                valid = [x for x in cl if int(x.get("pct_used", 0) or 0) >= min_pct]
                if not valid:
                    continue
                slot_id = "legacy:" + str(int(cl[0].get("ts", 0)))
                if slot_id in bucket_map:
                    continue
                base_caps = []
                raw_caps = []
                usd_caps = []
                leg_caps = []
                raw_effs = []
                for x in valid:
                    frac = int(x.get("pct_used", 0)) / 100.0
                    if frac <= 0:
                        continue
                    leg_caps.append(float(x.get("used", 0)) / frac)
                    sb = float(x.get("server_base_units", 0) or 0)
                    rt = float(x.get("raw_tokens", 0) or 0)
                    ct = float(x.get("cache_tokens", 0) or 0)
                    cu = float(x.get("cost_usd", 0) or 0)
                    if sb > 0:
                        base_caps.append(sb / frac)
                    if rt > 0:
                        raw_caps.append(rt / frac)
                        eff_approx = rt + 0.1 * ct
                        if eff_approx > 0:
                            raw_effs.append(rt / eff_approx)
                    if cu > 0:
                        usd_caps.append(cu / frac)
                if not leg_caps and not base_caps:
                    continue
                bucket_map[slot_id] = {
                    "first_ts": float(cl[0].get("ts", 0)),
                    "last_ts": float(cl[-1].get("ts", 0)),
                    "cap_leg": int(self._median_num(leg_caps, 0)),
                    "cap_base": int(self._median_num(base_caps, 0)),
                    "cap_raw": int(self._median_num(raw_caps, 0)),
                    "cap_usd": round(self._median_num(usd_caps, 0.0), 4),
                    "raw_eff": round(self._median_num(raw_effs, 0.45), 4),
                    "samples": len(valid),
                }
                changed = True
        if changed:
            self.save_history()

    @staticmethod
    def _fmt_cooldown_desc(reset_dt, now_utc=None) -> str:
        if reset_dt is None:
            return "Synchronizing..."
        if now_utc is None:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
        diff_secs = max(0, int((reset_dt - now_utc).total_seconds()))
        days = diff_secs // 86400
        hours = (diff_secs % 86400) // 3600
        mins = (diff_secs % 3600) // 60
        secs = diff_secs % 60
        local_dt = reset_dt.astimezone()
        clock_str = local_dt.strftime("%H:%M") if days == 0 else local_dt.strftime("%b %d %H:%M")
        if diff_secs <= 0:
            return f"Resetting now · ({clock_str})"
        if days > 0:
            return f"Resets in {days}d {hours:02d}h {mins:02d}m · {clock_str}"
        if hours > 0:
            return f"Resets in {hours}h {mins:02d}m {secs:02d}s · {clock_str}"
        return f"Resets in {mins}m {secs:02d}s · {clock_str}"

    def _hydrate_from_last_usage(self):
        lu = self.history.get("last_usage") or {}
        if not isinstance(lu, dict) or not lu:
            return
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        for key, attr_reset, attr_start, delta, pct_key in [
            ("gemini_weekly", "gemini_weekly_reset_dt", "weekly_start_dt", datetime.timedelta(days=7), "gemini_weekly_pct"),
            ("gemini_5h", "gemini_5h_reset_dt", "five_h_start_dt", datetime.timedelta(hours=5), "gemini_5h_pct"),
            ("tp_weekly", "tp_weekly_reset_dt", "tp_weekly_start_dt", datetime.timedelta(days=7), "tp_weekly_pct"),
            ("tp_5h", "tp_5h_reset_dt", "tp_five_h_start_dt", datetime.timedelta(hours=5), "tp_5h_pct"),
        ]:
            item = lu.get(key)
            if not isinstance(item, dict):
                continue
            try:
                pct = item.get("pct")
                iso = item.get("reset_iso")
                if iso:
                    rdt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
                    if rdt > now_utc - datetime.timedelta(hours=1):
                        setattr(self, attr_reset, rdt)
                        setattr(self, attr_start, rdt - delta)
                if pct is not None:
                    self.cached_metrics[pct_key] = int(pct)
            except Exception:
                pass
        self._refresh_cooldown_fields()

    def _refresh_cooldown_fields(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        for attr_dt, ts_key, desc_key in [
            ("gemini_weekly_reset_dt", "gemini_weekly_reset_ts", "gemini_weekly_desc"),
            ("gemini_5h_reset_dt", "gemini_5h_reset_ts", "gemini_5h_desc"),
            ("tp_weekly_reset_dt", "tp_weekly_reset_ts", "tp_weekly_desc"),
            ("tp_5h_reset_dt", "tp_5h_reset_ts", "tp_5h_desc"),
        ]:
            rdt = getattr(self, attr_dt, None)
            if rdt is not None:
                self.cached_metrics[ts_key] = rdt.timestamp()
                self.cached_metrics[desc_key] = self._fmt_cooldown_desc(rdt, now_utc)
            else:
                self.cached_metrics[ts_key] = None

    def start_worker(self):
        t_disk = threading.Thread(target=self._disk_worker_loop, daemon=True)
        t_disk.start()

        t_usage = threading.Thread(target=self._usage_worker_loop, daemon=True)
        t_usage.start()

    def _usage_worker_loop(self):
        while self.running:
            prev_5h = self.cached_metrics.get("gemini_5h_pct")
            prev_wk = self.cached_metrics.get("gemini_weekly_pct")
            try:
                self.query_official_usage()
            except Exception:
                pass
            # If /usage suddenly jumped to 100% from <95% (transient server glitch), re-verify in 15s instead of waiting
            cur_5h = self.cached_metrics.get("gemini_5h_pct")
            cur_wk = self.cached_metrics.get("gemini_weekly_pct")
            suspicious_jump = (
                (prev_5h is not None and prev_5h < 95 and cur_5h == 100)
                or (prev_wk is not None and prev_wk < 95 and cur_wk == 100)
            )
            time.sleep(15.0 if suspicious_jump else 90.0)

    def query_official_usage(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            # Run with USER_HOME cwd and SILENT_RUNNER_EXE to ensure zero child console/MCP windows ever flash
            if os.path.exists(SILENT_RUNNER_EXE) and os.path.exists(AGY_EXE):
                cmd = [SILENT_RUNNER_EXE, AGY_EXE, "-p", "/usage"]
            else:
                cmd = [AGY_EXE if os.path.exists(AGY_EXE) else "agy", "-p", "/usage"]
            env = os.environ.copy()
            env["AGY_CLI_DISABLE_AUTO_UPDATE"] = "true"
            out = subprocess.check_output(
                cmd,
                stdin=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=USER_HOME,
                env=env,
                text=True,
                timeout=25,
                startupinfo=si,
                creationflags=CREATE_NO_WINDOW
            )

            now = datetime.datetime.now(datetime.timezone.utc)
            lu = self.history.setdefault("last_usage", {})
            for line in out.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 4:
                    group, metric, pct_str, reset_iso = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
                    pct = int(pct_str.replace("%", "").strip())
                    reset_dt = datetime.datetime.fromisoformat(reset_iso.replace("Z", "+00:00"))
                    short_desc = self._fmt_cooldown_desc(reset_dt, now)

                    if "Gemini" in group:
                        if "Weekly" in metric:
                            self.cached_metrics["gemini_weekly_pct"] = pct
                            self.cached_metrics["gemini_weekly_desc"] = short_desc
                            self.weekly_start_dt = reset_dt - datetime.timedelta(days=7)
                            self.gemini_weekly_reset_dt = reset_dt
                            lu["gemini_weekly"] = {"pct": pct, "reset_iso": reset_iso}
                        elif "Five Hour" in metric:
                            self.cached_metrics["gemini_5h_pct"] = pct
                            self.cached_metrics["gemini_5h_desc"] = short_desc
                            self.five_h_start_dt = reset_dt - datetime.timedelta(hours=5)
                            self.gemini_5h_reset_dt = reset_dt
                            lu["gemini_5h"] = {"pct": pct, "reset_iso": reset_iso}
                    elif "Claude" in group or "GPT" in group:
                        if "Weekly" in metric:
                            self.cached_metrics["tp_weekly_pct"] = pct
                            self.cached_metrics["tp_weekly_desc"] = short_desc
                            self.tp_weekly_start_dt = reset_dt - datetime.timedelta(days=7)
                            self.tp_weekly_reset_dt = reset_dt
                            lu["tp_weekly"] = {"pct": pct, "reset_iso": reset_iso}
                        elif "Five Hour" in metric:
                            self.cached_metrics["tp_5h_pct"] = pct
                            self.cached_metrics["tp_5h_desc"] = short_desc
                            self.tp_five_h_start_dt = reset_dt - datetime.timedelta(hours=5)
                            self.tp_5h_reset_dt = reset_dt
                            lu["tp_5h"] = {"pct": pct, "reset_iso": reset_iso}

            self._refresh_cooldown_fields()
            self._update_pool_valuations()
            self._recompute_minimal_metrics()
            self.save_history()
        except Exception:
            pass

    def _update_pool_valuations(self):
        learned_5h_cap = self.compute_learned_cap(self.history.get("samples_5h", []), default=862066)
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
                            m = re.search(r"Model Selection`?\s+from\s+.*?\s+to\s+([^\n`]+?)\.\s+No need", c)
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
        gemini_legacy_30m = 0
        gemini_legacy_15m = 0
        gemini_base_30m = 0
        gemini_base_15m = 0
        gemini_steps_30m = 0
        gemini_steps_15m = 0
        tp_tokens = 0
        tp_cost = 0.0
        tp_base_units = 0
        tp_legacy_units = 0
        legacy_weighted_units = 0

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        cut_30m = now_utc - datetime.timedelta(minutes=30)
        cut_15m = now_utc - datetime.timedelta(minutes=15)

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
                                m = re.search(r"Model Selection`?\s+from\s+.*?\s+to\s+([^\n`]+?)\.\s+No need", c)
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
                                if dt >= cut_30m:
                                    gemini_legacy_30m += lw
                                if dt >= cut_15m:
                                    gemini_legacy_15m += lw
                        elif t in ["PLANNER_RESPONSE", "MODEL"]:
                            legacy_tok = estimate_tokens(c) + estimate_tokens(str(data.get("thinking", "")))
                            lw = int(legacy_tok * spec["weight"])
                            legacy_weighted_units += lw
                            if spec["pool"] == "tp":
                                tp_legacy_units += lw
                            else:
                                gemini_legacy_units += lw
                                if dt >= cut_30m:
                                    gemini_legacy_30m += lw
                                    gemini_steps_30m += 1
                                if dt >= cut_15m:
                                    gemini_legacy_15m += lw
                                    gemini_steps_15m += 1

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
                                if dt >= cut_30m:
                                    gemini_base_30m += step_base_units
                                if dt >= cut_15m:
                                    gemini_base_15m += step_base_units

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
            "gemini_legacy_30m": gemini_legacy_30m,
            "gemini_legacy_15m": gemini_legacy_15m,
            "gemini_base_30m": gemini_base_30m,
            "gemini_base_15m": gemini_base_15m,
            "gemini_steps_30m": gemini_steps_30m,
            "gemini_steps_15m": gemini_steps_15m,
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

    def _update_reset_cap_slot(self, rcap_key: str, reset_dt, pct_used: int, min_pct: int, base_units: int, raw_tokens: int, cache_tokens: int, leg_units: int, cost_usd: float):
        if reset_dt is None or pct_used < min_pct or pct_used > 98 or base_units <= 0:
            return
        frac = pct_used / 100.0
        rcaps = self.history.setdefault("reset_caps", {}).setdefault(rcap_key, {})
        slot_id = "reset:" + reset_dt.isoformat()
        eff_approx = raw_tokens + 0.1 * cache_tokens
        raw_eff = (raw_tokens / eff_approx) if eff_approx > 0 else 0.45
        cap_base = int(base_units / frac)
        cap_raw = int(raw_tokens / frac)
        cap_leg = int(leg_units / frac) if leg_units > 0 else 0
        cap_usd = round(cost_usd / frac, 4) if cost_usd > 0 else 0.0
        now_ts = time.time()

        cur = rcaps.get(slot_id)
        if not cur:
            rcaps[slot_id] = {
                "first_ts": now_ts,
                "last_ts": now_ts,
                "reset_ts": reset_dt.timestamp(),
                "cap_leg": cap_leg,
                "cap_base": cap_base,
                "cap_raw": cap_raw,
                "cap_usd": cap_usd,
                "raw_eff": round(raw_eff, 4),
                "samples": 1,
                "base_hist": [cap_base],
                "usd_hist": [cap_usd] if cap_usd > 0 else [],
            }
        else:
            bh = cur.setdefault("base_hist", [cur.get("cap_base", cap_base)])
            bh.append(cap_base)
            if len(bh) > 60:
                del bh[:-60]
            uh = cur.setdefault("usd_hist", [])
            if cap_usd > 0:
                uh.append(cap_usd)
                if len(uh) > 60:
                    del uh[:-60]
            cur["last_ts"] = now_ts
            cur["cap_base"] = int(self._median_num(bh, cap_base))
            cur["cap_raw"] = cap_raw if cur.get("cap_raw", 0) <= 0 else int((cur["cap_raw"] + cap_raw) / 2)
            cur["cap_leg"] = cap_leg or cur.get("cap_leg", 0)
            cur["cap_usd"] = round(self._median_num(uh, cap_usd), 4)
            cur["raw_eff"] = round(raw_eff, 4)
            cur["samples"] = int(cur.get("samples", 0)) + 1

        if len(rcaps) > 120:
            sorted_keys = sorted(rcaps.keys(), key=lambda k: rcaps[k].get("first_ts", 0))
            for old_k in sorted_keys[:-120]:
                rcaps.pop(old_k, None)

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
            self._update_reset_cap_slot(
                "g_5h", self.gemini_5h_reset_dt, g5_pct_used, 5,
                w5["gemini_base_units"], w5["gemini_tokens"], w5["cache"], w5["gemini_legacy_units"], w5["gemini_cost"]
            )
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
            self._update_reset_cap_slot(
                "g_weekly", self.gemini_weekly_reset_dt, gw_pct_used, 2,
                wWeek["gemini_base_units"], wWeek["gemini_tokens"], wWeek["cache"], wWeek["gemini_legacy_units"], wWeek["gemini_cost"]
            )
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
            self._update_reset_cap_slot(
                "tp_5h", self.tp_5h_reset_dt, tp5_pct_used, 5,
                w5_tp["tp_base_units"], w5_tp["tp_tokens"], w5_tp["cache"], w5_tp["tp_legacy_units"], w5_tp["tp_cost"]
            )
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
            self._update_reset_cap_slot(
                "tp_weekly", self.tp_weekly_reset_dt, tpw_pct_used, 2,
                wWeek_tp["tp_base_units"], wWeek_tp["tp_tokens"], wWeek_tp["cache"], wWeek_tp["tp_legacy_units"], wWeek_tp["tp_cost"]
            )
            changed = True

        if changed:
            self.last_cal_save_ts = now_ts
            self.save_history()

    def _build_model_rows(self, by_model_dict, active_model_name):
        learned_g_5h = self.compute_learned_cap(self.history.get("samples_5h", []), default=862066)
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
            time.sleep(1.0)

    def _resolve_project_label(self, raw_paths, first_user_text):
        m_ws = re.search(r"The user's active workspace is at\s+([^\r\n]+)", first_user_text or "")
        if m_ws:
            ws_p = m_ws.group(1).strip().rstrip("\\/")
            low_ws = ws_p.lower()
            if "storycrafter" in low_ws:
                return "Storycrafter"
            if "witcher3mod" in low_ws:
                for p in raw_paths:
                    lp = p.lower()
                    if "modlevelinggear" in lp:
                        return "Witcher3 · LevelingGear"
                    if "modautoapplyoils" in lp:
                        return "Witcher3 · AutoOils"
                return "Witcher3 Mod"
            if "sepetdedektifi" in low_ws:
                return "SepetDedektifi"
            return os.path.basename(ws_p) or ws_p

        for p in raw_paths:
            lp = p.lower()
            if "modlevelinggear" in lp:
                return "Witcher3 · LevelingGear"
            if "modautoapplyoils" in lp:
                return "Witcher3 · AutoOils"
            if "witcher3mod" in lp:
                return "Witcher3 Mod"
            if "storycrafter" in lp:
                return "Storycrafter"
            if "sepetdedektifi" in lp:
                return "SepetDedektifi"
            if "hud.pyw" in lp or "cohort_chat.py" in lp or "\\agy\\" in lp or "\\.gemini\\config" in lp:
                return "HUD & Global"

        for p in raw_paths:
            lp = p.lower()
            if not (".gemini\\" in lp or "brain\\" in lp):
                m_apps = re.search(r"ai generated stuff\\(?:apps\\)?([^\\]+)", lp)
                if m_apps:
                    return m_apps.group(1)
                d = p if os.path.isdir(p) else os.path.dirname(p)
                if d and len(d) > 3:
                    return os.path.basename(d) or d
        return "HUD & Global"

    def _fmt_idle_age(self, mins: float) -> str:
        if mins < 1.0:
            return "now"
        if mins < 60.0:
            return f"{int(round(mins))}m ago"
        hrs = mins / 60.0
        if hrs < 24.0:
            return f"{hrs:.1f}h ago" if hrs < 10 else f"{int(round(hrs))}h ago"
        days = hrs / 24.0
        return f"{int(round(days))}d ago"

    def _read_conversation_annotation(self, conv_id: str):
        ann_path = os.path.join(os.path.dirname(DESKTOP_BRAIN), "annotations", f"{conv_id}.pbtxt")
        if not os.path.exists(ann_path):
            return None, 0.0
        try:
            with open(ann_path, "r", encoding="utf-8", errors="ignore") as fp:
                txt = fp.read()
            m_title = re.search(r'title:\s*"((?:[^"\\]|\\.)*)"', txt)
            title = m_title.group(1).replace('\\"', '"').replace("\\\\", "\\").strip() if m_title else None
            m_view = re.search(r"last_user_view_time:\s*\{\s*seconds:\s*(\d+)", txt)
            view_ts = float(m_view.group(1)) if m_view else os.path.getmtime(ann_path)
            return title, view_ts
        except Exception:
            return None, 0.0

    def _parse_single_session(self, cand_log, mtime):
        try:
            fsize = os.path.getsize(cand_log)
        except Exception:
            fsize = 0
        conv_full_id = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(cand_log))))
        ann_title, ann_view_ts = self._read_conversation_annotation(conv_full_id)
        cached = self._conv_parse_cache.get(cand_log)
        if cached and cached[0] == mtime and cached[1] == fsize:
            res_cached = dict(cached[2])
            if not res_cached.get("skip"):
                if ann_title:
                    res_cached["title"] = ann_title
                res_cached["view_ts"] = ann_view_ts
                res_cached["sort_ts"] = max(mtime, ann_view_ts)
            return res_cached

        in_tokens = 0
        out_tokens = 0
        turns = 0
        steps_count = 0
        last_ctx_tokens = 0
        last_step_dt = None
        raw_paths = []
        first_user_text = ""
        first_topic = ""
        last_topic = ""
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
                        first_user_text = c
                        if (
                            "<USER_REQUEST>\n/usage\n</USER_REQUEST>" in c
                            or "<USER_REQUEST>\n1\n</USER_REQUEST>" in c
                            or "Benchmark Nonce " in c
                            or "[Benchmark ID:" in c
                            or ".cohort_sandbox" in c
                            or "ROUND 1 JURY DIRECTIVE" in c
                        ):
                            is_ping = True
                            break

                    if t == "USER_INPUT" and "<USER_SETTINGS_CHANGE>" in c and "Model Selection" in c:
                        m = re.search(r"Model Selection`?\s+from\s+.*?\s+to\s+([^\n`]+?)\.\s+No need", c)
                        if m:
                            session_model = m.group(1).strip()

                    if t == "USER_INPUT":
                        turns += 1
                        m_req = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", c, re.DOTALL)
                        if m_req:
                            req_txt = " ".join(m_req.group(1).strip().split())
                            if req_txt and not req_txt.startswith("/"):
                                clean_snip = req_txt[:42] + ("…" if len(req_txt) > 42 else "")
                                if not first_topic:
                                    first_topic = clean_snip
                                last_topic = clean_snip
                    elif t in ["PLANNER_RESPONSE", "MODEL"]:
                        steps_count += 1
                        if "created_at" in data:
                            try:
                                last_step_dt = datetime.datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
                            except Exception:
                                pass
                        if "input_tokens" in data or "output_tokens" in data:
                            step_in = int(data.get("input_tokens", 0) or 0)
                            step_cache = int(data.get("cache_read_tokens", 0) or data.get("cached_content_token_count", 0) or 0)
                            step_out = int(data.get("output_tokens", 0) or 0)
                            in_tokens += step_in
                            out_tokens += step_out
                            if (step_in + step_cache) > 0:
                                last_ctx_tokens = step_in + step_cache
                        else:
                            out_tokens += estimate_tokens(c) + estimate_tokens(str(data.get("thinking", "")))

                    if len(raw_paths) < 15 and data.get("tool_calls"):
                        for tc in data["tool_calls"]:
                            args = tc.get("args") or tc.get("arguments") or {}
                            for _, v in args.items():
                                if isinstance(v, str) and (":\\" in v or ":/" in v):
                                    raw_paths.append(v.replace("/", "\\").strip('"\''))
        except Exception:
            return None

        if is_ping or turns == 0 or steps_count == 0:
            res = {"skip": True}
            self._conv_parse_cache[cand_log] = (mtime, fsize, res)
            return res

        proj_label = self._resolve_project_label(raw_paths, first_user_text)
        resolved_title = ann_title or first_topic or last_topic
        res = {
            "skip": False,
            "id": conv_full_id[:8],
            "project": proj_label,
            "title": resolved_title,
            "topic": last_topic,
            "turns": turns,
            "steps": steps_count,
            "in_tokens": in_tokens,
            "out_tokens": out_tokens,
            "ctx_tokens": last_ctx_tokens,
            "last_step_dt": last_step_dt,
            "session_model": session_model,
            "mtime": mtime,
            "view_ts": ann_view_ts,
            "sort_ts": max(mtime, ann_view_ts),
        }
        self._conv_parse_cache[cand_log] = (mtime, fsize, res)
        return res

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

        # Active & Recent Desktop Conversations (skip subagents and /usage or Cohort sandbox pings)
        active_model_name = self.cached_metrics.get("active_model", "Gemini 4 Argon (Medium)")
        recent_sessions = []
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # Merge recent Desktop transcript logs with recently viewed conversations from annotations/*.pbtxt
        cand_map = {}
        for mtime, cand_log in all_logs:
            if DESKTOP_BRAIN.lower() in cand_log.lower():
                cand_map[os.path.normcase(cand_log)] = (mtime, cand_log)

        ann_dir = os.path.join(os.path.dirname(DESKTOP_BRAIN), "annotations")
        if os.path.exists(ann_dir):
            try:
                ann_files = sorted(glob.glob(os.path.join(ann_dir, "*.pbtxt")), key=os.path.getmtime, reverse=True)[:16]
                for af in ann_files:
                    cid = os.path.splitext(os.path.basename(af))[0]
                    tlog = os.path.join(DESKTOP_BRAIN, cid, ".system_generated", "logs", "transcript.jsonl")
                    norm_t = os.path.normcase(tlog)
                    if norm_t not in cand_map and os.path.exists(tlog):
                        cand_map[norm_t] = (os.path.getmtime(tlog), tlog)
            except Exception:
                pass

        desktop_cands = sorted(cand_map.values(), key=lambda x: x[0], reverse=True)

        for mtime, cand_log in desktop_cands:
            cand_id = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(cand_log))))
            if cand_id in subagent_map:
                continue

            parsed = self._parse_single_session(cand_log, mtime)
            if not parsed or parsed.get("skip"):
                continue

            last_step_dt = parsed.get("last_step_dt")
            last_ctx_tokens = parsed.get("ctx_tokens", 0)
            steps_count = parsed.get("steps", 0)
            idle_mins = max(0.0, (now_utc - last_step_dt).total_seconds() / 60.0) if last_step_dt else max(0.0, (time.time() - mtime) / 60.0)
            step_mult = round(max(1.0, (3500.0 + last_ctx_tokens * 0.10) / 6000.0), 1)
            if last_ctx_tokens >= 80000 and idle_mins >= 25.0:
                ctx_status = "cold"
            elif last_ctx_tokens >= 140000 or steps_count >= 400:
                ctx_status = "critical"
            elif last_ctx_tokens >= 95000 or steps_count >= 220:
                ctx_status = "warn"
            else:
                ctx_status = "safe"

            sess_item = {
                "id": parsed["id"],
                "project": parsed["project"],
                "title": parsed.get("title", ""),
                "topic": parsed["topic"],
                "turns": parsed["turns"],
                "steps": steps_count,
                "ctx_tokens": last_ctx_tokens,
                "mult": step_mult,
                "idle_mins": round(idle_mins, 1),
                "idle_str": self._fmt_idle_age(idle_mins),
                "status": ctx_status,
                "mtime": mtime,
                "sort_ts": parsed.get("sort_ts", mtime),
                "session_model": parsed.get("session_model"),
                "in_tokens": parsed.get("in_tokens", 0),
                "out_tokens": parsed.get("out_tokens", 0),
            }
            recent_sessions.append(sess_item)
            if len(recent_sessions) >= 18:
                break

        recent_sessions.sort(key=lambda s: s.get("sort_ts", s["mtime"]), reverse=True)
        recent_sessions = recent_sessions[:12]

        if recent_sessions:
            top_s = recent_sessions[0]
            # Auto-detect active conversation model (prefer focused/newest chat with detected model, else most recently modified)
            by_mtime = sorted(recent_sessions, key=lambda s: s["mtime"], reverse=True)
            if top_s.get("session_model"):
                active_model_name = top_s["session_model"]
            else:
                for s_m in by_mtime:
                    if s_m.get("session_model"):
                        active_model_name = s_m["session_model"]
                        break
            self.cached_metrics["active_model"] = active_model_name
            self.cached_metrics["active_conv_title"] = top_s.get("title") or top_s.get("topic") or ""
            self.cached_metrics["active_conv_project"] = top_s.get("project") or "Active Workspace"
            self.cached_metrics["workspace"] = top_s["project"]
            self.cached_metrics["turns"] = top_s["turns"]
            self.cached_metrics["session_total_tokens"] = top_s["in_tokens"] + top_s["out_tokens"]
            self.cached_metrics["session_context_tokens"] = top_s["ctx_tokens"]
            self.cached_metrics["session_steps"] = top_s["steps"]
            self.cached_metrics["session_step_mult"] = top_s["mult"]
            self.cached_metrics["session_idle_mins"] = top_s["idle_mins"]
            self.cached_metrics["session_ctx_status"] = top_s["status"]

        self.cached_metrics["recent_sessions"] = recent_sessions
        self._refresh_cooldown_fields()

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

        self._last_w5 = w5
        self._last_w5_tp = w5_tp
        self._last_wWeek = wWeek
        self._last_wWeek_tp = wWeek_tp
        self._last_by_model_5h = by_model_5h
        self._last_by_model_w = by_model_w

        # 3. Record empirical calibration samples, update incremental archive cache & build model rows
        self._record_calibration_samples(w5, wWeek, w5_tp, wWeek_tp)
        self._update_step_cache_tick()
        self.cached_metrics["models_5h"] = self._build_model_rows(by_model_5h, active_model_name)
        self.cached_metrics["models_weekly"] = self._build_model_rows(by_model_w, active_model_name)
        self._update_pool_valuations()
        self._compute_pace_windows(w5)
        self._recompute_minimal_metrics()

    def _parse_transcript_bins(self, log_path: str, mtime: float, fsize: int, subagent_map: dict):
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

        spawns = []
        pending_subagents = []
        bins_map = {}  # (bucket_ts, model_key) -> [steps, in, cache, out, leg, cost]
        unassigned_steps = []  # indexes of earlier bins if initial model revealed via "from X to Y"
        saw_switch = False

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
                            m = re.search(r"Model Selection`?\s+from\s+([^\n`]+?)\s+to\s+([^\n`]+?)\.\s+No need", c)
                            if m:
                                from_m = m.group(1).strip()
                                to_m = m.group(2).strip()
                                if not saw_switch and cur_model is None and from_m not in ("None", "Orchestrator", "Orchestrator (Carbon)") and ("(" in from_m or "Gemini" in from_m or "Claude" in from_m or "GPT" in from_m):
                                    for old_key in unassigned_steps:
                                        if old_key in bins_map:
                                            new_k = (old_key[0], from_m)
                                            prev_v = bins_map.pop(old_key)
                                            dst = bins_map.setdefault(new_k, [0, 0, 0, 0, 0, 0.0])
                                            for idx_v in range(6):
                                                dst[idx_v] += prev_v[idx_v]
                                    unassigned_steps.clear()
                                saw_switch = True
                                cur_model = to_m
                        elif "BENCH_" in c:
                            for btag, bmod in bench_tag_models.items():
                                if btag in c:
                                    cur_model = bmod
                                    break

                    for tc in data.get("tool_calls") or []:
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
                            spawns.append([cid, sm, cur_model or "Gemini 4 Argon (Medium)"])
                        pending_subagents = []

                    if data.get("modelName"):
                        cur_model = str(data.get("modelName")).strip()
                    elif data.get("model"):
                        cur_model = str(data.get("model")).strip()

                    if t not in ("PLANNER_RESPONSE", "MODEL") or "created_at" not in data:
                        continue
                    try:
                        dt = datetime.datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
                    except Exception:
                        continue

                    was_default = (cur_model is None)
                    model_key = cur_model or "Gemini 3.8 Flash (High)"
                    spec = get_model_spec(model_key)

                    legacy_tok = estimate_tokens(c) + estimate_tokens(str(data.get("thinking", "")))
                    lw = int(legacy_tok * spec["weight"])
                    if "input_tokens" in data or "output_tokens" in data:
                        in_tok = int(data.get("input_tokens", 0) or 0)
                        cache_tok = int(data.get("cache_read_tokens", 0) or data.get("cached_content_token_count", 0) or 0)
                        out_tok = int(data.get("output_tokens", 0) or 0)
                    else:
                        in_tok = estimate_tokens(c)
                        cache_tok = 0
                        out_tok = legacy_tok

                    cost_usd = (
                        (in_tok / 1_000_000.0) * spec["in"]
                        + (cache_tok / 1_000_000.0) * spec["cache"]
                        + (out_tok / 1_000_000.0) * spec["out"]
                    )

                    bucket_ts = int(dt.timestamp() // 300) * 300
                    bkey = (bucket_ts, model_key)
                    if was_default and not saw_switch and bkey not in bins_map:
                        unassigned_steps.append(bkey)
                    acc = bins_map.setdefault(bkey, [0, 0, 0, 0, 0, 0.0])
                    acc[0] += 1
                    acc[1] += in_tok
                    acc[2] += cache_tok
                    acc[3] += out_tok
                    acc[4] += lw
                    acc[5] += cost_usd
        except Exception:
            pass

        bins = [
            [bts, mkey, v[0], v[1], v[2], v[3], v[4], round(v[5], 6)]
            for (bts, mkey), v in bins_map.items()
        ]
        bins.sort(key=lambda x: x[0])
        return {"mtime": mtime, "size": fsize, "spawns": spawns, "bins": bins}

    def _get_cached_subagent_map(self, all_archive_logs):
        smap = {}
        with self._step_cache_lock:
            for _, p in all_archive_logs:
                entry = self._step_cache.get(os.path.normcase(p))
                if entry:
                    for cid, sm, pm in entry.get("spawns") or []:
                        smap[cid] = (sm, pm)
        return smap

    def _update_step_cache_tick(self):
        all_archive = []
        for b in BRAIN_DIRS:
            if os.path.exists(b):
                for f in glob.glob(os.path.join(b, "*", ".system_generated", "logs", "transcript.jsonl")):
                    try:
                        st = os.stat(f)
                        all_archive.append((st.st_mtime, st.st_size, f))
                    except Exception:
                        pass
        all_archive.sort(key=lambda x: x[0], reverse=True)
        self._archive_total_files = len(all_archive)

        now_ts = time.time()
        recent_cut = now_ts - 8 * 86400
        to_parse = []
        old_pending = []
        cached_count = 0

        with self._step_cache_lock:
            for mt, sz, p in all_archive:
                np = os.path.normcase(p)
                cur = self._step_cache.get(np)
                if cur and cur.get("mtime") == mt and cur.get("size") == sz:
                    cached_count += 1
                    continue
                if mt >= recent_cut:
                    to_parse.append((mt, sz, p))
                else:
                    old_pending.append((mt, sz, p))

        # Hydrate recent changed files plus up to 35 uncached historical logs per 1s tick
        batch = to_parse + old_pending[:35]
        if batch:
            smap = self._get_cached_subagent_map([(mt, p) for mt, _, p in all_archive])
            new_entries = {}
            for mt, sz, p in batch:
                parsed_entry = self._parse_transcript_bins(p, mt, sz, smap)
                new_entries[os.path.normcase(p)] = parsed_entry
                for cid, sm, pm in parsed_entry.get("spawns") or []:
                    smap[cid] = (sm, pm)
            with self._step_cache_lock:
                self._step_cache.update(new_entries)
            cached_count += len(batch)

        self._archive_cached_files = min(len(all_archive), cached_count)
        was_hydrated = self._archive_hydrated
        self._archive_hydrated = (len(old_pending) <= 35)
        if batch and (self._archive_hydrated and not was_hydrated or len(batch) >= 12):
            self.save_step_cache()

    def _compute_scope_usage_and_caps(
        self,
        pool: str,
        target_model: str,
        spec: dict,
        period_secs: float,
        cur_start_dt,
        cur_reset_dt,
        pct_rem: int,
        w_cur: dict,
        by_model_cur: dict,
        samp_key: str,
        rcap_key: str,
        fallback_base_cap: int,
    ) -> dict:
        now_ts = time.time()
        cur_start_ts = cur_start_dt.timestamp() if cur_start_dt else (now_ts - period_secs)
        w_m = max(0.1, float(spec.get("weight", 1.0)))

        # 1. Exact Current Reset Usage for Target Model (matches Verbose identically)
        cur_m = by_model_cur.get(target_model) or {}
        cur_m_in = int(cur_m.get("in_tokens", 0) or 0)
        cur_m_out = int(cur_m.get("out_tokens", 0) or 0)
        cur_m_cache = int(cur_m.get("cache_tokens", 0) or 0)
        cur_m_tokens = cur_m_in + cur_m_out
        cur_m_usd = float(cur_m.get("cost", 0.0) or 0.0)
        cur_m_steps = int(cur_m.get("steps", 0) or 0)

        # 2. Pool empirical token mix (r_in, r_out, r_cache_per_raw, raw_per_eff)
        # Prefer target model's own recent ratio if enough steps exist, else pool historical mix
        pool_in = pool_out = pool_cache = 0
        m_hist_in = m_hist_out = m_hist_cache = 0
        pool_active_slots = {}   # slot_idx (0=cur, 1=prev1, ...) -> True if pool steps > 0
        model_slot_stats = {}    # slot_idx -> [tokens, cache, usd, steps]
        seen_models = set(PRIMARY_SELECTABLE_MODELS)

        with self._step_cache_lock:
            cache_vals = list(self._step_cache.values())

        for entry in cache_vals:
            for bts, mkey, steps, in_t, cache_t, out_t, _leg, cost_u in entry.get("bins") or []:
                seen_models.add(mkey)
                mspec = get_model_spec(mkey)
                if mspec["pool"] != pool:
                    continue
                pool_in += in_t
                pool_out += out_t
                pool_cache += cache_t
                if mkey == target_model:
                    m_hist_in += in_t
                    m_hist_out += out_t
                    m_hist_cache += cache_t

                if bts >= cur_start_ts:
                    sidx = 0
                else:
                    sidx = int((cur_start_ts - bts) // period_secs) + 1
                if steps > 0:
                    pool_active_slots[sidx] = True
                if mkey == target_model:
                    st = model_slot_stats.setdefault(sidx, [0, 0, 0.0, 0])
                    st[0] += (in_t + out_t)
                    st[1] += cache_t
                    st[2] += cost_u
                    st[3] += steps

        # Determine realistic agent token mix for cost & raw-token projection
        # Require substantial cached agent traffic on the model before overriding pool-wide agent cache mix
        if (m_hist_in + m_hist_out) >= 500000 and m_hist_cache >= 1000000:
            mix_in, mix_out, mix_cache = m_hist_in, m_hist_out, m_hist_cache
        else:
            mix_in, mix_out, mix_cache = pool_in, pool_out, pool_cache
        mix_raw = mix_in + mix_out
        if mix_raw > 0:
            r_in = mix_in / mix_raw
            r_out = mix_out / mix_raw
            r_cache_per_raw = min(30.0, mix_cache / mix_raw)
            mix_eff = mix_raw + 0.1 * mix_cache
            raw_per_eff = max(0.30, min(0.85, mix_raw / mix_eff)) if mix_eff > 0 else 0.45
        else:
            r_in, r_out, r_cache_per_raw, raw_per_eff = 0.90, 0.10, 12.0, 0.45

        usd_per_1m_raw = r_in * spec["in"] + r_out * spec["out"] + r_cache_per_raw * spec["cache"]

        # 3. Completed historical reset slots for Last 3 & All Resets usage
        past_active_indices = sorted(idx for idx in pool_active_slots.keys() if idx >= 1)
        last3_indices = past_active_indices[:3]
        if not last3_indices and 0 in pool_active_slots:
            last3_indices = [0]

        all_indices = sorted(pool_active_slots.keys())
        if 0 not in all_indices and (cur_m_steps > 0 or w_cur):
            all_indices = [0] + all_indices

        def _sum_slots(indices, include_exact_cur: bool):
            tok_sum = cache_sum = steps_sum = 0
            usd_sum = 0.0
            active_for_model = 0
            for idx in indices:
                if idx == 0 and include_exact_cur:
                    st_tok, st_cache, st_usd, st_steps = cur_m_tokens, cur_m_cache, cur_m_usd, cur_m_steps
                else:
                    st = model_slot_stats.get(idx, [0, 0, 0.0, 0])
                    st_tok, st_cache, st_usd, st_steps = st[0], st[1], st[2], st[3]
                tok_sum += st_tok
                cache_sum += st_cache
                usd_sum += st_usd
                steps_sum += st_steps
                if st_steps > 0:
                    active_for_model += 1
            n_res = max(0, len(indices))
            return {
                "resets_count": n_res,
                "model_active_resets": active_for_model,
                "used_tokens": int(tok_sum),
                "used_cache_tokens": int(cache_sum),
                "used_usd": round(usd_sum, 4),
                "used_avg_tokens": int(tok_sum / n_res) if n_res > 0 else 0,
                "used_avg_usd": round(usd_sum / n_res, 4) if n_res > 0 else 0.0,
                "steps": int(steps_sum),
            }

        u_cur = {
            "resets_count": 1,
            "model_active_resets": 1 if cur_m_steps > 0 else 0,
            "used_tokens": cur_m_tokens,
            "used_cache_tokens": cur_m_cache,
            "used_usd": round(cur_m_usd, 4),
            "used_avg_tokens": cur_m_tokens,
            "used_avg_usd": round(cur_m_usd, 4),
            "steps": cur_m_steps,
        }
        u_last3 = _sum_slots(last3_indices, include_exact_cur=(0 in last3_indices and len(past_active_indices) == 0))
        u_all = _sum_slots(all_indices, include_exact_cur=True)

        # 4. Calibrated Capacity (cap_base) per Scope (Current / Last 3 Resets / All Resets)
        rcaps = self.history.get("reset_caps", {}).get(rcap_key, {})
        ordered_rcaps = sorted(rcaps.values(), key=lambda x: x.get("first_ts", 0))

        def _cap_from_rcap_list(items):
            vals = [int(it.get("cap_base", 0) or 0) for it in items if (it.get("cap_base", 0) or 0) > 0]
            if vals:
                return int(self._median_num(vals, 0))
            return 0

        # Pool fallback cap from raw samples (in base units) if reset_caps missing
        samp_arr = self.history.get(samp_key, [])
        samp_base_caps = []
        for s in samp_arr:
            p = int(s.get("pct_used", 0) or 0)
            sb = float(s.get("server_base_units", 0) or 0)
            if p >= 2 and sb > 0:
                samp_base_caps.append(sb / (p / 100.0))
        all_cap_base = _cap_from_rcap_list(ordered_rcaps) or int(self._median_num(samp_base_caps, fallback_base_cap))
        last3_cap_base = _cap_from_rcap_list(ordered_rcaps[-3:]) or all_cap_base

        # Current slot live calibration
        cur_pct_used = max(0, 100 - int(pct_rem))
        cur_base_used = float(w_cur.get("gemini_base_units" if pool == "gemini" else "tp_base_units", 0) or 0)
        cur_cap_base = 0
        cur_slot_key = ("reset:" + cur_reset_dt.isoformat()) if cur_reset_dt else None
        if cur_slot_key and cur_slot_key in rcaps and (rcaps[cur_slot_key].get("cap_base", 0) or 0) > 0:
            cur_cap_base = int(rcaps[cur_slot_key]["cap_base"])
            cur_source = "live slot"
        elif cur_pct_used >= 3 and cur_base_used > 0:
            cur_cap_base = int(cur_base_used / (cur_pct_used / 100.0))
            cur_source = "live est"
        else:
            cur_cap_base = last3_cap_base or all_cap_base
            cur_source = "hist fallback"

        def _calc_remain(cap_base_val: int, src_label: str, cal_slots_n: int):
            rem_base = max(0.0, cap_base_val * (max(0, min(100, int(pct_rem))) / 100.0))
            rem_eff = rem_base / w_m
            cap_eff = cap_base_val / w_m
            rem_tok = int(rem_eff * raw_per_eff)
            cap_tok = int(cap_eff * raw_per_eff)
            rem_usd = round((rem_tok / 1_000_000.0) * usd_per_1m_raw, 2)
            cap_usd = round((cap_tok / 1_000_000.0) * usd_per_1m_raw, 2)
            avg_step = max(200, int(spec.get("avg_step_base", 1800)))
            rem_steps = max(0, int(rem_eff / avg_step))
            return {
                "rem_tokens": rem_tok,
                "rem_usd": rem_usd,
                "cap_tokens": cap_tok,
                "cap_usd": cap_usd,
                "rem_steps": rem_steps,
                "cap_source": src_label,
                "cal_slots": cal_slots_n,
            }

        scopes = {
            "current": {**u_cur, **_calc_remain(cur_cap_base, cur_source, 1 if cur_source.startswith("live") else 0)},
            "last3": {**u_last3, **_calc_remain(last3_cap_base, f"{min(3, len(ordered_rcaps))} cal slots" if ordered_rcaps else "est", len(ordered_rcaps[-3:]))},
            "all": {**u_all, **_calc_remain(all_cap_base, f"{len(ordered_rcaps)} cal slots" if ordered_rcaps else "est", len(ordered_rcaps))},
        }
        return {
            "pct_rem": int(pct_rem),
            "pct_used": cur_pct_used,
            "reset_ts": cur_reset_dt.timestamp() if cur_reset_dt else None,
            "reset_desc": self._fmt_cooldown_desc(cur_reset_dt),
            "scopes": scopes,
            "seen_models": seen_models,
        }

    def _recompute_minimal_metrics(self):
        detected_model = self.cached_metrics.get("active_model") or "Gemini 4 Argon (Medium)"
        pref_model = (self.config or {}).get("minimal_model", "auto") or "auto"
        is_manual = (pref_model != "auto")
        target_model = pref_model if is_manual else detected_model
        spec = get_model_spec(target_model)
        pool = spec["pool"]

        if pool == "gemini":
            g5 = self._compute_scope_usage_and_caps(
                pool="gemini",
                target_model=target_model,
                spec=spec,
                period_secs=18000.0,
                cur_start_dt=self.five_h_start_dt,
                cur_reset_dt=self.gemini_5h_reset_dt,
                pct_rem=int(self.cached_metrics.get("gemini_5h_pct", 100)),
                w_cur=self._last_w5,
                by_model_cur=self._last_by_model_5h,
                samp_key="samples_5h",
                rcap_key="g_5h",
                fallback_base_cap=47_000_000,
            )
            gw = self._compute_scope_usage_and_caps(
                pool="gemini",
                target_model=target_model,
                spec=spec,
                period_secs=604800.0,
                cur_start_dt=self.weekly_start_dt,
                cur_reset_dt=self.gemini_weekly_reset_dt,
                pct_rem=int(self.cached_metrics.get("gemini_weekly_pct", 100)),
                w_cur=self._last_wWeek,
                by_model_cur=self._last_by_model_w,
                samp_key="samples_weekly",
                rcap_key="g_weekly",
                fallback_base_cap=180_000_000,
            )
        else:
            g5 = self._compute_scope_usage_and_caps(
                pool="tp",
                target_model=target_model,
                spec=spec,
                period_secs=18000.0,
                cur_start_dt=self.tp_five_h_start_dt,
                cur_reset_dt=self.tp_5h_reset_dt,
                pct_rem=int(self.cached_metrics.get("tp_5h_pct", 100)),
                w_cur=getattr(self, "_last_w5_tp", self._last_w5),
                by_model_cur=self._last_by_model_5h,
                samp_key="samples_tp_5h",
                rcap_key="tp_5h",
                fallback_base_cap=5_000_000,
            )
            gw = self._compute_scope_usage_and_caps(
                pool="tp",
                target_model=target_model,
                spec=spec,
                period_secs=604800.0,
                cur_start_dt=self.tp_weekly_start_dt,
                cur_reset_dt=self.tp_weekly_reset_dt,
                pct_rem=int(self.cached_metrics.get("tp_weekly_pct", 100)),
                w_cur=getattr(self, "_last_wWeek_tp", self._last_wWeek),
                by_model_cur=self._last_by_model_w,
                samp_key="samples_tp_weekly",
                rcap_key="tp_weekly",
                fallback_base_cap=10_000_000,
            )

        avail = list(PRIMARY_SELECTABLE_MODELS)
        for m in sorted((g5.get("seen_models") or set()) | (gw.get("seen_models") or set()) | {detected_model, target_model}):
            if m and m not in avail and m != "Gemini 3.8 Flash (Subagent)":
                avail.append(m)
        self.cached_metrics["available_models"] = avail
        self.cached_metrics["minimal"] = {
            "target_model": target_model,
            "detected_model": detected_model,
            "is_manual": is_manual,
            "pool": pool,
            "pool_label": "Gemini Pool" if pool == "gemini" else "Claude & GPT Pool",
            "weight": spec["weight"],
            "price_in": spec["in"],
            "price_out": spec["out"],
            "price_cache": spec["cache"],
            "conv_project": self.cached_metrics.get("active_conv_project", "Active Workspace"),
            "conv_title": self.cached_metrics.get("active_conv_title", ""),
            "archive_hydrated": self._archive_hydrated,
            "archive_cached_files": self._archive_cached_files,
            "archive_total_files": self._archive_total_files,
            "h5": {k: v for k, v in g5.items() if k != "seen_models"},
            "weekly": {k: v for k, v in gw.items() if k != "seen_models"},
        }

    def refresh_minimal_view(self):
        self._recompute_minimal_metrics()
        return self.cached_metrics.get("minimal", {})

    @staticmethod
    def _fmt_mins(mins: float) -> str:
        m = max(0, int(round(mins)))
        h = m // 60
        rem_m = m % 60
        if h > 0:
            return f"{h}h {rem_m:02d}m"
        return f"{rem_m}m"

    def _eval_pace_window(
        self,
        label: str,
        win_used_pct: float,
        win_mins: float,
        rem_pct: float,
        rem_mins: float,
        min_used_for_warn: float = 2.0,
    ) -> dict:
        win_mins = max(1.0, float(win_mins))
        rate_pct_min = win_used_pct / win_mins
        rate_pct_hr = rate_pct_min * 60.0
        proj_rem_burn_pct = rate_pct_min * rem_mins

        depletes = (
            rem_mins > 1.0
            and win_used_pct >= min_used_for_warn
            and proj_rem_burn_pct >= max(0.1, rem_pct - 0.05)
        )
        tight = (
            not depletes
            and rem_mins > 1.0
            and win_used_pct >= min_used_for_warn
            and proj_rem_burn_pct >= (rem_pct * 0.85)
        )

        if rate_pct_min > 0.0005:
            runway_mins = rem_pct / rate_pct_min
        else:
            runway_mins = 9999.0

        shortfall_mins = max(0.0, rem_mins - runway_mins) if depletes else 0.0

        if depletes:
            if shortfall_mins >= 1.0:
                runway_label = f"⚠️ 0% in {self._fmt_mins(runway_mins)} (-{self._fmt_mins(shortfall_mins)})"
            else:
                runway_label = f"⚠️ Hits 0% at reset ({self._fmt_mins(runway_mins)})"
        elif tight:
            runway_label = f"Tight: ~{self._fmt_mins(runway_mins)} runway"
        elif rate_pct_hr < 0.5:
            runway_label = "Runway: Idle / Safe"
        else:
            end_buf = max(0, int(round(rem_pct - proj_rem_burn_pct)))
            runway_label = f"Safe (~{end_buf}% left at reset)"

        return {
            "window": label,
            "window_mins": round(win_mins, 1),
            "used_pct": round(win_used_pct, 1),
            "rate_pct_hr": round(rate_pct_hr, 1),
            "proj_rem_burn_pct": round(proj_rem_burn_pct, 1),
            "runway_mins": round(runway_mins, 1),
            "shortfall_mins": round(shortfall_mins, 1),
            "warn": bool(depletes or tight),
            "critical": bool(depletes),
            "runway_label": runway_label,
        }

    def _compute_pace_windows(self, w5: dict):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        rem_pct = float(self.cached_metrics.get("gemini_5h_pct", 100))
        used_pct = max(0.0, 100.0 - rem_pct)

        if self.gemini_5h_reset_dt is None:
            idle_w = {
                "window": "Syncing",
                "window_mins": 0.0,
                "used_pct": 0.0,
                "rate_pct_hr": 0.0,
                "proj_rem_burn_pct": 0.0,
                "runway_mins": 9999.0,
                "shortfall_mins": 0.0,
                "warn": False,
                "critical": False,
                "runway_label": "Syncing clock...",
            }
            self.cached_metrics["pace_5h"] = {
                "updated_at": now_utc.isoformat(),
                "updated_ts": time.time(),
                "active_model": self.cached_metrics.get("active_model", "Gemini 4 Argon"),
                "gemini_5h_rem_pct": int(rem_pct),
                "gemini_5h_used_pct": int(used_pct),
                "elapsed_mins": 0.0,
                "rem_mins": 300.0,
                "elapsed_str": "--",
                "left_str": "--",
                "any_warning": False,
                "any_critical": False,
                "headline": "⟳ Synchronizing 5h reset clock...",
                "slot": dict(idle_w, window="0->Now Slot"),
                "w30m": dict(idle_w, window="Last 30m"),
                "w15m": dict(idle_w, window="Last 15m"),
            }
            return

        rem_secs = max(0.0, (self.gemini_5h_reset_dt - now_utc).total_seconds())
        rem_mins = min(300.0, rem_secs / 60.0)
        elapsed_mins = max(1.0, 300.0 - rem_mins)

        learned_5h_cap = float(
            self.compute_learned_cap(self.history.get("samples_5h", []), default=862066)
        )
        slot_leg = float(w5.get("gemini_legacy_units", 0) or 0)
        if used_pct >= 5.0 and slot_leg > 0:
            units_per_1pct = max((learned_5h_cap / 100.0) * 0.65, slot_leg / used_pct)
        else:
            units_per_1pct = max(100.0, learned_5h_cap / 100.0)

        leg_30m = float(w5.get("gemini_legacy_30m", 0) or 0)
        leg_15m = float(w5.get("gemini_legacy_15m", 0) or 0)

        cap_pct = used_pct if used_pct > 0 else 100.0
        used_30m_pct = min(cap_pct, leg_30m / units_per_1pct)
        used_15m_pct = min(used_30m_pct, leg_15m / units_per_1pct)

        eff_slot_mins = max(5.0, elapsed_mins)
        eff_30m_mins = min(30.0, eff_slot_mins)
        eff_15m_mins = min(15.0, eff_slot_mins)

        w_slot = self._eval_pace_window(
            "0->Now Slot",
            used_pct,
            eff_slot_mins,
            rem_pct,
            rem_mins,
            min_used_for_warn=5.0 if elapsed_mins < 15.0 else 2.0,
        )
        w_30m = self._eval_pace_window(
            "Last 30m", used_30m_pct, eff_30m_mins, rem_pct, rem_mins, min_used_for_warn=2.0
        )
        w_15m = self._eval_pace_window(
            "Last 15m", used_15m_pct, eff_15m_mins, rem_pct, rem_mins, min_used_for_warn=1.5
        )

        crit_windows = [w for w in (w_slot, w_30m, w_15m) if w["critical"]]
        warn_windows = [w for w in (w_slot, w_30m, w_15m) if w["warn"]]

        any_critical = bool(crit_windows)
        any_warning = bool(warn_windows)

        if crit_windows:
            worst = min(crit_windows, key=lambda x: x["runway_mins"])
            names_str = " + ".join(w["window"] for w in crit_windows)
            headline = (
                f"⚠️ PACE ALERT ({names_str}): Proj +{worst['proj_rem_burn_pct']:.0f}% >= "
                f"{rem_pct:.0f}% left (0% in {self._fmt_mins(worst['runway_mins'])})"
            )
        elif warn_windows:
            worst = min(warn_windows, key=lambda x: x["runway_mins"])
            headline = (
                f"⚠️ Tight 5h Pace ({worst['window']}): Proj +{worst['proj_rem_burn_pct']:.0f}% vs "
                f"{rem_pct:.0f}% left (~{self._fmt_mins(worst['runway_mins'])} runway)"
            )
        else:
            headline = f"✓ 5h Pace Safe across Slot, 30m & 15m ({rem_pct:.0f}% left)"

        pace_payload = {
            "updated_at": now_utc.isoformat(),
            "updated_ts": time.time(),
            "active_model": self.cached_metrics.get("active_model", "Gemini 4 Argon"),
            "gemini_5h_rem_pct": int(rem_pct),
            "gemini_5h_used_pct": int(used_pct),
            "elapsed_mins": round(elapsed_mins, 1),
            "rem_mins": round(rem_mins, 1),
            "elapsed_str": self._fmt_mins(elapsed_mins),
            "left_str": self._fmt_mins(rem_mins),
            "any_warning": any_warning,
            "any_critical": any_critical,
            "headline": headline,
            "slot": w_slot,
            "w30m": w_30m,
            "w15m": w_15m,
        }
        self.cached_metrics["pace_5h"] = pace_payload

        try:
            os.makedirs(os.path.dirname(QUOTA_PACE_FILE), exist_ok=True)
            tmp_file = QUOTA_PACE_FILE + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(pace_payload, f, indent=2)
            os.replace(tmp_file, QUOTA_PACE_FILE)
        except Exception:
            pass



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
            target_agy = AGY_EXE if os.path.exists(AGY_EXE) else "agy"
            base_args = [
                target_agy,
                "-p", "1",
                "--model", "Gemini 3.8 Flash (Low)",
                "--disable-slash-commands",
                "--dangerously-skip-permissions"
            ]
            if os.path.exists(SILENT_RUNNER_EXE) and os.path.exists(AGY_EXE):
                cmd = [SILENT_RUNNER_EXE] + base_args
            else:
                cmd = base_args
            env = os.environ.copy()
            env["AGY_CLI_DISABLE_AUTO_UPDATE"] = "true"
            subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=USER_HOME,
                env=env,
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
            target_agy = AGY_EXE if os.path.exists(AGY_EXE) else "agy"
            base_args = [
                target_agy,
                "-p", "1",
                "--model", "GPT-OSS 120B (Medium)",
                "--disable-slash-commands",
                "--dangerously-skip-permissions"
            ]
            if os.path.exists(SILENT_RUNNER_EXE) and os.path.exists(AGY_EXE):
                cmd = [SILENT_RUNNER_EXE] + base_args
            else:
                cmd = base_args
            env = os.environ.copy()
            env["AGY_CLI_DISABLE_AUTO_UPDATE"] = "true"
            subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=USER_HOME,
                env=env,
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
        self._engine = engine
        self._config = config
        self._window = None
        self._is_on_top = config.get("pinned", True)
        self._is_auto_prime = config.get("auto_prime", True)
        self._is_global_yolo = config.get("global_yolo", True)
        self._is_tp_expanded = config.get("tp_expanded", False)
        self._models_show_all = config.get("models_show_all", True)
        self._is_compact = False
        self._current_theme = config.get("theme", "oled")
        self._font_scale_full = float(config.get("font_scale_full", 1.0))
        self._font_scale_mini = float(config.get("font_scale_mini", 1.0))

        self._last_expanded_w = config.get("last_w", 550)
        self._last_expanded_h = config.get("last_h", 820 if self._is_tp_expanded else 790)
        self._view_mode = config.get("view_mode", "minimal")
        self._minimal_model = config.get("minimal_model", "auto")
        self._active_tab = config.get("active_tab", "5h")

    def _set_window(self, window):
        self._window = window

    def get_config(self):
        return self._config

    def get_metrics(self):
        return self._engine.cached_metrics

    def force_sync(self):
        self._engine._conv_parse_cache.clear()
        self._engine.query_official_usage()
        self._engine._compute_disk_metrics()
        return self._engine.cached_metrics

    def move_by(self, dx, dy):
        hwnd = get_hud_hwnd()
        if hwnd:
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            cur_x = rect[0]
            cur_y = rect[1]
            user32.SetWindowPos(hwnd, 0, cur_x + dx, cur_y + dy, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        elif self._window:
            try:
                self._window.move(self._window.x + dx, self._window.y + dy)
            except Exception:
                pass

    def resize_window(self, new_w, new_h):
        min_w = 160 if self._is_compact else 380
        min_h = 30 if self._is_compact else 320
        target_w = max(min_w, int(new_w))
        target_h = max(min_h, int(new_h))

        if not self._is_compact:
            self._last_expanded_w = target_w
            self._last_expanded_h = target_h
            self._config["last_w"] = target_w
            self._config["last_h"] = target_h
            save_hud_config(self._config)

        hwnd = get_hud_hwnd()
        if hwnd:
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            cur_x = rect[0]
            cur_y = rect[1]
            if not self._is_compact:
                self._config["last_x"] = int(cur_x)
                self._config["last_y"] = int(cur_y)
                save_hud_config(self._config)
            user32.SetWindowPos(hwnd, 0, cur_x, cur_y, target_w, target_h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        elif self._window:
            try:
                self._window.resize(target_w, target_h)
            except Exception:
                pass
        return True

    def save_window_pos(self):
        hwnd = get_hud_hwnd()
        if hwnd and not self._is_compact:
            rect = (ctypes.c_long * 4)()
            if user32.GetWindowRect(hwnd, rect):
                self._config["last_x"] = int(rect[0])
                self._config["last_y"] = int(rect[1])
                save_hud_config(self._config)
                return {"x": int(rect[0]), "y": int(rect[1])}
        return None

    def _compact_dimensions(self):
        return (
            int(round(272 * self._font_scale_mini)),
            int(round(82 * self._font_scale_mini)),
        )

    def set_compact_mode(self, is_compact):
        hwnd = get_hud_hwnd()
        if hwnd and not self._is_compact:
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            cur_w = rect[2] - rect[0]
            cur_h = rect[3] - rect[1]
            if cur_w > 300 and cur_h > 200:
                self._last_expanded_w = cur_w
                self._last_expanded_h = cur_h

        self._is_compact = is_compact

        if hwnd:
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            cur_x = rect[0]
            cur_y = rect[1]
            if is_compact:
                w, h = self._compact_dimensions()
            else:
                w = max(520, self._last_expanded_w)
                min_safe_h = (820 if self._is_tp_expanded else 760) if self._view_mode == "verbose" else 420
                h = max(min_safe_h, self._last_expanded_h)
            user32.SetWindowPos(hwnd, 0, cur_x, cur_y, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        elif self._window:
            try:
                if is_compact:
                    w, h = self._compact_dimensions()
                    self._window.resize(w, h)
                else:
                    w = max(520, self._last_expanded_w)
                    min_safe_h = (820 if self._is_tp_expanded else 760) if self._view_mode == "verbose" else 420
                    h = max(min_safe_h, self._last_expanded_h)
                    self._window.resize(w, h)
            except Exception:
                pass
        return self._is_compact

    def set_font_scale(self, mode, scale):
        val = max(0.75, min(3.0, float(scale)))
        if mode == "mini":
            self._font_scale_mini = val
            self._config["font_scale_mini"] = val
            save_hud_config(self._config)
            if self._is_compact:
                hwnd = get_hud_hwnd()
                w, h = self._compact_dimensions()
                if hwnd:
                    rect = (ctypes.c_long * 4)()
                    user32.GetWindowRect(hwnd, rect)
                    user32.SetWindowPos(hwnd, 0, rect[0], rect[1], w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)
                elif self._window:
                    try:
                        self._window.resize(w, h)
                    except Exception:
                        pass
        else:
            self._font_scale_full = val
            self._config["font_scale_full"] = val
            save_hud_config(self._config)
        return val

    def set_ctx_bars_prefs(self, count, unique_projects):
        c = max(1, min(8, int(count)))
        u = bool(unique_projects)
        self._config["ctx_bars_count"] = c
        self._config["ctx_unique_projects"] = u
        save_hud_config(self._config)
        return {"ctx_bars_count": c, "ctx_unique_projects": u}

    def set_tp_expanded(self, expanded):
        self._is_tp_expanded = expanded
        self._config["tp_expanded"] = self._is_tp_expanded
        save_hud_config(self._config)
        return self._is_tp_expanded

    def set_models_show_all(self, show_all):
        self._models_show_all = bool(show_all)
        self._config["models_show_all"] = self._models_show_all
        save_hud_config(self._config)
        return self._models_show_all

    def set_theme(self, theme_name):
        self._current_theme = theme_name
        self._config["theme"] = theme_name
        save_hud_config(self._config)
        return self._current_theme

    def set_view_mode(self, mode):
        m = "verbose" if mode == "verbose" else "minimal"
        self._view_mode = m
        self._config["view_mode"] = m
        save_hud_config(self._config)
        return self._view_mode

    def set_minimal_model(self, model_name):
        val = (model_name or "auto").strip() or "auto"
        self._minimal_model = val
        self._config["minimal_model"] = val
        save_hud_config(self._config)
        if hasattr(self._engine, "refresh_minimal_view"):
            self._engine.refresh_minimal_view()
        return self._minimal_model

    def set_active_tab(self, tab):
        t = "weekly" if tab == "weekly" else "5h"
        self._active_tab = t
        self._config["active_tab"] = t
        save_hud_config(self._config)
        return self._active_tab

    def toggle_global_yolo(self):
        self._is_global_yolo = not self._is_global_yolo
        self._config["global_yolo"] = self._is_global_yolo
        save_hud_config(self._config)
        return self._is_global_yolo

    def toggle_auto_prime(self):
        self._is_auto_prime = not self._is_auto_prime
        self._config["auto_prime"] = self._is_auto_prime
        save_hud_config(self._config)
        return self._is_auto_prime

    def toggle_on_top(self):
        self._is_on_top = not self._is_on_top
        self._config["pinned"] = self._is_on_top
        save_hud_config(self._config)
        
        hwnd = get_hud_hwnd()
        if hwnd:
            flag = HWND_TOPMOST if self._is_on_top else HWND_NOTOPMOST
            user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        return self._is_on_top

    def minimize(self):
        hwnd = get_hud_hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, 6)
        elif self._window:
            try:
                self._window.minimize()
            except Exception:
                pass

    def close(self):
        if self._window:
            threading.Thread(target=self._window.destroy, daemon=True).start()


def _hud_trace(msg: str):
    try:
        trace_p = os.path.join(os.path.dirname(HUD_CONFIG_FILE), "hud_startup_trace.log")
        with open(trace_p, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} [PID {os.getpid()}] {msg}\n")
    except Exception:
        pass


def main():
    global _ACTIVE_WEBVIEW_WINDOW
    _hud_trace(f"main() enter argv={sys.argv}")
    mutex_name = "Global\\AntigravityHUD_SingleInstance_Mutex"
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:
        _hud_trace("mutex already exists (183), exiting")
        sys.exit(0)
    _hud_trace("mutex acquired")

    start_minimized = ("--minimized" in sys.argv) or ("-m" in sys.argv)
    config = load_hud_config()

    engine = MetricsEngine(config)
    primer = AutoPrimerWorker(engine, config)
    primer.start()

    api = Api(engine, config)

    is_tp = config.get("tp_expanded", False)
    init_w = config.get("last_w", 550)
    init_h = config.get("last_h", 820 if is_tp else 790)

    init_x = config.get("last_x")
    init_y = config.get("last_y")
    win_kwargs = {}
    if isinstance(init_x, (int, float)) and isinstance(init_y, (int, float)):
        try:
            vx = user32.GetSystemMetrics(76)
            vy = user32.GetSystemMetrics(77)
            vw = user32.GetSystemMetrics(78) or 1920
            vh = user32.GetSystemMetrics(79) or 1080
            ix, iy = int(init_x), int(init_y)
            if vx - 100 <= ix <= vx + vw - 120 and vy - 40 <= iy <= vy + vh - 80:
                win_kwargs["x"] = ix
                win_kwargs["y"] = iy
        except Exception:
            pass

    _hud_trace(f"creating window {init_w}x{init_h} pos={win_kwargs} minimized={start_minimized}")
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
        background_color="#000000",
        **win_kwargs,
    )
    _ACTIVE_WEBVIEW_WINDOW = window
    api._set_window(window)

    def on_startup():
        _hud_trace("on_startup() entered")
        for i in range(30):
            hwnd = get_hud_hwnd()
            if hwnd:
                if start_minimized:
                    user32.ShowWindow(hwnd, 7)
                    _hud_trace(f"tick {i}: minimized hwnd={hwnd}")
                else:
                    user32.ShowWindow(hwnd, 4)
                    flag = HWND_TOPMOST if config.get("pinned", True) else HWND_NOTOPMOST
                    user32.SetWindowPos(
                        hwnd,
                        flag,
                        0,
                        0,
                        0,
                        0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
                    )
                    vis = user32.IsWindowVisible(hwnd)
                    _hud_trace(f"tick {i}: shown hwnd={hwnd} visible={vis}")
                break
            time.sleep(0.08)

    _hud_trace("calling webview.start(on_startup)")
    webview.start(on_startup)
    _hud_trace("webview.start returned")


if __name__ == "__main__":
    main()

