#!/usr/bin/env python3
"""Exercise all four upstream arithmetic instructions through the real host bus."""
from stage_run import run_stage

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("preparation",type=Path,help="Passing source-bound simulation/mapping report")
    args=parser.parse_args()
    preparation_path=args.preparation.resolve(strict=True)
    preparation=json.loads(preparation_path.read_text())
    if preparation["status"]!="PASS_SIMULATION_AND_MAPPING":
        raise ValueError("Need a completed passing preparation")
    design=preparation_path.parent/"design.v"
    if sha(design)!=preparation["artifacts"]["design.v"]:
        raise ValueError("Converted source differs from tested preparation")
    inputs={str(ROOT/name):digest for name,digest in preparation["inputs"].items()}
    for name,digest in inputs.items():
        if sha(Path(name))!=digest: raise ValueError(f"Preparation input changed: {name}")
    bench=ROOT/"fpga/tests/tb_arithmetic.sv"
    compiler=Path(shutil.which("iverilog") or "").resolve(strict=True)
    simulator=Path(shutil.which("vvp") or "").resolve(strict=True)
    inputs.update({str(p):sha(p) for p in (design,bench,Path(__file__).resolve(),
                                         preparation_path,compiler,simulator,ROOT/"fpga/tools/stage_run.py")})
    out=ROOT/"build/ypcb"/("arithmetic-check-"+str(time.time_ns()));out.mkdir()
    # Independent integer reference: include zero, high-bit values, truncating
    # quotients, underflow and overflowing products. Every divisor is nonzero.
    a=[255,254,0,1,128,127,250,17,202,99,3,240,129,64,5,200,251]
    b=[1,2,255,3,5,255,128,17,7,11,2,16,3,127,7,9,13]
    a += [255-v for v in a]
    b += list(reversed(b))
    reference=[(x+y)&255 for x,y in zip(a,b)]
    reference += [(x-y)&255 for x,y in zip(a,b)]
    reference += [(x*y)&255 for x,y in zip(a,b)]
    reference += [divmod(x,y)[0] for x,y in zip(a,b)]
    for name,values in (("operand_a.hex",a),("operand_b.hex",b),("results.hex",reference)):
        p=out/name;p.write_text("".join(f"{v:02x}\n" for v in values));inputs[str(p)]=sha(p)
    report=dict(status="RUNNING",source_report=str(preparation_path),inputs=inputs,
                scope="RTL host-bus execution on unchanged real two-core GPU; no mapped, routed or physical result",
                coverage=dict(opcodes={"ADD":3,"SUB":4,"MUL":5,"DIV":6},
                    thread_counts=[1,3,5,9,17],operand_sets=2,kernels=40,
                    checked_thread_results=280,checked_memory_bytes=10240,
                    divisors="Nonzero; division-by-zero behavior is not covered"),commands=[])
    def save(): (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    def run(argv,name):
        entry=dict(argv=list(map(str,argv)),log=str(out/(name+".log")),status="RUNNING")
        report["commands"].append(entry);save()
        returncode = run_stage(entry["argv"], cwd=out, log=Path(entry["log"]), entry=entry,
                               save=save, timeout=720)
        if returncode:raise RuntimeError(f"{name} failed: {entry['log']}")
        return Path(entry["log"]).read_text()
    try:
        run([compiler,"-g2012","-s","tb_arithmetic","-o",out/"arithmetic.vvp",design,bench],"compile")
        log=run([simulator,out/"arithmetic.vvp"],"run")
        for opcode in range(3,7):
            for iteration in range(2):
                for threads in (1,3,5,9,17):
                    marker=f"PASS arithmetic opcode={opcode} iteration={iteration} threads={threads} cycles="
                    if log.count(marker)!=1:raise ValueError(f"Missing or duplicate completion: {marker}")
        final="PASS real GPU host arithmetic: 40 kernels, 280 thread results, all 256 bytes per kernel"
        if log.count(final)!=1:raise ValueError("Missing arithmetic suite completion")
        for name,digest in inputs.items():
            if sha(Path(name))!=digest:raise ValueError(f"Arithmetic input changed: {name}")
        report.update(status="PASS_RTL_HOST_ARITHMETIC",artifacts={p.name:sha(p) for p in out.iterdir()
                      if p.is_file() and p.name!="report.json"});save()
        print(report["status"]+": "+str(out/"report.json"))
    except BaseException as exc:
        report.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                      reason=str(exc) or type(exc).__name__);save();raise


if __name__=="__main__":main()
