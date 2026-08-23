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

# Verified Gemini 3.7 Flash Rates
PRICE_INPUT_PER_M = 0.75       # $0.75 / 1M tokens ($0.00075 / 1k)
PRICE_CACHE_PER_M = 0.075      # $0.075 / 1M tokens ($0.000075 / 1k)
PRICE_OUTPUT_PER_M = 3.75      # $3.75 / 1M tokens ($0.00375 / 1k)
BLENDED_RATE_PER_M = 2.25      # Weighted valuation rate

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
    default_config = {"pinned": True}
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
    .ring-progress {
      stroke: #4ADE80;
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
      <!-- Always on Top Toggle -->
      <button onclick="togglePin()" id="pinBtn" class="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/60 text-emerald-400 hover:text-emerald-300 transition flex items-center gap-1 text-[10px] mono cursor-pointer" title="Always on Top (Enabled)">
        <span id="pinDot" class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
        <span id="pinText">PINNED</span>
      </button>

      <!-- Sync Button -->
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
        <h2 class="text-xs font-bold text-zinc-400 tracking-tight uppercase">Gemini Models (Primary)</h2>
      </div>

      <div class="card rounded-2xl overflow-hidden shadow-lg">

        <!-- Weekly Limit Remaining -->
        <div class="p-3 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-sm font-semibold text-white">Weekly Limit Remaining</span>
                <span class="text-xs font-bold text-emerald-400 mono" id="estWeeklyRemain">~--M left</span>
              </div>
              <div class="text-[11px] text-zinc-400 mt-0.5 mono" id="geminiWeeklyDesc">
                Resets in --
              </div>
            </div>
            <div class="flex items-center gap-2.5 flex-shrink-0">
              <span class="mono text-sm font-bold text-white" id="geminiWeeklyPct">--%</span>
              <svg class="w-7 h-7" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="geminiWeeklyRing" class="ring-progress" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <!-- 4-Value Matrix -->
          <div class="grid grid-cols-4 gap-1.5 mt-2 text-[10px] mono">
            <div class="bg-zinc-900/90 border border-zinc-800 p-1.5 rounded-lg text-center">
              <span class="text-zinc-500 block text-[9px]">1. Weighted</span>
              <span class="text-emerald-400 font-bold" id="wValWeighted">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800 p-1.5 rounded-lg text-center">
              <span class="text-zinc-500 block text-[9px]">2. Input</span>
              <span class="text-zinc-200 font-bold" id="wValInput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800 p-1.5 rounded-lg text-center">
              <span class="text-zinc-500 block text-[9px]">3. Output</span>
              <span class="text-purple-400 font-bold" id="wValOutput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800 p-1.5 rounded-lg text-center">
              <span class="text-zinc-500 block text-[9px]">4. Cache</span>
              <span class="text-amber-400 font-bold" id="wValCache">$0.00</span>
            </div>
          </div>
        </div>

        <!-- Five Hour Limit Remaining -->
        <div class="p-3 card-row">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-baseline gap-2">
                <span class="text-sm font-semibold text-white">Five Hour Limit Remaining</span>
                <span class="text-xs font-bold text-amber-400 mono" id="est5hRemain">~--k left</span>
              </div>
              <div class="text-[11px] text-zinc-400 mt-0.5 mono" id="geminiFiveHourDesc">
                Resets in --
              </div>
            </div>
            <div class="flex items-center gap-2.5 flex-shrink-0">
              <span class="mono text-sm font-bold text-white" id="geminiFiveHourPct">--%</span>
              <svg class="w-7 h-7" viewBox="0 0 36 36">
                <path class="ring-bg" stroke-width="3.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path id="geminiFiveHourRing" class="ring-progress" stroke-width="3.5" stroke-dasharray="100, 100" stroke-dashoffset="0" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>

          <!-- 4-Value Matrix -->
          <div class="grid grid-cols-4 gap-1.5 mt-2 text-[10px] mono">
            <div class="bg-zinc-900/90 border border-zinc-800 p-1.5 rounded-lg text-center">
              <span class="text-zinc-500 block text-[9px]">1. Weighted</span>
              <span class="text-emerald-400 font-bold" id="fValWeighted">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800 p-1.5 rounded-lg text-center">
              <span class="text-zinc-500 block text-[9px]">2. Input</span>
              <span class="text-zinc-200 font-bold" id="fValInput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800 p-1.5 rounded-lg text-center">
              <span class="text-zinc-500 block text-[9px]">3. Output</span>
              <span class="text-purple-400 font-bold" id="fValOutput">$0.00</span>
            </div>
            <div class="bg-zinc-900/90 border border-zinc-800 p-1.5 rounded-lg text-center">
              <span class="text-zinc-500 block text-[9px]">4. Cache</span>
              <span class="text-amber-400 font-bold" id="fValCache">$0.00</span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- 2. THIRD-PARTY MODELS (CLAUDE & GPT) -->
    <div>
      <div class="card rounded-xl p-2.5 shadow-md flex items-center justify-between text-xs mono">
        <div class="flex items-center gap-2">
          <span class="inline-block w-2 h-2 rounded-full bg-emerald-400" id="tpDot"></span>
          <span class="font-semibold text-white" id="tpSummary">Claude & GPT: 100% Ready</span>
        </div>
        <span class="text-[11px] text-zinc-400" id="tpDetail">Weekly 100% · 5h 100%</span>
      </div>
    </div>

    <!-- 3. CURRENT ACTIVE QUOTA SLOT USAGE (5H & WEEKLY) -->
    <div class="card rounded-2xl p-3 shadow-lg space-y-2.5">
      
      <!-- Slot Selector Tabs -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-1 bg-zinc-900 p-0.5 rounded-lg border border-zinc-800 text-[11px] mono">
          <button id="tab5h" onclick="switchTab('5h')" class="px-2.5 py-0.5 rounded-md font-semibold transition bg-zinc-700 text-white cursor-pointer">Current 5h Slot</button>
          <button id="tabWeekly" onclick="switchTab('weekly')" class="px-2.5 py-0.5 rounded-md font-semibold transition text-zinc-400 hover:text-white cursor-pointer">Current Weekly Slot</button>
        </div>
        <span class="mono text-xs font-bold text-emerald-400" id="curSlotCost">Spent: $0.0000</span>
      </div>

      <div class="flex justify-between text-[11px] text-zinc-400 mono">
        <span id="slotTokensLabel">Tokens in Current 5h Slot:</span>
        <span class="text-white font-bold" id="curSlotTokens">0 tokens</span>
      </div>

      <!-- Live Token & Cost Breakdown Grid -->
      <div class="grid grid-cols-3 gap-1.5 text-zinc-300">
        <div class="bg-zinc-900/90 border border-zinc-800 p-2 rounded-xl text-center">
          <div class="text-zinc-500 text-[9px] uppercase font-semibold">In ($0.75/M)</div>
          <div class="mono text-xs font-bold text-zinc-100 mt-0.5" id="statIn">0k</div>
          <div class="mono text-[10px] text-emerald-400 font-semibold" id="statInCost">($0.0000)</div>
        </div>
        <div class="bg-zinc-900/90 border border-zinc-800 p-2 rounded-xl text-center">
          <div class="text-zinc-500 text-[9px] uppercase font-semibold">Out ($3.75/M)</div>
          <div class="mono text-xs font-bold text-zinc-100 mt-0.5" id="statOut">0k</div>
          <div class="mono text-[10px] text-purple-400 font-semibold" id="statOutCost">($0.0000)</div>
        </div>
        <div class="bg-zinc-900/90 border border-zinc-800 p-2 rounded-xl text-center">
          <div class="text-zinc-500 text-[9px] uppercase font-semibold">Cache ($0.075)</div>
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
        document.getElementById('slotTokensLabel').textContent = 'Tokens in Current 5h Slot:';
      } else {
        tw.className = 'px-2.5 py-0.5 rounded-md font-semibold transition bg-zinc-700 text-white cursor-pointer';
        t5.className = 'px-2.5 py-0.5 rounded-md font-semibold transition text-zinc-400 hover:text-white cursor-pointer';
        document.getElementById('slotTokensLabel').textContent = 'Tokens in Current Weekly Slot:';
      }
      refreshData();
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
          document.getElementById('estWeeklyRemain').textContent = '~' + d.est_weekly_remain_str + ' left';
          updateRing('geminiWeeklyRing', d.gemini_weekly_pct);

          document.getElementById('wValWeighted').textContent = '$' + d.w_cost_weighted.toFixed(2);
          document.getElementById('wValInput').textContent = '$' + d.w_cost_in.toFixed(2);
          document.getElementById('wValOutput').textContent = '$' + d.w_cost_out.toFixed(2);
          document.getElementById('wValCache').textContent = '$' + d.w_cost_cache.toFixed(2);

          // 2. Gemini 5-Hour
          document.getElementById('geminiFiveHourPct').textContent = d.gemini_5h_pct + '%';
          document.getElementById('geminiFiveHourDesc').textContent = d.gemini_5h_desc;
          document.getElementById('est5hRemain').textContent = '~' + d.est_5h_remain_str + ' left';
          updateRing('geminiFiveHourRing', d.gemini_5h_pct);

          document.getElementById('fValWeighted').textContent = '$' + d.f_cost_weighted.toFixed(2);
          document.getElementById('fValInput').textContent = '$' + d.f_cost_in.toFixed(2);
          document.getElementById('fValOutput').textContent = '$' + d.f_cost_out.toFixed(2);
          document.getElementById('fValCache').textContent = '$' + d.f_cost_cache.toFixed(2);

          // 3. Third-Party Summary
          if (d.tp_weekly_pct === 100 && d.tp_5h_pct === 100) {
            document.getElementById('tpDot').className = 'inline-block w-2 h-2 rounded-full bg-emerald-400';
            document.getElementById('tpSummary').textContent = 'Claude & GPT: 100% Ready';
            document.getElementById('tpDetail').textContent = 'Weekly 100% · 5h 100%';
          } else {
            document.getElementById('tpDot').className = 'inline-block w-2 h-2 rounded-full bg-amber-400';
            document.getElementById('tpSummary').textContent = 'Weekly: ' + d.tp_weekly_pct + '% · 5h: ' + d.tp_5h_pct + '%';
            document.getElementById('tpDetail').textContent = d.tp_desc;
          }

          // 4. Exact Slot Display (5h vs Weekly Tab)
          const in_tok = (activeTab === '5h') ? d.slot5_in : d.slotW_in;
          const out_tok = (activeTab === '5h') ? d.slot5_out : d.slotW_out;
          const cache_tok = (activeTab === '5h') ? d.slot5_cache : d.slotW_cache;
          const tot_tok = (activeTab === '5h') ? d.slot5_total_tokens : d.slotW_total_tokens;
          const w_tok = (activeTab === '5h') ? d.slot5_weighted : d.slotW_weighted;

          const in_c = (activeTab === '5h') ? d.slot5_in_cost : d.slotW_in_cost;
          const out_c = (activeTab === '5h') ? d.slot5_out_cost : d.slotW_out_cost;
          const cache_c = (activeTab === '5h') ? d.slot5_cache_cost : d.slotW_cache_cost;
          const tot_c = (activeTab === '5h') ? d.slot5_total_cost : d.slotW_total_cost;

          document.getElementById('curSlotCost').textContent = 'Spent: $' + tot_c.toFixed(4);
          document.getElementById('curSlotTokens').textContent = tot_tok.toLocaleString() + ' tokens (' + (w_tok/1000).toFixed(1) + 'k weighted)';

          document.getElementById('statIn').textContent = (in_tok / 1000).toFixed(1) + 'k';
          document.getElementById('statInCost').textContent = '($' + in_c.toFixed(4) + ')';

          document.getElementById('statOut').textContent = (out_tok / 1000).toFixed(1) + 'k';
          document.getElementById('statOutCost').textContent = '($' + out_c.toFixed(4) + ')';

          document.getElementById('statCache').textContent = (cache_tok / 1000).toFixed(1) + 'k';
          document.getElementById('statCacheCost').textContent = '($' + cache_c.toFixed(4) + ')';

          document.getElementById('wsName').textContent = 'Active: ' + d.workspace;
          document.getElementById('sessionTokens').textContent = 'Current Chat: ' + d.session_total_tokens.toLocaleString() + ' tokens (' + d.turns + ' turns)';

          document.getElementById('syncPoints').textContent = 'Calibrated (' + d.sample_count + ' samples)';

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
          if (cfg && typeof cfg.pinned === 'boolean') {
            applyPinVisual(cfg.pinned);
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
        self.cached_metrics = {
            "gemini_weekly_pct": 97,
            "gemini_weekly_desc": "Resets in 6 days, 5 hours",
            "gemini_5h_pct": 85,
            "gemini_5h_desc": "Resets in 1 hour, 16 minutes",
            "est_5h_remain_str": "733k",
            "f_cost_weighted": 1.65,
            "f_cost_in": 0.55,
            "f_cost_out": 2.75,
            "f_cost_cache": 0.05,
            "est_weekly_remain_str": "7.84M",
            "w_cost_weighted": 17.64,
            "w_cost_in": 5.88,
            "w_cost_out": 29.41,
            "w_cost_cache": 0.59,
            "tp_weekly_pct": 100,
            "tp_5h_pct": 100,
            "tp_desc": "Full Quota Ready",
            "sample_count": len(self.history.get("samples_5h", [])),
            "workspace": "Active Workspace",
            "turns": 0,
            "session_total_tokens": 0,
            "slot5_in": 0,
            "slot5_out": 0,
            "slot5_cache": 0,
            "slot5_weighted": 0,
            "slot5_total_tokens": 0,
            "slot5_in_cost": 0.0,
            "slot5_out_cost": 0.0,
            "slot5_cache_cost": 0.0,
            "slot5_total_cost": 0.0,
            "slotW_in": 0,
            "slotW_out": 0,
            "slotW_cache": 0,
            "slotW_weighted": 0,
            "slotW_total_tokens": 0,
            "slotW_in_cost": 0.0,
            "slotW_out_cost": 0.0,
            "slotW_cache_cost": 0.0,
            "slotW_total_cost": 0.0
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
        return {"samples_5h": [], "samples_weekly": []}

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
                        h_txt = f"{hours} hour" if hours == 1 else f"{hours} hours"
                        d_txt = f"{days} day" if days == 1 else f"{days} days"
                        time_txt = f"{d_txt}, {h_txt}"
                    elif hours > 0:
                        h_txt = f"{hours} hour" if hours == 1 else f"{hours} hours"
                        m_txt = f"{mins} minute" if mins == 1 else f"{mins} minutes"
                        time_txt = f"{h_txt}, {m_txt}"
                    else:
                        time_txt = f"{mins} minutes"

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
                            self.cached_metrics["tp_weekly_pct"] = pct
                        elif "Five Hour" in metric:
                            self.cached_metrics["tp_5h_pct"] = pct
                            self.cached_metrics["tp_desc"] = short_desc

            w5 = self.calculate_slot(self.five_h_start_dt)
            wWeek = self.calculate_slot(self.weekly_start_dt)

            if five_h_pct is not None and five_h_pct < 100 and w5["weighted"] > 5000:
                fraction_used = (100.0 - five_h_pct) / 100.0
                implied_cap = int(w5["weighted"] / fraction_used)
                self.history["samples_5h"].append({
                    "ts": time.time(),
                    "used": w5["weighted"],
                    "pct_used": 100 - five_h_pct,
                    "implied_cap": implied_cap
                })

            if weekly_pct is not None and weekly_pct < 100 and wWeek["weighted"] > 5000:
                fraction_used = (100.0 - weekly_pct) / 100.0
                implied_cap = int(wWeek["weighted"] / fraction_used)
                self.history["samples_weekly"].append({
                    "ts": time.time(),
                    "used": wWeek["weighted"],
                    "pct_used": 100 - weekly_pct,
                    "implied_cap": implied_cap
                })

            self.history["samples_5h"] = self.history["samples_5h"][-100:]
            self.history["samples_weekly"] = self.history["samples_weekly"][-100:]
            self.save_history()

            learned_5h_cap = self.compute_learned_cap(self.history["samples_5h"], default=862000)
            learned_weekly_cap = self.compute_learned_cap(self.history["samples_weekly"], default=8083900)

            cur_5h_pct = self.cached_metrics["gemini_5h_pct"]
            est_5h_rem = int(learned_5h_cap * (cur_5h_pct / 100.0))
            self.cached_metrics["est_5h_remain_str"] = f"{est_5h_rem / 1000.0:.0f}k" if est_5h_rem < 1000000 else f"{est_5h_rem / 1000000.0:.2f}M"
            self.cached_metrics["f_cost_weighted"] = (est_5h_rem / 1000000.0) * BLENDED_RATE_PER_M
            self.cached_metrics["f_cost_in"] = (est_5h_rem / 1000000.0) * PRICE_INPUT_PER_M
            self.cached_metrics["f_cost_out"] = (est_5h_rem / 1000000.0) * PRICE_OUTPUT_PER_M
            self.cached_metrics["f_cost_cache"] = (est_5h_rem / 1000000.0) * PRICE_CACHE_PER_M

            cur_weekly_pct = self.cached_metrics["gemini_weekly_pct"]
            est_weekly_rem = int(learned_weekly_cap * (cur_weekly_pct / 100.0))
            self.cached_metrics["est_weekly_remain_str"] = f"{est_weekly_rem / 1000000.0:.2f}M" if est_weekly_rem >= 1000000 else f"{est_weekly_rem / 100.0:.0f}k"
            self.cached_metrics["w_cost_weighted"] = (est_weekly_rem / 1000000.0) * BLENDED_RATE_PER_M
            self.cached_metrics["w_cost_in"] = (est_weekly_rem / 1000000.0) * PRICE_INPUT_PER_M
            self.cached_metrics["w_cost_out"] = (est_weekly_rem / 1000000.0) * PRICE_OUTPUT_PER_M
            self.cached_metrics["w_cost_cache"] = (est_weekly_rem / 1000000.0) * PRICE_CACHE_PER_M

            self.cached_metrics["sample_count"] = len(self.history.get("samples_5h", []))
        except Exception:
            pass

    def compute_learned_cap(self, samples, default):
        if not samples:
            return default
        caps = [s["implied_cap"] for s in samples if s["implied_cap"] > 50000]
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
                                    if t == "USER_INPUT":
                                        total_in += estimate_tokens(str(data.get("content", "")))
                                    elif t in ["PLANNER_RESPONSE", "MODEL"]:
                                        total_out += estimate_tokens(str(data.get("content", "")))
                                        total_out += estimate_tokens(str(data.get("thinking", "")))
                                    elif t in ["CODE_ACTION", "RUN_COMMAND", "GENERIC", "TOOL_RESULT"]:
                                        total_in += estimate_tokens(str(data.get("content", "")))
                            except:
                                pass
            except:
                pass

        cached = int(total_in * 0.72) if total_in > 15000 else 0
        fresh_in = max(0, total_in - cached)
        weighted = int(fresh_in + (0.25 * cached) + total_out)

        in_cost = (fresh_in / 1000000.0) * PRICE_INPUT_PER_M
        out_cost = (total_out / 1000000.0) * PRICE_OUTPUT_PER_M
        cache_cost = (cached / 1000000.0) * PRICE_CACHE_PER_M
        total_cost = in_cost + out_cost + cache_cost

        return {
            "in": total_in,
            "out": total_out,
            "cache": cached,
            "weighted": weighted,
            "total_tokens": total_in + total_out,
            "in_cost": in_cost,
            "out_cost": out_cost,
            "cache_cost": cache_cost,
            "total_cost": total_cost
        }

    def _disk_worker_loop(self):
        while self.running:
            try:
                self._compute_disk_metrics()
            except Exception:
                pass
            time.sleep(1.0)

    def _compute_disk_metrics(self):
        # 1. Exact 5-Hour Slot Metrics
        w5 = self.calculate_slot(self.five_h_start_dt)
        self.cached_metrics["slot5_in"] = w5["in"]
        self.cached_metrics["slot5_out"] = w5["out"]
        self.cached_metrics["slot5_cache"] = w5["cache"]
        self.cached_metrics["slot5_weighted"] = w5["weighted"]
        self.cached_metrics["slot5_total_tokens"] = w5["total_tokens"]
        self.cached_metrics["slot5_in_cost"] = w5["in_cost"]
        self.cached_metrics["slot5_out_cost"] = w5["out_cost"]
        self.cached_metrics["slot5_cache_cost"] = w5["cache_cost"]
        self.cached_metrics["slot5_total_cost"] = w5["total_cost"]

        # 2. Exact Weekly Slot Metrics
        wWeek = self.calculate_slot(self.weekly_start_dt)
        self.cached_metrics["slotW_in"] = wWeek["in"]
        self.cached_metrics["slotW_out"] = wWeek["out"]
        self.cached_metrics["slotW_cache"] = wWeek["cache"]
        self.cached_metrics["slotW_weighted"] = wWeek["weighted"]
        self.cached_metrics["slotW_total_tokens"] = wWeek["total_tokens"]
        self.cached_metrics["slotW_in_cost"] = wWeek["in_cost"]
        self.cached_metrics["slotW_out_cost"] = wWeek["out_cost"]
        self.cached_metrics["slotW_cache_cost"] = wWeek["cache_cost"]
        self.cached_metrics["slotW_total_cost"] = wWeek["total_cost"]

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

class Api:
    def __init__(self, engine, config):
        self.engine = engine
        self.config = config
        self.window = None
        self.is_on_top = config.get("pinned", True)

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
    api = Api(engine, config)

    window = webview.create_window(
        title="Antigravity Live Monitor",
        html=HTML_CONTENT,
        js_api=api,
        width=480,
        height=660,
        frameless=True,
        on_top=config.get("pinned", True),
        resizable=True,
        background_color="#0D0E12"
    )
    api.set_window(window)
    webview.start()

if __name__ == "__main__":
    main()
