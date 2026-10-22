#!/usr/bin/env python3
"""Build source-bound simulation/mapping evidence; never connect to hardware."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from netlist_check import check_board_netlist
from stage_run import run_stage

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulator", choices=("icarus", "verilator", "both"), default="both")
    parser.add_argument("--synth", action="store_true")
    args = parser.parse_args()
    out = ROOT / "build/ypcb" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{time.time_ns()}")
    out.mkdir(parents=True)
    sources = sorted((ROOT / "src").glob("*.sv")) + sorted((ROOT / "fpga/rtl").glob("*.sv"))
    inputs = sources + sorted((ROOT / "fpga/tests").glob("*.sv")) + [
        ROOT / "fpga/generated/workloads.vh", ROOT / "fpga/generated/workloads.json",
        ROOT / "fpga/tools/gen_workloads.py", ROOT / "fpga/tools/netlist_check.py",
        Path(__file__).resolve(), ROOT / "fpga/tools/stage_run.py", ROOT / "fpga/ypcb.xdc"]
    report = dict(status="RUNNING", observed_utc=datetime.now(timezone.utc).isoformat(),
                  part="xc7k480tffg1156-2", clock_hz=50000000,
                  gpu=dict(cores=2, threads_per_block=4, data_channels=4),
                  board_reset="Four-clock pulse after FPGA configuration; no external reset/R28 dependency",
                  scope="RTL simulation and XC7 synthesis only; no placement, routing, timing signoff, bitstream or hardware proof",
                  inputs={str(p.relative_to(ROOT)): sha(p) for p in inputs}, commands=[])

    def save():
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(argv, name, timeout=600, stdout=None, markers=()):
        argv = list(map(str, argv))
        log_path = out / (name + ".log")
        entry = dict(argv=argv, log=str(log_path.relative_to(ROOT)), status="RUNNING")
        report["commands"].append(entry)
        save()
        print(name + " ...", flush=True)
        start = time.monotonic()
        try:
            returncode = run_stage(argv, cwd=ROOT, log=log_path, entry=entry,
                                   save=save, timeout=timeout, stdout=stdout)
            text = log_path.read_text()
            if returncode != 0 or any(s in text for s in ("FATAL:", "%Error", "ERROR:")):
                raise RuntimeError(f"{name} failed; see {log_path}")
            if any(marker not in text for marker in markers):
                raise RuntimeError(f"{name}: missing device-side completion marker; see {log_path}")
            entry["status"] = "PASS"
            entry["warnings"] = [line for line in text.splitlines() if "warning" in line.lower()]
            entry["pass_markers"] = [line for line in text.splitlines() if line.startswith("PASS")]
            return text
        except TimeoutError:
            entry["status"] = "FAIL_TIMEOUT"
            raise
        except Exception:
            entry["status"] = "FAIL"
            raise
        finally:
            entry["seconds"] = round(time.monotonic() - start, 3)
            save()

    try:
        run([sys.executable, ROOT / "fpga/tools/gen_workloads.py", "--check"], "generated_check")
        for tool in ("sv2v", "iverilog", "vvp", "verilator", "yosys"):
            path = shutil.which(tool)
            report.setdefault("tools", {})[tool] = dict(path=path)
        required = ["sv2v"]
        if args.simulator in ("icarus", "both"): required += ["iverilog", "vvp"]
        if args.simulator in ("verilator", "both"): required += ["verilator"]
        if args.synth: required += ["yosys"]
        for tool in required:
            if not report["tools"][tool]["path"]: raise RuntimeError(f"Missing tool: {tool}")
        for tool, flag in (("sv2v", "--version"), ("iverilog", "-V"), ("verilator", "--version"), ("yosys", "-V")):
            if tool in required:
                report["tools"][tool]["version"] = run([tool, flag], tool + "_version").strip()
        design = out / "design.v"
        run(["sv2v", "-I", ROOT / "fpga/generated", *sources], "convert", stdout=design)
        benches = {"demo": "PASS board RTL matadd + matmul", "soc": "PASS host protocol",
                   "fault": "PASS fault reset recovery",
                   "divider": "PASS divider: 65280 nonzero pairs, zero/X, stalls, inactive lane, reset and other arithmetic"}
        if args.simulator in ("icarus", "both"):
            for bench, marker in benches.items():
                executable = out / (bench + ".vvp")
                run(["iverilog", "-g2012", "-I", ROOT / "fpga/generated", "-s", "tb_" + bench,
                     "-o", executable, design, ROOT / "fpga/tests" / ("tb_" + bench + ".sv")], bench + "_icarus_build")
                run(["vvp", executable], bench + "_icarus_run", markers=[marker])
                if bench == "demo" and "PASS configuration reset: four edges, no R28" not in (out / (bench + "_icarus_run.log")).read_text():
                    raise RuntimeError("Missing configuration-time board reset verification")
        if args.simulator in ("verilator", "both"):
            # Four-state X injection is deliberately verified with Icarus only.
            for bench in ("demo", "soc"):
                obj = out / ("verilator_" + bench)
                run(["verilator", "--binary", "--timing", "-j", "2", "-Wno-fatal", "-I" + str(ROOT / "fpga/generated"),
                     "--top-module", "tb_" + bench, "--Mdir", obj, design,
                     ROOT / "fpga/tests" / ("tb_" + bench + ".sv")], bench + "_verilator_build", timeout=1200)
                run([obj / ("Vtb_" + bench)], bench + "_verilator_run", markers=[benches[bench]])
                if bench == "demo" and "PASS configuration reset: four edges, no R28" not in (out / (bench + "_verilator_run.log")).read_text():
                    raise RuntimeError("Missing configuration-time board reset verification")
        if args.synth:
            netlist = out / "synth.json"
            yosys_script = out / "synth.ys"
            yosys_script.write_text(f'read_verilog "{design}"\nhierarchy -check -top ypcb_tiny_gpu_top\n'
                                    'proc\nopt_clean\ncheck -assert\n'
                                    'synth_xilinx -family xc7 -top ypcb_tiny_gpu_top -flatten\ncheck -assert\n'
                                    f'write_json "{netlist}"\nwrite_verilog -noattr "{out / "mapped.v"}"\n')
            run(["yosys", "-Q", "-T", "-s", yosys_script], "synthesis", timeout=7200)
            report["synthesis_cells"] = check_board_netlist(json.loads(netlist.read_text()))
            report["configuration_reset_mapping"] = "Four INIT=0 FDREs, constant enable, no local reset, one clock, verified shift connections"
        changed = [p for p, digest in report["inputs"].items() if sha(ROOT / p) != digest]
        if changed: raise RuntimeError(f"Inputs changed during verification: {changed}")
        report["status"] = "PASS_SIMULATION_AND_MAPPING" if args.synth else "PASS_SIMULATION"
        report["artifacts"] = {str(p.relative_to(out)): sha(p) for p in out.glob("*") if p.is_file() and p.name != "report.json"}
        save()
        print(f"{report['status']}: {out / 'report.json'}", flush=True)
        return 0
    except BaseException as exc:
        report.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                      reason=str(exc) or type(exc).__name__)
        save()
        print(f"FAIL: {exc}\nReport: {out / 'report.json'}", file=sys.stderr)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


if __name__ == "__main__":
    raise SystemExit(main())
