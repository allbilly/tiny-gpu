"""Validate a completed native integrity record before reusing its result."""
import hashlib
import json
from pathlib import Path

PHASES = ["Running architecture database integrity check.", "Checking entity names.",
          "Checking location data.", "Checking connectivity data.", "Checking bucket data."]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def verify_architecture_report(path, executable, database, part):
    """Return the verified record and inputs, including the final report/log."""
    path = Path(path).resolve(strict=True)
    executable = Path(executable).resolve(strict=True)
    database = Path(database).resolve(strict=True)
    report = json.loads(path.read_text())
    if report.get("status") != "PASS_NATIVE_ARCHITECTURE_INTEGRITY_NOT_PHYSICAL_SIGNOFF":
        raise ValueError("Native architecture integrity has not passed")
    if report.get("part") != part or report.get("phases") != PHASES:
        raise ValueError("Native integrity part or phase coverage mismatch")
    command = report.get("command", {})
    expected = [str(executable), "--chipdb", str(database), "--device", part, "--test"]
    if command.get("argv") != expected or command.get("status") != "PASS" or command.get("returncode") != 0:
        raise ValueError("Native integrity requires the completed exact command with exit 0")
    if not command.get("seconds", 0) > 0 or not 0 < command.get("timeout_seconds", 0) <= 28800:
        raise ValueError("Native integrity duration/bound missing")
    if Path(report["executable"]["path"]).resolve() != executable or Path(report["database"]).resolve() != database:
        raise ValueError("Native integrity artifact paths mismatch")
    if report["executable"]["sha256"] != sha(executable):
        raise ValueError("Native integrity executable changed")
    inputs = dict(report["inputs"])
    if inputs.get(str(executable)) != sha(executable) or inputs.get(str(database)) != sha(database):
        raise ValueError("Native integrity did not bind both actual artifacts")
    build_path = Path(report["build_report"]).resolve(strict=True)
    if str(build_path) not in inputs: raise ValueError("Native build provenance was not bound")
    build = json.loads(build_path.read_text())
    if build.get("source_revision") != report.get("source_revision") or report.get("source_revision") != "c68c13582e972292c86a5025140d52e713384cbc":
        raise ValueError("Native integrity base revision mismatch")
    if build.get("status") != "PASS_LOOKUP_EQUIVALENCE_NOT_ARCHITECTURE_CHECKED" or not build.get("base_relink_byte_identical"):
        raise ValueError("Native build/equivalence provenance incomplete")
    if build.get("executable") != report.get("executable") or Path(build["database"]).resolve() != database:
        raise ValueError("Native build provenance artifacts mismatch")
    if any(inputs.get(p) != h for p, h in build["inputs"].items()):
        raise ValueError("Native integrity omitted a build input")
    log = Path(command["log"]).resolve(strict=True)
    if sha(log) != report.get("log_sha256"): raise ValueError("Native integrity log changed")
    text = log.read_text()
    position = -1
    for marker in PHASES:
        found = text.find(marker, position + 1)
        if found < 0: raise ValueError("Native log lacks an ordered integrity phase")
        position = found
    for p, expected_sha in inputs.items():
        if sha(p) != expected_sha: raise ValueError(f"Native integrity input changed: {p}")
    inputs[str(path)] = sha(path)
    inputs[str(log)] = sha(log)
    inputs[str(Path(__file__).resolve())] = sha(__file__)
    return report, inputs
