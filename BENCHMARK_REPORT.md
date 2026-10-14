# Antigravity Live Monitor — Empirical Quota & Token Speed (`tok/s`) Benchmark Report

- **Started At**: `2026-10-14T03:08:12.780599+00:00`
- **Completed At**: `2026-10-14T03:34:26.042768+00:00`
- **Status**: `completed`

---

## 1. Per-Model & Per-Effort Quota Ceiling & Weight Measurements

| Pool | Phase / Source | Model | Effort | Mode | 5h Drop | Wk Drop | Fresh Input | Output+Think | Eff. Tokens / 1% Drop | Implied 100% 5h Pool | Configured `w` | Empirical `w` |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini` | `phase1_flash_low` | **Gemini 3.8 Flash (Low)** | `low` | `output` | **-2%** | -1% | 349,152 | 203,863 | **279,568** | **27,956,850** | `0.50x` | **0.45x** |
| `gemini` | `phase2_flash_medium` | **Gemini 3.8 Flash (Medium)** | `medium` | `output` | **-2%** | -0% | 126,432 | 99,943 | **116,248** | **11,624,850** | `0.75x` | **1.00x** |
| `gemini` | `quota_history (39%->49%)` | **Gemini 4 Argon (Med/High)** | `med/high` | `mixed` | **-10%** | -3% | 1,278,517 *(raw)* | +28.89M *(cache)* | **416,796** *(127.8k fresh+out)* | **12.79M raw / 41.68M eff** | `2.5x–3.5x` | **2.0x–2.6x** |
| `tp` | `tp1_gpt_oss_120b_medium` | **GPT-OSS 120B (Medium)** | `medium` | `output` | **-0%** | -0% | 124,531 | 19,310 | **> 146,260** | **> 20,000,000** | `0.40x` | **<= 0.20x** |
| `tp` | `tp2_claude_sonnet_55_low` | **Claude Sonnet 5.5 (Low)** | `low` | `output` | **-4%** | -2% | 132,924 | 10,611 | **35,883** | **3,588,375** | `0.80x` | **1.00x–1.16x** |
| `tp` | `tp3_claude_sonnet_55_medium` | **Claude Sonnet 5.5 (Medium)** | `medium` | `output` | **-5%** | -2% | 179,210 | 22,844 | **41,791** | **4,179,160** | `1.00x` | **1.00x (Base)** |
| `tp` | `tp4_claude_sonnet_55_high` | **Claude Sonnet 5.5 (High)** | `high` | `output` | **-3%** | -2% | 79,003 | 16,652 | **33,265** | **3,326,566** | `1.50x` | **1.256x** |
| `tp` | `tp5_claude_opus_55_low` | **Claude Opus 5.5 (Low)** | `low` | `output` | **-4%** | -2% | 80,106 | 8,539 | **22,161** | **2,216,125** | `3.00x` | **1.886x** |
| `tp` | `tp6_claude_opus_55_medium` | **Claude Opus 5.5 (Medium)** | `medium` | `output` | **-5%** | -2% | 66,890 | 12,677 | **16,189** | **1,618,940** | `4.00x` | **2.581x** |
| `tp` | `tp7_claude_opus_55_high` | **Claude Opus 5.5 (High)** | `high` | `output` | **-5%** | -3% | 69,379 | 14,288 | **17,009** | **1,700,940** | `5.00x` | **2.457x** |

---

## 2. Per-Model & Per-Effort Generation Speed (`tok/s`) & Latency Benchmark

| Pool | Model | Effort | Mode | Steps | Avg Output Tok/Step | Median Output Speed (`tok/s`) | Peak Output Speed (`tok/s`) | E2E Speed (`tok/s`) | Input Prefill Speed (`tok/s`) | Avg Call Latency (`s`) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini` | **Gemini 3.8 Flash (Low)** | `low` | `output` | 13 | 15,681 | **231.0 tok/s** | **247.0 tok/s** | 223.6 tok/s | 469.9 tok/s | 71.07s |
| `gemini` | **Gemini 3.8 Flash (Medium)** | `medium` | `output` | 6 | 16,657 | **222.8 tok/s** | **236.7 tok/s** | 216.9 tok/s | 259.4 tok/s | 76.87s |
| `gemini` | **Gemini 4 Argon (High)** | `high` | `transcripts` | 75 | 367 | **138.0 tok/s** | **430.0 tok/s** | — | — | — |
| `gemini` | **Gemini 4 Argon (Medium)** | `medium` | `transcripts` | 97 | 1,548 | **127.0 tok/s** | **420.5 tok/s** | — | — | — |
| `tp` | **GPT-OSS 120B (Medium)** | `medium` | `output` | 6 | 3,218 | **105.8 tok/s** | **114.2 tok/s** | 98.6 tok/s | 734.9 tok/s | 32.49s |
| `tp` | **Claude Sonnet 5.5 (Low)** | `low` | `output` | 3 | 3,537 | **101.3 tok/s** | **102.0 tok/s** | 95.5 tok/s | 1,240.7 tok/s | 37.21s |
| `tp` | **Claude Sonnet 5.5 (Medium)** | `medium` | `output` | 6 | 3,807 | **103.7 tok/s** | **121.2 tok/s** | 97.4 tok/s | 768.0 tok/s | 37.55s |
| `tp` | **Claude Sonnet 5.5 (High)** | `high` | `output` | 3 | 5,550 | **109.5 tok/s** | **110.3 tok/s** | 105.6 tok/s | 476.8 tok/s | 54.22s |
| `tp` | **Claude Opus 5.5 (Low)** | `low` | `output` | 2 | 4,269 | **93.6 tok/s** | **94.7 tok/s** | 89.2 tok/s | 886.0 tok/s | 47.89s |
| `tp` | **Claude Opus 5.5 (Medium)** | `medium` | `output` | 2 | 6,338 | **98.6 tok/s** | **99.2 tok/s** | 95.3 tok/s | 525.1 tok/s | 66.49s |
| `tp` | **Claude Opus 5.5 (High)** | `high` | `output` | 2 | 7,144 | **100.3 tok/s** | **102.0 tok/s** | 97.3 tok/s | 480.3 tok/s | 73.49s |

