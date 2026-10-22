"""Select a reproducible native build for isolated lookup experiments."""
import argparse
import hashlib
import json
from pathlib import Path

REVISION = "c68c13582e972292c86a5025140d52e713384cbc"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_inputs(source):
    source = Path(source)
    return {str(p.resolve()): sha(p) for p in sorted(source.rglob("*"))
            if p.is_file() and not {".git", "__pycache__"}.intersection(p.relative_to(source).parts)
            and p.suffix not in (".pyc", ".pyo")}


def verify_base_report(path, build, source, database):
    path = Path(path).resolve(strict=True)
    report = json.loads(path.read_text())
    if report.get("status") == "PASS_TOOLCHAIN_BUILD_NOT_BOARD_SIGNOFF":
        if report.get("pins", {}).get("nextpnr-himbaechel", [None, None])[1] != REVISION:
            raise ValueError("Bootstrap source pin does not match the lookup backend")
        if not report.get("inputs") or not report.get("build") or not report.get("source"):
            raise ValueError("Bootstrap report lacks source provenance; rerun the updated bootstrap")
        if Path(report["build"]).resolve() != build or Path(report["source"]).resolve() != source:
            raise ValueError("Bootstrap source/build paths do not match the selection")
        executable = report["artifacts"]["nextpnr"]
        chipdb = report["artifacts"]["chipdb"]
        if Path(chipdb["path"]).resolve() != database or sha(database) != chipdb["sha256"]:
            raise ValueError("Selected chipdb differs from the completed bootstrap")
        inputs = dict(report["inputs"])
        current_sources = source_inputs(source)
        if set(report.get("native_source_inputs", [])) != set(current_sources):
            raise ValueError("Native source membership changed since bootstrap")
        if any(inputs.get(p) != digest for p, digest in current_sources.items()):
            raise ValueError("Native sources changed since bootstrap")
        if not report.get("commands") or any(c.get("status") != "PASS" or c.get("returncode") != 0
                                              for c in report["commands"]):
            raise ValueError("Bootstrap has an incomplete or failed command")
    elif report.get("status") == "PASS_NATIVE_EXECUTABLE_BUILD_AND_STARTUP":
        if report.get("source_revision") != REVISION:
            raise ValueError("Legacy base build source revision does not match")
        executable = report["executable"]
        inputs = dict(report["verification_inputs"])
    else:
        raise ValueError("Need a completed passing native build report")
    executable_path = Path(executable["path"]).resolve(strict=True)
    if executable_path != (build / "nextpnr-himbaechel").resolve():
        raise ValueError("Base executable does not belong to the selected build directory")
    if sha(executable_path) != executable["sha256"]:
        raise ValueError("Base executable changed")
    for name, digest in inputs.items():
        if sha(name) != digest:
            raise ValueError(f"Base build input changed: {name}")
    inputs[str(path)] = sha(path)
    inputs[str(executable_path)] = sha(executable_path)
    inputs[str(database)] = sha(database)
    return executable_path, inputs


def select_build(root, argv=None):
    root = Path(root)
    parser = argparse.ArgumentParser(description="Build an isolated lookup candidate from completed pinned native tools")
    parser.add_argument("--build-dir", type=Path, default=root / "build/ypcb/nextpnr-build")
    parser.add_argument("--source", type=Path, default=root / "build/ypcb/nextpnr-himbaechel")
    parser.add_argument("--chipdb", type=Path, help="Defaults to the exact-device database in --build-dir")
    parser.add_argument("--build-report", type=Path, help="Completed bootstrap or legacy native build report")
    args = parser.parse_args(argv)
    build = args.build_dir.resolve(strict=True)
    source = args.source.resolve(strict=True)
    database = (args.chipdb or build / "share/himbaechel/xilinx/chipdb-xc7k480t.bin").resolve(strict=True)
    metadata = build / "himbaechel/CMakeFiles/nextpnr-himbaechel.dir"
    if any(not (metadata / name).is_file() for name in ("flags.make", "link.txt")):
        raise ValueError("Lookup relinking requires a completed Unix Makefiles build with flags.make and link.txt; "
                         "run bootstrap_openxc7.py or select a compatible --build-dir")
    report_path = args.build_report
    if report_path is None:
        candidates = []
        for path in sorted((root / "build/ypcb").glob("bootstrap-*/report.json")):
            report = json.loads(path.read_text())
            if (report.get("status") == "PASS_TOOLCHAIN_BUILD_NOT_BOARD_SIGNOFF"
                    and report.get("build") and Path(report["build"]).resolve() == build):
                candidates.append(path)
        if not candidates:
            raise ValueError("No completed bootstrap for this build; run bootstrap_openxc7.py or supply --build-report")
        report_path = candidates[-1]
    report_path = report_path.resolve(strict=True)
    executable, inputs = verify_base_report(report_path, build, source, database)
    inputs[str(Path(__file__).resolve())] = sha(__file__)
    return build, source, database, report_path, executable, inputs
