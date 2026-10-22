#!/usr/bin/env python3
"""Assemble preserved valid GPU frames rejected by the known warning reader."""
import argparse
import json
from pathlib import Path
import shutil
import time

from board import bitstream_part
from frame_check import check_frames
from frame_inputs import verify_frame_inputs
from resume_openxc7 import PART, ROOT, BASE, sha, stage_log_has_error
from stage_run import run_stage

KNOWN_FRAME_RUNNER = "86e35195e494931fb34fbf710467d60a1d06c07e38d38bd17314b2b05347be3a"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    source = args.report.resolve(strict=True)
    original = json.loads(source.read_text())
    terminal_path = source.parent / "execution-result.json"
    terminal = json.loads(terminal_path.read_text())
    commands = original["commands"]
    if (original["status"] != "FAIL" or not original.get("reason", "").startswith("fasm_to_frames failed; see ")
            or original["part"] != PART or len(commands) != 1
            or commands[0].get("returncode") != 0 or commands[0].get("seconds", 0) <= 0
            or terminal["status"] != "FAIL_LOG_READER_IMPORTERROR_WARNING"
            or terminal["native_converter_returncode"] != 0 or terminal["wrapper_returncode"] != 1):
        raise ValueError("Only the preserved completed conversion with the known warning-reader failure can recover")
    if sha(source) != terminal["report_sha256"]:
        raise ValueError("Original conversion report changed")
    old_runner = ROOT / "fpga/tools/resume_openxc7.py"
    snapshot = Path(terminal["runner_snapshot"])
    inputs = dict(original["inputs"])
    if (inputs.get(str(old_runner)) != KNOWN_FRAME_RUNNER or sha(snapshot) != KNOWN_FRAME_RUNNER
            or terminal["runner_snapshot_sha256"] != KNOWN_FRAME_RUNNER):
        raise ValueError("Unknown original warning reader")
    inputs[str(snapshot)] = KNOWN_FRAME_RUNNER
    inputs[str(old_runner)] = sha(old_runner)
    for name, expected in inputs.items():
        if sha(Path(name)) != expected:
            raise ValueError(f"Original source/tool/proof changed: {name}")
    log_path = Path(commands[0]["log"])
    log = log_path.read_text()
    if sha(log_path) != terminal["log_sha256"] or stage_log_has_error(log):
        raise ValueError("Conversion log changed or contains actual errors")
    if "Falling back to the much slower pure Python textX based parser" not in log:
        raise ValueError("Original failure is not the known handled parser fallback")
    frames_source = source.parent / "tiny_gpu.frames"
    if sha(frames_source) != terminal["frames_sha256"] or frames_source.stat().st_size != terminal["frames_bytes"]:
        raise ValueError("Preserved frames changed")
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
    validation = check_frames(frames_source, db / PART / "part.json")
    out = BASE / ("openxc7-finish-" + str(time.time_ns()))
    out.mkdir()
    for name in ("tiny_gpu.frames", "routed.json", "placement.json", "timing.json", "tiny_gpu.fasm", "ypcb.literal.xdc"):
        path = source.parent / name
        shutil.copyfile(path, out / name)
        inputs[str(path)] = sha(path)
        inputs[str(out / name)] = sha(path)
    for path in (source, terminal_path, log_path, Path(__file__).resolve(),
                 ROOT / "fpga/tests/test_resume_openxc7.py"):
        inputs[str(path)] = sha(path)
    report = {k: v for k, v in original.items() if k not in ("status", "reason", "inputs", "commands", "artifacts")}
    report.update(status="RUNNING_BITSTREAM_ASSEMBLY", inputs=inputs, commands=[], frame_validation=validation,
        frame_recovery=dict(source_report=str(source), terminal_record=str(terminal_path),
            original_converter_command=commands[0], original_runner_sha256=KNOWN_FRAME_RUNNER,
            current_runner_sha256=sha(old_runner),
            scope="Reuse unchanged frames from actual converter exit 0, with hash, log and exact-part validation; no repeated conversion"))

    def save():
        tmp = out / "report.json.tmp"
        tmp.write_text(json.dumps(report, indent=2) + "\n")
        tmp.replace(out / "report.json")

    save()
    print(out / "report.json", flush=True)
    try:
        bit = out / "tiny_gpu_demo.bit"
        entry = dict(argv=list(map(str, [BASE / "prjxray-build/tools/xc7frames2bit", "--part_file",
            db / PART / "part.yaml", "--part_name", PART, "--frm_file", out / "tiny_gpu.frames",
            "--output_file", bit])), log=str(out / "frames_to_bit.log"), status="RUNNING")
        report["commands"].append(entry)
        save()
        result = run_stage(entry["argv"], cwd=ROOT, log=Path(entry["log"]), entry=entry, save=save, timeout=7200)
        text = Path(entry["log"]).read_text()
        entry["warnings"] = [line for line in text.splitlines() if "warning" in line.lower()]
        if result or stage_log_has_error(text):
            entry["status"] = "FAIL"
            raise ValueError("Native frame assembler failed; see " + entry["log"])
        report["bitstream_part"] = bitstream_part(bit)
        verify_frame_inputs(equivalence, ROOT, BASE)
        for name, expected in inputs.items():
            if sha(Path(name)) != expected:
                raise ValueError(f"Assembly input changed: {name}")
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
