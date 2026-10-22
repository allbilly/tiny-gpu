#!/usr/bin/env python3
"""YPCB prerequisite audit, staged DLC10 detection, and explicit SRAM loading."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

YPCB = Path.home() / "ypcb"
LOADER = YPCB / "openFPGALoader/build-xpcu-debug/openFPGALoader"
FIRMWARE = {
    "firmware/xusb_xp2-boot.hex": "4fe1a679efcc7ed7c01e738beaf29d8a1f1201731780dfc026f724a88aee527a",
    "firmware/xusb_xp2-overlay.hex": "f551e3c71efee0556b465dc9975d528115f9849ea143f51b5c44d6f3f4f4a9cf",
    "ref/fxload/a3load.hex": "5f27f666e408512b4e7ba6d53bee89410b31e4cb9f7c27930dfa3db65ab2a240",
}


def bitstream_part(path):
    """Read the standard Xilinx .bit header; reject raw or truncated images."""
    with path.open("rb") as stream:
        def read(count):
            value = stream.read(count)
            if len(value) != count: raise ValueError("Truncated bitstream header")
            return value
        def u16(): return struct.unpack(">H", read(2))[0]
        read(u16())
        if u16() != 1 or read(1) != b"a": raise ValueError("Invalid .bit header")
        read(u16())
        if read(1) != b"b": raise ValueError("Missing .bit part field")
        part = read(u16()).rstrip(b"\0").decode("ascii")
        for field in (b"c", b"d"):
            if read(1) != field: raise ValueError("Malformed .bit metadata")
            read(u16())
        if read(1) != b"e": raise ValueError("Missing bitstream payload")
        length = struct.unpack(">I", read(4))[0]
        if length == 0 or path.stat().st_size - stream.tell() != length:
            raise ValueError("Invalid bitstream payload length")
        if not re.fullmatch(r"(?:xc)?7k480tffg1156(?:-2)?", part):
            raise ValueError(f"Wrong FPGA/package in bitstream: {part}")
        return part


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Read-only prerequisite check (default)")
    group.add_argument("--detect", action="store_true", help="Initialize cable RAM and scan FPGA; no configuration write")
    group.add_argument("--program", type=Path, help="Explicitly load a matching .bit into volatile FPGA SRAM")
    args = parser.parse_args()
    report = dict(observed_utc=datetime.now(timezone.utc).isoformat(),
                  loader=str(LOADER), loader_present=LOADER.is_file(), firmware={})
    for name, expected in FIRMWARE.items():
        path = YPCB / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        report["firmware"][name] = dict(present=path.is_file(), checksum_matches=actual == expected, sha256=actual)
    report["stage2_present"] = (YPCB / "ref/inspur-adventures/scripts/xpcu_stage2.py").is_file()
    report["init_script_present"] = (YPCB / "dlc10-init.sh").is_file()
    report["vivado"] = shutil.which("vivado")
    report["vivado_lab"] = shutil.which("vivado_lab")
    try:
        usb = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=10)
        usb_ok = usb.returncode == 0
        report["usb"] = dict(status="PASS" if usb_ok else "UNAVAILABLE",
                             returncode=usb.returncode, stderr=usb.stderr.strip())
        report["cables"] = ([line for line in usb.stdout.splitlines()
                             if re.search(r"03fd:(0013|0008)", line)] if usb_ok else None)
    except (OSError, subprocess.TimeoutExpired) as exc:
        usb_ok = False
        report["usb"] = dict(status="UNAVAILABLE", error=str(exc))
        report["cables"] = None
    report["prerequisites_ok"] = (report["loader_present"] and all(v["checksum_matches"] for v in report["firmware"].values())
                                      and report["stage2_present"] and report["init_script_present"])
    print(json.dumps(report, indent=2), flush=True)
    if not (args.detect or args.program): return 0 if report["prerequisites_ok"] and usb_ok else 1
    if not report["prerequisites_ok"] or not usb_ok or len(report["cables"]) != 1:
        raise ValueError("Require intact DLC10 prerequisites and exactly one connected cable")
    if args.program:
        path = args.program.resolve(strict=True)
        print(f"Bitstream part: {bitstream_part(path)}; SHA256={hashlib.sha256(path.read_bytes()).hexdigest()}", flush=True)
    subprocess.run(["bash", YPCB / "dlc10-init.sh"], check=True, timeout=120)
    # Independently audit the entire currently observed chain before loading.
    detect = subprocess.run([LOADER, "--cable", "xilinxPlatformCableUsb", "--freq", "500000", "--detect"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30, check=True)
    print(detect.stdout, flush=True)
    codes = re.findall(r"idcode\s+(0x[0-9a-f]+)", detect.stdout.lower())
    if codes != ["0x23751093"]: raise ValueError(f"Unexpected/ambiguous chain: {codes}")
    if args.program:
        print("Loading volatile SRAM. Existing flash contents are preserved.", flush=True)
        subprocess.run([LOADER, "--cable", "xilinxPlatformCableUsb", "--freq", "500000", "--index-chain", "0", path],
                       check=True, timeout=300)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
