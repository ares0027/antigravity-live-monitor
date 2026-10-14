"""Analyze all existing Gemini 4 Argon & Gemini 3.8 Flash telemetry from quota_history.json and transcripts."""

from __future__ import annotations

import datetime
import glob
import json
import os
import re
import statistics
from pathlib import Path
from typing import Any

CLI_BRAIN = Path.home() / ".agy" / "antigravity" / "brain"
DESKTOP_BRAIN = Path.home() / ".gemini" / "antigravity" / "brain"
QUOTA_HIST = Path(r"C:\Users\baran\AppData\Local\agy\bin\quota_history.json")
BENCH_RESULTS = Path(r"C:\Users\baran\antigravity-live-monitor\argon_benchmark_results.json")


def analyze() -> None:
    # 1. Check any Phase 3 Flash High transcripts
    p3_convs = []
    for b in (CLI_BRAIN, DESKTOP_BRAIN):
        for p in glob.glob(str(b / "*" / ".system_generated" / "logs" / "transcript.jsonl")):
            if os.path.getmtime(p) < 1791947900:
                continue
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip() for l in f if l.strip()]
            if lines and "BENCH_phase3_flash_high" in lines[0]:
                p3_convs.append((p, len(lines)))
    print(f"Phase 3 Flash High transcripts: {len(p3_convs)}")

    # 2. Analyze quota_history.json transitions today (ts > 1791945000)
    qh = json.loads(QUOTA_HIST.read_text(encoding="utf-8"))
    s5 = [s for s in qh.get("samples_5h", []) if s.get("ts", 0) > 1791945000]
    sw = [s for s in qh.get("samples_weekly", []) if s.get("ts", 0) > 1791945000]

    transitions_5h: list[dict[str, Any]] = []
    prev_pct = None
    for s in s5:
        pct = s.get("pct_used")
        if prev_pct is None or pct != prev_pct:
            transitions_5h.append(s)
        prev_pct = pct

    print("\n=== 5-HOUR QUOTA BOUNDARY TRANSITIONS (TODAY) ===")
    for i, t in enumerate(transitions_5h):
        dt_str = datetime.datetime.fromtimestamp(t["ts"], tz=datetime.timezone.utc).strftime("%H:%M:%S")
        pct = t["pct_used"]
        used = t.get("used", 0)
        srv = t.get("server_base_units", 0)
        raw = t.get("raw_tokens", 0)
        cache = t.get("cache_tokens", 0)
        if i > 0:
            prev = transitions_5h[i - 1]
            dpct = pct - prev["pct_used"]
            d_used = used - prev.get("used", 0)
            d_srv = srv - prev.get("server_base_units", 0)
            d_raw = raw - prev.get("raw_tokens", 0)
            d_cache = cache - prev.get("cache_tokens", 0)
            d_eff = d_raw + int(d_cache * 0.1)
            print(
                f"  {prev['pct_used']}% -> {pct}% (+{dpct}%) @ {dt_str} UTC | "
                f"d_legacy={d_used:,} | d_raw_tok={d_raw:,} | d_cache_tok={d_cache:,} | "
                f"d_eff_tok(0.1x cache)={d_eff:,} | d_srv_units={d_srv:,}"
            )
        else:
            print(
                f"  START {pct}% @ {dt_str} UTC | legacy={used:,} | raw_tok={raw:,} | cache_tok={cache:,}"
            )

    # Compare pure Argon window (39% -> 49%, ts 1791945689.9 to 1791947292.1) vs Flash window (49% -> 53%)
    t39 = next((x for x in transitions_5h if x["pct_used"] == 39), None)
    t49 = next((x for x in transitions_5h if x["pct_used"] == 49), None)
    t53 = next((x for x in transitions_5h if x["pct_used"] == 53), None)

    if t39 and t49:
        dp = 49 - 39
        d_leg = t49["used"] - t39["used"]
        d_raw = t49["raw_tokens"] - t39["raw_tokens"]
        d_cache = t49["cache_tokens"] - t39["cache_tokens"]
        d_eff = d_raw + int(d_cache * 0.1)
        d_srv = t49["server_base_units"] - t39["server_base_units"]
        print(f"\n=== PURE ARGON USAGE SLICE (39% -> 49%, +{dp}% 5h drop) ===")
        print(f"  Legacy units per 1% drop: {d_leg / dp:,.0f} -> Implied 100% 5h Cap = {d_leg / dp * 100:,.0f} legacy units")
        print(f"  Fresh+Out tokens per 1% drop: {d_raw / dp:,.0f} -> Implied 100% 5h Cap = {d_raw / dp * 100:,.0f} raw tokens")
        print(f"  Cache tokens per 1% drop: {d_cache / dp:,.0f}")
        print(f"  Effective tokens (raw + 0.1*cache) per 1% drop: {d_eff / dp:,.0f} -> Implied 100% 5h Cap = {d_eff / dp * 100:,.0f} eff tokens")
        print(f"  Weighted Server Base Units (at 2.0x) per 1% drop: {d_srv / dp:,.0f} -> Implied 100% 5h Cap = {d_srv / dp * 100:,.0f}")

    # 3. Extract step-level generation speeds (tok/s) and token breakdown across all recent transcripts by model!
    model_stats: dict[str, dict[str, Any]] = {}
    for b in (CLI_BRAIN, DESKTOP_BRAIN):
        if not b.exists():
            continue
        for p in glob.glob(str(b / "*" / ".system_generated" / "logs" / "transcript.jsonl")):
            try:
                if os.path.getmtime(p) < 1791800000:  # last ~40 hours
                    continue
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip() for l in f if l.strip()]
                if not lines:
                    continue

                cur_model = "Gemini 4 Argon (High)" if b == DESKTOP_BRAIN else "Unknown"
                prev_dt: datetime.datetime | None = None

                for line in lines:
                    obj = json.loads(line)
                    t = obj.get("type", "")
                    c = str(obj.get("content", ""))
                    created = obj.get("created_at")
                    dt = (
                        datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
                        if created
                        else None
                    )

                    if t == "USER_INPUT":
                        if "<USER_SETTINGS_CHANGE>" in c and "Model Selection" in c:
                            m = re.search(r"from\s+([^\n\r]+?)\s+to\s+([^\n\r\.]+)", c)
                            if m:
                                cur_model = m.group(2).strip()
                        if "BENCH_phase1_flash_low" in c:
                            cur_model = "Gemini 3.8 Flash (Low)"
                        elif "BENCH_phase2_flash_medium" in c:
                            cur_model = "Gemini 3.8 Flash (Medium)"
                        elif "BENCH_phase3_flash_high" in c:
                            cur_model = "Gemini 3.8 Flash (High)"

                    if t in ("PLANNER_RESPONSE", "MODEL"):
                        out_t = int(obj.get("output_tokens", 0) or 0)
                        in_t = int(obj.get("input_tokens", 0) or 0)
                        cache_t = int(obj.get("cache_read_tokens", 0) or 0)
                        if out_t > 80 and dt and prev_dt:
                            elapsed = (dt - prev_dt).total_seconds()
                            if 0.5 < elapsed < 180.0:
                                st = model_stats.setdefault(
                                    cur_model,
                                    {
                                        "steps": 0,
                                        "in_tokens": 0,
                                        "cache_tokens": 0,
                                        "out_tokens": 0,
                                        "tok_per_sec": [],
                                    },
                                )
                                st["steps"] += 1
                                st["in_tokens"] += in_t
                                st["cache_tokens"] += cache_t
                                st["out_tokens"] += out_t
                                st["tok_per_sec"].append(round(out_t / elapsed, 2))
                    if dt:
                        prev_dt = dt
            except Exception:
                continue

    print("\n=== EMPIRICAL GENERATION SPEED (TOK/S) FROM TRANSCRIPTS ===")
    for m, st in sorted(model_stats.items()):
        sps = st["tok_per_sec"]
        if not sps:
            continue
        # Filter outliers where user/system paused or tool waited
        clean_sps = [x for x in sps if 10.0 <= x <= 450.0]
        if not clean_sps:
            clean_sps = sps
        print(
            f"  {m:30s} | steps={st['steps']:4d} | out_tok={st['out_tokens']:9,d} | "
            f"median={statistics.median(clean_sps):6.1f} tok/s | "
            f"p75={statistics.quantiles(clean_sps, n=4)[2] if len(clean_sps)>=4 else statistics.mean(clean_sps):6.1f} tok/s | "
            f"max={max(clean_sps):6.1f} tok/s"
        )


if __name__ == "__main__":
    analyze()
