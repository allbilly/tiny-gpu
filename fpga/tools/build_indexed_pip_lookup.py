#!/usr/bin/env python3
"""Build and compare an isolated, context-safe indexed nextpnr name lookup."""
from stage_run import run_stage
from lookup_build import select_build

import difflib
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
DEVICE = "xc7k480tffg1156-2"
REVISION = "c68c13582e972292c86a5025140d52e713384cbc"
CACHE_PREAMBLE = '''// Process-local, bounded to one current architecture. Constructor reset is
// unconditional, so reused Context/database addresses never reuse stale data.
using PipWireNameIndex = dict<IdString, std::vector<int>>;
static std::mutex pip_name_index_mutex;
static const Arch *pip_name_index_owner = nullptr;
static std::unordered_map<const void *, std::shared_ptr<const PipWireNameIndex>> pip_name_indices;

static void reset_pip_name_index(const Arch *owner)
{
    std::lock_guard<std::mutex> lock(pip_name_index_mutex);
    pip_name_indices.clear();
    pip_name_index_owner = owner;
}

'''
NEW_LOOKUP = '''PipId Arch::getPipByName(IdStringList name) const
{
    NPNR_ASSERT(name.size() == 3 || (name.size() == 4 && name[3] == id("INV")));
    const int tile = tile_name2idx.at(name[0]);
    const auto &tdata = chip_tile_info(chip_info, tile);
    std::shared_ptr<const PipWireNameIndex> names;
    {
        std::lock_guard<std::mutex> lock(pip_name_index_mutex);
        if (pip_name_index_owner != this) {
            pip_name_indices.clear();
            pip_name_index_owner = this;
        }
        auto &entry = pip_name_indices[&tdata];
        if (!entry) {
            auto index = std::make_shared<PipWireNameIndex>();
            for (int wire = 0; wire < tdata.wires.ssize(); ++wire)
                (*index)[IdString(tdata.wires[wire].name)].push_back(wire);
            entry = index;
        }
        names = entry;
    }
    // Own the immutable index while the global cache changes contexts. Keep
    // all duplicate wire names and the minimum matching pip, as in the base.
    const auto matches = names->find(name[1]);
    if (matches == names->end())
        return PipId();
    int first = -1;
    for (int wire : matches->second) {
        for (int pip : tdata.wires[wire].pips_uphill) {
            NPNR_ASSERT(pip >= 0 && pip < tdata.pips.ssize());
            const auto &pdata = tdata.pips[pip];
            NPNR_ASSERT(pdata.dst_wire == wire);
            if (IdString(tdata.wires[pdata.src_wire].name) != name[2])
                continue;
            const auto tmp_pip = PipId(tile, pip);
            if ((name.size() == 3 && !isPipInverting(tmp_pip)) ||
                (name.size() == 4 && isPipInverting(tmp_pip))) {
                if (first < 0 || pip < first)
                    first = pip;
            }
        }
    }
    return first < 0 ? PipId() : PipId(tile, first);
}

'''


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def main():
    BASE, SOURCE, DATABASE, manifest, exe, base_inputs = select_build(ROOT)
    out = ROOT / "build/ypcb" / f"indexed-pip-lookup-{time.time_ns()}"
    out.mkdir()
    report = {"status": "RUNNING", "source_revision": REVISION,
              "source": str(SOURCE), "database": str(DATABASE), "base_build_report": str(manifest),
              "commands": [], "inputs": dict(base_inputs),
              "scope": "Wire-name index plus constructor cache reset; unchanged class layout/backend objects/database and native architecture assertions"}
    def save(): (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    def bind(path):
        p = Path(path).resolve()
        digest = sha(p)
        if str(p) in report["inputs"] and report["inputs"][str(p)] != digest:
            raise ValueError(f"Base build input changed before binding: {p}")
        report["inputs"][str(p)] = digest
    def run(argv, name, timeout=3600):
        log = out / (name + ".log")
        entry = {"argv": [str(x) for x in argv], "cwd": str(BASE / "himbaechel"),
                 "log": str(log), "status": "RUNNING", "timeout_seconds": timeout}
        report["commands"].append(entry); save()
        returncode = run_stage(entry["argv"], cwd=BASE / "himbaechel", log=log,
                               entry=entry, save=save, timeout=timeout)
        if returncode: raise RuntimeError(f"{name} failed; see {log}")
        bind(log)
        return log.read_text()
    save()
    print(out / "report.json", flush=True)
    try:
        revision = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(SOURCE), "status", "--porcelain", "--untracked-files=no"], text=True)
        if revision != REVISION or dirty: raise ValueError("Pinned base source changed")
        bind(manifest); bind(exe); bind(DATABASE); bind(__file__); bind(ROOT / "fpga/tools/stage_run.py")
        bench = ROOT / "fpga/tests/indexed_pip_lookup_equivalence.cc"; bind(bench)
        bind(ROOT / "fpga/tests/pip_lookup_equivalence.cc")
        bind(ROOT / "fpga/tools/build_pip_lookup.py")
        for p in SOURCE.rglob("*"):
            if p.is_file() and ".git" not in p.relative_to(SOURCE).parts: bind(p)
        for p in (BASE / "common").rglob("*"):
            if p.is_file(): bind(p)
        flags = BASE / "himbaechel/CMakeFiles/nextpnr-himbaechel.dir/flags.make"
        link = BASE / "himbaechel/CMakeFiles/nextpnr-himbaechel.dir/link.txt"
        bind(flags); bind(link)
        flag_values = dict(line.split(" = ", 1) for line in flags.read_text().splitlines() if " = " in line)
        compile_flags = sum((shlex.split(flag_values[k]) for k in ("CXX_DEFINES", "CXX_INCLUDES", "CXX_FLAGS")), [])
        link_args = shlex.split(link.read_text()); bind(link_args[0])
        for arg in link_args:
            if arg.endswith((".o", ".a")) or ".so" in arg:
                bind((BASE / "himbaechel" / arg).resolve())
        def relink(output, arch_object=None, main_object=None):
            args = list(link_args)
            args[args.index("-o")+1] = str(output)
            for i, arg in enumerate(args):
                if arg.startswith("-Wl,--dependency-file="):
                    args[i] = "-Wl,--dependency-file=" + str(output) + ".d"
                elif arch_object and arg.endswith("/arch.cc.o"):
                    args[i] = str(arch_object)
                elif main_object and arg.endswith("/main.cc.o"):
                    args[i] = str(main_object)
            return args
        baseline = out / "base-relinked"
        run(relink(baseline), "base_relink")
        if sha(baseline) != sha(exe): raise ValueError("Retained objects do not reproduce the verified base executable")
        bind(baseline); report["base_relink_byte_identical"] = True; save()
        original_path = SOURCE / "himbaechel/arch.cc"
        original = original_path.read_text()
        begin = original.index("PipId Arch::getPipByName(IdStringList name) const\n")
        end = original.index("IdStringList Arch::getPipName(PipId pip) const\n", begin)
        candidate = original[:begin] + NEW_LOOKUP + original[end:]
        candidate = candidate.replace("#include <filesystem>", "#include <filesystem>\n#include <memory>\n#include <mutex>\n#include <unordered_map>", 1)
        constructor = "Arch::Arch(ArchArgs args) : args(args)\n{\n"
        if candidate.count(constructor) != 1:
            raise ValueError("Expected exactly one unchanged constructor")
        candidate = candidate.replace(constructor, CACHE_PREAMBLE + constructor + "    reset_pip_name_index(this);\n", 1)
        source = out / "arch.cc"; source.write_text(candidate); bind(source)
        patch = out / "lookup.patch"
        patch.write_text("".join(difflib.unified_diff(original.splitlines(keepends=True), candidate.splitlines(keepends=True),
                                                  fromfile="a/himbaechel/arch.cc", tofile="b/himbaechel/arch.cc")))
        bind(patch)
        arch_object = out / "arch.cc.o"
        run([link_args[0], *compile_flags, "-c", source, "-o", arch_object], "compile_lookup")
        bind(arch_object)
        candidate_exe = out / "nextpnr-himbaechel"
        run(relink(candidate_exe, arch_object=arch_object), "candidate_link"); bind(candidate_exe)
        probe_object = out / "probe.cc.o"
        run([link_args[0], *compile_flags, "-c", bench, "-o", probe_object], "compile_probe"); bind(probe_object)
        probe = out / "lookup-equivalence"
        run(relink(probe, arch_object=arch_object, main_object=probe_object), "probe_link"); bind(probe)
        text = run([probe, DEVICE, DATABASE], "lookup_equivalence", timeout=2400)
        if ("PASS lookup equivalence:" not in text or
                "PASS context lifetime checks: 3 contexts, 4 visits, 980016 comparisons" not in text or
                "Full native architecture integrity remains required." not in text):
            raise ValueError("Missing diagnostic completion markers")
        run([candidate_exe, "--version"], "version")
        for p, h in report["inputs"].items():
            if sha(p) != h: raise ValueError(f"Input changed during build: {p}")
        report.update(status="PASS_LOOKUP_EQUIVALENCE_NOT_ARCHITECTURE_CHECKED",
                      executable={"path": str(candidate_exe), "sha256": sha(candidate_exe)},
                      equivalence_log=str(out / "lookup_equivalence.log"),
                      remaining="Complete unchanged native --test, actual GPU P&R, assembly, electrical/timing/physical signoff")
    except BaseException as e:
        report.update(status="FAIL" if isinstance(e, Exception) else "FAIL_INTERRUPTED",
                      failure=str(e) or type(e).__name__); save(); print(str(e), file=sys.stderr)
        return 130 if isinstance(e, KeyboardInterrupt) else 1
    save(); print(json.dumps({"report": str(out / "report.json"), "status": report["status"]}), flush=True)
    return 0


if __name__ == "__main__": raise SystemExit(main())
