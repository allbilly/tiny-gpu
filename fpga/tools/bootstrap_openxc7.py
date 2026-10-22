#!/usr/bin/env python3
"""Reproduce the project-local maintained openXC7 toolchain, without sudo."""
from stage_run import run_stage
from lookup_build import source_inputs, sha

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "build/ypcb"
PINS = {
    "nextpnr-himbaechel": ("https://github.com/openXC7/nextpnr.git", "c68c13582e972292c86a5025140d52e713384cbc"),
    "prjxray-db": ("https://github.com/openXC7/prjxray-db.git", "517d66a383676cb971177ea92b0ff3b6ea6e8690"),
    "prjxray": ("https://github.com/openXC7/prjxray.git", "ed3331c6200f421164101388759fc2860b0f5634"),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--build-timeout", type=int, default=28800,
                        help="Bound each native build in seconds; large chipdb import can exceed two hours on a shared host")
    parser.add_argument("--eigen-prefix", type=Path, default=Path.home() / "rknpu-fpga/build/openxc7/prefix")
    parser.add_argument("--python", default=shutil.which("python3.13") or shutil.which("python3"))
    args = parser.parse_args()
    if args.jobs<1 or args.jobs>8: raise ValueError("jobs must be 1–8")
    if not 1 <= args.build_timeout <= 28800: raise ValueError("build-timeout must be 1..28800")
    BASE.mkdir(parents=True, exist_ok=True)
    out = BASE / ("bootstrap-" + str(time.time_ns())); out.mkdir()
    report = dict(status="RUNNING", pins=PINS, jobs=args.jobs,
                  native_build_timeout=args.build_timeout, commands=[])
    def save(): (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    def run(argv, name, timeout=7200, env=None):
        log = out / (name + ".log")
        entry = dict(argv=list(map(str,argv)), log=str(log), status="RUNNING")
        report["commands"].append(entry); save()
        print(name + " ...",flush=True)
        returncode = run_stage(entry["argv"], cwd=ROOT, log=log, entry=entry,
                               save=save, timeout=timeout, env=env)
        if returncode: raise RuntimeError(f"{name} failed: {log}")
    try:
        for name,(url,revision) in PINS.items():
            path=BASE/name
            if not path.exists(): run(["git","clone","--depth","1",url,path],name+"_clone",timeout=1200)
            actual=subprocess.check_output(["git","-C",path,"rev-parse","HEAD"],text=True).strip()
            dirty=subprocess.check_output(["git","-C",path,"status","--porcelain"],text=True)
            if dirty: raise ValueError(f"Refuse changed/incomplete tool source checkout: {path}")
            if actual!=revision:
                run(["git","-C",path,"fetch","--depth","1","origin",revision],name+"_fetch",timeout=1200)
                run(["git","-C",path,"checkout","--detach",revision],name+"_pin")
        nextpnr=BASE/"nextpnr-himbaechel"; xray=BASE/"prjxray"
        run(["git","-C",nextpnr,"submodule","update","--init","--depth","1","himbaechel/uarch/xilinx/meta"],"nextpnr_meta",timeout=1200)
        run(["git","-C",xray,"submodule","update","--init","--depth","1","--jobs",str(args.jobs),
             *["third_party/"+name for name in ("abseil-cpp","cctz","googletest","gflags","yaml-cpp","sanitizers-cmake","fasm")]],"xray_submodules",timeout=1800)
        frozen_sources = source_inputs(nextpnr)
        report.update(source=str(nextpnr), build=str(BASE / "nextpnr-build"),
                      native_source_inputs=sorted(frozen_sources), inputs=dict(frozen_sources))
        for tool in (Path(__file__).resolve(), ROOT / "fpga/tools/stage_run.py", ROOT / "fpga/tools/lookup_build.py"):
            report["inputs"][str(tool)] = sha(tool)
        save()
        command=["cmake","-G","Unix Makefiles","-S",nextpnr,"-B",BASE/"nextpnr-build","-DARCH=himbaechel","-DHIMBAECHEL_UARCH=xilinx",
                 "-DBUILD_GUI=OFF","-DBUILD_PYTHON=OFF","-DUSE_IPO=OFF","-DCMAKE_BUILD_TYPE=Release",
                 "-DHIMBAECHEL_PRJXRAY_DB="+str(BASE/"prjxray-db"),"-DHIMBAECHEL_XILINX_DEVICES=xc7k480t"]
        if args.eigen_prefix.exists(): command += ["-DCMAKE_PREFIX_PATH="+str(args.eigen_prefix)]
        run(command,"nextpnr_configure")
        run(["cmake","--build",BASE/"nextpnr-build","--target","nextpnr-himbaechel","-j",str(args.jobs)],
            "nextpnr_build",timeout=args.build_timeout)
        # Compatibility flags from the pinned nextpnr CI's prjxray build.
        env=os.environ.copy()
        env["CFLAGS"]="-include stdint.h -Wno-free-nonheap-object"
        env["CXXFLAGS"]="-include stdint.h -Wno-free-nonheap-object"
        run(["cmake","-S",xray,"-B",BASE/"prjxray-build","-DCMAKE_BUILD_TYPE=Release",
             "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"],"xray_configure",env=env)
        run(["cmake","--build",BASE/"prjxray-build","--target","xc7frames2bit","-j",str(args.jobs)],
            "xray_build",timeout=args.build_timeout)
        venv=BASE/"xray-venv"
        if not venv.exists(): run([args.python,"-m","venv",venv],"venv")
        python=venv/"bin/python"
        run([python,"-m","pip","install","--disable-pip-version-check","-e",xray/"third_party/fasm",
             "-e",xray],"python_dependencies",timeout=1800)
        for name,path in {"nextpnr":BASE/"nextpnr-build/nextpnr-himbaechel",
                          "chipdb":BASE/"nextpnr-build/share/himbaechel/xilinx/chipdb-xc7k480t.bin",
                          "xc7frames2bit":BASE/"prjxray-build/tools/xc7frames2bit"}.items():
            if not path.is_file(): raise ValueError(f"Missing build artifact: {path}")
            with path.open("rb") as stream:
                report.setdefault("artifacts",{})[name]=dict(path=str(path),sha256=hashlib.file_digest(stream,"sha256").hexdigest())
        run([BASE/"nextpnr-build/nextpnr-himbaechel","--version"],"nextpnr_version")
        if source_inputs(nextpnr) != frozen_sources:
            raise ValueError("Native sources changed during bootstrap")
        for name, digest in report["inputs"].items():
            if sha(name) != digest:
                raise ValueError(f"Bootstrap input changed: {name}")
        report["status"]="PASS_TOOLCHAIN_BUILD_NOT_BOARD_SIGNOFF"; save()
        print(report["status"]+": "+str(out/"report.json"))
    except BaseException as exc:
        report.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                      reason=str(exc) or type(exc).__name__); save(); raise


if __name__=="__main__": main()
