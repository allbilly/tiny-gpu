"""Bind frame conversion to its database, source and installed dependencies."""
import hashlib
from pathlib import Path


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree_files(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"Missing frame-tool dependency directory: {directory}")
    return {p.resolve() for p in directory.rglob("*") if p.is_file()
            and not {".git", "__pycache__"}.intersection(p.relative_to(directory).parts)
            and p.suffix not in (".pyc", ".pyo")}


def capture_frame_inputs(root, base):
    """Capture before execution, including file membership for optional DB data."""
    root, base = Path(root), Path(base)
    files = {root / "fpga/tools" / name for name in (
        "frame_inputs.py", "check_frame_tools.py", "fasm_to_frames.py",
        "frame_check.py", "board.py", "stage_run.py")}
    files.update((base / "prjxray-build/tools/xc7frames2bit",
                  base / "xray-venv/bin/python", base / "xray-venv/pyvenv.cfg",
                  base / "prjxray/utils/fasm2frames.py"))
    directories = [base / "prjxray-db/kintex7", base / "prjxray/prjxray",
                   base / "prjxray/third_party/fasm"]
    packages = sorted((base / "xray-venv/lib").glob("python*/site-packages"))
    if not packages:
        raise ValueError("Missing frame-tool Python environment dependencies")
    for directory in [*directories, *packages]:
        files.update(tree_files(directory))
    return {str(p): sha(p) for p in sorted(files)}


def verify_frame_inputs(record, root, base):
    current = capture_frame_inputs(root, base)
    if set(record.get("frame_tool_inputs", [])) != set(current):
        raise ValueError("Frame-tool dependency set is missing or changed; rerun both frame checks")
    for name, digest in current.items():
        if record["inputs"].get(name) != digest:
            raise ValueError(f"Frame-tool dependency changed: {name}")
    return current
