# hbf-ready-bench

Reproducible LLM inference benchmarks (prefill vs decode throughput) to inform requirements for an intermediate memory tier (**HBF-class**) between **HBM** and **SSD**.

This repo uses **llama.cpp’s `llama-bench`** because it prints stable, machine-parseable throughput:
- **ppXXX** = *prefill / prompt processing* tokens/sec
- **tgXXX** = *decode / token generation* tokens/sec

You can run sweeps over prompt length (p) and generation length (n) to build a performance surface and later re-run under “tier constraints” (bandwidth/latency/QoS emulation).

---

## Tested environment

- Windows 11 + **WSL2 Ubuntu**
- `llama.cpp` built from source
- Model: **Qwen2.5-3B-Instruct GGUF (Q4_K_M)** (good for 16GB RAM)
- Benchmark: `llama-bench` with `pp` and `tg` throughput

> Tip: Keep model files in the Linux filesystem (`~/models/`), not under `/mnt/c/...`, for consistent performance.

---

## 0) Repo layout (what’s in here)
Typical files:
- `harness/run_llama_bench.py` — run one benchmark and write JSON
- `harness/sweep_llama_bench.py` — run a grid sweep (p×n) and write CSV + JSONs
- `harness/system_info.py` — capture system/WSL context into `results/system_info.json`

V2 (HBF emulation additions):
- `emulation/tier_copy.py` — **you added this**; throttled “tier” copy with BW cap + per-chunk latency
- `harness/sweep_hbf_weight_tier.py` — stage model via `tier_copy.py` at different constraints, then run `llama-bench`
- `emulation/kv_spill_sim.py` — compute decode ceiling vs tier BW/lat for assumed KV spill volume
- `docs/hbf_emulation_v2.md` — interpretation and examples

> Note: V2 emulates HBF-like tier constraints without real HBF hardware. It produces requirement curves.

---

## 1) Install WSL2 Ubuntu (Windows)

In **PowerShell (Admin)**:

```powershell
wsl --install -d Ubuntu-24.04
```

Reboot if prompted.

Launch Ubuntu:

```powershell
wsl -d Ubuntu-24.04
```

---

## 2) Install dependencies (inside Ubuntu / WSL)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git build-essential cmake python3 python3-venv python3-pip wget unzip
mkdir -p ~/work ~/models
```

---

## 3) Build llama.cpp (inside Ubuntu / WSL)

```bash
cd ~/work
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build -j 2
```

Verify:

```bash
ls -la build/bin | grep llama-bench
```

### If the build gets killed (“Terminated”)
Rebuild with fewer parallel jobs:

```bash
cmake --build build -j 1
```

---

## 4) Download Qwen GGUF model (recommended baseline)

For a 16GB machine, start with:

**Qwen2.5-3B-Instruct GGUF → Q4_K_M**

Download into Linux FS:

```bash
cd ~/models
wget -O qwen2.5-3b-instruct-q4_k_m.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
```

Confirm size:

```bash
ls -lh ~/models/qwen2.5-3b-instruct-q4_k_m.gguf
```

### Alternate: download on Windows and copy into WSL
If it’s in Windows Downloads:

```bash
cp /mnt/c/Users/<WIN_USERNAME>/Downloads/qwen2.5-3b-instruct-q4_k_m.gguf ~/models/
```

To print your Windows username from WSL:

```bash
cmd.exe /c echo %USERNAME%
```

---

## 5) Set up this repo’s Python environment

From this repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x harness/*.py
```

(Optional) capture machine context:

```bash
./harness/system_info.py
cat results/system_info.json | head
```

---

## 6) Run a single benchmark (pp/tg throughput)

### A) Run `llama-bench` directly

```bash
~/work/llama.cpp/build/bin/llama-bench \
  -m ~/models/qwen2.5-3b-instruct-q4_k_m.gguf \
  -t 8 \
  -p 256 \
  -n 256
```

You will see two rows at the end:
- `pp256` (prefill t/s)
- `tg256` (decode t/s)

### B) Run via the repo harness (writes JSON)

```bash
./harness/run_llama_bench.py \
  --model ~/models/qwen2.5-3b-instruct-q4_k_m.gguf \
  -t 8 -p 256 -n 256 \
  --mode warm \
  --out results/bench_p256_n256.json
```

Inspect:

```bash
python3 - <<'PY'
import json
d=json.load(open("results/bench_p256_n256.json"))
print("pp_tps:", d.get("pp_tps"))
print("tg_tps:", d.get("tg_tps"))
print("rows:", [(r.get("test"), r.get("tps")) for r in d.get("rows", [])])
PY
```

---

## 7) Run a BOTH sweep (prompt × generation grid)

Example grid: p ∈ {64,128,256} and n ∈ {64,128,256}

