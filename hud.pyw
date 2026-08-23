import os
import sys
import json
import glob
import time
import datetime
import threading
import subprocess
import ctypes
import webview

USER_HOME = os.path.expanduser("~")
CLI_BRAIN = os.path.join(USER_HOME, ".gemini", "antigravity-cli", "brain")
DESKTOP_BRAIN = os.path.join(USER_HOME, ".gemini", "antigravity", "brain")
QUOTA_HISTORY_FILE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "quota_history.json")
HUD_CONFIG_FILE = os.path.join(USER_HOME, "AppData", "Local", "agy", "bin", "hud_config.json")

CREATE_NO_WINDOW = 0x08000000

# Verified Gemini Rates (Gemini 3.7 Flash)
GEMINI_PRICE_IN = 0.75       # $0.75 / 1M
GEMINI_PRICE_CACHE = 0.075   # $0.075 / 1M
GEMINI_PRICE_OUT = 3.75      # $3.75 / 1M
GEMINI_PRICE_WEIGHTED = 2.25 # Blended weighted rate

# Verified Third-Party Rates (Claude 3.7 / 3.5 Sonnet & GPT-4o)
TP_PRICE_IN = 3.00           # $3.00 / 1M
TP_PRICE_CACHE = 0.30        # $0.30 / 1M
TP_PRICE_OUT = 15.00         # $15.00 / 1M
TP_PRICE_WEIGHTED = 6.00     # Blended weighted rate

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

def check_single_instance():
    mutex_name = "Local\\AntigravityLiveMonitor_SingleInstance_Mutex"
    mutex = kernel32.CreateMutexW(None, True, mutex_name)
    last_error = kernel32.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
    return mutex

