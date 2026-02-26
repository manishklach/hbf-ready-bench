# Findings V1 (Warm vs “Cold” WSL Restart Runs)

## Summary

This file summarizes **V1 baseline results** from `llama-bench` on:

- **CPU:** AMD Ryzen 3 5300U (WSL2 reports 8 CPUs)
- **Threads:** 8
- **Model:** Qwen2.5-3B-Instruct (GGUF) Q4_K_M (~1.95 GiB)
- **Workload metric:** `llama-bench` throughput:
  - **pp** = prefill/prompt processing tokens/sec
  - **tg** = decode/token generation tokens/sec

You ran:
- A **warm** sweep with **1 run per (p,n)** point (9 points total).
- A **“cold”** sweep with **3 repeats per (p,n)** point, where “cold” is *post-WSL-restart* (`wsl --shutdown`), not necessarily “worse caching.”

**Key takeaway:** In this environment, the post-WSL-restart (“cold”) runs were often **faster** than the earlier warm baseline for p ≥ 128. This indicates the benchmark is sensitive to **system state** (background load, thermal/power behavior, WSL resource allocation). That sensitivity is itself relevant for HBF-style tier discussions because it highlights the need for **QoS and repeatability**.

---

## Warm baseline (1× per point)

| p | n | pp_mean | tg_mean |
| --- | --- | --- | --- |
| 64.00 | 64.00 | 20.21 | 4.95 |
| 64.00 | 128.00 | 22.81 | 8.37 |
| 64.00 | 256.00 | 27.35 | 8.15 |
| 128.00 | 64.00 | 25.31 | 7.39 |
| 128.00 | 128.00 | 23.88 | 6.71 |
| 128.00 | 256.00 | 23.14 | 7.81 |
| 256.00 | 64.00 | 25.54 | 8.60 |
| 256.00 | 128.00 | 25.89 | 10.42 |
| 256.00 | 256.00 | 28.59 | 7.47 |

---

## Post-WSL-restart (“cold”) summary (median across 3 repeats)

For each (p,n) grid point, we report:
- `pp_median`, `tg_median` across the 3 repeats
- min/max to show run-to-run spread

| p | n | repeats | pp_median | tg_median | pp_min | pp_max | tg_min | tg_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 64.00 | 64.00 | 3.00 | 18.26 | 5.36 | 12.05 | 23.04 | 3.93 | 5.41 |
| 64.00 | 128.00 | 3.00 | 17.46 | 3.94 | 16.80 | 23.61 | 2.95 | 7.19 |
| 64.00 | 256.00 | 3.00 | 26.04 | 5.23 | 25.75 | 32.16 | 4.70 | 5.92 |
| 128.00 | 64.00 | 3.00 | 38.72 | 12.62 | 37.00 | 40.21 | 11.10 | 12.98 |
| 128.00 | 128.00 | 3.00 | 34.72 | 11.39 | 30.00 | 41.86 | 8.38 | 11.61 |
| 128.00 | 256.00 | 3.00 | 39.37 | 11.79 | 37.99 | 41.36 | 11.74 | 11.94 |
| 256.00 | 64.00 | 3.00 | 40.86 | 12.14 | 39.37 | 40.93 | 11.67 | 12.31 |
| 256.00 | 128.00 | 3.00 | 40.60 | 11.87 | 40.43 | 40.80 | 11.82 | 11.95 |
| 256.00 | 256.00 | 3.00 | 39.55 | 12.05 | 38.78 | 40.40 | 11.96 | 12.19 |

---

## Warm vs Post-WSL-restart comparison

Because warm has only **one run per point**, treat the deltas below as **indicative**, not definitive.  
(Recommended next step: re-run warm with `--repeats 3`.)

| p | n | pp_warm | pp_median | pp_delta_pct | tg_warm | tg_median | tg_delta_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 64.00 | 64.00 | 20.21 | 18.26 | -9.65 | 4.95 | 5.36 | 8.28 |
| 64.00 | 128.00 | 22.81 | 17.46 | -23.45 | 8.37 | 3.94 | -52.93 |
| 64.00 | 256.00 | 27.35 | 26.04 | -4.79 | 8.15 | 5.23 | -35.83 |
| 128.00 | 64.00 | 25.31 | 38.72 | 52.98 | 7.39 | 12.62 | 70.77 |
| 128.00 | 128.00 | 23.88 | 34.72 | 45.39 | 6.71 | 11.39 | 69.75 |
| 128.00 | 256.00 | 23.14 | 39.37 | 70.14 | 7.81 | 11.79 | 50.96 |
| 256.00 | 64.00 | 25.54 | 40.86 | 59.98 | 8.60 | 12.14 | 41.16 |
| 256.00 | 128.00 | 25.89 | 40.60 | 56.82 | 10.42 | 11.87 | 13.92 |
| 256.00 | 256.00 | 28.59 | 39.55 | 38.34 | 7.47 | 12.05 | 61.31 |

**Observations:**
- For **p=64**, decode (`tg`) is low and noisy in both sweeps; several points show large variance.
- For **p≥128**, post-restart throughput is consistently higher:
  - `pp` often rises into the ~**37–41 t/s** range
  - `tg` often rises into the ~**11–12 t/s** range

---

## Why this matters for HBF

HBF is intended to be a tier between HBM and SSD for inference-critical data (weights/KV/cache spill). Standards discussions need workload-driven targets such as:

- “To keep **decode** (`tg`) within X% of baseline, the tier must sustain Y throughput and meet tail-latency/QoS constraints.”
- “Prefill (`pp`) is more bandwidth-like; decode is more QoS/latency sensitive.”

This repo’s value is that it produces:
1) **A reproducible baseline surface** (pp/tg over prompt/gen sizes), and  
2) A harness that can be re-run under explicit **tier constraints** (V2) to produce **degradation curves**.

---

## Recommendations for V1 cleanup (quick)

1) Re-run warm with repeats:
```bash
./harness/sweep_llama_bench.py \
  --model ~/models/qwen2.5-3b-instruct-q4_k_m.gguf \
  -t 8 --mode warm \
  --p_list 64,128,256 --n_list 64,128,256 \
  --repeats 3 \
  --out_dir results/sweep_warm_r3 \
  --csv_out results/bench_sweep_warm_r3.csv
```

2) Capture run conditions in notes (plugged in, Windows power mode, background apps).

3) For HBF relevance (V2), add explicit tier-constraint emulation and re-run the sweep to quantify pp/tg degradation vs constraint parameters.

---

## Raw inputs used

- Warm CSV: `results/bench_sweep.csv`
- Cold CSV: `results/bench_sweep_cold.csv`
- Per-point JSON artifacts: `results/sweep/` and `results/sweep_cold/`
