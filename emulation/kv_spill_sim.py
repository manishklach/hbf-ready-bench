#!/usr/bin/env python3
"""
kv_spill_sim.py

V2: Simple KV-cache spill requirement simulator for "HBF-like" tiers.

Purpose:
- Translate an assumed KV spill volume per generated token into a *decode throughput ceiling*
  given a tier bandwidth and per-operation latency.
- Helps answer: "If KV must spill to a mid-tier, how fast must that tier be so tg doesn't collapse?"

This is a model-agnostic first-order calculator; it's intentionally simple.

Usage:
python3 emulation/kv_spill_sim.py --kv_kb_per_token 256 --tier_mbps_list 500,1000,2000,4000,8000 --op_lat_ms 0.05 --ops_per_token 2
"""
import argparse
from typing import List

def ceiling_tg_tps(kv_kb_per_token: float, tier_mbps: float, op_lat_ms: float, ops_per_token: float) -> float:
    bytes_per_token = kv_kb_per_token * 1000.0
    bw_bytes_per_s = tier_mbps * 1_000_000.0
    io_time_s = bytes_per_token / bw_bytes_per_s
    lat_time_s = (ops_per_token * op_lat_ms) / 1000.0
    per_token_s = io_time_s + lat_time_s
    return float("inf") if per_token_s <= 0 else 1.0 / per_token_s

def main():
    ap = argparse.ArgumentParser(description="KV spill decode ceiling simulator for HBF-like tiers.")
    ap.add_argument("--kv_kb_per_token", type=float, default=256.0)
    ap.add_argument("--tier_mbps", type=float, default=None)
    ap.add_argument("--tier_mbps_list", default=None)
    ap.add_argument("--op_lat_ms", type=float, default=0.05)
    ap.add_argument("--ops_per_token", type=float, default=2.0)
    args = ap.parse_args()

    if args.tier_mbps is None and args.tier_mbps_list is None:
        raise SystemExit("Provide --tier_mbps or --tier_mbps_list")

    mbps_vals: List[float] = []
    if args.tier_mbps_list:
        mbps_vals = [float(x.strip()) for x in args.tier_mbps_list.split(",") if x.strip()]
    else:
        mbps_vals = [float(args.tier_mbps)]

    print("kv_kb_per_token=", args.kv_kb_per_token)
    print("op_lat_ms=", args.op_lat_ms)
    print("ops_per_token=", args.ops_per_token)
    print("")
    print("tier_mbps,tg_tps_max")
    for mbps in mbps_vals:
        tg = ceiling_tg_tps(args.kv_kb_per_token, mbps, args.op_lat_ms, args.ops_per_token)
        print(f"{mbps:g},{tg:.3f}")

if __name__ == "__main__":
    main()
