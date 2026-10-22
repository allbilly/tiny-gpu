#!/usr/bin/env python3
"""Exercise exact-part frame tools with an empty design; no GPU or board proof."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fpga/tools"))
from frame_check import check_frames
from board import bitstream_part
from frame_inputs import capture_frame_inputs, verify_frame_inputs
from stage_run import run_stage

BASE = ROOT / "build/ypcb"
PART = "xc7k480tffg1156-2"
DB = BASE / "prjxray-db/kintex7"
PYTHON = BASE / "xray-venv/bin/python"
ASSEMBLER = BASE / "prjxray-build/tools/xc7frames2bit"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def compare_reports(paths):
    records = []
    for path in paths:
        path = path.resolve(strict=True)
        report = json.loads(path.read_text())
        if report["status"] != "PASS_EXACT_PART_FRAME_TOOLS_ONLY" or report["part"] != PART:
            raise ValueError(f"Need passing exact-part frame check: {path}")
        verify_frame_inputs(report, ROOT, BASE)
        for name, expected in report["inputs"].items():
            if sha(Path(name)) != expected: raise ValueError(f"Frame-check input changed: {name}")
        for name, expected in report["artifacts"].items():
            if sha(path.parent / name) != expected: raise ValueError(f"Frame-check artifact changed: {name}")
        records.append((path, report))
    if {report["grid_cache"] for _, report in records} != {False, True}:
        raise ValueError("Compare one cached run and one untouched reference run")
    frame_hashes = {report["artifacts"]["empty-design.frames"] for _, report in records}
    if len(frame_hashes) != 1:
        raise ValueError("Cached/reference configuration frames differ")
    verified = {}
    for path, report in records:
        for name, digest in report["inputs"].items():
            if name in verified and verified[name] != digest:
                raise ValueError(f"Frame checks used different dependencies: {name}")
            verified[name] = digest
        verified[str(path)] = sha(path)
        for name, digest in report["artifacts"].items():
            verified[str(path.parent / name)] = digest
    result = dict(status="PASS_EXACT_PART_FRAME_EQUIVALENCE", part=PART,
                  observed_utc=datetime.now(timezone.utc).isoformat(), frames_sha256=next(iter(frame_hashes)),
                  inputs=verified, frame_tool_inputs=records[0][1]["frame_tool_inputs"],
                  reports={"cached" if report["grid_cache"] else "reference":
                           dict(path=str(path), sha256=sha(path), frame_validation=report["frame_validation"],
                                commands=report["commands"]) for path, report in records},
                  scope="Actual full-device empty-design frame equivalence; unchanged vendor conversion rules; no GPU P&R or physical signoff",
                  timing_scope="Observed wall times under shared host load; not a controlled benchmark")
    output = BASE / "frame-grid-cache-check.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"] + ": " + str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uncached", action="store_true", help="Reference run with the untouched vendor converter")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("CACHED_REPORT", "REFERENCE_REPORT"),
                        help="Verify existing completed runs and save their exact-part equivalence proof")
    args = parser.parse_args()
    if args.compare:
        compare_reports(args.compare)
        return
    converter = BASE / "prjxray/utils/fasm2frames.py" if args.uncached else ROOT / "fpga/tools/fasm_to_frames.py"
    hashes = capture_frame_inputs(ROOT, BASE)
    out = BASE / ("frame-smoke-" + str(time.time_ns()))
    out.mkdir()
    report = dict(status="RUNNING", observed_utc=datetime.now(timezone.utc).isoformat(), part=PART,
                  grid_cache=not args.uncached,
                  scope="Empty-design frame-tool check only; no tiny-gpu RTL, P&R or physical FPGA result",
                  inputs=hashes, frame_tool_inputs=sorted(hashes), commands=[])

    def save():
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(argv, name, stdout=None):
        log = out / (name + ".log")
        entry = dict(argv=list(map(str, argv)), log=str(log), status="RUNNING")
        report["commands"].append(entry); save(); print(name + " ...", flush=True)
        returncode = run_stage(entry["argv"], cwd=ROOT, log=log, entry=entry,
                               save=save, timeout=7200, stdout=stdout)
        text = log.read_text().lower()
        if returncode or any(word in text for word in ("invalid word address", "invalid frame address",
                                                             "not found or invalid", "failed to write bitstream")):
            entry["status"] = "FAIL"; save(); raise ValueError(f"Frame-tool failure: {log}")
        entry["status"] = "PASS"; save()

    try:
        fasm = out / "empty-design.fasm"
        frames = out / "empty-design.frames"
        bit = out / "empty-design.bit"
        fasm.write_text("# Empty design for tool verification only; contains no tiny-gpu logic.\n")
        run([PYTHON, converter, "--part", PART, "--db-root", DB, fasm],
            "fasm_to_frames", stdout=frames)
        report["frame_validation"] = check_frames(frames, DB / PART / "part.json", require_nonzero=False)
        run([ASSEMBLER, "--part_file", DB / PART / "part.yaml", "--part_name", PART,
             "--frm_file", frames, "--output_file", bit], "frames_to_bit")
        report["bitstream_part"] = bitstream_part(bit)
        verify_frame_inputs(report, ROOT, BASE)
        for name, expected in hashes.items():
            if sha(Path(name)) != expected: raise ValueError(f"Tool input changed: {name}")
        report["artifacts"] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "report.json"}
        report["status"] = "PASS_EXACT_PART_FRAME_TOOLS_ONLY"
        save(); print(report["status"] + ": " + str(out / "report.json"))
    except BaseException as exc:
        report.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                      reason=str(exc) or type(exc).__name__); save(); raise


if __name__ == "__main__": main()