---

## 3. Structural Pool Architecture Findings

1. **Third-Party Shared Pool (`Claude` & `GPT-OSS`) Weekly-to-5h Ratio is Exactly `2.0x`**:
   - Across all 7 Third-Party benchmark phases, total 5-hour quota dropped **`-26%`** (`100% -> 74%`) while Weekly quota dropped **`-13%`** (`100% -> 87%`).
   - That proves the **entire Weekly Third-Party limit is only `2.0x` a single 5-hour Third-Party window** (~`8.36M` effective tokens on `Claude Sonnet 5.5 (Medium)` or ~`3.3M` effective tokens on `Claude Opus 5.5 (Medium/High)` for the entire week).
2. **Gemini Pool Weekly-to-5h Ratio is `~3.33x`**:
   - Across `10%` of 5-hour Argon burn (`39% -> 49%`), Weekly quota dropped `3%` (`2% -> 5%`), confirming the Gemini Weekly pool is `~3.33x` a single 5-hour Gemini window.
3. **Thinking / Effort Multiplier Effect**:
   - On `Gemini 3.8 Flash`, moving from `Low` (`0` thinking) to `Medium` (reasoning enabled) increased quota burn per call by **`2.40x`** (`279.6k` eff tokens/1% $\rightarrow$ `116.2k` eff tokens/1%).
   - On `Claude Sonnet 5.5`, moving from `Medium` (`0` thinking) to `High` (`7.2k` thinking chars) increased burn weight by **`1.26x`** (`41.8k` $\rightarrow$ `33.3k` eff tokens/1%).
   - On `Claude Opus 5.5`, `Medium` and `High` both burn at **`~2.5x`** the rate of `Claude Sonnet 5.5 (Medium)` (`~16.2k–17.0k` eff tokens per `1%` drop, or **`~1.62M–1.70M` effective tokens for a 100% 5-hour window**), while `Claude Opus 5.5 (Low)` burns at **`1.89x`** (`~2.22M` effective tokens for a 100% 5h window).
   - **`GPT-OSS 120B (Medium)`** is virtually free on the Third-Party pool (`146,260` tokens burned `0%` of 5h and `0%` of Weekly quota, weight `<= 0.20x`).
