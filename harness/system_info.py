#!/usr/bin/env python3
import json
import platform
import subprocess
from pathlib import Path

def sh(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True).strip()

def main():
    info = {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "uname": sh("uname -a"),
        "cpu": {"lscpu": sh("lscpu || true")},
        "memory": {"free_h": sh("free -h || true")},
        "disk": {"df_h": sh("df -h || true")},
        "wsl": {
            "kernel": sh("uname -r"),
            "is_wsl": "microsoft" in sh("uname -r").lower(),
        },
    }

    out = Path("results/system_info.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"Wrote: {out}")

if __name__ == "__main__":
    main()
