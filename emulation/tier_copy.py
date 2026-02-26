#!/usr/bin/env python3
import argparse, time, os
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--mbps", type=float, required=True, help="Throttle rate in MB/s (decimal MB).")
    ap.add_argument("--chunk_mb", type=float, default=4.0, help="Chunk size in MB.")
    ap.add_argument("--lat_ms", type=float, default=0.0, help="Extra sleep per chunk (ms).")
    args = ap.parse_args()

    src = Path(args.src).expanduser()
    dst = Path(args.dst).expanduser()
    dst.parent.mkdir(parents=True, exist_ok=True)

    chunk = int(args.chunk_mb * 1024 * 1024)
    target_bps = args.mbps * 1_000_000.0
    lat_s = args.lat_ms / 1000.0

    start = time.time()
    total = 0

    with src.open("rb") as fsrc, dst.open("wb") as fdst:
        while True:
            t0 = time.time()
            buf = fsrc.read(chunk)
            if not buf:
                break
            fdst.write(buf)
            total += len(buf)

            # throttle: ensure each chunk takes at least len(buf)/target_bps seconds
            need = len(buf) / target_bps
            spent = time.time() - t0
            sleep_s = max(0.0, need - spent) + lat_s
            if sleep_s > 0:
                time.sleep(sleep_s)

    dur = time.time() - start
    gb = total / 1e9
    eff = (total / 1e6) / dur  # MB/s

    print(f"copied_bytes={total}")
    print(f"duration_s={dur:.3f}")
    print(f"size_GB={gb:.3f}")
    print(f"effective_MBps={eff:.2f}")

if __name__ == "__main__":
    main()
