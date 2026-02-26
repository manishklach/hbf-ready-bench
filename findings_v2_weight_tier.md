# Findings V2 — HBF Emulation: Weight-Tier Sweep (staged model)

## What this experiment measures

We emulate a constrained “weight tier” (HBF-like) by **staging** the GGUF model through `emulation/tier_copy.py` with:
- requested bandwidth cap (`tier_mbps`, decimal MB/s)
- extra latency per chunk (`tier_lat_ms`, applied once per 4MB chunk)
- chunk size: 4MB

Then we run `llama-bench` on the staged model and record:
- **stage_seconds** and **stage_effective_mbps**
- **pp256** (prefill) and **tg256** (decode) throughput

This produces a workload-driven curve connecting tier properties to end-to-end “first-run” weight staging costs.

## Environment

- Model: `qwen2.5-3b-instruct-q4_k_m.gguf` (~1.95 GiB)
- Threads: 8
- Bench: `llama-bench -p 256 -n 256`
- CSV: `results/hbf_weight_tier_v2.csv`
- Repeats: 3 per (tier_mbps, tier_lat_ms) point

## High-level takeaways

- **Staging dominates first-run latency** under low effective bandwidth: median stage time ranged from **9.5s** (fastest point) up to **32.4s** (slowest point).
- Effective staging throughput **saturates** on this setup: observed max `stage_effective_mbps` was ~**220.6 MB/s** (decimal), which is far below the higher requested caps (1000–2000 MB/s). Interpret tier effects using **effective** MB/s, not the requested cap.
- `pp/tg` throughput varies with system state (CPU scheduling/boost/background load). For tier requirements, treat `pp/tg` as secondary here and focus first on **staging time vs effective MB/s**; then stabilize `pp/tg` with more controlled conditions if needed.

## Median summary table (per tier point)

Columns:
- `stage_seconds_median`: median staging time across repeats
- `stage_eff_median`: median effective MB/s observed during staging
- `pp_median` / `tg_median`: median of parsed pp/tg means from the `xx ± yy` strings
- min/max stage seconds included for spread

| tier_mbps | tier_lat_ms | repeats | stage_seconds_median | stage_eff_median | pp_median | tg_median | stage_seconds_min | stage_seconds_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 250 | 0 | 3 | 9.54 | 220.59 | 34.02 | 7.73 | 9.54 | 9.54 |
| 250 | 1 | 3 | 24.86 | 84.67 | 37.32 | 8.04 | 24.86 | 24.86 |
| 250 | 5 | 3 | 31.36 | 67.12 | 37.04 | 8.06 | 31.36 | 31.36 |
| 500 | 0 | 3 | 32.39 | 64.99 | 36.09 | 11.07 | 32.39 | 32.39 |
| 500 | 1 | 3 | 15.16 | 138.86 | 39.38 | 8.74 | 15.16 | 15.16 |
| 500 | 5 | 3 | 22.00 | 95.68 | 36.53 | 8.72 | 22.00 | 22.00 |
| 1000 | 0 | 3 | 20.65 | 101.93 | 27.27 | 8.00 | 20.65 | 20.65 |
| 1000 | 1 | 3 | 22.34 | 94.21 | 25.90 | 8.45 | 22.34 | 22.34 |
| 1000 | 5 | 3 | 14.45 | 145.68 | 25.79 | 8.46 | 14.45 | 14.45 |
| 2000 | 0 | 3 | 18.55 | 113.45 | 24.43 | 6.42 | 18.55 | 18.55 |
| 2000 | 1 | 3 | 28.00 | 75.17 | 40.74 | 8.86 | 28.00 | 28.00 |
| 2000 | 5 | 3 | 20.33 | 103.54 | 37.64 | 8.56 | 20.33 | 20.33 |

## Notable points (medians)

- Fastest staging point: requested `250 MB/s`, `lat=0 ms` → **9.5s** @ **220.6 MB/s**
- Slowest staging point: requested `500 MB/s`, `lat=0 ms` → **32.4s** @ **65.0 MB/s**
- Highest `tg` median: `500 MB/s`, `lat=0 ms` → **tg≈11.07 tok/s**
- Lowest `tg` median: `2000 MB/s`, `lat=0 ms` → **tg≈6.42 tok/s**

## Interpretation in HBF terms

### Weight-tier story (TTFT / first-run latency)

This experiment approximates the “weights reside in a mid-tier” cost as **model staging time**. If weights must be fetched/staged at request time, the tier must deliver enough **effective bandwidth** (and sufficiently low per-access overhead) so staging does not dominate user-visible latency.

A practical next metric to report is:
- `total_first_run_seconds = stage_seconds + bench_wall_seconds`

(bench wall time isn’t in the current CSV; add it in the harness or compute from JSON.)

### Decode sensitivity (tg)

Once the model is staged locally, decode throughput (`tg`) is dominated by compute/system state. To derive HBF requirements for **decode-critical spills** (e.g., KV spilling to tier), use the KV spill simulator (`emulation/kv_spill_sim.py`) to compute a **decode ceiling** as a function of tier BW/latency/jitter.

## Recommended follow-ups (V2.1)

1) Add `bench_wall_seconds` to CSV so we can compute **end-to-end first-run** latency.
2) Run the same sweep under controlled conditions (plugged-in, best-performance power mode) to reduce `pp/tg` variance.
3) Calibrate KV bytes/token for Qwen2.5-3B and run `kv_spill_sim.py` sweeps to produce decode requirement curves.

---
## Raw inputs
- `results/hbf_weight_tier_v2.csv`
- `results/hbf_weight_tier_v2/*.json`
