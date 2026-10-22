#!/usr/bin/env python3
"""Run the complete native architecture test with source-bound provenance."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import stage_run

ROOT = Path(__file__).resolve().parents[2]
PART = "xc7k480tffg1156-2"
PHASES = ["Running architecture database integrity check.", "Checking entity names.",
          "Checking location data.", "Checking connectivity data.", "Checking bucket data."]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_report", type=Path)
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 28800: raise ValueError("Require a bounded timeout of 1..28800 seconds")
    build_report = args.build_report.resolve(strict=True)
    build = json.loads(build_report.read_text())
    out = ROOT / "build/ypcb" / f"architecture-check-{time.time_ns()}"
    out.mkdir()
    report = {"status": "RUNNING", "part": PART, "build_report": str(build_report),
              "inputs": dict(build["inputs"]), "started_utc": utc(),
              "scope": "Complete native architecture integrity; no GPU execution, electrical or physical timing proof"}
    def save():
        temporary = out / "report.json.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(out / "report.json")
    report["inputs"][str(build_report)] = sha(build_report)
    report["inputs"][str(Path(__file__).resolve())] = sha(__file__)
    report["inputs"][str(Path(stage_run.__file__).resolve())] = sha(stage_run.__file__)
    print(out / "report.json", flush=True); save()
    try:
        if build["status"] != "PASS_LOOKUP_EQUIVALENCE_NOT_ARCHITECTURE_CHECKED":
            raise ValueError("Require completed native build and actual lookup equivalence")
        if build["source_revision"] != "c68c13582e972292c86a5025140d52e713384cbc" or not build["base_relink_byte_identical"]:
            raise ValueError("Unexpected base revision or unverified retained objects")
        for path, expected in report["inputs"].items():
            if sha(path) != expected: raise ValueError(f"Build input changed: {path}")
        exe = Path(build["executable"]["path"])
        database = Path(build["database"])
        if sha(exe) != build["executable"]["sha256"]: raise ValueError("Candidate executable changed")
        argv = [str(exe), "--chipdb", str(database), "--device", PART, "--test"]
        log = out / "database_integrity.log"
        command = {"argv": argv, "log": str(log), "status": "RUNNING", "timeout_seconds": args.timeout}
        report.update(executable=build["executable"], database=str(database), command=command,
                      source_revision=build["source_revision"], namespace=os.readlink("/proc/self/ns/pid"))
        result = stage_run.run_stage(argv, cwd=ROOT, log=log, entry=command,
                                     save=save, timeout=args.timeout, poll_seconds=3)
        report["log_sha256"] = sha(log); save()
        if result != 0: raise RuntimeError(f"Full native architecture check failed; see {log}")
        text = log.read_text()
        if any(marker not in text for marker in PHASES): raise ValueError("Native log lacks a required integrity phase")
        for path, expected in report["inputs"].items():
            if sha(path) != expected: raise ValueError(f"Input changed during native integrity check: {path}")
        report.update(status="PASS_NATIVE_ARCHITECTURE_INTEGRITY_NOT_PHYSICAL_SIGNOFF", phases=PHASES,
                      completed_utc=utc(), scope="All original native integrity assertions completed for this exact package; no GPU or physical proof")
    except KeyboardInterrupt:
        report.update(status="FAIL_INTERRUPTED", failure="Architecture check interrupted", completed_utc=utc())
        save(); print(report["failure"], file=sys.stderr); return 130
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as e:
        report.update(status="FAIL", failure=str(e), completed_utc=utc()); save(); print(str(e), file=sys.stderr); return 1
    save(); print(json.dumps({"report": str(out / "report.json"), "status": report["status"]}), flush=True)
    return 0


if __name__ == "__main__": raise SystemExit(main())