```bash
./harness/sweep_llama_bench.py \
  --model ~/models/qwen2.5-3b-instruct-q4_k_m.gguf \
  -t 8 \
  --mode warm \
  --p_list 64,128,256 \
  --n_list 64,128,256 \
  --repeats 1 \
  --out_dir results/sweep \
  --csv_out results/bench_sweep.csv
```

Inspect:

```bash
head -n 5 results/bench_sweep.csv
tail -n 5 results/bench_sweep.csv
ls results/sweep | head
```

Outputs:
- `results/bench_sweep.csv` (summary)
- `results/sweep/*.json` (one JSON per grid point)

---

## 8) Warm vs Cold sweeps (WSL “cold-ish” protocol)

Why: cold runs approximate “first-touch / not-cached” behavior and are useful for tier-sensitivity.

### Cold protocol
1) From PowerShell (Windows):

```powershell
wsl --shutdown
```

2) Relaunch Ubuntu:

```powershell
wsl -d Ubuntu-24.04
```

3) Run the same sweep labeled cold:

```bash
cd ~/work/hbf-ready-bench
source .venv/bin/activate

./harness/sweep_llama_bench.py \
  --model ~/models/qwen2.5-3b-instruct-q4_k_m.gguf \
  -t 8 \
  --mode cold \
  --p_list 64,128,256 \
  --n_list 64,128,256 \
  --repeats 3 \
  --out_dir results/sweep_cold \
  --csv_out results/bench_sweep_cold.csv
```

Now you can compare warm vs cold surfaces and quantify % drops in `pp` vs `tg`.

---

## 9) How this relates to HBF (why this repo is useful)

HBF is positioned as a memory tier between HBM and SSD. Standards discussions need **workload-driven targets**:
- How much throughput (and stability/QoS) is required so **decode (tg)** doesn’t collapse?
- How much bandwidth is needed so **prefill (pp)** stays within X% of baseline?

This repo provides:
- A reproducible baseline surface (`pp` and `tg` over p/n)
- A harness that can be re-run under “tier constraints” (bandwidth/latency/QoS emulation) to produce degradation curves
- CSV/JSON artifacts that can be used in OCP-style discussions or future compliance tests

**V1 goal:** baseline + sweep + warm/cold surfaces  
**V2 goal:** add explicit “tier constraint” emulation and plot/report deltas

---

---

# V2: HBF-like tier emulation (weight-tier + KV spill)

HBF is positioned as a memory tier between HBM and SSD. To make this concrete without HBF hardware, V2 adds tools that emulate a constrained tier and generate *workload-driven requirement curves*.

## V2-A) Weight-tier emulation (staged model through constrained tier)

This models a “weights live in a tier” workflow:
1) Stage (copy) the model through a **bandwidth/latency constrained** path (`emulation/tier_copy.py`)
2) Run `llama-bench` on the staged model
3) Record:
   - staging time / effective MB/s
   - `pp` (prefill) and `tg` (decode) tokens/sec

### 1) Create a staged directory
```bash
mkdir -p ~/models_staged
```

### 2) Run a sweep over tier constraints
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

Outputs:
- `results/hbf_weight_tier.csv` (summary)
- `results/hbf_weight_tier/*.json` (per-point artifacts)
- staged models under `~/models_staged/`

**Interpretation:** if staging dominates end-to-end latency, the tier BW/lat targets need to be higher, or the system must prefetch/hide staging.

## V2-B) KV spill decode ceiling simulator

Decode throughput is often the first to collapse when a tier has poor latency/jitter. This simulator turns “KV spill to tier” into a quantitative ceiling:

```bash
python3 emulation/kv_spill_sim.py \
  --kv_kb_per_token 256 \
  --tier_mbps_list 500,1000,2000,4000,8000 \
  --op_lat_ms 0.05 \
  --ops_per_token 2
```

This prints `tier_mbps,tg_tps_max`, a conservative “decode cap” imposed by BW+latency assumptions.

See `docs/hbf_emulation_v2.md` for more details.


## 10) Troubleshooting

### `llama-bench` exists but takes time
Large p/n tests on CPU can take a while. Start with `-p 64 -n 64` as a smoke test.

### Build gets killed (“Terminated”)
- Use fewer parallel jobs: `cmake --build build -j 1`
- Ensure WSL has enough memory/swap.

### WSL reports less memory than the machine has
WSL may auto-limit memory. Increase via:
`C:\Users\<YOU>\.wslconfig`

```ini
[wsl2]
memory=12GB
swap=8GB
processors=8
```

Then:

```powershell
wsl --shutdown
```

Relaunch and confirm:

```bash
free -h
```

---

## License
If you plan to share widely, pick a license (MIT/Apache-2.0) and add `LICENSE`.
