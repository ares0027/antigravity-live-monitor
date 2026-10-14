"""Headless Empirical Quota & Token Weight Benchmark for Gemini 4 Argon.

Waits silently in the background until the 5-hour Gemini quota window has <= N minutes
remaining (default: 10 minutes), then spends the remaining 5h quota across controlled
phases (Fresh Input, Heavy Output/Thinking, and Argon Low/Medium/High Tier Sweep)
to empirically calibrate Antigravity Live Monitor.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

USER_HOME = Path.home()
AGY_EXE = USER_HOME / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
CLI_BRAIN = USER_HOME / ".gemini" / "antigravity-cli" / "brain"
DESKTOP_BRAIN = USER_HOME / ".gemini" / "antigravity" / "brain"
RESULTS_FILE = Path(__file__).resolve().parent / "argon_benchmark_results.json"

CREATE_NO_WINDOW = 0x08000000


def _hidden_startupinfo() -> subprocess.STARTUPINFO:
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


def query_usage() -> dict[str, Any]:
    """Query official `/usage` endpoint via headless `agy.exe -p /usage`."""
    cmd = [str(AGY_EXE if AGY_EXE.exists() else "agy"), "-p", "/usage"]
    out = subprocess.check_output(
        cmd,
        stdin=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=25,
        startupinfo=_hidden_startupinfo(),
        creationflags=CREATE_NO_WINDOW,
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    info: dict[str, Any] = {"queried_at": now.isoformat()}
    for line in out.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            group, metric, pct_str, reset_iso = (p.strip() for p in parts[:4])
            pct = int(pct_str.replace("%", "").strip())
            reset_dt = datetime.datetime.fromisoformat(reset_iso.replace("Z", "+00:00"))
            rem_secs = max(0.0, (reset_dt - now).total_seconds())
            if "Gemini" in group and "Five Hour" in metric:
                info["gemini_5h_pct"] = pct
                info["gemini_5h_reset_iso"] = reset_iso
                info["gemini_5h_reset_dt"] = reset_dt
                info["gemini_5h_rem_secs"] = rem_secs
            elif "Gemini" in group and "Weekly" in metric:
                info["gemini_weekly_pct"] = pct
                info["gemini_weekly_reset_iso"] = reset_iso
    return info


def get_transcript_snapshot(since_ts: float) -> dict[str, int]:
    """Sum exact server-reported telemetry tokens across transcripts modified since `since_ts`."""
    totals = {"steps": 0, "in_tokens": 0, "cache_tokens": 0, "out_tokens": 0}
    for brain in (CLI_BRAIN, DESKTOP_BRAIN):
        if not brain.exists():
            continue
        pattern = str(brain / "*" / ".system_generated" / "logs" / "transcript.jsonl")
        for log_path in glob.glob(pattern):
            try:
                if os.path.getmtime(log_path) < since_ts - 5.0:
                    continue
                with open(log_path, "r", encoding="utf-8", errors="ignore") as fp:
                    for line in fp:
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        if data.get("type") not in ("PLANNER_RESPONSE", "MODEL"):
                            continue
                        created = data.get("created_at")
                        if not created:
                            continue
                        dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
                        if dt.timestamp() >= since_ts:
                            totals["steps"] += 1
                            totals["in_tokens"] += int(data.get("input_tokens", 0) or 0)
                            totals["cache_tokens"] += int(
                                data.get("cache_read_tokens", 0)
                                or data.get("cached_content_token_count", 0)
                                or 0
                            )
                            totals["out_tokens"] += int(data.get("output_tokens", 0) or 0)
            except Exception:
                continue
    return totals


def run_agy_prompt(prompt: str, model: str, timeout: int = 90) -> bool:
    """Execute a single headless prompt on the specified model without stealing focus."""
    cmd = [
        str(AGY_EXE if AGY_EXE.exists() else "agy"),
        "-p",
        prompt,
        "--model",
        model,
        "--disable-slash-commands",
        "--dangerously-skip-permissions",
    ]
    try:
        subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=_hidden_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            timeout=timeout,
            check=False,
        )
        return True
    except Exception:
        return False


def make_synthetic_input_prompt(word_count: int = 6000) -> str:
    """Create an un-cached synthetic payload with a unique nonce to force fresh input tokens."""
    nonce = uuid.uuid4().hex
    block = " ".join(f"tok_{i % 997}_{nonce[:6]}" for i in range(word_count))
    return (
        f"Benchmark Nonce {nonce}.\n"
        f"Below is a synthetic telemetry payload. Do not analyze or summarize it. "
        f"Reply with the single word OK and nothing else.\n\n{block}"
    )


def make_heavy_output_prompt() -> str:
    """Create a tiny input prompt that forces maximum output and reasoning tokens."""
    nonce = uuid.uuid4().hex[:8]
    return (
        f"[Benchmark ID: {nonce}] Write an exhaustive, 2,500-word mathematical and architectural "
        f"treatise deriving multi-dimensional Kalman filtering, Monte Carlo Markov Chain convergence "
        f"proofs, and stochastic differential equations with full step-by-step symbolic derivations."
    )


def save_results(state: dict[str, Any]) -> None:
    try:
        RESULTS_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini 4 Argon Quota Benchmark Runner")
    parser.add_argument(
        "--wait-until-mins",
        type=float,
        default=10.0,
        help="Wait until <= N minutes remain in the 5-hour Gemini window before starting (default: 10.0)",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Start benchmarking immediately without waiting for the 10-minute window",
    )
    args = parser.parse_args()

    state: dict[str, Any] = {
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "wait_until_mins": 0.0 if args.now else args.wait_until_mins,
        "status": "waiting_for_window",
        "phases": [],
    }
    save_results(state)

    # 1. Wait loop until <= wait_until_mins remain on the 5h window
    target_rem_secs = 0.0 if args.now else (args.wait_until_mins * 60.0)
    initial_reset_iso: str | None = None

    while True:
        try:
            u = query_usage()
        except Exception as exc:
            state["last_error"] = str(exc)
            save_results(state)
            time.sleep(30.0)
            continue

        rem_secs = u.get("gemini_5h_rem_secs", 999999.0)
        pct_rem = u.get("gemini_5h_pct", 0)
        initial_reset_iso = u.get("gemini_5h_reset_iso")
        state["last_usage_check"] = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "gemini_5h_pct": pct_rem,
            "rem_mins": round(rem_secs / 60.0, 2),
            "reset_iso": initial_reset_iso,
        }
        save_results(state)

        if pct_rem <= 0:
            state["status"] = "completed_quota_already_zero"
            save_results(state)
            return

        if args.now or rem_secs <= target_rem_secs:
            break

        # Sleep smartly: check every 45s when far, or every 15s when within 15 minutes
        sleep_s = 15.0 if rem_secs <= target_rem_secs + 300 else 45.0
        time.sleep(sleep_s)

    state["status"] = "running_benchmark"
    state["benchmark_triggered_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_results(state)

    # Define controlled benchmark phases to execute in the final 10-minute window
    schedule = [
        ("phase1_fresh_input_argon_medium", "Gemini 4 Argon (Medium)", "input", 2),
        ("phase2_heavy_output_argon_medium", "Gemini 4 Argon (Medium)", "output", 2),
        ("phase3_tier_sweep_argon_low", "Gemini 4 Argon (Low)", "output", 2),
        ("phase4_tier_sweep_argon_high", "Gemini 4 Argon (High)", "output", 2),
    ]

    for phase_name, model_name, mode, iterations in schedule:
        u_before = query_usage()
        # Stop immediately if the 5h window reset or reached 0%
        if (
            u_before.get("gemini_5h_pct", 0) <= 0
            or u_before.get("gemini_5h_rem_secs", 0) <= 15.0
            or (initial_reset_iso and u_before.get("gemini_5h_reset_iso") != initial_reset_iso)
        ):
            break

        phase_start_ts = time.time()
        runs_completed = 0
        for _ in range(iterations):
            u_chk = query_usage()
            if (
                u_chk.get("gemini_5h_pct", 0) <= 0
                or u_chk.get("gemini_5h_rem_secs", 0) <= 15.0
                or (initial_reset_iso and u_chk.get("gemini_5h_reset_iso") != initial_reset_iso)
            ):
                break
            prompt = make_synthetic_input_prompt(6500) if mode == "input" else make_heavy_output_prompt()
            if run_agy_prompt(prompt, model=model_name, timeout=75):
                runs_completed += 1

        u_after = query_usage()
        tok_delta = get_transcript_snapshot(phase_start_ts)
        pct_drop = int(u_before.get("gemini_5h_pct", 0)) - int(u_after.get("gemini_5h_pct", 0))

        state["phases"].append(
            {
                "phase": phase_name,
                "model": model_name,
                "mode": mode,
                "runs": runs_completed,
                "pct_before": u_before.get("gemini_5h_pct"),
                "pct_after": u_after.get("gemini_5h_pct"),
                "pct_drop": pct_drop,
                "tokens": tok_delta,
                "rem_secs_after": round(u_after.get("gemini_5h_rem_secs", 0.0), 1),
            }
        )
        save_results(state)

    # Phase 5: Drain any remaining 5h quota before the reset using Gemini 4 Argon (High)
    drain_start_ts = time.time()
    u_drain_before = query_usage()
    drain_runs = 0
    while True:
        u_cur = query_usage()
        if (
            u_cur.get("gemini_5h_pct", 0) <= 0
            or u_cur.get("gemini_5h_rem_secs", 0) <= 12.0
            or (initial_reset_iso and u_cur.get("gemini_5h_reset_iso") != initial_reset_iso)
        ):
            break
        prompt = make_heavy_output_prompt()
        if run_agy_prompt(prompt, model="Gemini 4 Argon (High)", timeout=60):
            drain_runs += 1
        if drain_runs >= 30:
            break

    if drain_runs > 0:
        u_drain_after = query_usage()
        state["phases"].append(
            {
                "phase": "phase5_final_exhaustion_argon_high",
                "model": "Gemini 4 Argon (High)",
                "mode": "mixed_drain",
                "runs": drain_runs,
                "pct_before": u_drain_before.get("gemini_5h_pct"),
                "pct_after": u_drain_after.get("gemini_5h_pct"),
                "pct_drop": int(u_drain_before.get("gemini_5h_pct", 0))
                - int(u_drain_after.get("gemini_5h_pct", 0)),
                "tokens": get_transcript_snapshot(drain_start_ts),
                "rem_secs_after": round(u_drain_after.get("gemini_5h_rem_secs", 0.0), 1),
            }
        )

    state["status"] = "completed"
    state["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_results(state)


if __name__ == "__main__":
    main()
