#!/usr/bin/env python3
"""Recover old mapping classification/timeout failures, preserving evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

from netlist_check import check_board_netlist
from stage_run import run_stage

ROOT = Path(__file__).resolve().parents[2]
# The original runner erroneously classified $scopeinfo as generic logic.
OLD_RUNNER_SHA = "189eed80bc7741154d188ac052fcf6b404ab206925bf32d233e75bd6a5d393f1"
MARKERS = {"demo": "PASS board RTL matadd + matmul", "soc": "PASS host protocol",
           "fault": "PASS fault reset recovery"}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--resynthesize", action="store_true",
                        help="Rerun a timed-out mapper with a two-hour bound; retain successful simulator builds")
    args = parser.parse_args()
    original = args.report.resolve(strict=True)
    previous = json.loads(original.read_text())
    runner = "fpga/tools/prepare.py"
    if previous.get("status") != "FAIL":
        raise ValueError("Original run must have reached a terminal failure")
    if not args.resynthesize and previous.get("reason") != "Unmapped synthesis cells":
        raise ValueError("Only the original scope-metadata classifier failure can reuse mapping")
    if previous["inputs"].get(runner) != OLD_RUNNER_SHA or sha(original.parent / "prepare-snapshot.py") != OLD_RUNNER_SHA:
        raise ValueError("Original runner/snapshot does not match the known classifier error")
    inputs = {name: value for name, value in previous["inputs"].items() if name != runner}
    for name, expected in inputs.items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"Previously tested input changed: {name}")
    commands = {Path(entry["log"]).stem: entry for entry in previous["commands"]}
    required = ["generated_check", "convert"] + ([] if args.resynthesize else ["synthesis"])
    required += [f"{bench}_icarus_{step}" for bench in MARKERS for step in ("build", "run")]
    required += [f"{bench}_verilator_{step}" for bench in ("demo", "soc") for step in ("build", "run")]
    for name in required:
        entry = commands.get(name, {})
        if entry.get("status") != "PASS" or entry.get("returncode") != 0:
            raise ValueError(f"Previous command did not pass: {name}")
        log = ROOT / entry["log"]
        text = log.read_text()
        if any(error in text for error in ("FATAL:", "%Error", "ERROR:")):
            raise ValueError(f"Previous failure in {name}")
        if name.endswith("_run"):
            if MARKERS[name.split("_")[0]] not in text:
                raise ValueError(f"Previous completion marker missing: {name}")
    synthesis = commands["synthesis"]
    if args.resynthesize and synthesis.get("status") != "TIMEOUT":
        raise ValueError("Resynthesis recovery requires an original mapper timeout")
    if synthesis["argv"] != ["yosys", "-Q", "-T", "-s", str(original.parent / "synth.ys")]:
        raise ValueError("Unexpected original mapping invocation")
    expected_script = (f'read_verilog "{original.parent / "design.v"}"\n'
                       'hierarchy -check -top ypcb_tiny_gpu_top\nproc\nopt_clean\ncheck -assert\n'
                       'synth_xilinx -family xc7 -top ypcb_tiny_gpu_top -flatten\ncheck -assert\n'
                       f'write_json "{original.parent / "synth.json"}"\n'
                       f'write_verilog -noattr "{original.parent / "mapped.v"}"\n')
    if (original.parent / "synth.ys").read_text() != expected_script:
        raise ValueError("Original mapping script differs from the tested XC7 recipe")
    cells = None
    if not args.resynthesize:
        netlist = original.parent / "synth.json"
        cells = check_board_netlist(json.loads(netlist.read_text()))
        if not cells.get("$scopeinfo"):
            raise ValueError("Original rejection was not caused by scope metadata")
    out = ROOT / "build/ypcb" / ("recheck-" + str(time.time_ns()))
    out.mkdir()
    for name in (runner, "fpga/tools/netlist_check.py", "fpga/tools/recheck_mapping.py", "fpga/tools/stage_run.py"):
        inputs[name] = sha(ROOT / name)
    report = dict(status="RUNNING", observed_utc=datetime.now(timezone.utc).isoformat(),
                  part=previous["part"], clock_hz=previous["clock_hz"], gpu=previous["gpu"],
                  scope=previous["scope"], inputs=inputs, commands=[], tools=previous["tools"],
                  synthesis_cells=cells,
                  reused_mapping=dict(source_report=str(original), source_report_sha256=sha(original),
                                      reused=not args.resynthesize,
                                      runner_snapshot_sha256=OLD_RUNNER_SHA,
                                      reason=("Mapper timeout: rerun only mapping" if args.resynthesize else
                                              "Correct scope-metadata classification; no HDL, bench or constraint changes"),
                                      original_command=synthesis,
                                      original_artifacts={name: sha(original.parent / name) for name in
                                                          ("design.v", "synth.ys") +
                                                          (() if args.resynthesize else ("synth.json", "mapped.v"))},
                                      original_logs={name: sha(ROOT / commands[name]["log"]) for name in required}))

    def save():
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(argv, name, marker=None, stdout=None, timeout=600):
        log = out / (name + ".log")
        entry = dict(argv=list(map(str, argv)), log=str(log.relative_to(ROOT)), status="RUNNING")
        report["commands"].append(entry)
        save()
        print(name + " ...", flush=True)
        returncode = run_stage(entry["argv"], cwd=ROOT, log=log, entry=entry,
                               save=save, timeout=timeout, stdout=stdout)
        text = log.read_text()
        entry.update(pass_markers=[line for line in text.splitlines() if line.startswith("PASS")])
        if returncode or any(error in text for error in ("FATAL:", "%Error", "ERROR:")) or (marker and marker not in text):
            entry["status"] = "FAIL"
            raise ValueError(f"Replay failed: {log}")
        save()

    try:
        if not args.resynthesize:
            for name in ("synth.json", "mapped.v", "synth.ys", "synthesis.log"):
                shutil.copyfile(original.parent / name, out / name)
            for name in ("synth.json", "mapped.v", "synth.ys"):
                if sha(out / name) != report["reused_mapping"]["original_artifacts"][name]:
                    raise ValueError(f"Mapping artifact changed while copying: {name}")
        # Fresh conversion must byte-match the design consumed by the original
        # compiler and mapper. Re-execute every simulator; do not rebuild them.
        sources = sorted((ROOT / "src").glob("*.sv")) + sorted((ROOT / "fpga/rtl").glob("*.sv"))
        run([sys.executable, ROOT / "fpga/tools/gen_workloads.py", "--check"], "generated_check")
        design = out / "design.v"
        run(["sv2v", "-I", ROOT / "fpga/generated", *sources], "convert", stdout=design)
        if sha(design) != sha(original.parent / "design.v"):
            raise ValueError("Fresh conversion differs from the previously compiled/mapped design")
        report["reused_mapping"]["design_sha256"] = sha(design)
        report["reused_executables"] = {}
        for bench, marker in MARKERS.items():
            executable = original.parent / (bench + ".vvp")
            report["reused_executables"][str(executable)] = sha(executable)
            run(["vvp", executable], bench + "_icarus_run", marker)
        for bench in ("demo", "soc"):
            executable = original.parent / ("verilator_" + bench) / ("Vtb_" + bench)
            report["reused_executables"][str(executable)] = sha(executable)
            run([executable], bench + "_verilator_run", MARKERS[bench])
        if args.resynthesize:
            script = out / "synth.ys"
            script.write_text(expected_script.replace(str(original.parent), str(out)))
            run(["yosys", "-Q", "-T", "-s", script], "synthesis", timeout=7200)
            report["synthesis_cells"] = check_board_netlist(json.loads((out / "synth.json").read_text()))
        for name, expected in inputs.items():
            if sha(ROOT / name) != expected:
                raise ValueError(f"Input changed during recheck: {name}")
        for name, expected in report["reused_executables"].items():
            if sha(Path(name)) != expected:
                raise ValueError(f"Executable changed during recheck: {name}")
        report["artifacts"] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "report.json"}
        report["status"] = "PASS_SIMULATION_AND_MAPPING"
        save()
        print(report["status"] + ": " + str(out / "report.json"))
    except BaseException as exc:
        report.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                      reason=str(exc) or type(exc).__name__)
        save()
        raise


if __name__ == "__main__":
    main()
