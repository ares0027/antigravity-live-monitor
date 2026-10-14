"""Headless Empirical Quota, Effort & Token Speed (tok/s) Benchmark for Antigravity.

Covers BOTH Quota Pools + Per-Model / Per-Effort Speed Benchmarking:
1. Gemini Pool (Gemini 3.8 Flash Low/Med/High & Gemini 4 Argon Low/Med/High):
   Waits until <= N minutes remain on the expiring 5-hour Gemini window (default: 16 mins),
   runs isolated calibration phases across every Gemini model & effort tier, measures exact
   Output/Thinking tok/s and Fresh Input prefill tok/s, and drains the expiring 5h Gemini quota
   to 0% before reset.
2. Third-Party Pool (GPT-OSS 120B Medium, Claude Sonnet 5.5 Low/Med/High, Claude Opus 5.5 Low/Med/High):
   Runs surgical, bounded calibration phases (2%-4% 5h drop per tier) across every Third-Party
   model & effort tier to reverse-engineer the shared Third-Party pool ceiling, relative model
   multipliers, and generation speeds (tok/s) without exhausting the 7-day Weekly Third-Party quota.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import glob
import json
import os
import statistics
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
REPORT_FILE = Path(__file__).resolve().parent / "BENCHMARK_REPORT.md"

CREATE_NO_WINDOW = 0x08000000
CLI_BOOT_OVERHEAD_SECS = 2.2  # Local agy.exe process init & auth handshake overhead

CONFIGURED_WEIGHTS = {
    # Gemini Pool (Baseline: Gemini 3.8 Flash (High) = 1.00x)
    "Gemini 3.8 Flash (Low)": 0.50,
    "Gemini 3.8 Flash (Medium)": 0.75,
    "Gemini 3.8 Flash (High)": 1.00,
    "Gemini 4 Argon (Low)": 1.80,
    "Gemini 4 Argon (Medium)": 2.50,
    "Gemini 4 Argon (High)": 3.50,
    # Third-Party Pool (Baseline: Claude Sonnet 5.5 (Medium) = 1.00x)
    "GPT-OSS 120B (Medium)": 0.40,
    "Claude Sonnet 5.5 (Low)": 0.80,
    "Claude Sonnet 5.5 (Medium)": 1.00,
    "Claude Sonnet 5.5 (High)": 1.50,
    "Claude Opus 5.5 (Low)": 3.00,
    "Claude Opus 5.5 (Medium)": 4.00,
    "Claude Opus 5.5 (High)": 5.00,
}


def _hidden_startupinfo() -> subprocess.STARTUPINFO:
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


def estimate_content_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 3.8))


def query_usage() -> dict[str, Any]:
    """Query official `/usage` endpoint via headless `agy.exe -p /usage` for both Gemini and TP pools."""
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
            if "Gemini" in group:
                if "Five Hour" in metric:
                    info["gemini_5h_pct"] = pct
                    info["gemini_5h_reset_iso"] = reset_iso
                    info["gemini_5h_reset_dt"] = reset_dt
                    info["gemini_5h_rem_secs"] = rem_secs
                elif "Weekly" in metric:
                    info["gemini_weekly_pct"] = pct
                    info["gemini_weekly_reset_iso"] = reset_iso
            elif "Claude" in group or "GPT" in group:
                if "Five Hour" in metric:
                    info["tp_5h_pct"] = pct
                    info["tp_5h_reset_iso"] = reset_iso
                    info["tp_5h_reset_dt"] = reset_dt
                    info["tp_5h_rem_secs"] = rem_secs
                elif "Weekly" in metric:
                    info["tp_weekly_pct"] = pct
                    info["tp_weekly_reset_iso"] = reset_iso
    return info


def get_transcript_snapshot(
    since_ts: float,
    phase_tag: str | None = None,
    call_timings: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Sum exact server-reported telemetry, legacy content tokens, and per-call tok/s speeds."""
    totals: dict[str, Any] = {
        "conversations": 0,
        "steps": 0,
        "in_tokens": 0,
        "cache_tokens": 0,
        "out_tokens": 0,
        "thinking_chars": 0,
        "response_chars": 0,
        "legacy_content_tokens": 0,
        "call_latencies_sec": [],
        "out_tok_per_sec_samples": [],
        "e2e_out_tok_per_sec_samples": [],
        "in_tok_per_sec_samples": [],
    }
    call_timings = call_timings or {}

    for brain in (CLI_BRAIN, DESKTOP_BRAIN):
        if not brain.exists():
            continue
        pattern = str(brain / "*" / ".system_generated" / "logs" / "transcript.jsonl")
        for log_path in glob.glob(pattern):
            try:
                if os.path.getmtime(log_path) < since_ts - 5.0:
                    continue
                with open(log_path, "r", encoding="utf-8", errors="ignore") as fp:
                    lines = [l.strip() for l in fp if l.strip()]
                if not lines:
                    continue

                first_obj = json.loads(lines[0])
                first_content = str(first_obj.get("content", ""))
                if phase_tag and phase_tag not in first_content:
                    continue

                matched_wall_sec: float | None = None
                for c_nonce, w_sec in call_timings.items():
                    if c_nonce in first_content:
                        matched_wall_sec = w_sec
                        break

                conv_counted = False
                conv_in = 0
                conv_out = 0
                first_dt: datetime.datetime | None = None
                last_dt: datetime.datetime | None = None

                for line in lines:
                    data = json.loads(line)
                    created = data.get("created_at")
                    if not created:
                        continue
                    dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if dt.timestamp() < since_ts - 2.0:
                        continue

                    if first_dt is None:
                        first_dt = dt
                    last_dt = dt

                    t = data.get("type", "")
                    c = str(data.get("content", ""))
                    if t in ("USER_INPUT", "CODE_ACTION", "RUN_COMMAND", "GENERIC", "TOOL_RESULT"):
                        totals["legacy_content_tokens"] += estimate_content_tokens(c)
                    elif t in ("PLANNER_RESPONSE", "MODEL"):
                        if not conv_counted:
                            totals["conversations"] += 1
                            conv_counted = True
                        totals["steps"] += 1
                        think_str = str(data.get("thinking", ""))
                        totals["thinking_chars"] += len(think_str)
                        totals["response_chars"] += len(c)
                        totals["legacy_content_tokens"] += (
                            estimate_content_tokens(c) + estimate_content_tokens(think_str)
                        )
                        in_t = int(data.get("input_tokens", 0) or 0)
                        cache_t = int(
                            data.get("cache_read_tokens", 0)
                            or data.get("cached_content_token_count", 0)
                            or 0
                        )
                        out_t = int(data.get("output_tokens", 0) or 0)
                        totals["in_tokens"] += in_t
                        totals["cache_tokens"] += cache_t
                        totals["out_tokens"] += out_t
                        conv_in += in_t
                        conv_out += out_t

                if conv_counted:
                    # Determine elapsed seconds for this conversation
                    elapsed_sec = matched_wall_sec
                    if elapsed_sec is None and first_dt and last_dt:
                        diff = (last_dt - first_dt).total_seconds()
                        if diff > 0.2:
                            elapsed_sec = diff
                    if elapsed_sec and elapsed_sec > 0.2:
                        net_sec = max(0.4, elapsed_sec - CLI_BOOT_OVERHEAD_SECS)
                        totals["call_latencies_sec"].append(round(elapsed_sec, 2))
                        if conv_out > 0:
                            totals["out_tok_per_sec_samples"].append(round(conv_out / net_sec, 2))
                            totals["e2e_out_tok_per_sec_samples"].append(
                                round(conv_out / elapsed_sec, 2)
                            )
                        if conv_in > 0:
                            totals["in_tok_per_sec_samples"].append(round(conv_in / net_sec, 2))
            except Exception:
                continue

    totals["total_fresh_plus_out"] = totals["in_tokens"] + totals["out_tokens"]
    totals["effective_cache_discounted_tokens"] = (
        totals["in_tokens"] + totals["out_tokens"] + int(totals["cache_tokens"] * 0.1)
    )

    out_sps = totals["out_tok_per_sec_samples"]
    e2e_sps = totals["e2e_out_tok_per_sec_samples"]
    in_sps = totals["in_tok_per_sec_samples"]
    lats = totals["call_latencies_sec"]

    totals["speed_metrics"] = {
        "median_out_tok_per_sec": round(statistics.median(out_sps), 1) if out_sps else 0.0,
        "mean_out_tok_per_sec": round(statistics.mean(out_sps), 1) if out_sps else 0.0,
        "max_out_tok_per_sec": round(max(out_sps), 1) if out_sps else 0.0,
        "median_e2e_out_tok_per_sec": round(statistics.median(e2e_sps), 1) if e2e_sps else 0.0,
        "median_in_tok_per_sec": round(statistics.median(in_sps), 1) if in_sps else 0.0,
        "avg_call_latency_sec": round(statistics.mean(lats), 2) if lats else 0.0,
    }
    return totals


