#!/usr/bin/env python3
"""Place/route a source-verified tiny-gpu netlist, optionally assemble bits."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "build/ypcb"
PART = "xc7k480tffg1156-2"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def verify_mapped_report(path, preparation_path, preparation):
    report=json.loads(path.read_text())
    if report["status"]!="PASS_MAPPED_FUNCTIONAL_SIMULATION":
        raise ValueError("Need a completed passing UNISIM functional check")
    if Path(report["source_report"]).resolve()!=preparation_path:
        raise ValueError("Mapped check belongs to another preparation")
    if report["netlist_sha256"]!=preparation["artifacts"]["mapped.v"]:
        raise ValueError("Mapped check used another netlist")
    inputs=dict(report["inputs"])
    inputs.update({str(ROOT/name):digest for name,digest in report["models"].items()})
    for name,digest in inputs.items():
        if sha(Path(name))!=digest: raise ValueError(f"Mapped-check input changed: {name}")
    inputs[str(path)]=sha(path)
    return inputs


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("preparation",type=Path,help="Passing prepare.py --synth report")
    parser.add_argument("--assemble",action="store_true",help="Also emit an unprogrammed candidate .bit")
    parser.add_argument("--seed",type=int,default=12350)
    parser.add_argument("--place-route-timeout",type=int,default=7200,
                        help="Finite placement/routing limit in seconds (1..28800; default 7200)")
    parser.add_argument("--nextpnr",type=Path,default=BASE/"nextpnr-build/nextpnr-himbaechel",
                        help="Executable built from the pinned backend; chipdb is supplied separately")
    parser.add_argument("--chipdb",type=Path,
                        default=BASE/"nextpnr-build/share/himbaechel/xilinx/chipdb-xc7k480t.bin",
                        help="Completed exact-device database built from the pinned generator")
    parser.add_argument("--mapped-report",type=Path,help="Completed UNISIM check; defaults to latest check for this preparation")
    parser.add_argument("--architecture-report",type=Path,
                        help="Completed full native integrity record for this exact executable, database and package")
    args=parser.parse_args()
    if not 1 <= args.place_route_timeout <= 28800:
        parser.error("--place-route-timeout must be between 1 and 28800 seconds")
    path=args.preparation.resolve(strict=True)
    preparation=json.loads(path.read_text())
    if preparation["status"]!="PASS_SIMULATION_AND_MAPPING": raise ValueError("Need a passing simulation and mapping report")
    for name,expected in preparation["inputs"].items():
        if sha(ROOT/name)!=expected: raise ValueError(f"Preparation input changed: {name}")
    netlist=path.parent/"synth.json"
    if sha(netlist)!=preparation["artifacts"]["synth.json"]: raise ValueError("Netlist changed since preparation")
    candidates=sorted(path.parent.glob("mapped-check-*/report.json"))
    mapped_path=args.mapped_report.resolve(strict=True) if args.mapped_report else (candidates[-1] if candidates else None)
    if mapped_path is None: raise ValueError("Run mapped_check.py before placement/routing")
    verified_inputs={str(ROOT/name):digest for name,digest in preparation["inputs"].items()}
    verified_inputs.update(verify_mapped_report(mapped_path,path,preparation))
    cache_check=BASE/"frame-grid-cache-check.json"
    if args.assemble:
        equivalence=json.loads(cache_check.read_text())
        from frame_inputs import verify_frame_inputs
        verify_frame_inputs(equivalence, ROOT, BASE)
        if equivalence["status"]!="PASS_EXACT_PART_FRAME_EQUIVALENCE" or equivalence["part"]!=PART:
            raise ValueError("Need passing exact-part frame-cache comparison before assembly")
        for name,digest in equivalence["inputs"].items():
            if sha(Path(name))!=digest: raise ValueError(f"Frame-cache comparison input changed: {name}")
        verified_inputs.update(equivalence["inputs"])
        verified_inputs[str(cache_check)]=sha(cache_check)
    from bootstrap_openxc7 import PINS
    for name,(_,revision) in PINS.items():
        checkout=BASE/name
        actual=subprocess.check_output(["git","-C",checkout,"rev-parse","HEAD"],text=True).strip()
        if actual!=revision: raise ValueError(f"Wrong {name} revision: {actual}")
        subprocess.run(["git","-C",checkout,"diff","--quiet","HEAD"],check=True)
    nextpnr=args.nextpnr.resolve(strict=True)
    chipdb=args.chipdb.resolve(strict=True)
    native_integrity=None
    if args.architecture_report:
        from native_proof import verify_architecture_report
        native_integrity, native_inputs=verify_architecture_report(
            args.architecture_report,nextpnr,chipdb,PART)
        verified_inputs.update(native_inputs)
    db=BASE/"prjxray-db/kintex7"
    from board_profile import PINS as BOARD_PINS, CONFIGURATION, normalized_xdc
    constraint_source=ROOT/"fpga/ypcb.xdc"
    literal_constraints, external_exceptions = normalized_xdc(constraint_source.read_text())
    package=db/PART/"package_pins.csv"
    timing_sources = [BASE/"nextpnr-himbaechel/himbaechel/uarch/xilinx/gen/xilinx_gen.py",
                      BASE/"prjxray-db/artix7/timings/slicem.sdf",
                      BASE/"prjxray-db/artix7/timings/BRAM_L.sdf"]
    out=BASE/("openxc7-"+str(time.time_ns())); out.mkdir()
    report=dict(status="RUNNING",part=PART,seed=args.seed,source_report=str(path),
        mapped_functional_report=str(mapped_path),
        inputs={str(p):sha(p) for p in (netlist,nextpnr,chipdb,path,constraint_source,package,
                                       ROOT/"fpga/tools/board_profile.py",ROOT/"fpga/tools/frame_check.py",
                                       ROOT/"fpga/tools/placement_check.py",
                                       ROOT/"fpga/tools/board.py",ROOT/"fpga/tools/bootstrap_openxc7.py",
                                       ROOT/"fpga/tools/stage_run.py",
                                       db/PART/"part.json",Path(__file__).resolve(),*timing_sources)},commands=[],
        tool_source_pins={name:revision for name,(_,revision) in PINS.items()},
        scope="Estimated open-source placement/routing and optional bit assembly; no physical FPGA proof",
        timing_model=dict(speed_grade="DEFAULT; not XC7K480T-2 characterization",
            placeholder_delays=["SITE_NULL", "SLICE_LUTX", "SLICE_FFX"],
            kintex_primitives_using_artix_sdf=["SELMUX2_1", "CARRY4", "RAMB18E1", "RAMB36E1"],
            timing_signoff=False),
        selected_board_profile=dict(clock_pin="AA28", clock_mhz=50, iostandard="LVCMOS18",
            configuration=CONFIGURATION, reset="Four-clock pulse after FPGA configuration; R28 unused",
            source="User-selected active openTPU YPCB constraints",
            configuration_scope="Vivado electrical metadata; native flow does not perform configuration/electrical DRC"),
        remaining_board_checks=["Physical LED polarity", "Independent electrical/configuration DRC and full timing coverage",
            "Volatile FPGA load and observed PASS/heartbeat"],
        external_exceptions_not_applied=external_exceptions)
    report["inputs"].update(verified_inputs)
    if native_integrity:
        native_build=json.loads(Path(native_integrity["build_report"]).read_text())
        report["architecture_integrity_report"]=str(args.architecture_report.resolve())
        report["native_compiler_build_report"]=native_integrity["build_report"]
        report["native_compiler_derivation"]=dict(
            base_revision=native_integrity["source_revision"],
            change=native_build["scope"],
            class_layout="Unchanged", native_integrity_assertions="All original assertions retained",
            patches={p:h for p,h in native_integrity["inputs"].items() if p.endswith("/lookup.patch")})
    database_build=chipdb.parent/"report.json"
    if database_build.is_file():
        database_report=json.loads(database_build.read_text())
        if (database_report.get("status")!="PASS_NATIVE_BBA_SNAPSHOT_ASSEMBLY_NOT_ARCHITECTURE_CHECKED" or
                database_report.get("device")!="xc7k480t" or
                Path(database_report["binary"]).resolve()!=chipdb or
                database_report["binary_sha256"]!=sha(chipdb)):
            raise ValueError("Completed native database assembly report does not match this chipdb")
        expected_database_pins={name:PINS[name][1] for name in ("nextpnr-himbaechel","prjxray-db")}
        if database_report["source_pins"]!=expected_database_pins:
            raise ValueError("Database build does not match both pinned generator/database sources")
        for name,digest in database_report["inputs"].items():
            if sha(Path(name))!=digest: raise ValueError(f"Database build input changed: {name}")
        report["native_database_build_report"]=str(database_build)
        report["inputs"].update(database_report["inputs"])
        report["inputs"][str(database_build)]=sha(database_build)
    references=BASE/"board-reference-check.json"
    if references.is_file():
        reference_report=json.loads(references.read_text())
        for name,digest in reference_report["inputs"].items():
            if sha(Path(name))!=digest: raise ValueError(f"Board reference changed: {name}")
        report["board_reference_report"]=str(references)
        report["inputs"].update(reference_report["inputs"])
        report["inputs"][str(references)]=sha(references)
    selected_reference=BASE/"opentpu-profile-review.json"
    if selected_reference.is_file():
        selected=json.loads(selected_reference.read_text())
        profile=selected.get("profile",{})
        if (selected.get("status")!="PASS_ACTIVE_OPENTPU_PROFILE_SELECTED_FOR_PREPARATION" or
                profile.get("part")!=PART or profile.get("clock_pin")!="AA28" or
                profile.get("clock_mhz")!=50 or profile.get("clock_iostandard")!="LVCMOS18" or
                profile.get("config_voltage")!=CONFIGURATION["CONFIG_VOLTAGE"] or
                profile.get("cfgbvs")!=CONFIGURATION["CFGBVS"]):
            raise ValueError("Selected openTPU reference does not match board profile")
        # Bind the review's immutable reference snapshots when available.
        # Legacy reviews bind their donor files directly; their historical
        # local Tcl-test inputs are covered by the current preparation instead.
        donor=Path(selected["donor"])
        reference_inputs=selected.get("reference_inputs")
        if reference_inputs is None:
            reference_inputs={name:digest for name,digest in selected["inputs"].items()
                              if Path(name).is_relative_to(donor)}
        if not reference_inputs:
            raise ValueError("Selected board review has no bound reference sources")
        for name,digest in reference_inputs.items():
            if sha(Path(name))!=digest: raise ValueError(f"Selected board source changed: {name}")
            report["inputs"][name]=digest
        report["selected_board_profile"]["evidence_report"]=str(selected_reference)
        report["selected_board_profile"]["donor_revision"]=selected["revision"]
        report["inputs"][str(selected_reference)]=sha(selected_reference)
    for workload in (ROOT/"test/test_matadd.py",ROOT/"test/test_matmul.py"):
        report["inputs"][str(workload)]=sha(workload)
    if args.assemble:
        report["frame_cache_equivalence_report"]=str(cache_check)
        for source in (BASE/"prjxray-build/tools/xc7frames2bit",BASE/"prjxray/utils/fasm2frames.py",
                       ROOT/"fpga/tools/fasm_to_frames.py"):
            report["inputs"][str(source)]=sha(source)
    report["place_route_timeout_seconds"]=args.place_route_timeout
    def save():
        temporary=out/"report.json.tmp"
        temporary.write_text(json.dumps(report,indent=2)+"\n")
        temporary.replace(out/"report.json")
    def run(argv,name,stdout=None,timeout=7200):
        from stage_run import run_stage
        log=out/(name+".log")
        entry=dict(argv=list(map(str,argv)),log=str(log),status="RUNNING")
        report["commands"].append(entry); save(); print(name+" ...",flush=True)
        result=run_stage(entry["argv"],cwd=ROOT,log=log,entry=entry,save=save,
                         timeout=timeout,stdout=stdout)
        text=log.read_text()
        entry.update(warnings=[line for line in text.splitlines() if "warning" in line.lower()]); save()
        if result or any(error in text.lower() for error in
                ("invalid word address", "invalid frame address", "not found or invalid", "failed to write bitstream")):
            entry["status"]="FAIL"; save()
            raise RuntimeError(f"{name} failed; see {log}")
        return text
    try:
        run([sys.executable,ROOT/"fpga/tools/gen_workloads.py","--check"],"generated_check")
        with package.open() as source: package_rows={r["pin"]:r for r in csv.DictReader(source)}
        report["package_pins"]={port:package_rows[pin] for port,pin in BOARD_PINS.items()}
        xdc=out/"ypcb.literal.xdc"
        xdc.write_text(literal_constraints)
        run([nextpnr,"--version"],"version")
        if native_integrity:
            source_command=native_integrity["command"]
            report["commands"].append(dict(
                argv=source_command["argv"],log=source_command["log"],status="REUSED_PASS",
                returncode=source_command["returncode"],source_seconds=source_command["seconds"],
                evidence_report=str(args.architecture_report.resolve()),
                scope="Reuse completed full native architecture integrity for identical artifacts"))
            integrity=Path(source_command["log"]).read_text(); save()
        else:
            integrity=run([nextpnr,"--chipdb",chipdb,"--device",PART,"--test"],"database_integrity")
        integrity_phases=["Running architecture database integrity check.",
                          "Checking entity names.", "Checking location data.",
                          "Checking connectivity data.", "Checking bucket data."]
        if any(marker not in integrity for marker in integrity_phases):
            raise ValueError("Architecture integrity log does not cover every pinned check phase")
        report["database_integrity_validation"]=dict(part=PART, phases=integrity_phases,
            scope="Native database integrity; no physical timing or GPU execution proof")
        save()
        timing=out/"timing.json"; fasm=out/"tiny_gpu.fasm"; placement=out/"placement.json"
        log=run([nextpnr,"--chipdb",chipdb,"--device",PART,"--json",netlist,
                 "-o","xdc="+str(xdc),"-o","fasm="+str(fasm),
                 "-o","placement="+str(placement),"-o","hold-fix",
                 "--freq","50","--seed",str(args.seed),"--router","router2",
                 "--report",timing,"--write",out/"routed.json"],"place_route",
                timeout=args.place_route_timeout)
        if any(s in log.lower() for s in ("unrouted nets remain", "failed to route", "not fully routed",
                                          "ignoring constraint", "unsupported constraint", "matched nothing")):
            raise ValueError("Routing/constraint warning requires investigation")
        clocks=json.loads(timing.read_text()).get("fmax",{})
        if len(clocks)!=1: raise ValueError(f"Expected one timed clock domain, got {clocks}")
        for name,clock in clocks.items():
            achieved=float(clock["achieved"]); constraint=float(clock["constraint"])
            if not math.isfinite(achieved) or not math.isfinite(constraint) or achieved<50 or abs(constraint-50)>1e-6:
                raise ValueError(f"50 MHz timing estimate failed: {name}: {clock}")
        report["estimated_fmax"]=clocks
        from placement_check import check_placement
        report["placement_validation"]=check_placement(
            json.loads((out/"routed.json").read_text()),json.loads(placement.read_text()),package_rows,
            json.loads(netlist.read_text()))
        if not fasm.is_file() or not any(line.strip() and not line.lstrip().startswith("#")
                                         for line in fasm.read_text().splitlines()):
            raise ValueError("No configuration features emitted for the GPU")
        report["status"]="PASS_ESTIMATED_PNR_NOT_PHYSICAL_SIGNOFF"; save()
        if args.assemble:
            python=BASE/"xray-venv/bin/python"
            frames=out/"tiny_gpu.frames"; bit=out/"tiny_gpu_demo.bit"
            run([python,ROOT/"fpga/tools/fasm_to_frames.py","--part",PART,"--db-root",db,fasm],
                "fasm_to_frames",stdout=frames)
            from frame_check import check_frames
            report["frame_validation"]=check_frames(frames,db/PART/"part.json")
            run([BASE/"prjxray-build/tools/xc7frames2bit","--part_file",db/PART/"part.yaml",
                 "--part_name",PART,"--frm_file",frames,"--output_file",bit],"frames_to_bit")
            from board import bitstream_part
            report["bitstream_part"]=bitstream_part(bit)
            verify_frame_inputs(equivalence, ROOT, BASE)
            report["status"]="PASS_CANDIDATE_BITSTREAM_NOT_PHYSICAL_SIGNOFF"
        for name,expected in report["inputs"].items():
            if sha(Path(name))!=expected: raise ValueError(f"PNR input changed: {name}")
        report["artifacts"]={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!="report.json"}
        save(); print(report["status"]+": "+str(out/"report.json"))
    except BaseException as exc:
        report.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                      reason=str(exc) or type(exc).__name__); save(); raise


if __name__=="__main__": main()
