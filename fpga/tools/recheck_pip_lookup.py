#!/usr/bin/env python3
"""Recover the diagnostic formatting error without recompiling a valid lookup."""
from stage_run import run_stage

import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def main():
    source_report = Path(sys.argv[1]).resolve(strict=True)
    previous = json.loads(source_report.read_text())
    out = ROOT / "build/ypcb" / f"pip-lookup-recheck-{time.time_ns()}"
    out.mkdir()
    report = {"status": "RUNNING", "source_revision": previous["source_revision"],
              "source": previous["source"], "database": previous["database"],
              "previous_report": str(source_report), "inputs": {}, "commands": [],
              "scope": "Reuse verified completed native compilation; correct only diagnostic string formatting, then compare actual lookups"}
    def save(): (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    def bind(path):
        p = Path(path).resolve(); report["inputs"][str(p)] = sha(p)
    def run(argv, name, timeout=1800):
        log = out / (name + ".log")
        entry = {"argv": [str(p) for p in argv], "cwd": previous["commands"][0]["cwd"],
                 "log": str(log), "status": "RUNNING", "timeout_seconds": timeout}
        report["commands"].append(entry); save()
        returncode = run_stage(entry["argv"], cwd=entry["cwd"], log=log,
                               entry=entry, save=save, timeout=timeout)
        if returncode: raise RuntimeError(f"{name} failed; see {log}")
        bind(log); return log.read_text()
    print(out / "report.json", flush=True); save()
    try:
        commands = previous["commands"]
        if previous["status"] != "FAIL" or len(commands) != 4 or commands[-1]["status"] != "FAIL":
            raise ValueError("Require the preserved diagnostic-compile failure")
        if not previous.get("base_relink_byte_identical"):
            raise ValueError("Base relink did not reproduce the original binary")
        for command in commands[:3]:
            if command["status"] != "PASS" or command["returncode"] != 0:
                raise ValueError("Cannot reuse an unfinished native build stage")
        bench = ROOT / "fpga/tests/pip_lookup_equivalence.cc"
        frozen = source_report.parent / "failed-probe.cc"
        expected_old = previous["inputs"][str(bench)]
        if sha(frozen) != expected_old: raise ValueError("Old diagnostic source snapshot mismatch")
        original = frozen.read_text()
        if original.count("name.c_str(&ctx)") != 1 or bench.read_text() != original.replace("name.c_str(&ctx)", "name.str(&ctx)"):
            raise ValueError("Recovery permits only the diagnostic formatting correction")
        report["replaced_input"] = {"path": str(bench), "previous_sha256": expected_old,
                                    "frozen_path": str(frozen), "current_sha256": sha(bench)}
        for path, expected in previous["inputs"].items():
            if path == str(bench): continue
            if sha(path) != expected: raise ValueError(f"Compiled input changed: {path}")
            bind(path)
        bind(source_report); bind(frozen); bind(bench); bind(__file__); bind(ROOT / "fpga/tools/stage_run.py")
        for command in commands[:3]: bind(command["log"])
        report["reused_native_commands"] = commands[:3]
        report["base_relink_byte_identical"] = True; save()
        compile_args = list(commands[-1]["argv"])
        probe_object = out / "probe.cc.o"
        compile_args[compile_args.index("-o") + 1] = str(probe_object)
        run(compile_args, "compile_probe"); bind(probe_object)
        link_args = list(commands[2]["argv"])
        probe = out / "lookup-equivalence"
        link_args[link_args.index("-o") + 1] = str(probe)
        for i, arg in enumerate(link_args):
            if arg.endswith("/main.cc.o"): link_args[i] = str(probe_object)
            elif arg.startswith("-Wl,--dependency-file="):
                link_args[i] = "-Wl,--dependency-file=" + str(probe) + ".d"
        run(link_args, "probe_link"); bind(probe)
        text = run([probe, "xc7k480tffg1156-2", previous["database"]], "lookup_equivalence", timeout=1200)
        if "PASS lookup equivalence:" not in text or "Full native architecture integrity remains required." not in text:
            raise ValueError("Missing diagnostic completion markers")
        exe = source_report.parent / "nextpnr-himbaechel"
        run([exe, "--version"], "version")
        for path, expected in report["inputs"].items():
            if sha(path) != expected: raise ValueError(f"Input changed during recovery: {path}")
        report.update(status="PASS_LOOKUP_EQUIVALENCE_NOT_ARCHITECTURE_CHECKED",
                      executable={"path": str(exe), "sha256": sha(exe)},
                      equivalence_log=str(out / "lookup_equivalence.log"),
                      remaining="Complete native architecture integrity, actual GPU P&R, assembly and board signoff")
    except BaseException as e:
        report.update(status="FAIL" if isinstance(e, Exception) else "FAIL_INTERRUPTED",
                      failure=str(e) or type(e).__name__); save(); print(str(e), file=sys.stderr)
        return 130 if isinstance(e, KeyboardInterrupt) else 1
    save(); print(json.dumps({"report": str(out / "report.json"), "status": report["status"]}), flush=True)
    return 0


if __name__ == "__main__": raise SystemExit(main())