def run_agy_prompt(
    prompt: str, model: str, effort: str, call_nonce: str, timeout: int = 85
) -> tuple[bool, str, float]:
    """Execute a single headless prompt and measure exact wall-clock execution time."""
    cmd = [
        str(AGY_EXE if AGY_EXE.exists() else "agy"),
        "-p",
        prompt,
        "--model",
        model,
        "--effort",
        effort,
        "--disable-slash-commands",
        "--dangerously-skip-permissions",
    ]
    t0 = time.perf_counter()
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
        return True, call_nonce, (time.perf_counter() - t0)
    except Exception:
        return False, call_nonce, (time.perf_counter() - t0)


def make_synthetic_input_prompt(
    phase_tag: str, call_nonce: str, word_count: int = 22000
) -> str:
    """Create an un-cached synthetic payload (~30k+ tokens + 22k system prompt = ~52k fresh input tokens)."""
    block = " ".join(
        f"v{(i * 73) % 9973}_{call_nonce[-5:]}_{i % 389}" for i in range(word_count)
    )
    return (
        f"Benchmark Nonce {call_nonce} [{phase_tag}].\n"
        f"Do not call any tools. Do not analyze or summarize the text below. "
        f"Reply with the single word OK and nothing else.\n\n{block}"
    )


def make_heavy_output_prompt(
    phase_tag: str, call_nonce: str, extra_input_words: int = 4000
) -> str:
    """Create a prompt that forces maximum chain-of-thought reasoning + dense output tokens."""
    pad = " ".join(
        f"ctx_{(i * 31) % 4099}_{call_nonce[-4:]}" for i in range(extra_input_words)
    )
    return (
        f"[Benchmark ID: {call_nonce}] [{phase_tag}]\n"
        f"IMPORTANT: Do NOT call any tools or read any files. Respond purely in plain text.\n"
        f"Write an exhaustive, 3,500-word graduate-level mathematical and systems engineering treatise "
        f"deriving: (1) Continuous-time Extended Kalman-Bucy filtering over Riemannian manifolds, "
        f"(2) Hamiltonian Monte Carlo convergence bounds with explicit Lyapunov functions, "
        f"(3) Non-asymptotic concentration inequalities for high-dimensional random matrices, and "
        f"(4) Full step-by-step symbolic derivations for every theorem.\n\n"
        f"Reference entropy seed:\n{pad}"
    )