def load_hud_config():
    default_config = {"pinned": True, "auto_prime": True, "global_yolo": True, "active_tab": "5h"}
    if os.path.exists(HUD_CONFIG_FILE):
        try:
            with open(HUD_CONFIG_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    default_config.update(d)
        except Exception:
            pass
    return default_config

def save_hud_config(config_dict):
    try:
        os.makedirs(os.path.dirname(HUD_CONFIG_FILE), exist_ok=True)
        with open(HUD_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)
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
            if rect[2] - rect[0] > 100 and rect[3] - rect[1] > 100:
                hwnds.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return hwnds[0] if hwnds else None

def estimate_tokens(text):
    if not text:
        return 0
    return max(1, int(len(text) / 3.8))

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Antigravity Live Monitor</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
  <style>
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background-color: #0D0E12;
      color: #E2E8F0;
      margin: 0;
      padding: 0;
      user-select: none;
      overflow: hidden;
    }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .card {
      background: #16181D;
      border: 1px solid #23262F;
    }
    .card-row {
      border-bottom: 1px solid #23262F;
    }
    .card-row:last-child {
      border-bottom: none;
    }
    .ring-bg { stroke: #23272F; }
    .ring-progress-emerald {
      stroke: #4ADE80;
      transition: stroke-dashoffset 0.4s ease;
      transform: rotate(-90deg);
      transform-origin: 50% 50%;
    }
    .ring-progress-purple {
      stroke: #C084FC;
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
  </style>
</head>
<body class="flex flex-col h-screen box-border antialiased rounded-2xl border border-zinc-800/90 shadow-2xl overflow-hidden bg-[#0D0E12]">

  <!-- 0. SLEEK CUSTOM TITLEBAR (DRAGGABLE) -->
  <div id="titlebar" class="drag-handle flex items-center justify-between px-3 py-2 bg-[#12141A] border-b border-[#23262F] select-none flex-shrink-0">
    <div class="flex items-center gap-2 pointer-events-none">
      <div class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></div>
      <span class="text-xs font-bold text-zinc-200 tracking-wide mono">Antigravity Live Monitor</span>
    </div>

    <!-- Controls -->
    <div class="flex items-center gap-1.5" onclick="event.stopPropagation()">
      <!-- Global YOLO Mode Toggle -->
      <button onclick="toggleYolo()" id="yoloBtn" class="px-2 py-0.5 rounded bg-red-950/80 border border-red-800/60 text-red-400 hover:text-red-300 transition flex items-center gap-1 text-[10px] mono cursor-pointer" title="Global YOLO Mode (Auto-Approve All Permissions)">
        <span id="yoloDot" class="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse"></span>
        <span id="yoloText">YOLO: ON</span>
      </button>

      <!-- Auto-Prime Toggle -->
      <button onclick="togglePrime()" id="primeBtn" class="px-2 py-0.5 rounded bg-amber-950/80 border border-amber-800/60 text-amber-400 hover:text-amber-300 transition flex items-center gap-1 text-[10px] mono cursor-pointer" title="Auto-Prime Dual Cooldowns (Gemini + Claude/GPT)">
        <span id="primeDot" class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
        <span id="primeText">PRIME: ON</span>
      </button>

      <!-- Always on Top Toggle -->
      <button onclick="togglePin()" id="pinBtn" class="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/60 text-emerald-400 hover:text-emerald-300 transition flex items-center gap-1 text-[10px] mono cursor-pointer" title="Always on Top">
        <span id="pinDot" class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
        <span id="pinText">PINNED</span>
      </button>

      <!-- Refresh Sync -->
      <button onclick="triggerSync()" id="syncBtn" class="p-1 px-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-white transition text-xs mono cursor-pointer" title="Force Refresh Quota">
        ↻
      </button>

      <!-- Minimize -->
      <button onclick="minimizeWindow()" class="p-1 px-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-white transition text-xs mono cursor-pointer" title="Minimize">
        −
      </button>

      <!-- Close -->
      <button onclick="closeWindow()" class="p-1 px-1.5 rounded hover:bg-red-950/70 text-zinc-400 hover:text-red-400 transition text-xs mono cursor-pointer" title="Close">
        ✕
      </button>
    </div>
  </div>

  <!-- MAIN SCROLLABLE CONTENT -->
  <div class="p-3.5 space-y-3 flex-1 overflow-y-auto">

    <!-- 1. GEMINI MODELS SECTION -->
    <div>
      <div class="flex items-center justify-between mb-1.5 px-1">
        <h2 class="text-xs font-bold text-emerald-400 tracking-tight uppercase flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-400 inline-block"></span>
          Gemini Models (Primary Engine)
        </h2>
        <span class="text-[10px] text-zinc-500 mono">$0.75 in · $3.75 out</span>
      </div>

      <div class="card rounded-2xl overflow-hidden shadow-lg">

        <!-- Gemini Weekly Limit -->
        <div class="p-2.5 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-xs font-semibold text-white">Weekly Limit Remaining</span>
                <span class="text-xs font-bold text-emerald-400 mono" id="geminiWeeklyRemain">~--M left</span>
              </div>
              <div class="text-[10px] text-zinc-400 mt-0.5 mono" id="geminiWeeklyDesc">Resets in --</div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="mono text-xs font-bold text-white" id="geminiWeeklyPct">--%</span>
              <svg class="w-6 h-6" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="geminiWeeklyRing" class="ring-progress-emerald" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <!-- 4-Value Matrix -->
          <div class="grid grid-cols-4 gap-1 mt-1.5 text-[9px] mono">
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">1. Weighted</span>
              <span class="text-emerald-400 font-bold" id="gwValWeighted">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">2. Input</span>
              <span class="text-zinc-200 font-bold" id="gwValInput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">3. Output</span>
              <span class="text-purple-400 font-bold" id="gwValOutput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">4. Cache</span>
              <span class="text-amber-400 font-bold" id="gwValCache">$0.00</span>
            </div>
          </div>
        </div>

        <!-- Gemini Five Hour Limit -->
        <div class="p-2.5 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-xs font-semibold text-white">Five Hour Limit Remaining</span>
                <span class="text-xs font-bold text-amber-400 mono" id="gemini5hRemain">~--k left</span>
              </div>
              <div class="text-[10px] text-zinc-400 mt-0.5 mono" id="gemini5hDesc">Resets in --</div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="mono text-xs font-bold text-white" id="gemini5hPct">--%</span>
              <svg class="w-6 h-6" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="gemini5hRing" class="ring-progress-emerald" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <!-- 4-Value Matrix -->
          <div class="grid grid-cols-4 gap-1 mt-1.5 text-[9px] mono">
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">1. Weighted</span>
              <span class="text-emerald-400 font-bold" id="gfValWeighted">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">2. Input</span>
              <span class="text-zinc-200 font-bold" id="gfValInput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">3. Output</span>
              <span class="text-purple-400 font-bold" id="gfValOutput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">4. Cache</span>
              <span class="text-amber-400 font-bold" id="gfValCache">$0.00</span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- 2. CLAUDE & GPT THIRD-PARTY SECTION -->
    <div>
      <div class="flex items-center justify-between mb-1.5 px-1">
        <h2 class="text-xs font-bold text-purple-400 tracking-tight uppercase flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-purple-400 inline-block"></span>
          Claude & GPT Models (Third-Party)
        </h2>
        <span class="text-[10px] text-zinc-500 mono">$3.00 in · $15.00 out</span>
      </div>

      <div class="card rounded-2xl overflow-hidden shadow-lg border-purple-900/30">

        <!-- Claude Weekly Limit -->
        <div class="p-2.5 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-xs font-semibold text-white">Weekly Limit Remaining</span>
                <span class="text-xs font-bold text-purple-400 mono" id="tpWeeklyRemain">~--M left</span>
              </div>
              <div class="text-[10px] text-zinc-400 mt-0.5 mono" id="tpWeeklyDesc">Resets in --</div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="mono text-xs font-bold text-white" id="tpWeeklyPct">--%</span>
              <svg class="w-6 h-6" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="tpWeeklyRing" class="ring-progress-purple" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <!-- 4-Value Matrix -->
          <div class="grid grid-cols-4 gap-1 mt-1.5 text-[9px] mono">
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">1. Weighted</span>
              <span class="text-purple-400 font-bold" id="tpwValWeighted">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">2. Input</span>
              <span class="text-zinc-200 font-bold" id="tpwValInput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">3. Output</span>
              <span class="text-purple-300 font-bold" id="tpwValOutput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">4. Cache</span>
              <span class="text-amber-400 font-bold" id="tpwValCache">$0.00</span>
            </div>
          </div>
        </div>

        <!-- Claude Five Hour Limit -->
        <div class="p-2.5 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-xs font-semibold text-white">Five Hour Limit Remaining</span>
                <span class="text-xs font-bold text-amber-400 mono" id="tp5hRemain">~--k left</span>
              </div>
              <div class="text-[10px] text-zinc-400 mt-0.5 mono" id="tp5hDesc">Resets in --</div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="mono text-xs font-bold text-white" id="tp5hPct">--%</span>
              <svg class="w-6 h-6" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="tp5hRing" class="ring-progress-purple" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <!-- 4-Value Matrix -->
          <div class="grid grid-cols-4 gap-1 mt-1.5 text-[9px] mono">
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">1. Weighted</span>
              <span class="text-purple-400 font-bold" id="tpfValWeighted">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">2. Input</span>
              <span class="text-zinc-200 font-bold" id="tpfValInput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">3. Output</span>
              <span class="text-purple-300 font-bold" id="tpfValOutput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800/90 p-1 rounded text-center">
              <span class="text-zinc-500 block text-[8px]">4. Cache</span>
              <span class="text-amber-400 font-bold" id="tpfValCache">$0.00</span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- 3. CURRENT ACTIVE QUOTA SLOT USAGE -->
    <div class="card rounded-2xl p-3 shadow-lg space-y-2.5">
      
      <!-- Slot Selector Tabs -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-1 bg-zinc-900 p-0.5 rounded-lg border border-zinc-800 text-[11px] mono">
          <button id="tab5h" onclick="switchTab('5h')" class="px-2.5 py-0.5 rounded-md font-semibold transition bg-zinc-700 text-white cursor-pointer">Current 5h Slot</button>
          <button id="tabWeekly" onclick="switchTab('weekly')" class="px-2.5 py-0.5 rounded-md font-semibold transition text-zinc-400 hover:text-white cursor-pointer">Current Weekly Slot</button>
        </div>
        <span class="mono text-xs font-bold text-emerald-400" id="curSlotCost">Total Spent: $0.0000</span>
      </div>

      <!-- Model Category Breakdown Sub-bars -->
      <div class="grid grid-cols-2 gap-2 text-[10px] mono">
        <div class="bg-zinc-900/90 border border-emerald-950 p-1.5 rounded-lg">
          <div class="flex justify-between text-zinc-400">
            <span>Gemini Spent:</span>
            <span class="text-emerald-400 font-bold" id="geminiSlotCost">$0.0000</span>
          </div>
          <div class="text-[9px] text-zinc-500 mt-0.5" id="geminiSlotTokens">0 tokens</div>
        </div>
        <div class="bg-zinc-900/90 border border-purple-950 p-1.5 rounded-lg">
          <div class="flex justify-between text-zinc-400">
            <span>Claude/GPT Spent:</span>
            <span class="text-purple-400 font-bold" id="tpSlotCost">$0.0000</span>
          </div>
          <div class="text-[9px] text-zinc-500 mt-0.5" id="tpSlotTokens">0 tokens</div>
        </div>
      </div>

      <!-- Live Token & Cost Breakdown Grid -->
      <div class="grid grid-cols-3 gap-1.5 text-zinc-300">
        <div class="bg-zinc-900/90 border border-zinc-800 p-2 rounded-xl text-center">
          <div class="text-zinc-500 text-[9px] uppercase font-semibold">Total In</div>
          <div class="mono text-xs font-bold text-zinc-100 mt-0.5" id="statIn">0k</div>
          <div class="mono text-[10px] text-emerald-400 font-semibold" id="statInCost">($0.0000)</div>
        </div>
        <div class="bg-zinc-900/90 border border-zinc-800 p-2 rounded-xl text-center">
          <div class="text-zinc-500 text-[9px] uppercase font-semibold">Total Out</div>
          <div class="mono text-xs font-bold text-zinc-100 mt-0.5" id="statOut">0k</div>
          <div class="mono text-[10px] text-purple-400 font-semibold" id="statOutCost">($0.0000)</div>
        </div>
        <div class="bg-zinc-900/90 border border-zinc-800 p-2 rounded-xl text-center">
          <div class="text-zinc-500 text-[9px] uppercase font-semibold">Total Cache</div>
          <div class="mono text-xs font-bold text-zinc-100 mt-0.5" id="statCache">0k</div>
          <div class="mono text-[10px] text-amber-400 font-semibold" id="statCacheCost">($0.0000)</div>
        </div>
      </div>
      
      <!-- Current Session Context Sub-pill -->
      <div class="pt-1.5 border-t border-zinc-800/80 flex justify-between items-center text-[10px] text-zinc-500 mono">
        <span id="wsName">Active: Workspace</span>
        <span id="sessionTokens">Current Chat: 0 tokens (0 turns)</span>
      </div>
    </div>

  </div>

  <!-- FOOTER STATUS -->
  <div class="flex items-center justify-between px-3.5 py-1.5 border-t border-zinc-800/80 text-[11px] text-zinc-500 mono font-medium bg-[#12141A] flex-shrink-0">
    <span class="flex items-center gap-1.5 text-zinc-400">
      <span class="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
      <span id="syncPoints">Slot Engine Synchronized (1s)</span>
    </span>
    <span id="timestamp">--:--:--</span>
  </div>

  <script>
    let activeTab = '5h';
    let isPinned = true;
    let isAutoPrime = true;
    let isGlobalYolo = true;
    let isDragging = false;
    let startX = 0, startY = 0;

    function setupDrag() {
      const tb = document.getElementById('titlebar');
      if (tb) {
        tb.addEventListener('mousedown', (e) => {
          if (e.target.closest('button') || e.target.closest('input')) return;
          if (e.button === 0) {
            isDragging = true;
            startX = e.screenX;
            startY = e.screenY;
          }
        });

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
          }
        });

        window.addEventListener('mouseup', () => {
          isDragging = false;
        });
      }
    }

    function applyYoloVisual(enabled) {
      isGlobalYolo = enabled;
      const dot = document.getElementById('yoloDot');
      const text = document.getElementById('yoloText');
      const btn = document.getElementById('yoloBtn');
      if (isGlobalYolo) {
        dot.className = 'w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse';
        btn.className = 'px-2 py-0.5 rounded bg-red-950/80 border border-red-800/60 text-red-400 hover:text-red-300 transition flex items-center gap-1 text-[10px] mono cursor-pointer';
        text.textContent = 'YOLO: ON';
        btn.title = 'Global YOLO Mode (Enabled - Auto-Approve All Permissions)';
      } else {
        dot.className = 'w-1.5 h-1.5 rounded-full bg-zinc-500';
        btn.className = 'px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition flex items-center gap-1 text-[10px] mono cursor-pointer';
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
        dot.className = 'w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse';
        btn.className = 'px-2 py-0.5 rounded bg-amber-950/80 border border-amber-800/60 text-amber-400 hover:text-amber-300 transition flex items-center gap-1 text-[10px] mono cursor-pointer';
        text.textContent = 'PRIME: ON';
        btn.title = 'Auto-Prime Dual Cooldowns (Enabled)';
      } else {
        dot.className = 'w-1.5 h-1.5 rounded-full bg-zinc-500';
        btn.className = 'px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition flex items-center gap-1 text-[10px] mono cursor-pointer';
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
        dot.className = 'w-1.5 h-1.5 rounded-full bg-emerald-400';
        btn.className = 'px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/60 text-emerald-400 hover:text-emerald-300 transition flex items-center gap-1 text-[10px] mono cursor-pointer';
        text.textContent = 'PINNED';
        btn.title = 'Always on Top (Enabled)';
      } else {
        dot.className = 'w-1.5 h-1.5 rounded-full bg-zinc-500';
        btn.className = 'px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition flex items-center gap-1 text-[10px] mono cursor-pointer';
        text.textContent = 'UNPIN';
        btn.title = 'Always on Top (Disabled)';
      }
    }

    function switchTab(tab) {
      activeTab = tab;
      const t5 = document.getElementById('tab5h');
      const tw = document.getElementById('tabWeekly');
      if (tab === '5h') {
        t5.className = 'px-2.5 py-0.5 rounded-md font-semibold transition bg-zinc-700 text-white cursor-pointer';
        tw.className = 'px-2.5 py-0.5 rounded-md font-semibold transition text-zinc-400 hover:text-white cursor-pointer';
      } else {
        tw.className = 'px-2.5 py-0.5 rounded-md font-semibold transition bg-zinc-700 text-white cursor-pointer';
        t5.className = 'px-2.5 py-0.5 rounded-md font-semibold transition text-zinc-400 hover:text-white cursor-pointer';
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

    async function triggerSync() {
      const btn = document.getElementById('syncBtn');
      btn.textContent = '...';
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.force_sync();
        await refreshData();
      }
      setTimeout(() => { btn.textContent = '↻'; }, 1000);
    }

    async function refreshData() {
      if (window.pywebview && window.pywebview.api) {
        try {
          const d = await window.pywebview.api.get_metrics();
          if (!d) return;

          // 1. Gemini Weekly
          document.getElementById('geminiWeeklyPct').textContent = d.gemini_weekly_pct + '%';
          document.getElementById('geminiWeeklyDesc').textContent = d.gemini_weekly_desc;
          document.getElementById('geminiWeeklyRemain').textContent = '~' + d.gemini_est_weekly_remain_str + ' left';
          updateRing('geminiWeeklyRing', d.gemini_weekly_pct);

          document.getElementById('gwValWeighted').textContent = '$' + d.gw_cost_weighted.toFixed(2);
          document.getElementById('gwValInput').textContent = '$' + d.gw_cost_in.toFixed(2);
          document.getElementById('gwValOutput').textContent = '$' + d.gw_cost_out.toFixed(2);
          document.getElementById('gwValCache').textContent = '$' + d.gw_cost_cache.toFixed(2);

          // 2. Gemini 5-Hour
          document.getElementById('gemini5hPct').textContent = d.gemini_5h_pct + '%';
          document.getElementById('gemini5hDesc').textContent = d.gemini_5h_desc;
          document.getElementById('gemini5hRemain').textContent = '~' + d.gemini_est_5h_remain_str + ' left';
          updateRing('gemini5hRing', d.gemini_5h_pct);

          document.getElementById('gfValWeighted').textContent = '$' + d.gf_cost_weighted.toFixed(2);
          document.getElementById('gfValInput').textContent = '$' + d.gf_cost_in.toFixed(2);
          document.getElementById('gfValOutput').textContent = '$' + d.gf_cost_out.toFixed(2);
          document.getElementById('gfValCache').textContent = '$' + d.gf_cost_cache.toFixed(2);

          // 3. Claude & GPT Weekly
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
          document.getElementById('geminiSlotTokens').textContent = g_tokens.toLocaleString() + ' tokens';
          document.getElementById('tpSlotCost').textContent = '$' + tp_cost.toFixed(4);
          document.getElementById('tpSlotTokens').textContent = tp_tokens.toLocaleString() + ' tokens';

          document.getElementById('statIn').textContent = (in_tok / 1000).toFixed(1) + 'k';
          document.getElementById('statInCost').textContent = '($' + in_c.toFixed(4) + ')';

          document.getElementById('statOut').textContent = (out_tok / 1000).toFixed(1) + 'k';
          document.getElementById('statOutCost').textContent = '($' + out_c.toFixed(4) + ')';

          document.getElementById('statCache').textContent = (cache_tok / 1000).toFixed(1) + 'k';
          document.getElementById('statCacheCost').textContent = '($' + cache_c.toFixed(4) + ')';

          document.getElementById('wsName').textContent = 'Active: ' + d.workspace;
          document.getElementById('sessionTokens').textContent = 'Current Chat: ' + d.session_total_tokens.toLocaleString() + ' tokens (' + d.turns + ' turns)';
          document.getElementById('syncPoints').textContent = 'Dual Engine Calibrated (' + d.sample_count + ' samples)';

          const now = new Date();
          document.getElementById('timestamp').textContent = now.toTimeString().split(' ')[0];
        } catch (err) {
          console.error(err);
        }
      }
    }

    async function init() {
      setupDrag();
      if (window.pywebview && window.pywebview.api) {
        try {
          const cfg = await window.pywebview.api.get_config();
          if (cfg) {
            if (typeof cfg.pinned === 'boolean') applyPinVisual(cfg.pinned);
            if (typeof cfg.auto_prime === 'boolean') applyPrimeVisual(cfg.auto_prime);
            if (typeof cfg.global_yolo === 'boolean') applyYoloVisual(cfg.global_yolo);
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
        self.five_h_start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)
        self.weekly_start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
        self.tp_five_h_start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)
        self.tp_weekly_start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)

        self.cached_metrics = {
            # Gemini Models
            "gemini_weekly_pct": 97,
            "gemini_weekly_desc": "Resets in 6 days, 5 hours, 0 mins",
            "gemini_5h_pct": 100,
            "gemini_5h_desc": "Resets in 1 hour, 16 mins",
            "gemini_est_5h_remain_str": "862k",
            "gf_cost_weighted": 1.94,
            "gf_cost_in": 0.65,
            "gf_cost_out": 3.23,
            "gf_cost_cache": 0.06,
            "gemini_est_weekly_remain_str": "7.84M",
            "gw_cost_weighted": 17.64,
            "gw_cost_in": 5.88,
            "gw_cost_out": 29.41,
            "gw_cost_cache": 0.59,

            # Claude & GPT Models
            "tp_weekly_pct": 99,
            "tp_weekly_desc": "Resets in 6 days, 23 hours, 58 mins",
            "tp_5h_pct": 98,
            "tp_5h_desc": "Resets in 4 hours, 58 mins",
            "tp_est_5h_remain_str": "245k",
            "tpf_cost_weighted": 1.47,
            "tpf_cost_in": 0.74,
            "tpf_cost_out": 3.68,
            "tpf_cost_cache": 0.07,
            "tp_est_weekly_remain_str": "1.49M",
            "tpw_cost_weighted": 8.91,
            "tpw_cost_in": 4.46,
            "tpw_cost_out": 22.28,
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
            "slotW_tp_tokens": 0
        }
        self.running = True
        self.start_worker()

    def load_history(self):
        if os.path.exists(QUOTA_HISTORY_FILE):
            try:
                with open(QUOTA_HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
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

            out = subprocess.check_output(
                ["agy", "-p", "/usage"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=12,
                startupinfo=si,
                creationflags=CREATE_NO_WINDOW
            )

            now = datetime.datetime.now(datetime.timezone.utc)
            five_h_pct = None
            weekly_pct = None
            tp_five_h_pct = None
            tp_weekly_pct = None

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
                            weekly_pct = pct
                            self.cached_metrics["gemini_weekly_pct"] = pct
                            self.cached_metrics["gemini_weekly_desc"] = short_desc
                            self.weekly_start_dt = reset_dt - datetime.timedelta(days=7)
                        elif "Five Hour" in metric:
                            five_h_pct = pct
                            self.cached_metrics["gemini_5h_pct"] = pct
                            self.cached_metrics["gemini_5h_desc"] = short_desc
                            self.five_h_start_dt = reset_dt - datetime.timedelta(hours=5)
                    elif "Claude" in group or "GPT" in group:
                        if "Weekly" in metric:
                            tp_weekly_pct = pct
                            self.cached_metrics["tp_weekly_pct"] = pct
                            self.cached_metrics["tp_weekly_desc"] = short_desc
                            self.tp_weekly_start_dt = reset_dt - datetime.timedelta(days=7)
                        elif "Five Hour" in metric:
                            tp_five_h_pct = pct
                            self.cached_metrics["tp_5h_pct"] = pct
                            self.cached_metrics["tp_5h_desc"] = short_desc
                            self.tp_five_h_start_dt = reset_dt - datetime.timedelta(hours=5)

            # Calculate learned capacities
            learned_5h_cap = self.compute_learned_cap(self.history.get("samples_5h", []), default=862000)
            learned_weekly_cap = self.compute_learned_cap(self.history.get("samples_weekly", []), default=8083900)
            learned_tp_5h_cap = self.compute_learned_cap(self.history.get("samples_tp_5h", []), default=250000)
            learned_tp_weekly_cap = self.compute_learned_cap(self.history.get("samples_tp_weekly", []), default=1500000)

            # 1. Gemini Metrics Calculations
            cur_g_5h = self.cached_metrics["gemini_5h_pct"]
            est_g_5h_rem = int(learned_5h_cap * (cur_g_5h / 100.0))
            self.cached_metrics["gemini_est_5h_remain_str"] = f"{est_g_5h_rem / 1000.0:.0f}k" if est_g_5h_rem < 1000000 else f"{est_g_5h_rem / 1000000.0:.2f}M"
            self.cached_metrics["gf_cost_weighted"] = (est_g_5h_rem / 1000000.0) * GEMINI_PRICE_WEIGHTED
            self.cached_metrics["gf_cost_in"] = (est_g_5h_rem / 1000000.0) * GEMINI_PRICE_IN
            self.cached_metrics["gf_cost_out"] = (est_g_5h_rem / 1000000.0) * GEMINI_PRICE_OUT
            self.cached_metrics["gf_cost_cache"] = (est_g_5h_rem / 1000000.0) * GEMINI_PRICE_CACHE

            cur_g_weekly = self.cached_metrics["gemini_weekly_pct"]
            est_g_w_rem = int(learned_weekly_cap * (cur_g_weekly / 100.0))
            self.cached_metrics["gemini_est_weekly_remain_str"] = f"{est_g_w_rem / 1000000.0:.2f}M" if est_g_w_rem >= 1000000 else f"{est_g_w_rem / 1000.0:.0f}k"
            self.cached_metrics["gw_cost_weighted"] = (est_g_w_rem / 1000000.0) * GEMINI_PRICE_WEIGHTED
            self.cached_metrics["gw_cost_in"] = (est_g_w_rem / 1000000.0) * GEMINI_PRICE_IN
            self.cached_metrics["gw_cost_out"] = (est_g_w_rem / 1000000.0) * GEMINI_PRICE_OUT
            self.cached_metrics["gw_cost_cache"] = (est_g_w_rem / 1000000.0) * GEMINI_PRICE_CACHE

            # 2. Claude & GPT Third-Party Metrics Calculations
            cur_tp_5h = self.cached_metrics["tp_5h_pct"]
            est_tp_5h_rem = int(learned_tp_5h_cap * (cur_tp_5h / 100.0))
            self.cached_metrics["tp_est_5h_remain_str"] = f"{est_tp_5h_rem / 1000.0:.0f}k" if est_tp_5h_rem < 1000000 else f"{est_tp_5h_rem / 1000000.0:.2f}M"
            self.cached_metrics["tpf_cost_weighted"] = (est_tp_5h_rem / 1000000.0) * TP_PRICE_WEIGHTED
            self.cached_metrics["tpf_cost_in"] = (est_tp_5h_rem / 1000000.0) * TP_PRICE_IN
            self.cached_metrics["tpf_cost_out"] = (est_tp_5h_rem / 1000000.0) * TP_PRICE_OUT
            self.cached_metrics["tpf_cost_cache"] = (est_tp_5h_rem / 1000000.0) * TP_PRICE_CACHE

            cur_tp_weekly = self.cached_metrics["tp_weekly_pct"]
            est_tp_w_rem = int(learned_tp_weekly_cap * (cur_tp_weekly / 100.0))
            self.cached_metrics["tp_est_weekly_remain_str"] = f"{est_tp_w_rem / 1000000.0:.2f}M" if est_tp_w_rem >= 1000000 else f"{est_tp_w_rem / 1000.0:.0f}k"
            self.cached_metrics["tpw_cost_weighted"] = (est_tp_w_rem / 1000000.0) * TP_PRICE_WEIGHTED
            self.cached_metrics["tpw_cost_in"] = (est_tp_w_rem / 1000000.0) * TP_PRICE_IN
            self.cached_metrics["tpw_cost_out"] = (est_tp_w_rem / 1000000.0) * TP_PRICE_OUT
            self.cached_metrics["tpw_cost_cache"] = (est_tp_w_rem / 1000000.0) * TP_PRICE_CACHE

            self.cached_metrics["sample_count"] = len(self.history.get("samples_5h", []))
        except Exception:
            pass

    def compute_learned_cap(self, samples, default):
        if not samples:
            return default
        caps = [s["implied_cap"] for s in samples if s.get("implied_cap", 0) > 10000]
        if not caps:
            return default
        caps.sort()
        mid = len(caps) // 2
        return caps[mid]

    def calculate_slot(self, start_dt):
        start_ts = start_dt.timestamp()

        all_logs = []
        for b in [CLI_BRAIN, DESKTOP_BRAIN]:
            if os.path.exists(b):
                for f in glob.glob(os.path.join(b, "*", ".system_generated", "logs", "transcript.jsonl")):
                    try:
                        mt = os.path.getmtime(f)
                        if mt >= start_ts:
                            all_logs.append((mt, f))
                    except:
                        pass

        all_logs.sort(key=lambda x: x[0], reverse=True)

        total_in = 0
        total_out = 0
        gemini_tokens = 0
        tp_tokens = 0

        for mt, log_path in all_logs:
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as fp:
                    for line in fp:
                        if not line.strip(): continue
                        try:
                            data = json.loads(line)
                        except:
                            continue
                        if "created_at" in data:
                            try:
                                dt = datetime.datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
                                if dt >= start_dt:
                                    t = data.get("type", "")
                                    in_tok = 0
                                    out_tok = 0
                                    if t == "USER_INPUT":
                                        in_tok = estimate_tokens(str(data.get("content", "")))
                                    elif t in ["PLANNER_RESPONSE", "MODEL"]:
                                        out_tok = estimate_tokens(str(data.get("content", ""))) + estimate_tokens(str(data.get("thinking", "")))
                                    elif t in ["CODE_ACTION", "RUN_COMMAND", "GENERIC", "TOOL_RESULT"]:
                                        in_tok = estimate_tokens(str(data.get("content", "")))

                                    total_in += in_tok
                                    total_out += out_tok

                                    # Check model tag
                                    model_name = str(data.get("modelName", "") or data.get("model", "")).lower()
                                    if "claude" in model_name or "gpt" in model_name:
                                        tp_tokens += (in_tok + out_tok)
                                    else:
                                        gemini_tokens += (in_tok + out_tok)
                            except:
                                pass
            except:
                pass

        cached = int(total_in * 0.72) if total_in > 15000 else 0
        fresh_in = max(0, total_in - cached)

        in_cost = (fresh_in / 1000000.0) * GEMINI_PRICE_IN
        out_cost = (total_out / 1000000.0) * GEMINI_PRICE_OUT
        cache_cost = (cached / 1000000.0) * GEMINI_PRICE_CACHE
        total_cost = in_cost + out_cost + cache_cost

        gemini_cost = (gemini_tokens / 1000000.0) * GEMINI_PRICE_WEIGHTED
        tp_cost = (tp_tokens / 1000000.0) * TP_PRICE_WEIGHTED

        return {
            "in": total_in,
            "out": total_out,
            "cache": cached,
            "total_tokens": total_in + total_out,
            "in_cost": in_cost,
            "out_cost": out_cost,
            "cache_cost": cache_cost,
            "total_cost": total_cost,
            "gemini_tokens": gemini_tokens,
            "gemini_cost": gemini_cost,
            "tp_tokens": tp_tokens,
            "tp_cost": tp_cost
        }

    def _disk_worker_loop(self):
        while self.running:
            try:
                self._compute_disk_metrics()
            except Exception:
                pass
            time.sleep(1.0)

    def _compute_disk_metrics(self):
        # 1. 5-Hour Slot Metrics
        w5 = self.calculate_slot(self.five_h_start_dt)
        self.cached_metrics["slot5_in"] = w5["in"]
        self.cached_metrics["slot5_out"] = w5["out"]
        self.cached_metrics["slot5_cache"] = w5["cache"]
        self.cached_metrics["slot5_in_cost"] = w5["in_cost"]
        self.cached_metrics["slot5_out_cost"] = w5["out_cost"]
        self.cached_metrics["slot5_cache_cost"] = w5["cache_cost"]
        self.cached_metrics["slot5_total_cost"] = w5["total_cost"]
        self.cached_metrics["slot5_gemini_cost"] = w5["gemini_cost"]
        self.cached_metrics["slot5_gemini_tokens"] = w5["gemini_tokens"]
        self.cached_metrics["slot5_tp_cost"] = w5["tp_cost"]
        self.cached_metrics["slot5_tp_tokens"] = w5["tp_tokens"]

        # 2. Weekly Slot Metrics
        wWeek = self.calculate_slot(self.weekly_start_dt)
        self.cached_metrics["slotW_in"] = wWeek["in"]
        self.cached_metrics["slotW_out"] = wWeek["out"]
        self.cached_metrics["slotW_cache"] = wWeek["cache"]
        self.cached_metrics["slotW_in_cost"] = wWeek["in_cost"]
        self.cached_metrics["slotW_out_cost"] = wWeek["out_cost"]
        self.cached_metrics["slotW_cache_cost"] = wWeek["cache_cost"]
        self.cached_metrics["slotW_total_cost"] = wWeek["total_cost"]
        self.cached_metrics["slotW_gemini_cost"] = wWeek["gemini_cost"]
        self.cached_metrics["slotW_gemini_tokens"] = wWeek["gemini_tokens"]
        self.cached_metrics["slotW_tp_cost"] = wWeek["tp_cost"]
        self.cached_metrics["slotW_tp_tokens"] = wWeek["tp_tokens"]

        # 3. Active Session Context
        all_logs = []
        for b in [CLI_BRAIN, DESKTOP_BRAIN]:
            if os.path.exists(b):
                for f in glob.glob(os.path.join(b, "*", ".system_generated", "logs", "transcript.jsonl")):
                    try:
                        mtime = os.path.getmtime(f)
                        all_logs.append((mtime, f))
                    except:
                        pass

        all_logs.sort(key=lambda x: x[0], reverse=True)
        if not all_logs:
            return

        latest_mtime, latest_log = all_logs[0]

        in_tokens = 0
        out_tokens = 0
        turns = 0
        ws_name = None

        with open(latest_log, "r", encoding="utf-8", errors="ignore") as fp:
            for line in fp:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                except:
                    continue

                t = data.get("type", "")
                if t == "USER_INPUT":
                    turns += 1
                    in_tokens += estimate_tokens(str(data.get("content", "")))
                elif t in ["PLANNER_RESPONSE", "MODEL"]:
                    out_tokens += estimate_tokens(str(data.get("content", "")))
                    out_tokens += estimate_tokens(str(data.get("thinking", "")))
                elif t in ["CODE_ACTION", "RUN_COMMAND", "GENERIC", "TOOL_RESULT"]:
                    in_tokens += estimate_tokens(str(data.get("content", "")))

                if not ws_name and data.get("tool_calls"):
                    for tc in data["tool_calls"]:
                        args = tc.get("args") or tc.get("arguments") or {}
                        for k, v in args.items():
                            if isinstance(v, str):
                                val = v.replace("/", "\\").strip('"\'')
                                if not (".gemini\\" in val.lower() or "brain\\" in val.lower()):
                                    p = val if os.path.isdir(val) else os.path.dirname(val)
                                    if p and len(p) > 3:
                                        ws_name = os.path.basename(p) or p
                                        break
                        if ws_name: break

        self.cached_metrics["workspace"] = ws_name or "Active Workspace"
        self.cached_metrics["turns"] = turns
        self.cached_metrics["session_total_tokens"] = in_tokens + out_tokens

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
                    now_ts = time.time()
                    # 1. Gemini Models Pool
                    cur_gemini_5h = self.engine.cached_metrics.get("gemini_5h_pct", 100)
                    if cur_gemini_5h >= 100 and (now_ts - self.last_gemini_prime) > 180:
                        self.last_gemini_prime = now_ts
                        self.trigger_gemini_prime()

                    # 2. Third-Party (Claude & GPT) Pool
                    cur_tp_5h = self.engine.cached_metrics.get("tp_5h_pct", 100)
                    if cur_tp_5h >= 100 and (now_ts - self.last_tp_prime) > 180:
                        self.last_tp_prime = now_ts
                        self.trigger_tp_prime()
            except Exception:
                pass
            time.sleep(30.0)

    def trigger_gemini_prime(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            # Cheapest Gemini Flash model with Lowest effort, disabled slash expansions & single token output
            subprocess.Popen(
                ["agy", "-p", "Reply with: 1", "--model", "Gemini 3.5 Flash (Low)", "--disable-slash-commands"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=si,
                creationflags=CREATE_NO_WINDOW
            )
            time.sleep(5.0)
            self.engine.query_official_usage()
        except Exception:
            pass

    def trigger_tp_prime(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            # Cheapest third-party model with disabled slash expansions & single token output
            subprocess.Popen(
                ["agy", "-p", "Reply with: 1", "--model", "GPT-OSS 120B (Medium)", "--disable-slash-commands"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=si,
                creationflags=CREATE_NO_WINDOW
            )
            time.sleep(5.0)
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
            user32.ShowWindow(hwnd, 6) # SW_MINIMIZE = 6
        elif self.window:
            try:
                self.window.minimize()
            except Exception:
                pass

    def close(self):
        if self.window:
            threading.Thread(target=self.window.destroy, daemon=True).start()

def main():
    _mutex = check_single_instance()
    config = load_hud_config()

    engine = MetricsEngine()
    primer = AutoPrimerWorker(engine, config)
    primer.start()

    api = Api(engine, config)

    window = webview.create_window(
        title="Antigravity Live Monitor",
        html=HTML_CONTENT,
        js_api=api,
        width=500,
        height=820,
        frameless=True,
        on_top=config.get("pinned", True),
        resizable=True,
        background_color="#0D0E12"
    )
    api.set_window(window)
    webview.start()

if __name__ == "__main__":
    main()
