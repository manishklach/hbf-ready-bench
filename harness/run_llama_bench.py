#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise SystemExit(p.stdout)
    return p.stdout

def parse_rows(out: str) -> List[Dict[str, Any]]:
    """
    Parses llama-bench markdown-like table rows into dicts.
    Returns list of data rows (usually two: ppXXX and tgXXX).
    """
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    rows = [ln for ln in lines if ln.startswith("|") and ln.endswith("|")]

    if len(rows) < 3:
        return []

    # rows[0] header, rows[1] separator, rows[2:] data
    data_rows = rows[2:]
    parsed: List[Dict[str, Any]] = []

    for r in data_rows:
        parts = [p.strip() for p in r.strip("|").split("|")]
        # expected 7 columns
        if len(parts) < 7:
            continue
        parsed.append({
            "model": parts[0],
            "size": parts[1],
            "params": parts[2],
            "backend": parts[3],
            "threads": int(parts[4]) if parts[4].isdigit() else parts[4],
            "test": parts[5],   # e.g., pp256 or tg256
            "tps": parts[6],    # e.g., "27.78 ± 0.58"
        })
    return parsed

def pick_tg_pp(rows: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    pp = next((r["tps"] for r in rows if str(r.get("test","")).startswith("pp")), None)
    tg = next((r["tps"] for r in rows if str(r.get("test","")).startswith("tg")), None)
    return {"pp_tps": pp, "tg_tps": tg}

def main():
    ap = argparse.ArgumentParser(description="Run llama-bench and write a JSON artifact.")
    ap.add_argument("--llama_bench", default=str(Path.home() / "work" / "llama.cpp" / "build" / "bin" / "llama-bench"))
    ap.add_argument("--model", required=True)
    ap.add_argument("-t", "--threads", type=int, default=8)
    ap.add_argument("-p", "--prompt_tokens", type=int, default=256)
    ap.add_argument("-n", "--gen_tokens", type=int, default=256)
    ap.add_argument("--mode", default="warm")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    bench = Path(args.llama_bench).expanduser()
    model = Path(args.model).expanduser()
    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not bench.exists():
        raise SystemExit(f"llama-bench not found: {bench}")
    if not model.exists():
        raise SystemExit(f"model not found: {model}")

    cmd = [
        str(bench),
        "-m", str(model),
        "-t", str(args.threads),
        "-p", str(args.prompt_tokens),
        "-n", str(args.gen_tokens),
    ]

    start = time.time()
    out = run(cmd)
    wall_ms = (time.time() - start) * 1000.0

    rows = parse_rows(out)
    tps = pick_tg_pp(rows)

    artifact = {
        "schema": "hbf-ready-bench.llama-bench.v1",
        "timestamp_unix": int(time.time()),
        "mode": args.mode,
        "tag": args.tag,
        "cmd": " ".join(shlex.quote(x) for x in cmd),
        "wall_time_ms": wall_ms,
        "model_path": str(model),
        "prompt_tokens": args.prompt_tokens,
        "gen_tokens": args.gen_tokens,
        "pp_tps": tps["pp_tps"],
        "tg_tps": tps["tg_tps"],
        "rows": rows,
        "output_tail": "\n".join(out.strip().splitlines()[-80:]),
    }

    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"Wrote: {out_path}")
    print(f"pp_tps={artifact['pp_tps']}  tg_tps={artifact['tg_tps']}")

if __name__ == "__main__":
    main()
