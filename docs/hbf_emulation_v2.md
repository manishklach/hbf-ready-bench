# HBF Emulation V2

These additions emulate *HBF-like tier constraints* without real HBF hardware.

## A) Weight-tier emulation (model staging)

We emulate a constrained tier by copying a GGUF model through `emulation/tier_copy.py` with:
- bandwidth cap (MB/s)
- per-chunk added latency (ms)
- chunk size (MB)

Then we run `llama-bench` on the staged model and record:
- staging time (seconds)
- effective staging throughput (MB/s)
- `pp` and `tg` tokens/sec from `llama-bench`

### Run a sweep

```bash
./harness/sweep_hbf_weight_tier.py \
  --model ~/models/qwen2.5-3b-instruct-q4_k_m.gguf \
  --staged_dir ~/models_staged \
  --mbps_list 250,500,1000,2000,4000 \
  --lat_ms_list 0,0.05,0.2 \
  -t 8 -p 256 -n 256 \
  --mode hbf-emu \
  --out_dir results/hbf_weight_tier \
  --csv_out results/hbf_weight_tier.csv
```

Interpretation:
- If staging dominates end-to-end latency, the tier BW/lat targets need to be higher.
- If `tg` is stable but staging is slow, the tier may still be viable if prefetch/hiding is possible.

## B) KV spill simulator (decode ceiling)

`emulation/kv_spill_sim.py` converts an assumed KV spill volume per token into a theoretical max decode throughput
given tier BW and per-op latency.

Example:

```bash
python3 emulation/kv_spill_sim.py \
  --kv_kb_per_token 256 \
  --tier_mbps_list 500,1000,2000,4000,8000 \
  --op_lat_ms 0.05 \
  --ops_per_token 2
```

This turns qualitative claims ("between HBM and SSD") into quantitative requirement curves.

## Next steps
- Add plots for sweep CSVs.
- Calibrate KV bytes/token from model config.
- Add concurrency/batching and jitter/QoS models.
