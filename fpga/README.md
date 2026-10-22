# tiny-gpu on YPCB-00338-1P1

This board port executes **the actual tiny-gpu RTL**, with two cores, four
threads per block, all original arithmetic including DIV, and all four data
channels. A synchronous arbiter connects those channels to on-chip program
and data BRAMs. The autonomous demo loads and checks the upstream matrix
addition and matrix multiplication kernels sequentially. No host CPU computes
the FPGA results. The existing `vp/` SystemC and QBox models remain separate
behavioral software models.

The FPGA wrapper enables `PIPELINED_DIV=1`: DIV computes its upper four
quotient bits in the existing WAIT cycle and its lower four in EXECUTE.
Register writeback and instruction sequencing use the existing UPDATE cycle.
The upstream GPU, core and ALU default this option to 0. This change addresses
the first completed route's 35.313 MHz divider path. The reset-corrected route estimates
97.428 MHz against 50 MHz. This is open-source estimated timing; full
XC7K480T-2 timing and electrical signoff remain pending.

The target is `xc7k480tffg1156-2`, using the onboard 50 MHz clock. The source
board files are the local `~/ypcb/ref/ypcb_00338_1p1_hack/` checkout and the
[public board reference](https://github.com/TiferKing/ypcb_00338_1p1_hack).
Only clock and LED pins are used. Running this demo needs a powered
card and working JTAG cable; it does not need PCIe enumeration or external DDR.
The selected preparation profile follows the active openTPU YPCB build at
`~/openTPU/boards/ypcb-00338/constraints/otpu_top_ld.xdc`:
AA28 at 50 MHz with LVCMOS18, `CONFIG_VOLTAGE=1.8`, and `CFGBVS=GND`.
The user selected this reference profile. openTPU's `create_project.tcl`
loads this XDC for its current `otpu_fpga_top_ld` top; its board documentation
records production use of that design. The archived vendor XDMA LVCMOS33
clock choice remains historical evidence, recorded in
`build/ypcb/board-reference-check.json`; it is not the selected profile.
The exact openTPU source revision, hashes and findings are recorded in
`build/ypcb/opentpu-profile-review.json`.

## Historical candidate (2026-10-06)

The reset-corrected candidate recorded on 2026-10-06 is
`build/ypcb/openxc7-1791294584961856221/tiny_gpu_demo.bit`:
18,735,173 bytes, exact part `xc7k480tffg1156-2`, SHA256
`2b64691f5a0be6deed105fb720e8896310ef246391179aaddae9c55bb9e1bd5b`.
These candidate, preparation and mapped reports describe historical source
snapshots. Their input hashes do not validate the updated working-tree tooling;
create fresh preparation and verification reports for current sources.

Its `report.json` and adjacent `execution-result.json` record native/wrapper
exit 0 and verification of all 1,729 bound inputs and 13 artifacts.

The top has no R28 reset port. Four INIT=0 flip-flops hold reset for the first
four 50 MHz oscillator edges after configuration. RTL and mapped tests pass,
including both original kernels after each of two Xilinx GSR releases.
The actual native route estimates 97.428 MHz against 50 MHz and validates all
12,067 placed cells, both BRAMs and four exact package pins/sites/tiles.
Legal, nonempty exact-part frames and the complete bitstream header/payload
pass validation. See [STATUS.md](STATUS.md) for exact evidence and remaining
requirements.

That historical candidate uses AA28/LVCMOS18 with the user-selected openTPU
configuration metadata, 1.8 V and CFGBVS GND. The source XDC explicitly records
those values; native assembly does not replace full electrical/configuration
DRC. The native estimate does not provide independent XC7K480T-2 timing or
electrical signoff. Physical LED polarity remains an observation check.
The read-only USB check at 2026-10-06T14:13 UTC is unavailable (`libusb: -99`),
so cable state is unknown. No FPGA or flash programming was performed.

The old R28-dependent bitstream is historical. Its source snapshots and
original failures are preserved in [PREPARATION_HISTORY.md](PREPARATION_HISTORY.md).

## Repeatable preparation

```bash
cd ~/tiny-gpu
make ypcb-generated-check
make ypcb-test       # Icarus + Verilator, real RTL
make ypcb-synth      # the same tests, then Yosys XC7 primitive mapping
python3 fpga/tools/board.py --check
python3 fpga/tools/inventory_home.py
```

The read-only board check prints firmware/tool results even when `lsusb`
fails. In that case it exits 1, records `usb.status=UNAVAILABLE` and
`cables=null`; an unavailable USB scan does not prove that a cable is absent.
Detection and programming require a successful scan and exactly one cable.

Required tools are `python3`, `sv2v`, `iverilog`, `vvp`, `verilator`, a C++
compiler, and `yosys`. `cocotb` is not needed for these board tests. Existing
upstream `make test_matadd` / `make test_matmul` still use cocotb. Workload
images are generated from the actual literal programs/data in those tests;
`--check` rejects stale generated images.

Every preparation attempt creates a separate directory under `build/ypcb/`
with source SHA256s, tool paths/versions, exact commands, logs, and a report.
A report can pass only after bounded simulations emit their completion
markers and results compare equal. Mapping additionally requires both BRAMs
and no remaining generic Yosys logic cells. `$scopeinfo` hierarchy metadata
is accepted, as it is ignored by nextpnr's importer. Inherited upstream Verilator warnings
are retained in reports. The board wrapper is converted with sv2v because the
upstream source uses unpacked-array resets and other nonportable SV constructs.

To functionally test the actual mapped primitives after a synthesis report:

```bash
python3 fpga/tools/mapped_check.py build/ypcb/<attempt>/report.json
```

This uses unmodified, pinned Xilinx UNISIM functional models, including
RAMB18E1/RAMB36E1 and DSP48E1, with their license preserved under
`fpga/tests/vendor/`. Bare declarations of RAM in Yosys `cells_sim.v` are
insufficient. Mapped simulation has no routed/SDF delays and proves neither
board timing nor a physical result.

Additional host-loaded arithmetic kernels run against the unchanged converted
source from a passing preparation:

```bash
python3 fpga/tools/arithmetic_check.py build/ypcb/<attempt>/report.json
```

This executes ADD, SUB, MUL and DIV with two operand sets at 1/3/5/9/17 threads,
checking 280 thread results and every data-memory byte after all 40 kernels.
Reference values are generated independently with Python integer arithmetic;
all divisors are nonzero. The separate report binds the original preparation,
converted source, fixtures, bench and actual simulator binaries. It is an RTL
functional check, without mapped/routed delays or physical execution.

## What the tests cover

- Both original kernels, configuration-time board reset, sticky
  success, and both LED polarities.
- Mapped primitives execute both original kernels after each of two simulated
  configurations using Xilinx UNISIM GSR and primitive INIT values.
- Six executions with varied matrix inputs, including 8-bit wraparound.
- 1, 3, 5, 9, and 17 threads: inactive lanes, partial blocks, and redispatch.
- Host request/response stability, instruction-memory readback, unsupported
  addresses, invalid thread counts, and rejection of memory writes/start while
  running.
- Infinite-kernel watchdog, timeout reporting, reset, and subsequent execution.
- Corrupted and four-state X output rejection, sticky failure, and reset
  recovery. The X check is performed with Icarus.
- All 65,280 defined unsigned 8-bit DIV pairs against integer arithmetic and
  the default ALU, plus zero/X results, stalled WAIT, disabled lanes, reset
  recovery and the other arithmetic operations. This four-state check uses
  Icarus and compares outputs at the same EXECUTE edge.

These tests exposed a scheduler bug: the last thread's `next_pc` was selected
even when that lane was disabled in a partial block. `src/scheduler.sv` now
selects thread 0, which is active for every nonempty block. Branch divergence
remains unsupported as in upstream tiny-gpu.

## Board indicators and reset

| Signal | Package pin | Meaning |
|---|---|---|
| SYS_CLK | AA28 | 50 MHz, LVCMOS18 |
| LED0 (red) | P30 | Both kernel results passed |
| LED1 (green) | M30 | Failure; remains asserted until reset |
| LED2 (yellow) | N30 | Heartbeat |

The reset pipeline starts at zero at FPGA configuration, holding the demo in
reset for four oscillator edges. R28 is unused, matching openTPU's board-port
choice. This demo uses the 50 MHz oscillator directly, so it needs neither an
MMCM lock signal nor a PCIe reset input. Reloading the FPGA restarts the demo;
the SoC host interface retains its tested execution-reset operation.
The local reset releases on oscillator edges, consistent with
[AMD's startup synchronization guidance](https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/Controlling-and-Synchronizing-Device-Startup).
LED polarity still requires observation on the actual card. Set
`LED_ACTIVE_LOW=1` at synthesis if the indicators are electrically active-low.
The heartbeat uses counter bit 25: at 50 MHz its period is about 1.34 seconds.
The pin XML/workbook identify these LED colors. openTPU documents R28 as
unwired and omits it from the production top; this design also omits it.

## Host register interface

`tiny_gpu_soc` exposes a single outstanding synchronous host transaction.
Hold `host_valid`, direction, address, and data until `host_ready`; lower valid
for at least one clock before the next request. `host_error` accompanies a
rejected transaction. Memory reads take two clocks; responses stay stable
until valid drops. Accesses have implicit widths shown below, with data in the
low bits of the 32-bit bus. There are no byte strobes or unaligned accesses.

| Byte address | Access | Function |
|---|---|---|
| 0x0000 | R/W | Thread count, 1–255 |
| 0x0004 | W | Write 1 to launch an idle, configured GPU |
| 0x0008 | R | Bit 0 done, bit 1 busy, bit 2 timed out |
| 0x000c | W | Write 1 to reset execution; memory contents preserved |
| 0x0010 | R | GPU run clocks |
| 0x0014 | R | Identity/version 0x54475001 |
| 0x1000 + 2*i | R/W | 16-bit instruction i, 0–255 |
| 0x2000 + i | R/W | 8-bit data i, 0–255 |

Reset execution between launches. The default watchdog is 1,000,000 clocks
(20 ms at 50 MHz). Memory accesses are rejected while busy. This bus is used
by the on-card demo; an external JTAG MMIO or PCIe host transport is **not yet
connected**. Existing QBox ioctl code is a software-facing reference for a
future transport, not a driver for this FPGA bitstream.

## Bitstream build with openXC7

openXC7 is the selected build flow for this board port. The current `.bit`
was produced by Yosys, nextpnr and Project X-Ray, with no Vivado dependency.
The native route, exact-pin placement, frames and final bitstream checks pass.
Full Vivado is an optional cross-check; its absence does not block this flow.
The native timing-model limitations described below remain part of the evidence.

The completed open-source route is local under `build/ypcb/`, using the
maintained [openXC7/nextpnr](https://github.com/openXC7/nextpnr) Himbaechel
Xilinx backend. Its source pin is `c68c13582e972292c86a5025140d52e713384cbc`;
its own CI pins Project X-Ray DB `517d66a383676cb971177ea92b0ff3b6ea6e8690`
and Project X-Ray `ed3331c6200f421164101388759fc2860b0f5634`.
The older `~/rknpu-fpga` nextpnr/database experiments had failed integrity
checks and are retained as references, rather than adopted for this design.
Native compilation, device-database generation, placement/routing, frame
assembly, and physical signoff are separate stages; a running build or
synthesis success is not a bitstream or board pass.

Reproduce the pinned native tools and then place/route a passing preparation:

```bash
python3 fpga/tools/bootstrap_openxc7.py --jobs 2
python3 fpga/tools/mapped_check.py build/ypcb/<attempt>/report.json
python3 fpga/tools/openxc7.py build/ypcb/<attempt>/report.json
```

The historical reset-corrected preparation and mapped check passed on
2026-10-06. The following records that run's command; its source-bound reports
are not reusable after changes to their inputs. Use fresh report paths to
build the updated working tree:

```bash
python3 fpga/tools/openxc7.py \
  build/ypcb/20261006T132509Z-1791293109938073395/report.json \
  --mapped-report build/ypcb/20261006T132509Z-1791293109938073395/mapped-check-1791294029647816110/report.json \
  --nextpnr build/ypcb/indexed-pip-lookup-1791249124670098489/nextpnr-himbaechel \
  --chipdb build/ypcb/chipdb-snapshot-1791225384442307175/chipdb-xc7k480t.bin \
  --architecture-report build/ypcb/architecture-check-1791250929474836590/report.json \
  --place-route-timeout 28800 --assemble
```

P&R requires the latest mapped functional check to pass for this same
preparation, with its netlist, bench and UNISIM model hashes unchanged. An
explicit `--mapped-report` can select a completed check. Those inputs and
the tested RTL remain bound to the P&R report through the end of execution.
The compiled backend must also pass `--test` against the exact XC7K480T
database and package before placement/routing. Executable startup alone is
not a database-integrity result; the command and log are retained separately.

Before assembling bits, check the exact-part frame tools and compare the
cached converter with its untouched reference. Each command prints its
separate report path:

```bash
python3 fpga/tools/check_frame_tools.py
python3 fpga/tools/check_frame_tools.py --uncached
python3 fpga/tools/check_frame_tools.py --compare <cached-report.json> <reference-report.json>
python3 fpga/tools/openxc7.py build/ypcb/<attempt>/report.json --assemble
```

The converter's `Database.grid()` rebuilds the whole tile grid on each call.
`fasm_to_frames.py` reuses that read-only object per database instance while
executing the unchanged pinned converter. Assembly requires a source-bound
byte-for-byte comparison of the actual frame files. The empty-design check
tests the frame tools and is not a GPU bitstream or hardware result.
Both converter runs bind the complete Kintex database, converter/FASM sources,
and virtual-environment interpreter and packages before execution. Fresh
cached and `--uncached` checks are required for the updated tooling; comparison
rejects older reports that lack this dependency binding. Hashing present-day
files cannot upgrade an old proof.

The bootstrap reuses `~/rknpu-fpga/build/openxc7/prefix` for Eigen headers when
available; provide `--eigen-prefix` for another installation. It builds only
the XC7K480T database and installs Python frame-tool dependencies in a local
Python 3.13 virtual environment. Sources, binaries, database and logs live in
`build/ypcb/`; other project checkouts and host shell settings are unchanged.
Native builds have an eight-hour per-command bound, configurable with
`--build-timeout`; the exact-device import has already exceeded two hours
under shared host load. IPO is disabled to avoid a redundant link-time
optimization stage. This does not remove FPGA resources or GPU operations.
The P&R runner preserves 50 MHz and uses no timing-failure/unrouted waiver.
For a separately compiled executable from the same pinned backend, supply
`--nextpnr /absolute/path/to/nextpnr-himbaechel`. The exact XC7K480T chipdb is
still required and supplied separately; the executable path/hash are recorded.
A separately completed exact-device database can be selected with
`--chipdb /absolute/path/to/chipdb-xc7k480t.bin`. When its directory contains
our native BBA assembly `report.json`, the runner verifies both source pins,
completed binary and all recorded assembly-input hashes. Full native
architecture integrity remains required for that exact package.
An isolated local lookup candidate is built with
`python3 fpga/tools/build_pip_lookup.py`. It relinks the retained native objects
to reproduce the verified original binary, changes only the pip-name lookup
to use the existing destination-wire adjacency index, and compares it with
the original algorithm on the actual database. This equivalence check does
not replace architecture validation. Run the complete native test with:

```bash
python3 fpga/tools/architecture_check.py <completed-lookup-build-report.json>
```

A separate indexed variant avoids scanning every destination wire on every
lookup:

```bash
python3 fpga/tools/build_indexed_pip_lookup.py
```

Both lookup builders default to the completed bootstrap artifacts in
`build/ypcb/nextpnr-build` and discover the latest passing bootstrap report.
They require a source-bound bootstrap from the updated tooling. Use
`--build-dir`, `--source`, `--chipdb`, and `--build-report` to select other
verified inputs. For example, the historical isolated native build used
`--build-dir build/ypcb/nextpnr-cli-build`,
`--chipdb build/ypcb/chipdb-snapshot-1791225384442307175/chipdb-xc7k480t.bin`,
and `--build-report build/ypcb/nextpnr-cli-build-manifest.json`; its recorded
input hashes still need to match before reuse.
The bootstrap selects CMake's Unix Makefiles generator because these isolated
relinks consume its `flags.make` and `link.txt` metadata. Other generators are
rejected by preflight rather than treated as compatible builds.

It changes the lookup and adds a constructor cache reset, preserving the class
layout, backend objects, original first-match/inversion rules and native
integrity assertions. Its bounded process-local cache retains all duplicate
wire names. The real-database comparison also exercises interleaved and rebuilt
contexts: three contexts, four visits and 980,016 comparisons. Compilation and
comparison must finish successfully before its report can be supplied to the
same complete native architecture check. See [STATUS.md](STATUS.md) for actual
completion; source inspection or a running build is not a validation result.

The native test defaults to a 7,200-second bound. For this large device under
shared load, `--timeout 28800` selects the supported eight-hour bound. A passing
report still requires native exit 0, all five integrity phases and unchanged
input hashes. Each attempt has its own report; timed-out attempts remain failed.

A completed passing integrity record can be supplied to the P&R command as
`--architecture-report <completed-integrity-report.json>`, together with the
matching `--nextpnr` and `--chipdb`. It verifies the actual exit status, all
five ordered integrity phases, executable/database/package, log and every
build input hash. The report binds the compiler's local patch and records the
reused test explicitly. A RUNNING or failed record is rejected before P&R.
Placement/routing defaults to a 7,200-second limit. An explicit
`--place-route-timeout 28800` allows up to eight hours while retaining the full
GPU, 50 MHz constraint and every validation gate. Stage reports record the
selected bound, live process CPU/RSS, actual exit code and elapsed time.
Timeouts terminate the owned process group, reap the child, and remain failures.
`python3 -B -m unittest discover -s fpga/tests -p 'test_*.py' -v` checks the
build/placement/configuration gates and real process timeout/cleanup behavior.
Its literal XDC records the LED observation exception which nextpnr does not
apply; no internal path is exempted. CONFIG_VOLTAGE/CFGBVS are validated as
the selected source-XDC metadata and recorded in the native report. They are
Vivado electrical properties and are omitted from nextpnr's I/O-only XDC;
the native flow does not perform configuration/electrical DRC.
A candidate bitstream still needs the
explicit remaining electrical/timing/physical checks listed in its report.
The runner also checks the actual placement dump and routed pad attributes:
exactly four pads, their package pins, physical sites/tiles, LVCMOS18,
directions, complete cell placement, and both BRAMs. This catches pin-location
errors even if the constraint parser does not report them.
The routed top is matched to the verified synthesis top's source annotation
and exact port shapes. PAD connections must match the routed top bits. The
pinned writer defaults the module name to `top`; its post-route hook writes
physical site/BEL names while the placement dump retains raw grid names.
The previous revision's normalized-top failure was recovered without
repeating P&R. That narrow recovery required native exit 0, the original
failed report, artifact hashes and exact old reader/runner snapshots.
It rechecked source/tool/clock/placement/frame gates in a separate candidate
directory. The failed reports remain preserved in [PREPARATION_HISTORY.md](PREPARATION_HISTORY.md).

The first recovery's native converter exited 0, but its old log reader
mistook a handled `ImportError:` fallback warning for an error. Those valid
frames were independently checked and used by the completed finisher.
That recovery verified the exact original runner snapshot, terminal exits,
source/artifact hashes, conversion log and legal nonempty frame data before
native assembly. It wrote a fresh candidate directory without repeating
conversion or P&R. Two diagnostic tests check handled warnings and actual
errors. All original failed reports remain unchanged. Those recovery helpers
require their original source profile; the changed reset top needs fresh P&R.

The pinned backend's generator uses a `DEFAULT` speed grade and placeholder
LUT/register/site delays. It substitutes Artix-7 SDF for Kintex-7 carry, mux,
and BRAM timing. The estimate therefore does not establish XC7K480T-2 setup
or hold closure; the report records and hashes these timing sources.
Frame assembly rejects invalid-address/word diagnostics, checks legal frame
addresses and 101-word data against this exact part's `part.json`, and rejects
an empty GPU configuration before checking the resulting `.bit` header.

An earlier runner rejected `$scopeinfo` after otherwise successful mapping.
For that exact classifier error only, the original failed report and runner
snapshot can be retained and rechecked with:

```bash
python3 fpga/tools/recheck_mapping.py build/ypcb/<original-attempt>/report.json
```

This requires unchanged tested source, constraints and successful original
commands. A fresh sv2v conversion must match the compiled/mapped design, and
all Icarus and Verilator binaries execute again. The new report identifies
the reused synthesis command and hashes; it does not rewrite the original.
If that same runner timed out during mapping, add `--resynthesize` to rerun
only mapping after conversion/replays. The mapper has a two-hour bound;
simulation builds are retained and no partial netlist is accepted.

## Optional Vivado cross-check

The historical 2026-10-06 source snapshot is
`build/ypcb/vivado-source-bundle-1791294825793650197/tinygpu-ypcb-source.tar.gz`
(187,176 bytes, SHA256
`8f3ee04ebf62e9847058961d79f2fd438f9e0d980041961948534e8434097255`).
Its `BUILD.txt` contains the exact selected-profile commands and report
retention instructions. The adjacent `report.json` records successful hash,
workload and make-plan checks against a clean extraction. It contains sources,
not an FPGA image or full Vivado result. Its hashes bind the historical
sources, not the updated checkout. Produce fresh verification reports before
packaging current sources; the old bundle remains an archival artifact.

Full Vivado can build the exact part with:

```bash
make ypcb-vivado
```

By default the Tcl flow writes routed checkpoints and utilization/timing/DRC
reports. To select the user-approved openTPU board profile explicitly and
request a `.bit` on a full Vivado installation:

```bash
TINYGPU_CLOCK_IOSTANDARD=LVCMOS18 \
TINYGPU_CONFIG_VOLTAGE=1.8 \
TINYGPU_CFGBVS=GND \
TINYGPU_EMIT_BITSTREAM=1 make ypcb-vivado
```

These are the active openTPU XDC's settings, rather than values inferred from
the LED I/O standard. The command still requires full Vivado and passing
implementation checks; it does not program hardware.
The routed clock standard must match the explicit selection and is recorded
in `electrical.txt`. The current Yosys/nextpnr candidate uses the tested
LVCMOS18 profile; a confirmed LVCMOS33 clock requires a separately verified
build with that constraint.
`python3 -m unittest fpga/tests/test_vivado_config.py -v` checks the real
pre-build Tcl validation, stopping at the first Vivado command. It covers
missing/invalid clock selections and configuration-voltage/CFGBVS pairs;
it does not execute or replace Vivado implementation.
The flow rejects negative setup/hold slack and blocking DRC violations;
no severity demotion or internal timing exception is used. It never programs
hardware. This command requires a full Vivado installation with support for
the selected part; Vivado Lab is a programming/debug tool and cannot execute
this build.

## Cable and eventual volatile load

`board.py --check` verifies all three firmware hashes and the staged DLC10
helper in `~/ypcb`, and reports the currently connected cables. Detection uses
the already validated Fedora `~/ypcb/dlc10-init.sh`, initializes cable RAM,
and requires exactly the FPGA IDCODE `0x23751093` with no extra chain devices.
It does not copy the older macOS donor's speculative CPLD entry or automatic
retry/program loop.

```bash
python3 fpga/tools/board.py --detect
# Only after reviewing a complete bitstream build and actual board identity:
python3 fpga/tools/board.py --program /absolute/path/to/tiny_gpu_demo.bit
```

The programming command validates the Xilinx `.bit` part/package header and
payload length, audits the current chain, and uses volatile FPGA SRAM loading.
Power cycling reloads the existing flash image. No flash erase/write command
is provided. Successful loading still requires observing PASS and heartbeat
on the actual card to establish a hardware result.

## Home-project reuse audit

See [PROJECTS.md](PROJECTS.md) for the inspected project list and donor choices.
The machine-readable, timestamped inventory is generated at
`build/ypcb/home-project-inventory.json`. Existing uncommitted `vp/` work and
other projects are preserved. No commit, push, FPGA load, or flash write was
performed as part of preparation.