def compute_empirical_summary(phases: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute model-specific and effort-specific capacity ceilings, burn weights, and tok/s speeds."""
    by_phase: dict[str, Any] = {}
    gemini_base_eff_per_pct: float | None = None
    gemini_base_leg_per_pct: float | None = None
    tp_base_eff_per_pct: float | None = None
    tp_base_leg_per_pct: float | None = None

    for p in phases:
        pool = p.get("pool", "gemini")
        drop = p.get("pct_drop_5h", 0)
        tok = p.get("tokens", {})
        spd = tok.get("speed_metrics", {})
        fresh_plus_out = tok.get("total_fresh_plus_out", 0)
        eff_tok = tok.get("effective_cache_discounted_tokens", 0)
        leg_tok = tok.get("legacy_content_tokens", 0)

        if drop > 0 and fresh_plus_out > 0:
            tok_per_1pct = fresh_plus_out / float(drop)
            eff_per_1pct = eff_tok / float(drop)
            leg_per_1pct = leg_tok / float(drop)
            implied_5h_ceiling_raw = int(tok_per_1pct * 100.0)
            implied_5h_ceiling_eff = int(eff_per_1pct * 100.0)
            implied_5h_ceiling_legacy = int(leg_per_1pct * 100.0)
        else:
            tok_per_1pct = 0.0
            eff_per_1pct = 0.0
            leg_per_1pct = 0.0
            implied_5h_ceiling_raw = 0
            implied_5h_ceiling_eff = 0
            implied_5h_ceiling_legacy = 0

        if p.get("model") == "Gemini 3.8 Flash (High)" and drop > 0 and eff_per_1pct > 0:
            gemini_base_eff_per_pct = eff_per_1pct
            gemini_base_leg_per_pct = leg_per_1pct
        elif p.get("model") == "Claude Sonnet 5.5 (Medium)" and drop > 0 and eff_per_1pct > 0:
            tp_base_eff_per_pct = eff_per_1pct
            tp_base_leg_per_pct = leg_per_1pct

        by_phase[p["phase"]] = {
            "pool": pool,
            "model": p.get("model"),
            "effort": p.get("effort"),
            "mode": p.get("mode"),
            "pct_drop_5h": drop,
            "pct_drop_weekly": p.get("pct_drop_weekly", 0),
            "steps": tok.get("steps", 0),
            "in_tokens": tok.get("in_tokens", 0),
            "cache_tokens": tok.get("cache_tokens", 0),
            "out_tokens": tok.get("out_tokens", 0),
            "thinking_chars": tok.get("thinking_chars", 0),
            "avg_out_tokens_per_step": int(tok.get("out_tokens", 0) / max(1, tok.get("steps", 1))),
            "median_out_tok_per_sec": spd.get("median_out_tok_per_sec", 0.0),
            "mean_out_tok_per_sec": spd.get("mean_out_tok_per_sec", 0.0),
            "max_out_tok_per_sec": spd.get("max_out_tok_per_sec", 0.0),
            "median_e2e_out_tok_per_sec": spd.get("median_e2e_out_tok_per_sec", 0.0),
            "median_in_tok_per_sec": spd.get("median_in_tok_per_sec", 0.0),
            "avg_call_latency_sec": spd.get("avg_call_latency_sec", 0.0),
            "tokens_per_1pct_drop": int(tok_per_1pct),
            "eff_tokens_per_1pct_drop": int(eff_per_1pct),
            "legacy_units_per_1pct_drop": int(leg_per_1pct),
            "implied_100pct_5h_ceiling_raw_tokens": implied_5h_ceiling_raw,
            "implied_100pct_5h_ceiling_eff_tokens": implied_5h_ceiling_eff,
            "implied_100pct_5h_ceiling_legacy_units": implied_5h_ceiling_legacy,
            "configured_weight": CONFIGURED_WEIGHTS.get(p.get("model", ""), 1.0),
        }

    for k, entry in by_phase.items():
        pool = entry.get("pool", "gemini")
        base_eff = gemini_base_eff_per_pct if pool == "gemini" else tp_base_eff_per_pct
        base_leg = gemini_base_leg_per_pct if pool == "gemini" else tp_base_leg_per_pct

        if base_eff and entry["eff_tokens_per_1pct_drop"] > 0:
            entry["empirical_server_token_weight"] = round(
                base_eff / float(entry["eff_tokens_per_1pct_drop"]), 3
            )
        else:
            entry["empirical_server_token_weight"] = None

        if base_leg and entry["legacy_units_per_1pct_drop"] > 0:
            entry["empirical_legacy_content_weight"] = round(
                base_leg / float(entry["legacy_units_per_1pct_drop"]), 3
            )
        else:
            entry["empirical_legacy_content_weight"] = None

    io_solution: dict[str, Any] = {}
    p_in = by_phase.get("phase5_argon_medium_fresh_input")
    p_out = by_phase.get("phase6_argon_medium_heavy_output")
    if p_in and p_out and p_in["pct_drop_5h"] > 0 and p_out["pct_drop_5h"] > 0:
        i1, o1, d1 = float(p_in["in_tokens"]), float(p_in["out_tokens"]), float(p_in["pct_drop_5h"])
        i2, o2, d2 = float(p_out["in_tokens"]), float(p_out["out_tokens"]), float(p_out["pct_drop_5h"])
        det = i1 * o2 - i2 * o1
        if abs(det) > 1e-6:
            alpha = (d1 * o2 - d2 * o1) / det
            gamma = (i1 * d2 - i2 * d1) / det
            if alpha > 0 and gamma > 0:
                io_solution = {
                    "pct_drop_per_1M_input_tokens": round(alpha * 1_000_000.0, 4),
                    "pct_drop_per_1M_output_tokens": round(gamma * 1_000_000.0, 4),
                    "output_to_input_burn_ratio": round(gamma / alpha, 3),
                    "pure_input_5h_ceiling_tokens": int(100.0 / alpha),
                    "pure_output_5h_ceiling_tokens": int(100.0 / gamma),
                }

    return {
        "by_phase": by_phase,
        "argon_medium_input_vs_output_regression": io_solution,
    }


def write_markdown_report(state: dict[str, Any]) -> None:
    """Write a comprehensive Markdown report (`BENCHMARK_REPORT.md`) with Quota + Tok/s Speed tables."""
    summary = state.get("empirical_summary", {})
    by_phase = summary.get("by_phase", {})
    io_reg = summary.get("argon_medium_input_vs_output_regression", {})

    lines = [
        "# Antigravity Live Monitor — Empirical Quota & Token Speed (`tok/s`) Benchmark Report",
        "",
        f"- **Started At**: `{state.get('started_at')}`",
        f"- **Triggered At**: `{state.get('benchmark_triggered_at')}`",
        f"- **Completed At**: `{state.get('completed_at')}`",
        f"- **Status**: `{state.get('status')}`",
        "",
        "## 1. Per-Model & Per-Effort Quota Ceiling & Weight Measurements",
        "",
        "| Pool | Phase | Model | Effort | Mode | 5h Drop | Wk Drop | Fresh Input | Output+Think | Tokens / 1% Drop | Implied 100% 5h Pool | Configured `w` | Empirical `w` |",
        "| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for phase_key, d in by_phase.items():
        emp_w = f"{d['empirical_server_token_weight']}x" if d.get("empirical_server_token_weight") else "N/A"
        lines.append(
            f"| `{d.get('pool')}` | `{phase_key}` | **{d.get('model')}** | `{d.get('effort')}` | `{d.get('mode')}` | "
            f"**-{d.get('pct_drop_5h')}%** | -{d.get('pct_drop_weekly')}% | "
            f"{d.get('in_tokens'):,} | {d.get('out_tokens'):,} | **{d.get('eff_tokens_per_1pct_drop'):,}** | "
            f"**{d.get('implied_100pct_5h_ceiling_eff_tokens'):,}** | `{d.get('configured_weight')}x` | **{emp_w}** |"
        )

    lines.extend(
        [
            "",
            "## 2. Per-Model & Per-Effort Generation Speed (`tok/s`) & Latency Benchmark",
            "",
            "| Pool | Model | Effort | Mode | Steps | Avg Output Tok/Step | Median Output Speed (`tok/s`) | Peak Output Speed (`tok/s`) | E2E Speed (`tok/s`) | Input Prefill Speed (`tok/s`) | Avg Call Latency (`s`) |",
            "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for phase_key, d in by_phase.items():
        lines.append(
            f"| `{d.get('pool')}` | **{d.get('model')}** | `{d.get('effort')}` | `{d.get('mode')}` | "
            f"{d.get('steps')} | {d.get('avg_out_tokens_per_step'):,} | "
            f"**{d.get('median_out_tok_per_sec')} tok/s** | **{d.get('max_out_tok_per_sec')} tok/s** | "
            f"{d.get('median_e2e_out_tok_per_sec')} tok/s | {d.get('median_in_tok_per_sec'):,} tok/s | "
            f"{d.get('avg_call_latency_sec')}s |"
        )

    if io_reg:
        lines.extend(
            [
                "",
                "## 3. Gemini 4 Argon (Medium) — Input vs. Output/Thinking Token Weight Regression",
                "",
                f"- **Quota Burn per 1M Fresh Input Tokens**: `{io_reg.get('pct_drop_per_1M_input_tokens')}%`",
                f"- **Quota Burn per 1M Output + Thinking Tokens**: `{io_reg.get('pct_drop_per_1M_output_tokens')}%`",
                f"- **Empirical Output-to-Input Burn Multiplier ($\\gamma / \\alpha$)**: **`{io_reg.get('output_to_input_burn_ratio')}x`**",
                f"- **Implied 100% 5-Hour Pure Input Ceiling**: `{io_reg.get('pure_input_5h_ceiling_tokens'):,}` tokens",
                f"- **Implied 100% 5-Hour Pure Output Ceiling**: `{io_reg.get('pure_output_5h_ceiling_tokens'):,}` tokens",
            ]
        )

    try:
        REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def save_results(state: dict[str, Any]) -> None:
    try:
        if state.get("phases"):
            state["empirical_summary"] = compute_empirical_summary(state["phases"])
            write_markdown_report(state)
        RESULTS_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def run_parallel_batch(
    model: str,
    effort: str,
    mode: str,
    phase_tag: str,
    workers: int,
    call_timings: dict[str, float],
    input_words: int = 22000,
    output_pad_words: int = 4000,
) -> int:
    """Run `workers` concurrent headless `agy.exe` calls and record exact wall-clock timings per call."""
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for _ in range(workers):
            c_nonce = f"CALL_{uuid.uuid4().hex[:10]}"
            prompt = (
                make_synthetic_input_prompt(phase_tag, c_nonce, word_count=input_words)
                if mode == "input"
                else make_heavy_output_prompt(phase_tag, c_nonce, extra_input_words=output_pad_words)
            )
            futures.append(pool.submit(run_agy_prompt, prompt, model, effort, c_nonce, 85))
        for fut in as_completed(futures):
            try:
                ok, c_nonce, w_sec = fut.result()
                call_timings[c_nonce] = w_sec
                if ok:
                    completed += 1
            except Exception:
                pass
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini & Third-Party Quota + Speed Benchmark Runner")
    parser.add_argument(
        "--wait-until-mins",
        type=float,
        default=16.0,
        help="Wait until <= N minutes remain in the 5-hour Gemini window before starting (default: 16.0)",
    )
    parser.add_argument(
        "--tp-max-5h-drop",
        type=int,
        default=28,
        help="Maximum total 5-hour %% to spend on the Third-Party pool across all TP phases (default: 28%%)",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Start benchmarking immediately without waiting",
    )
    args = parser.parse_args()

    state: dict[str, Any] = {
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "wait_until_mins": 0.0 if args.now else args.wait_until_mins,
        "tp_max_5h_drop": args.tp_max_5h_drop,
        "status": "waiting_for_window",
        "phases": [],
    }
    save_results(state)

    target_rem_secs = 0.0 if args.now else (args.wait_until_mins * 60.0)
    initial_reset_iso: str | None = None

    while True:
        try:
            u = query_usage()
        except Exception as exc:
            state["last_error"] = str(exc)
            save_results(state)
            time.sleep(25.0)
            continue

        rem_secs = u.get("gemini_5h_rem_secs", 999999.0)
        pct_rem = u.get("gemini_5h_pct", 0)
        initial_reset_iso = u.get("gemini_5h_reset_iso")
        state["last_usage_check"] = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "gemini_5h_pct": pct_rem,
            "gemini_weekly_pct": u.get("gemini_weekly_pct"),
            "tp_5h_pct": u.get("tp_5h_pct"),
            "tp_weekly_pct": u.get("tp_weekly_pct"),
            "rem_mins": round(rem_secs / 60.0, 2),
            "reset_iso": initial_reset_iso,
        }
        save_results(state)

        if args.now or rem_secs <= target_rem_secs:
            break

        sleep_s = 12.0 if rem_secs <= target_rem_secs + 240 else 30.0
        time.sleep(sleep_s)

    state["status"] = "running_gemini_benchmark"
    state["benchmark_triggered_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_results(state)

    # PART A: 7 Gemini Model & Effort Phases (executed first before the expiring 5h Gemini window resets!)
    gemini_phases = [
        ("phase1_flash_low", "gemini", "Gemini 3.8 Flash (Low)", "low", "output", 2, 4, 4),
        ("phase2_flash_medium", "gemini", "Gemini 3.8 Flash (Medium)", "medium", "output", 2, 4, 4),
        ("phase3_flash_high_baseline", "gemini", "Gemini 3.8 Flash (High)", "high", "output", 3, 4, 5),
        ("phase4_argon_low", "gemini", "Gemini 4 Argon (Low)", "low", "output", 4, 4, 5),
        ("phase5_argon_medium_fresh_input", "gemini", "Gemini 4 Argon (Medium)", "medium", "input", 5, 4, 6),
        ("phase6_argon_medium_heavy_output", "gemini", "Gemini 4 Argon (Medium)", "medium", "output", 5, 4, 6),
        ("phase7_argon_high_max_drain", "gemini", "Gemini 4 Argon (High)", "high", "output", 999, 6, 25),
    ]

    for phase_id, pool, model_name, effort_flag, mode, target_drop, workers, max_batches in gemini_phases:
        try:
            u_before = query_usage()
        except Exception:
            continue

        if (
            u_before.get("gemini_5h_pct", 0) <= 0
            or u_before.get("gemini_5h_rem_secs", 0) <= 10.0
            or (initial_reset_iso and u_before.get("gemini_5h_reset_iso") != initial_reset_iso)
        ):
            break

        phase_tag = f"BENCH_{phase_id}_{uuid.uuid4().hex[:6]}"
        phase_start_ts = time.time()
        batches_run = 0
        calls_completed = 0
        call_timings: dict[str, float] = {}
        u_after = u_before

        while batches_run < max_batches:
            batches_run += 1
            calls_completed += run_parallel_batch(
                model_name, effort_flag, mode, phase_tag, workers, call_timings
            )
            try:
                u_after = query_usage()
            except Exception:
                break

            cur_drop = int(u_before.get("gemini_5h_pct", 0)) - int(u_after.get("gemini_5h_pct", 0))
            if (
                cur_drop >= target_drop
                or u_after.get("gemini_5h_pct", 0) <= 0
                or u_after.get("gemini_5h_rem_secs", 0) <= 10.0
                or (initial_reset_iso and u_after.get("gemini_5h_reset_iso") != initial_reset_iso)
            ):
                break

        tok_delta = get_transcript_snapshot(
            phase_start_ts, phase_tag=phase_tag, call_timings=call_timings
        )
        pct_drop_5h = int(u_before.get("gemini_5h_pct", 0)) - int(u_after.get("gemini_5h_pct", 0))
        pct_drop_weekly = int(u_before.get("gemini_weekly_pct", 0)) - int(
            u_after.get("gemini_weekly_pct", 0)
        )

        state["phases"].append(
            {
                "phase": phase_id,
                "pool": pool,
                "phase_tag": phase_tag,
                "model": model_name,
                "effort": effort_flag,
                "mode": mode,
                "workers": workers,
                "batches": batches_run,
                "calls_completed": calls_completed,
                "pct_5h_before": u_before.get("gemini_5h_pct"),
                "pct_5h_after": u_after.get("gemini_5h_pct"),
                "pct_drop_5h": pct_drop_5h,
                "pct_weekly_before": u_before.get("gemini_weekly_pct"),
                "pct_weekly_after": u_after.get("gemini_weekly_pct"),
                "pct_drop_weekly": pct_drop_weekly,
                "tokens": tok_delta,
                "rem_secs_after": round(u_after.get("gemini_5h_rem_secs", 0.0), 1),
            }
        )
        save_results(state)

    # PART B: Surgical Third-Party (Claude & GPT) Shared Pool Calibration + Speed Benchmark
    state["status"] = "running_third_party_benchmark"
    save_results(state)

    tp_phases = [
        ("tp1_gpt_oss_120b_medium", "tp", "GPT-OSS 120B (Medium)", "medium", "output", 2, 2, 3),
        ("tp2_claude_sonnet_55_low", "tp", "Claude Sonnet 5.5 (Low)", "low", "output", 2, 2, 3),
        ("tp3_claude_sonnet_55_medium_baseline", "tp", "Claude Sonnet 5.5 (Medium)", "medium", "output", 3, 2, 3),
        ("tp4_claude_sonnet_55_high", "tp", "Claude Sonnet 5.5 (High)", "high", "output", 3, 2, 3),
        ("tp5_claude_opus_55_low", "tp", "Claude Opus 5.5 (Low)", "low", "output", 3, 1, 2),
        ("tp6_claude_opus_55_medium", "tp", "Claude Opus 5.5 (Medium)", "medium", "output", 4, 1, 2),
        ("tp7_claude_opus_55_high", "tp", "Claude Opus 5.5 (High)", "high", "output", 4, 1, 2),
    ]

    try:
        u_tp_initial = query_usage()
        tp_start_5h_pct = int(u_tp_initial.get("tp_5h_pct", 100))
    except Exception:
        tp_start_5h_pct = 100

    for phase_id, pool, model_name, effort_flag, mode, target_drop, workers, max_batches in tp_phases:
        try:
            u_before = query_usage()
        except Exception:
            continue

        cur_tp_5h = int(u_before.get("tp_5h_pct", 0))
        total_tp_spent = tp_start_5h_pct - cur_tp_5h
        if cur_tp_5h <= 50 or total_tp_spent >= args.tp_max_5h_drop:
            break

        phase_tag = f"BENCH_{phase_id}_{uuid.uuid4().hex[:6]}"
        phase_start_ts = time.time()
        batches_run = 0
        calls_completed = 0
        call_timings = {}
        u_after = u_before

        while batches_run < max_batches:
            batches_run += 1
            calls_completed += run_parallel_batch(
                model_name,
                effort_flag,
                mode,
                phase_tag,
                workers,
                call_timings,
                input_words=8000,
                output_pad_words=1500,
            )
            try:
                u_after = query_usage()
            except Exception:
                break

            cur_drop = int(u_before.get("tp_5h_pct", 0)) - int(u_after.get("tp_5h_pct", 0))
            if (
                cur_drop >= target_drop
                or int(u_after.get("tp_5h_pct", 0)) <= 50
                or (tp_start_5h_pct - int(u_after.get("tp_5h_pct", 0))) >= args.tp_max_5h_drop
            ):
                break

        tok_delta = get_transcript_snapshot(
            phase_start_ts, phase_tag=phase_tag, call_timings=call_timings
        )
        pct_drop_5h = int(u_before.get("tp_5h_pct", 0)) - int(u_after.get("tp_5h_pct", 0))
        pct_drop_weekly = int(u_before.get("tp_weekly_pct", 0)) - int(
            u_after.get("tp_weekly_pct", 0)
        )

        state["phases"].append(
            {
                "phase": phase_id,
                "pool": pool,
                "phase_tag": phase_tag,
                "model": model_name,
                "effort": effort_flag,
                "mode": mode,
                "workers": workers,
                "batches": batches_run,
                "calls_completed": calls_completed,
                "pct_5h_before": u_before.get("tp_5h_pct"),
                "pct_5h_after": u_after.get("tp_5h_pct"),
                "pct_drop_5h": pct_drop_5h,
                "pct_weekly_before": u_before.get("tp_weekly_pct"),
                "pct_weekly_after": u_after.get("tp_weekly_pct"),
                "pct_drop_weekly": pct_drop_weekly,
                "tokens": tok_delta,
                "rem_secs_after": round(u_after.get("tp_5h_rem_secs", 0.0), 1),
            }
        )
        save_results(state)

    state["status"] = "completed"
    state["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_results(state)


if __name__ == "__main__":
    main()
