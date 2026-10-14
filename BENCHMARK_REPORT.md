# Antigravity Live Monitor — Empirical Quota, Token, Dollar & Speed (`tok/s`) Benchmark Report

- **Started At**: `2026-10-14T03:08:12.780599+00:00`
- **Completed At**: `2026-10-14T03:34:26.042768+00:00`
- **Calibration Version**: `v3.0 (Ground-Truth De-Duplicated against quota_history.json)`
- **Interactive Dashboard**: [`benchmark_dashboard.html`](file:///C:/Users/baran/antigravity-live-monitor/benchmark_dashboard.html)

---

## 1. Per-Model & Per-Effort Quota Ceiling & Weight Measurements (`1.00x = Gemini 3.8 Flash High`)

| Pool | Model | Effort | De-Duplicated Weight (`w`) | Legacy Units / `1%` 5h | 100% 5h Legacy Cap | 100% Weekly Legacy Cap | 100% Weekly Raw API Tokens (`In+Out`) | Weekly Realistic API Value (`$`) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini` | **Gemini 3.8 Flash (Low)** | `low` | **`0.45x`** | `19,157` | `1,915,700` | **`17,964,200`** | **`195.11M`** | **`$98.80`** |
| `gemini` | **Gemini 3.8 Flash (Medium)** | `medium` | **`0.87x`** | `9,909` | `990,880` | **`9,291,800`** | **`100.92M`** | **`$73.59`** |
| `gemini` | **Gemini 3.8 Flash (High)** | `high` | **`1.00x` (Base)** | `8,621` | `862,066` | **`8,083,900`** | **`87.80M`** | **`$96.04`** |
| `gemini` | **Gemini 4 Argon (Low)** | `low` | **`1.05x`** | `8,210` | `821,015` | **`7,698,950`** | **`83.62M`** | **`$150.90`** |
| `gemini` | **Gemini 4 Argon (Medium)** | `medium` | **`1.34x`** | `6,435` | `643,500` | **`6,032,760`** | **`65.52M`** | **`$157.64`** |
| `gemini` | **Gemini 4 Argon (High)** | `high` | **`1.70x`** | `5,071` | `507,098` | **`4,755,235`** | **`51.65M`** | **`$200.72`** |
| `tp` | **GPT-OSS 120B (Medium)** | `medium` | **`<= 0.20x`** | `12,750` | `1,275,000` | **`2,550,000`** | **`> 40.00M`** | **`$31.62`** |
| `tp` | **Claude Sonnet 5.5 (Low)** | `low` | **`1.00x`** | `2,550` | `255,000` | **`510,000`** | **`7.18M`** | **`$24.74`** |
| `tp` | **Claude Sonnet 5.5 (Medium)** | `medium` | **`1.00x` (TP Base)** | `2,550` | `255,000` | **`510,000`** | **`8.36M`** | **`$24.74`** |
| `tp` | **Claude Sonnet 5.5 (High)** | `high` | **`1.25x`** | `2,040` | `204,000` | **`408,000`** | **`6.65M`** | **`$19.79`** |
| `tp` | **Claude Opus 5.5 (Low)** | `low` | **`1.90x`** | `1,342` | `134,210` | **`268,420`** | **`4.43M`** | **`$65.09`** |
| `tp` | **Claude Opus 5.5 (Medium)** | `medium` | **`2.50x`** | `1,020` | `102,000` | **`204,000`** | **`3.24M`** | **`$49.47`** |
| `tp` | **Claude Opus 5.5 (High)** | `high` | **`2.50x`** | `1,020` | `102,000` | **`204,000`** | **`3.40M`** | **`$49.47`** |

---

## 2. Per-Model & Per-Effort Generation Speed (`tok/s`) & Latency Benchmark

| Pool | Model | Effort | Mode | Steps | Avg Output Tok/Step | Median Output Speed (`tok/s`) | Peak Output Speed (`tok/s`) | E2E Speed (`tok/s`) | Input Prefill Speed (`tok/s`) | Avg Call Latency (`s`) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini` | **Gemini 3.8 Flash (Low)** | `low` | `output` | 13 | 15,681 | **231.0 tok/s** | **247.0 tok/s** | 155.8 tok/s | 469.9 tok/s | 10.6s |
| `gemini` | **Gemini 3.8 Flash (Medium)** | `medium` | `output` | 6 | 16,657 | **222.8 tok/s** | **236.7 tok/s** | 132.5 tok/s | 259.4 tok/s | 9.5s |
| `gemini` | **Gemini 3.8 Flash (High)** | `high` | `transcripts` | 59,695 | 235 | **218.0 tok/s** | **234.0 tok/s** | 128.0 tok/s | — | 10.2s |
| `gemini` | **Gemini 4 Argon (High)** | `high` | `transcripts` | 75 | 367 | **138.0 tok/s** | **430.0 tok/s** | 91.2 tok/s | — | 15.1s |
| `gemini` | **Gemini 4 Argon (Medium)** | `medium` | `transcripts` | 97 | 1,548 | **127.0 tok/s** | **420.5 tok/s** | 88.4 tok/s | — | 14.2s |
| `tp` | **GPT-OSS 120B (Medium)** | `medium` | `output` | 6 | 3,218 | **105.8 tok/s** | **114.2 tok/s** | 56.1 tok/s | 734.9 tok/s | 12.9s |
| `tp` | **Claude Sonnet 5.5 (Low)** | `low` | `output` | 3 | 3,537 | **101.3 tok/s** | **102.0 tok/s** | 57.6 tok/s | 1,240.7 tok/s | 14.3s |
| `tp` | **Claude Sonnet 5.5 (Medium)** | `medium` | `output` | 6 | 3,807 | **103.7 tok/s** | **121.2 tok/s** | 54.6 tok/s | 768.0 tok/s | 14.1s |
| `tp` | **Claude Sonnet 5.5 (High)** | `high` | `output` | 3 | 5,550 | **109.5 tok/s** | **110.3 tok/s** | 64.9 tok/s | 476.8 tok/s | 13.5s |
| `tp` | **Claude Opus 5.5 (Low)** | `low` | `output` | 2 | 4,269 | **93.6 tok/s** | **94.7 tok/s** | 52.8 tok/s | 886.0 tok/s | 17.2s |
| `tp` | **Claude Opus 5.5 (Medium)** | `medium` | `output` | 2 | 6,338 | **98.6 tok/s** | **99.2 tok/s** | 47.2 tok/s | 525.1 tok/s | 14.8s |
| `tp` | **Claude Opus 5.5 (High)** | `high` | `output` | 2 | 7,144 | **100.3 tok/s** | **102.0 tok/s** | 52.2 tok/s | 480.3 tok/s | 16.0s |

---

## 3. Last 4 Weeks Historical Counterfactual (`Gemini 3.8 Flash High` vs. `Gemini 4 Argon`)

| Weekly Cohort | Agentic Steps | Unweighted Legacy Units (`Raw API Eq.`) | **Actual: 100% `Flash High`** (`8.08M` Wk Cap) | **If 100% `Argon Low`** (`1.05x` = `7.70M` Cap) | **If 100% `Argon Medium`** (`1.34x` = `6.03M` Cap) | **If 100% `Argon High`** (`1.70x` = `4.75M` Cap) | API Dollar Value (`Flash High` $\rightarrow$ `Argon Med` $\rightarrow$ `Argon High`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Week 4 (21–28d ago)** | `9,424` | **`2.10M` leg** (`22.8M` API) | **`25.9%` / wk** *(OK)* | **`27.2%` / wk** *(OK)* | **`34.8%` / wk** *(OK)* | **`44.1%` / wk** *(OK)* | **`$24.90`** $\rightarrow$ **`$54.80`** $\rightarrow$ **`$88.50`** |
| **Week 3 (14–21d ago)** | `12,415` | **`3.08M` leg** (`33.5M` API) | **`38.1%` / wk** *(OK)* | **`40.0%` / wk** *(OK)* | **`51.1%` / wk** *(OK)* | **`64.8%` / wk** *(OK)* | **`$36.60`** $\rightarrow$ **`$80.50`** $\rightarrow$ **`$130.10`** |
| **Week 2 (7–14d ago)** | `15,099` | **`3.45M` leg** (`37.5M` API) | **`42.7%` / wk** *(OK)* | **`44.8%` / wk** *(OK)* | **`57.2%` / wk** *(OK)* | **`72.5%` / wk** *(OK)* | **`$41.00`** $\rightarrow$ **`$90.10`** $\rightarrow$ **`$145.60`** |
| **Week 1 (0–7d ago)** | `22,757` | **`5.38M` leg** (`58.4M` API) | **`66.5%` / wk** *(OK)* | **`69.8%` / wk** *(OK)* | **`89.1%` / wk** *(OK)* | **`113.1%` / wk** *(6.2d)* | **`$63.90`** $\rightarrow$ **`$140.50`** $\rightarrow$ **`$226.90`** |
| **4-Week Cumulative** | **`59,695`** | **`14.01M` leg** (`152.1M` API) | **`43.3%` / wk avg** (`1.73` pools) | **`45.5%` / wk avg** (`1.82` pools) | **`58.0%` / wk avg** (`2.32` pools) | **`73.6%` / wk avg** (`2.95` pools) | **`$166.40`** $\rightarrow$ **`$365.90`** $\rightarrow$ **`$591.10`** |

---

## 4. Structural Pool Architecture Findings

1. **Gemini Pool Weekly-to-5h Ratio is `9.38x`**:
   - Simultaneous `samples_5h` (`862,066` legacy units cap) and `samples_weekly` (`8,083,900` legacy units cap) in `quota_history.json` confirm the Weekly Gemini pool is **`9.38x`** a single 5-hour Gemini window.
2. **De-Duplicated `Gemini 4 Argon` Burn Multiplier (`1.34x` Medium / `1.70x` High vs. `Flash High`)**:
   - After removing the `2.0x` pre-multiplier that `hud.pyw` had applied to `used` in `quota_history.json`, `Gemini 4 Argon (Medium)` consumed `6,435` unweighted legacy units per `1%` 5h drop compared to `8,620` on `Gemini 3.8 Flash (High)`—an empirical burn ratio of **`1.34x`**.
3. **Third-Party Shared Pool (`Claude` & `GPT-OSS`) Weekly-to-5h Ratio is `2.00x`**:
   - Across all 7 Third-Party benchmark phases, total 5-hour quota dropped **`-26%`** (`100% -> 74%`) while Weekly quota dropped **`-13%`** (`100% -> 87%`).
