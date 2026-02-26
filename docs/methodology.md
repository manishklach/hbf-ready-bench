# Methodology (v1)

This repo benchmarks LLM inference behavior under different "tier" conditions, starting with WSL + CPU llama.cpp.

## Metrics (v1)
- `prompt_eval_ms`, `prompt_tok_per_s` (from llama.cpp timing summary)
- `gen_eval_ms`, `gen_tok_per_s` (from llama.cpp timing summary)
- `ttft_est_ms` (estimated): `prompt_eval_ms + gen_ms_per_token` (first generated token)
  - Note: llama.cpp may not emit true TTFT; this estimate is consistent and comparable across runs.

## Run modes
- `warm`: run once to warm caches (discard), then measure (or use `--repeat 2` and take run 2).
- `cold`: for WSL, approximate by restarting WSL between runs:
  - In PowerShell: `wsl --shutdown`
  - Then relaunch Ubuntu and run again.
- `direct`: placeholder label for future (O_DIRECT/bypass-cache style tests).

## Storage location
For consistent IO, keep model files under Linux filesystem: `~/models/`
Avoid `/mnt/c/...` for benchmarking.

## Reproducibility
Record:
- system fingerprint (`results/system_info.json`)
- exact command line used (captured in run JSON)
- model name + quant
- threads used
