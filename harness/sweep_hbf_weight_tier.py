#!/usr/bin/env python3
"""
sweep_hbf_weight_tier.py

V2: "Weight-tier" (HBF-like) emulation by staging the model through a throttled copy, then
running llama-bench on the staged model.

This is not real HBF hardware. It produces *workload-driven requirement curves*:
- Given an effective tier bandwidth (MB/s) and per-chunk latency (ms),
  what is the staging time and what are pp/tg throughput numbers?

Outputs:
- Per-point JSON artifacts under --out_dir
- One CSV summary at --csv_out

Example:
./harness/sweep_hbf_weight_tier.py \
  --model ~/models/qwen2.5-3b-instruct-q4_k_m.gguf \
  --staged_dir ~/models_staged \
  --mbps_list 250,500,1000,2000,4000 \
  --lat_ms_list 0,0.05,0.2 \
  -t 8 -p 256 -n 256 \
  --mode hbf-emu \
  --out_dir results/hbf_weight_tier \
  --csv_out results/hbf_weight_tier.csv
"""
import argparse
import csv
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

def run_capture(cmd: List[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout)
    return p.stdout

def parse_tier_copy(out: str) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    for ln in out.splitlines():
        if "=" in ln:
            k, v = ln.strip().split("=", 1)
            try:
                if "." in v:
                    d[k] = float(v)
                else:
                    d[k] = int(v)
            except:
                d[k] = v
    return d

def parse_llama_bench_rows(out: str) -> List[Dict[str, str]]:
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    rows = [ln for ln in lines if ln.startswith("|") and ln.endswith("|")]
    if len(rows) < 3:
        return []
    data_rows = rows[2:]
    parsed = []
    for r in data_rows:
        parts = [p.strip() for p in r.strip("|").split("|")]
        if len(parts) < 7:
            continue
        parsed.append({
            "model": parts[0],
            "size": parts[1],
            "params": parts[2],
            "backend": parts[3],
            "threads": parts[4],
            "test": parts[5],
            "tps": parts[6],
        })
    return parsed

def pick_pp_tg(rows: List[Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    pp = next((r["tps"] for r in rows if r.get("test","").startswith("pp")), None)
    tg = next((r["tps"] for r in rows if r.get("test","").startswith("tg")), None)
    return pp, tg

def main():
    ap = argparse.ArgumentParser(description="Sweep HBF-like weight-tier constraints (tier copy + llama-bench).")
    ap.add_argument("--tier_copy", default=str(Path.home() / "work" / "hbf-ready-bench" / "emulation" / "tier_copy.py"),
                    help="Path to emulation/tier_copy.py in your repo.")
    ap.add_argument("--llama_bench", default=str(Path.home() / "work" / "llama.cpp" / "build" / "bin" / "llama-bench"))
    ap.add_argument("--model", required=True)
    ap.add_argument("--staged_dir", required=True)
    ap.add_argument("--mbps_list", default="250,500,1000,2000,4000")
    ap.add_argument("--lat_ms_list", default="0,0.05,0.2")
    ap.add_argument("--chunk_mb", type=float, default=4.0)
    ap.add_argument("-t", "--threads", type=int, default=8)
    ap.add_argument("-p", "--prompt_tokens", type=int, default=256)
    ap.add_argument("-n", "--gen_tokens", type=int, default=256)
    ap.add_argument("--mode", default="hbf-emu")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out_dir", default="results/hbf_weight_tier")
    ap.add_argument("--csv_out", default="results/hbf_weight_tier.csv")
    ap.add_argument("--repeats", type=int, default=1)
    args = ap.parse_args()

    tier_copy = Path(args.tier_copy).expanduser()
    llama_bench = Path(args.llama_bench).expanduser()
    model = Path(args.model).expanduser()
    staged_dir = Path(args.staged_dir).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    csv_out = Path(args.csv_out).expanduser()

    if not tier_copy.exists():
        raise SystemExit(f"tier_copy.py not found: {tier_copy}")
    if not llama_bench.exists():
        raise SystemExit(f"llama-bench not found: {llama_bench}")
    if not model.exists():
        raise SystemExit(f"model not found: {model}")

    staged_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out.parent.mkdir(parents=True, exist_ok=True)

    mbps_vals = [float(x.strip()) for x in args.mbps_list.split(",") if x.strip()]
    lat_vals = [float(x.strip()) for x in args.lat_ms_list.split(",") if x.strip()]

    fieldnames = [
        "timestamp_unix","mode","tag","model","threads","p","n","repeat",
        "tier_mbps","tier_lat_ms","tier_chunk_mb","stage_seconds","stage_effective_mbps",
        "pp_tps","tg_tps","json_path"
    ]

    with csv_out.open("w", newline="", encoding="utf-8") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=fieldnames)
        w.writeheader()

        for mbps in mbps_vals:
            for lat_ms in lat_vals:
                staged_path = staged_dir / f"{model.name}.staged_mbps{mbps:g}_lat{lat_ms:g}_chunk{args.chunk_mb:g}.gguf"

                print(f"\n=== STAGE mbps={mbps:g} lat_ms={lat_ms:g} chunk_mb={args.chunk_mb:g} ===")
                stage_cmd = [
                    "python3", str(tier_copy),
                    "--src", str(model),
                    "--dst", str(staged_path),
                    "--mbps", str(mbps),
                    "--chunk_mb", str(args.chunk_mb),
                    "--lat_ms", str(lat_ms),
                ]
                t0 = time.time()
                stage_out = run_capture(stage_cmd)
                stage_wall = time.time() - t0
                stage_parsed = parse_tier_copy(stage_out)
                stage_eff = stage_parsed.get("effective_MBps")

                for r_i in range(1, args.repeats + 1):
                    print(f"--- BENCH repeat {r_i}/{args.repeats} ---")
                    bench_cmd = [
                        str(llama_bench),
                        "-m", str(staged_path),
                        "-t", str(args.threads),
                        "-p", str(args.prompt_tokens),
                        "-n", str(args.gen_tokens),
                    ]
                    b0 = time.time()
                    bench_out = run_capture(bench_cmd)
                    bench_wall = time.time() - b0

                    rows = parse_llama_bench_rows(bench_out)
                    pp_tps, tg_tps = pick_pp_tg(rows)

                    artifact = {
                        "schema": "hbf-ready-bench.hbf-weight-tier.v1",
                        "timestamp_unix": int(time.time()),
                        "mode": args.mode,
                        "tag": args.tag,
                        "model": str(model),
                        "staged_model": str(staged_path),
                        "threads": args.threads,
                        "prompt_tokens": args.prompt_tokens,
                        "gen_tokens": args.gen_tokens,
                        "tier": {"mbps": mbps, "lat_ms": lat_ms, "chunk_mb": args.chunk_mb},
                        "stage": {"cmd": stage_cmd, "wall_seconds": stage_wall, "parsed": stage_parsed, "stdout": stage_out},
                        "bench": {"cmd": bench_cmd, "wall_seconds": bench_wall, "rows": rows, "pp_tps": pp_tps, "tg_tps": tg_tps},
                        "output_tail": "\n".join((stage_out + "\n" + bench_out).strip().splitlines()[-120:]),
                    }

                    json_path = out_dir / f"weight_tier_mbps{mbps:g}_lat{lat_ms:g}_p{args.prompt_tokens}_n{args.gen_tokens}_r{r_i}.json"
                    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

                    w.writerow({
                        "timestamp_unix": artifact["timestamp_unix"],
                        "mode": args.mode,
                        "tag": args.tag,
                        "model": str(model),
                        "threads": args.threads,
                        "p": args.prompt_tokens,
                        "n": args.gen_tokens,
                        "repeat": r_i,
                        "tier_mbps": mbps,
                        "tier_lat_ms": lat_ms,
                        "tier_chunk_mb": args.chunk_mb,
                        "stage_seconds": stage_parsed.get("duration_s", stage_wall),
                        "stage_effective_mbps": stage_eff,
                        "pp_tps": pp_tps,
                        "tg_tps": tg_tps,
                        "json_path": str(json_path),
                    })

    print(f"\nWrote CSV: {csv_out}")
    print(f"Wrote per-point JSONs: {out_dir}")
    print(f"Staged models in: {staged_dir}")

if __name__ == "__main__":
    main()
