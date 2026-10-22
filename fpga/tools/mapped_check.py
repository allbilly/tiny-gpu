#!/usr/bin/env python3
"""Simulate a successful preparation run's mapped netlist with real UNISIMs."""
from stage_run import run_stage

import argparse
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    path = args.report.resolve(strict=True)
    preparation = json.loads(path.read_text())
    if preparation["status"] != "PASS_SIMULATION_AND_MAPPING":
        raise ValueError("Mapped test requires a completed passing synthesis report")
    for source, expected in preparation["inputs"].items():
        if digest(ROOT / source) != expected: raise ValueError(f"Source changed: {source}")
    mapped = path.parent / "mapped.v"
    if digest(mapped) != preparation["artifacts"]["mapped.v"]: raise ValueError("Netlist hash mismatch")
    bench = ROOT / "fpga/tests/tb_mapped.sv"
    vendor = ROOT / "fpga/tests/vendor/xilinx-unisim"
    models = sorted(vendor.rglob("*.v")) + [vendor / "LICENSE"]
    out = path.parent / ("mapped-check-" + str(time.time_ns()))
    out.mkdir()
    report = dict(status="RUNNING", source_report=str(path), netlist_sha256=digest(mapped),
                  bench_sha256=digest(bench), models={str(p.relative_to(ROOT)): digest(p) for p in models},
                  inputs={str(p): digest(p) for p in (path, mapped, bench, Path(__file__).resolve(), ROOT / "fpga/tools/stage_run.py")},
                  scope="XC7 primitive functional simulation; no routed delays, timing signoff or hardware proof", commands=[])
    def save(): (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    def run(argv, name, markers=()):
        log = out / (name + ".log")
        entry = dict(argv=list(map(str, argv)), log=str(log), status="RUNNING")
        report["commands"].append(entry); save()
        returncode = run_stage(entry["argv"], cwd=ROOT, log=log, entry=entry,
                               save=save, timeout=1800)
        text = log.read_text()
        if returncode or any(error in text.upper() for error in ("FATAL:", "ERROR:")) or any(marker not in text for marker in markers):
            entry["status"] = "FAIL"
            raise RuntimeError(f"Mapped check failed; see {log}")
        entry["pass_markers"] = [line for line in text.splitlines() if line.startswith("PASS")]
        save()
    try:
        executable = out / "mapped.vvp"
        run(["iverilog", "-g2012", "-s", "tb_mapped", "-s", "glbl", "-y", vendor / "verilog/src/unisims",
             "-o", executable, mapped, vendor / "verilog/src/glbl.v", bench], "build")
        run(["vvp", executable], "run", ["PASS mapped XC7 primitives: both kernels, configuration iteration=0",
            "PASS mapped XC7 primitives: both kernels, configuration iteration=1",
            "PASS mapped configuration reset: four INIT flip-flops, two GSR releases"])
        for model, expected in report["models"].items():
            if digest(ROOT / model) != expected: raise ValueError(f"Model changed: {model}")
        for source, expected in preparation["inputs"].items():
            if digest(ROOT / source) != expected: raise ValueError(f"Source changed during mapped check: {source}")
        for name, expected in report["inputs"].items():
            if digest(Path(name)) != expected: raise ValueError(f"Mapped input changed: {name}")
        report["status"] = "PASS_MAPPED_FUNCTIONAL_SIMULATION"
        print(report["status"] + ": " + str(out / "report.json"))
    except BaseException as exc:
        report.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                      reason=str(exc) or type(exc).__name__); save(); raise
    save()


if __name__ == "__main__":
    main()
