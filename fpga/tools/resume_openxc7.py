#!/usr/bin/env python3
"""Recover the known placement-reader failure without rerunning native P&R."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time

from board import bitstream_part
from frame_check import check_frames
from frame_inputs import verify_frame_inputs
from placement_check import check_placement
from stage_run import run_stage

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "build/ypcb"
PART = "xc7k480tffg1156-2"
KNOWN_OLD = {
    "fpga/tools/openxc7.py": "6521957c372e730a4e6051834112dc6527444081286f4d85d5aef894668d439e",
    "fpga/tools/placement_check.py": "c719083ef9fdd56d64359b261c812e3489b7d614a0aecd2234403539217ad42e",
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage_log_has_error(text):
    # ImportError in a handled parser-fallback warning is not an ERROR
    # diagnostic. Unhandled exceptions also retain their nonzero exit status.
    return bool(re.search(r"^\s*(?:error|fatal):", text, re.MULTILINE | re.IGNORECASE)
                or "Traceback (most recent call last):" in text
                or any(marker in text.lower() for marker in (
                    "invalid word address", "invalid frame address", "not found or invalid",
                    "failed to write bitstream")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    source_path = args.report.resolve(strict=True)
    original = json.loads(source_path.read_text())
    terminal_path = source_path.parent / "execution-result.json"
    terminal = json.loads(terminal_path.read_text())
    if (original.get("status") != "FAIL" or original.get("reason") != "Unexpected routed top module"
            or original.get("part") != PART or terminal.get("native_returncode") != 0
            or terminal.get("pipeline_returncode") != 1):
        raise ValueError("Only the recorded native-P&R PASS / normalized-top reader failure can recover")
    commands = original["commands"]
    if len(commands) != 4 or any(c.get("returncode") != 0 or c.get("status") not in ("PASS", "REUSED_PASS")
                                 for c in commands):
        raise ValueError("Original preflight and native P&R did not all complete")
    route = commands[-1]
    argv = route["argv"]
    preparation_path = Path(original["source_report"])
    netlist = preparation_path.parent / "synth.json"
    if (argv[argv.index("--freq") + 1] != "50" or argv[argv.index("--device") + 1] != PART
            or Path(argv[argv.index("--json") + 1]) != netlist):
        raise ValueError("Original command differs from the exact 50 MHz preparation")
    for name, expected in terminal["artifacts"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"Preserved route artifact changed: {name}")
    inputs = dict(original["inputs"])
    replacements = {}
    for relative, expected in KNOWN_OLD.items():
        current = ROOT / relative
        snapshot = source_path.parent / "source-snapshot" / relative
        if inputs.get(str(current)) != expected or sha(snapshot) != expected:
            raise ValueError(f"Unknown original reader/runner: {relative}")
        inputs[str(snapshot)] = expected
        inputs[str(current)] = sha(current)
        replacements[relative] = dict(original_sha256=expected, current_sha256=sha(current),
                                      original_snapshot=str(snapshot))
    for name, expected in inputs.items():
        if sha(Path(name)) != expected:
            raise ValueError(f"Original source/tool/proof changed: {name}")
    preparation = json.loads(preparation_path.read_text())
    if preparation["status"] != "PASS_SIMULATION_AND_MAPPING" or sha(netlist) != preparation["artifacts"]["synth.json"]:
        raise ValueError("Verified synthesis differs from the routed source")
    log = Path(route["log"]).read_text()
    if any(marker in log.lower() for marker in ("error:", "unrouted nets remain", "failed to route",
            "not fully routed", "ignoring constraint", "unsupported constraint", "matched nothing")):
        raise ValueError("Original routing log requires investigation")
    clocks = json.loads((source_path.parent / "timing.json").read_text()).get("fmax", {})
    if len(clocks) != 1:
        raise ValueError("Expected exactly one timed clock domain")
    for clock in clocks.values():
        achieved, constraint = float(clock["achieved"]), float(clock["constraint"])
        if not math.isfinite(achieved) or not math.isfinite(constraint) or achieved < 50 or abs(constraint - 50) > 1e-6:
            raise ValueError("Original route fails the 50 MHz estimate")
    db = BASE / "prjxray-db/kintex7"
    equivalence_path = BASE / "frame-grid-cache-check.json"
    equivalence = json.loads(equivalence_path.read_text())
    if equivalence.get("status") != "PASS_EXACT_PART_FRAME_EQUIVALENCE":
        raise ValueError("Need a current frame-tool equivalence proof")
    verify_frame_inputs(equivalence, ROOT, BASE)
    for name, digest in equivalence["inputs"].items():
        if sha(Path(name)) != digest:
            raise ValueError(f"Frame equivalence input changed: {name}")
    inputs.update(equivalence["inputs"])
    inputs[str(equivalence_path)] = sha(equivalence_path)
    with (db / PART / "package_pins.csv").open() as stream:
        package_rows = {row["pin"]: row for row in csv.DictReader(stream)}
    placement = check_placement(json.loads((source_path.parent / "routed.json").read_text()),
        json.loads((source_path.parent / "placement.json").read_text()), package_rows, json.loads(netlist.read_text()))
    fasm_source = source_path.parent / "tiny_gpu.fasm"
    if not any(line.strip() and not line.lstrip().startswith("#") for line in fasm_source.read_text().splitlines()):
        raise ValueError("No GPU configuration features")
    for relative in ("fpga/tools/resume_openxc7.py", "fpga/tests/test_placement_check.py",
                     "build/ypcb/nextpnr-himbaechel/json/jsonwrite.cc",
                     "build/ypcb/nextpnr-himbaechel/himbaechel/uarch/xilinx/xilinx.cc",
                     "build/ypcb/nextpnr-himbaechel/himbaechel/uarch/xilinx/fasm.cc"):
        inputs[str(ROOT / relative)] = sha(ROOT / relative)
    inputs[str(source_path)] = sha(source_path)
    inputs[str(terminal_path)] = sha(terminal_path)
    out = BASE / ("openxc7-resume-" + str(time.time_ns()))
    out.mkdir()
    for name in ("routed.json", "placement.json", "timing.json", "tiny_gpu.fasm", "ypcb.literal.xdc"):
        source = source_path.parent / name
        shutil.copyfile(source, out / name)
        inputs[str(source)] = sha(source)
        inputs[str(out / name)] = sha(source)
    report = {k: v for k, v in original.items() if k not in ("status", "reason", "inputs", "commands", "artifacts")}
    report.update(status="PASS_REVALIDATED_ESTIMATED_PNR_NOT_PHYSICAL_SIGNOFF", inputs=inputs,
        commands=[], placement_validation=placement, estimated_fmax=clocks,
        recovery=dict(source_report=str(source_path), terminal_record=str(terminal_path),
            original_native_command=route, accepted_reader_changes=replacements,
            source_writer_behavior="Default top name and physical site/BEL attributes verified in pinned backend source",
            scope="Reuse unchanged complete native route after strict corrected placement verification; no new P&R"))

    def save():
        temporary = out / "report.json.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(out / "report.json")

    def run(argv, name, stdout=None):
        entry = dict(argv=list(map(str, argv)), log=str(out / (name + ".log")), status="RUNNING")
        report["commands"].append(entry)
        save()
        print(name + " ...", flush=True)
        result = run_stage(entry["argv"], cwd=ROOT, log=Path(entry["log"]), entry=entry,
                           save=save, timeout=7200, stdout=stdout)
        text = Path(entry["log"]).read_text()
        entry["warnings"] = [line for line in text.splitlines() if "warning" in line.lower()]
        if result or stage_log_has_error(text):
            entry["status"] = "FAIL"
            raise ValueError(f"{name} failed; see {entry['log']}")
        save()

    save()
    print(out / "report.json", flush=True)
    try:
        frames, bit = out / "tiny_gpu.frames", out / "tiny_gpu_demo.bit"
        run([BASE / "xray-venv/bin/python", ROOT / "fpga/tools/fasm_to_frames.py",
             "--part", PART, "--db-root", db, out / "tiny_gpu.fasm"], "fasm_to_frames", stdout=frames)
        report["frame_validation"] = check_frames(frames, db / PART / "part.json")
        save()
        run([BASE / "prjxray-build/tools/xc7frames2bit", "--part_file", db / PART / "part.yaml",
             "--part_name", PART, "--frm_file", frames, "--output_file", bit], "frames_to_bit")
        report["bitstream_part"] = bitstream_part(bit)
        verify_frame_inputs(equivalence, ROOT, BASE)
        for name, expected in inputs.items():
            if sha(Path(name)) != expected:
                raise ValueError(f"Recovery input changed: {name}")
        report["artifacts"] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "report.json"}
        report["status"] = "PASS_CANDIDATE_BITSTREAM_NOT_PHYSICAL_SIGNOFF"
        save()
        print(report["status"] + ": " + str(out / "report.json"), flush=True)
    except BaseException as exc:
        report.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                      reason=str(exc) or type(exc).__name__)
        save()
        raise


if __name__ == "__main__":
    main()
