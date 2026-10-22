#!/usr/bin/env python3
"""Inventory every visible home project and locate plausible FPGA donors."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
KEYWORDS = ("fpga", "xc7", "ypcb", "vivado", "tiny-gpu", "jtag", "bscan", "systemc", "verilator", "sv2v", "nextpnr")


def main():
    rows = []
    for project in sorted(Path.home().iterdir()):
        if not project.is_dir() or project.name.startswith("."):
            continue
        docs = {}
        for name in ("README.md", "README.rst", "README", "Makefile", "CMakeLists.txt"):
            path = project / name
            if path.is_file():
                docs[name] = [line[:240] for line in path.read_text(errors="replace").splitlines()
                              if any(key in line.lower() for key in KEYWORDS)][:10]
        revision = None
        if (project / ".git").exists():
            revision = subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"],
                                      capture_output=True, text=True, timeout=10).stdout.strip()
        command = ["rg", "--files", "--maxdepth", "6", str(project)]
        for pattern in ("*fpga*", "*jtag*", "*bscan*", "*.xdc", "*vivado*", "*sv2v*", "*nextpnr*", "AGENTS.md"):
            command += ["-g", pattern]
        for pattern in ("!**/build/**", "!**/out/**", "!**/node_modules/**", "!**/obj_dir/**", "!**/.git/**",
                        "!**/artifacts/**", "!**/verification/runs/**", "!**/third_party/**"):
            command += ["-g", pattern]
        scan = subprocess.run(command, capture_output=True, text=True, timeout=60)
        rows.append(dict(path=str(project), revision=revision, documentation_hits=docs,
                         candidate_files=scan.stdout.splitlines(), file_scan_returncode=scan.returncode))
    output = ROOT / "build/ypcb/home-project-inventory.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(observed_utc=datetime.now(timezone.utc).isoformat(),
        scope="Every non-hidden top-level home directory; root documentation plus candidate filename scan to depth six excluding generated/build/dependency trees. Relevant donors inspected further manually.",
        projects=rows), indent=2) + "\n")
    print(f"{len(rows)} home directories inventoried: {output}")


if __name__ == "__main__":
    main()
