#!/usr/bin/env python3
import argparse
import csv
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TPS_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:±\s*([0-9]+(?:\.[0-9]+)?))?\s*$")

def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout)
    return p.stdout

def parse_rows(out: str) -> List[Dict[str, str]]:
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
            "test": parts[5],   # ppXXX or tgXXX
            "tps": parts[6],    # "26.74 ± 3.32"
        })
    return parsed

def extract_mean_std(tps_str: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    if not tps_str:
        return None, None
    m = TPS_RE.match(tps_str.strip())
    if not m:
        return None, None
    mean = float(m.group(1))
    std = float(m.group(2)) if m.group(2) is not None else None
    return mean, std

def pick_pp_tg(rows: List[Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    pp = next((r["tps"] for r in rows if r.get("test","").startswith("pp")), None)
    tg = next((r["tps"] for r in rows if r.get("test","").startswith("tg")), None)
    return pp, tg

def main():
    ap = argparse.ArgumentParser(description="Sweep llama-bench across prompt/gen token grid and write JSON + CSV.")
    ap.add_argument("--llama_bench", default=str(Path.home() / "work" / "llama.cpp" / "build" / "bin" / "llama-bench"))
    ap.add_argument("--model", required=True)
    ap.add_argument("-t", "--threads", type=int, default=8)
    ap.add_argument("--mode", default="warm")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out_dir", default="results/sweep", help="Directory for per-run JSON files")
    ap.add_argument("--csv_out", default="results/bench_sweep.csv", help="CSV summary output path")
    ap.add_argument("--p_list", default="64,128,256", help="Comma-separated prompt token sizes")
    ap.add_argument("--n_list", default="64,128,256", help="Comma-separated gen token sizes")
    ap.add_argument("--repeats", type=int, default=1, help="Repeat each grid point and report all rows in CSV")
    args = ap.parse_args()

    bench = Path(args.llama_bench).expanduser()
    model = Path(args.model).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    csv_out = Path(args.csv_out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out.parent.mkdir(parents=True, exist_ok=True)

    if not bench.exists():
        raise SystemExit(f"llama-bench not found: {bench}")
    if not model.exists():
        raise SystemExit(f"model not found: {model}")

    p_vals = [int(x.strip()) for x in args.p_list.split(",") if x.strip()]
    n_vals = [int(x.strip()) for x in args.n_list.split(",") if x.strip()]

    # CSV header
    fieldnames = [
        "timestamp_unix","mode","tag","model_path","threads","p","n","repeat",
        "pp_tps","pp_mean","pp_std","tg_tps","tg_mean","tg_std",
        "json_path"
    ]

    with csv_out.open("w", newline="", encoding="utf-8") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=fieldnames)
        w.writeheader()

        for p in p_vals:
            for n in n_vals:
                for r_i in range(1, args.repeats + 1):
                    cmd = [
                        str(bench),
                        "-m", str(model),
                        "-t", str(args.threads),
                        "-p", str(p),
                        "-n", str(n),
                    ]
                    print(f"\n=== sweep p={p} n={n} repeat={r_i}/{args.repeats} ===")
                    start = time.time()
                    out = run(cmd)
                    wall_ms = (time.time() - start) * 1000.0

                    rows = parse_rows(out)
                    pp_tps, tg_tps = pick_pp_tg(rows)
                    pp_mean, pp_std = extract_mean_std(pp_tps)
                    tg_mean, tg_std = extract_mean_std(tg_tps)

                    artifact = {
                        "schema": "hbf-ready-bench.llama-bench.v1",
                        "timestamp_unix": int(time.time()),
                        "mode": args.mode,
                        "tag": args.tag,
                        "cmd": cmd,
                        "wall_time_ms": wall_ms,
                        "model_path": str(model),
                        "threads": args.threads,
                        "prompt_tokens": p,
                        "gen_tokens": n,
                        "pp_tps": pp_tps,
                        "tg_tps": tg_tps,
                        "rows": rows,
                        "output_tail": "\n".join(out.strip().splitlines()[-80:]),
                    }

                    json_path = out_dir / f"bench_p{p}_n{n}_r{r_i}.json"
                    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

                    w.writerow({
                        "timestamp_unix": artifact["timestamp_unix"],
                        "mode": args.mode,
                        "tag": args.tag,
                        "model_path": str(model),
                        "threads": args.threads,
                        "p": p,
                        "n": n,
                        "repeat": r_i,
                        "pp_tps": pp_tps,
                        "pp_mean": pp_mean,
                        "pp_std": pp_std,
                        "tg_tps": tg_tps,
                        "tg_mean": tg_mean,
                        "tg_std": tg_std,
                        "json_path": str(json_path),
                    })

    print(f"\nWrote CSV: {csv_out}")
    print(f"Wrote per-run JSONs under: {out_dir}")

if __name__ == "__main__":
    main()
