# Historical preparation records

The observations below were preserved before the final candidate handoff.
Statements about active jobs or pending stages apply to their recorded time.
See [STATUS.md](STATUS.md) for the current result.

# Current YPCB preparation status

Observed UTC: 2026-10-06T10:20:15.371653+00:00.

The earlier combinational-divider P&R retry completed with native and wrapper exit 1: its routed
estimate is 35.313 MHz. The critical path traverses a thread's combinational
DIV logic. Its routed JSON, FASM, placement, timing, logs and six source
snapshots are preserved in `build/ypcb/openxc7-1791274494013479030/`.
The adjacent `execution-result.json` records both actual exit codes and the
completed audit of all 1,721 bound inputs. Assembly did not start.

A new FPGA-only `PIPELINED_DIV=1` option splits DIV into two four-bit stages
using the existing WAIT and EXECUTE cycles. The upstream default remains 0.
The board SoC enables the option without changing the scheduler or instruction
sequence. The exhaustive four-state divider check passes all 65,280 nonzero operand
pairs plus zero/X, stalled WAIT, inactive-lane, reset and other arithmetic
checks: `build/ypcb/divider-check-1791277934293914760/report.json`. Fresh board
simulation, synthesis, mapped simulation and arithmetic proofs are completed
below. The newer native route passes its 50 MHz estimate; assembly and physical
signoff remain separate. Historical reports later in this file describe prior RTL.

All four fresh Icarus benches pass in
`build/ypcb/20261006T091331Z-1791278011531255368/report.json`: demo, host
protocol, fault/reset and divider. Both Verilator board benches also pass. Fresh synthesis passed with
both RAMB18E1 memories, no generic logic and zero check problems; preparation
session 24844 exited 0. The adjacent `execution-result.json` verifies all
27 source and 27 artifact hashes. The downstream arithmetic and mapped
checks completed in session 25717, with source/helper hashes: `build/ypcb/post-divider-verification-1791278468090250654/report.json`.

Fresh host-loaded arithmetic also passed all 40 kernels, 280 thread results
and all 256 data bytes after each kernel, including DIV at 1/3/5/9/17 threads:
`build/ypcb/arithmetic-check-1791278874755083888/report.json`. Both native
commands exited 0 and all bound inputs still match. The new mapped primitive
matrix test also passes both kernels twice across reset, 3,921 clocks each:
`build/ypcb/20261006T091331Z-1791278011531255368/mapped-check-1791279044298211122/report.json`.
The downstream wrapper exited 0 and its adjacent `execution-result.json`
verifies all 64 bound inputs.

The full two-core native P&R completed with exit 0 and an estimated 93.197 MHz
against 50 MHz, after 1,261.082 seconds:
`build/ypcb/openxc7-1791279462406736988/report.json`. It routed all nets,
reported no hold violations and emitted routed JSON, FASM, timing and placement.
The wrapper exited 1 because the placement reader assumed the original top
name rather than the pinned writer's `top`. The adjacent `execution-result.json`
preserves both actual exits and the completed audit of all 1,733 bound inputs.
The failed report and original reader/runner snapshots remain unchanged.

The corrected reader verifies the source top annotation, exact port shapes and
PAD connections. It compares physical site/BEL names written by the backend's
post-route hook, while retaining the separate raw himbaechel name. Actual
validation passes all 12,014 cells, both BRAMs and all five exact package pins,
sites, tiles, directions and LVCMOS18 properties. All 27 build, placement,
process and Vivado configuration tests pass (session 27451, exit 0).
Assembly-only recovery is running in session 90338 via
`fpga/tools/resume_openxc7.py`. It validates the preserved artifacts, accepts
only the known reader/runner changes through exact snapshots, and assembles a
fresh candidate with the original frame/header gates. No duplicate P&R runs.
The converter completed with exit 0 after 440.232 seconds:
`build/ypcb/openxc7-resume-1791281285801037576/report.json`.
Its 45,892 supplied frames are legal for the exact part, with 62,990 nonzero
words and 444 legal frames left for assembler zero-fill. The wrapper matched
`error:` inside a handled `ImportError:` parser-fallback warning and exited 1.
Its adjacent `execution-result.json` preserves actual exits, all 1,736 bound
input checks, frame/log/report hashes and the exact runner snapshot.
The warning reader is corrected, with two additional diagnostic tests passing.
`fpga/tools/finish_openxc7.py` validates and reuses those frames for assembly;
it does not repeat conversion or P&R. No candidate bitstream or physical
signoff is claimed yet.

The board port executes the real two-core tiny-gpu RTL with four threads per
block and four arbitrated data channels. All current-source Icarus and
Verilator board/host tests pass: both original matrix kernels, six varied-input
kernels, 1/3/5/9/17-thread partial blocks, busy-access rejection, watchdog,
and recovery. Four-state corrupt/X-result rejection passes with Icarus.
The additional source-bound host arithmetic suite passes:
`build/ypcb/arithmetic-check-1791227350712649357/report.json`. It executes
40 ADD/SUB/MUL/DIV kernels through the actual two-core GPU, verifies 280 thread
results at 1/3/5/9/17 threads and checks all 256 data bytes after each kernel.
Its nonzero-divisor fixtures cover integer truncation, high-bit values,
underflow and overflow. This is RTL execution, not mapped or physical proof.
Those completed reports bind the HDL before the divider timing change above.
The scheduler PC bug found in partial blocks is fixed. All 46 visible home
directories were inventoried in the refreshed scan. The three DLC10 firmware hashes and existing
staged Fedora helper are verified.

The original source-bound run at
`build/ypcb/20261005T133048Z-1791207048789320847/report.json` records all 16
completed commands passing, followed by an actual 1800-second synthesis
timeout during ABC mapping. It remains unchanged as failed evidence.

The runner is now corrected to accept `$scopeinfo` hierarchy metadata and
reject generic logic, missing BRAMs and incorrect board ports. Seven directed
build-gate tests pass, including exact-part frame corruption checks. Mapping has a 7200-second bound. The completed recovery is
`build/ypcb/recheck-1791211205550980240/report.json`: its fresh conversion
byte-matches the previously compiled design, all five simulator executables
replay successfully, and fresh resynthesis passes. Its artifacts and source
hashes were independently checked: two RAMB18E1 memories, no generic logic,
and zero problems in both Yosys checks. Tested HDL,
constraints and workloads still match their original hashes; simulation
builds are reused, and each executable runs again. The earlier separate
source mapping with two BRAMs is not accepted for the corrected RTL.

The pinned maintained openXC7 nextpnr executable has finished building, with
exit code 0. Its actual `--version` and `--help` checks also pass. The complete
Xilinx backend was compiled with IPO disabled and the chipdb supplied
externally; no device or GPU capability was removed. Executable/source/cache
and log hashes are recorded in
`build/ypcb/nextpnr-cli-build-manifest.json`.

The exact XC7K480T native database has been assembled successfully: 63,345,877
bytes. A closed, complete BBA snapshot was assembled while the original Python
process finished. The original CMake database target subsequently completed;
its BBA and both binary copies byte-match the independently assembled snapshot.
The two source-bound records are
`build/ypcb/chipdb-snapshot-1791225384442307175/report.json` and
`build/ypcb/nextpnr-chipdb-build-manifest.json`. Only the original redundant
executable compilation was cancelled, after those completed artifacts matched.
The separately built complete nextpnr executable remains verified.

The original integrity run reached pip-name checking, but its execution handle
became unavailable when the environment switched to a managed sandbox. Its
last RUNNING report remains unchanged; no native exit was observed. The new
sandbox process namespace cannot expose its earlier workers, and a read-only
host D-Bus query was denied. `build/ypcb/execution-context-recovery.json`
records this observation gap, not a claimed native failure or pass.

The full integrity/P&R/assembly pipeline has been resumed in a new managed
session from the completed immutable tools/database, with a separate output
directory. It still requires every native integrity phase, the unchanged real
two-core GPU, 50 MHz, full placement/pin/BRAM checks, and valid nonempty frames.
No database generation or GPU synthesis was restarted. That attempt did not establish architecture integrity,
GPU placement/routing or candidate-bitstream assembly.
The managed attempt
`build/ypcb/openxc7-1791227839541162839/report.json` failed at the actual
7200-second limit during native pip-name round trips. Its failure report,
logs and exact runner snapshot are preserved; `execution-result.json`
records wrapper exit 1 without inventing a native exit code. Location,
connectivity, bucket-data and P&R did not complete in that attempt.

A read-only layout count finds 209,267,576 represented pips. The original
linear name lookup would examine 352,538,011,105 entries if all round trips
are unique; this is a workload calculation, not validation or native progress.
`build/ypcb/database-workload-counts.json` records the database/layout hashes.
An isolated lookup candidate uses the existing destination-wire adjacency
index and preserves the first matching edge and inversion qualifier. It changes
one function, with the original class layout and all native integrity assertions.
Relinking the retained objects reproduces the verified original executable
byte for byte. The candidate's real-data comparison against the original
algorithm passes 245,004 cases across all 98 represented tile types and 40,834
type-level pips, including reversed names, inversion qualifiers and missing
wires. Its record is
`build/ypcb/pip-lookup-recheck-1791233512064460050/report.json`.
The first diagnostic compile failed on an error-message API name; the failed
report and original diagnostic are preserved, and recovery recompiles only
the corrected diagnostic. Native compilation/linking are reused with input
hash checks. This equivalence result is not architecture validation.

The candidate's first complete native check reached the actual 7200-second
limit during pip-name checking:
`build/ypcb/architecture-check-1791234256810965872/report.json`.
The wrapper exited 1 and observed native SIGTERM exit -15 after 7,203.509
seconds. Its last telemetry recorded 1,667.77 CPU seconds over 7,199.873
elapsed seconds. The report/log hashes and both terminal job results are
preserved in the adjacent `execution-result.json`. This is a timeout failure,
not architecture validation; no location/connectivity/bucket pass is claimed.

The same executable/database and complete exact-package `--test` have passed
with the original assertions and an explicit 28,800-second bound:
`build/ypcb/architecture-check-1791241546997172246/report.json`.
The native process exited 0 after 25,180.492 seconds, completing entity names,
locations, connectivity and bucket checks. The runner's final audit verified
all 1,634 bound input hashes and completed at 2026-10-06T06:07:11.163657+00:00.
The wrapper also exited 0; the adjacent `execution-result.json` preserves both
terminal results and final report/log hashes. This validates the exact native
executable/database/package, while GPU P&R and physical signoff remain pending.

The separate indexed candidate's native build and comparison have completed:
`build/ypcb/indexed-pip-lookup-1791249124670098489/report.json`.
Its baseline relink byte-matches the verified original executable; both native
objects and both candidate/diagnostic links exited 0. The real-data comparison
passes 980,016 cases across three contexts and four visits, covering all 98
represented tile types and 40,834 type-level pips on every visit. Interleaving
and reconstruction are exercised. All 1,631 recorded input hashes match.
The candidate executable SHA is `58c47c834e825819388c64bf12737b26330500a73f221e942633f37508fc912a`.
It adds a bounded wire-name index and resets it on every constructor call,
without changing the class layout or any native architecture assertion. All
duplicate wire names and first-match/inversion rules are retained.

The indexed candidate's complete exact-package native test has also passed:
`build/ypcb/architecture-check-1791250929474836590/report.json`.
It exited 0 after 18,020.461 seconds, completing names, locations, connectivity
and bucket checks with all original assertions. The final audit verified all
1,633 bound input hashes, completing at 2026-10-06T06:43:41.764298+00:00.
The wrapper exited 0; the adjacent `execution-result.json` preserves both
terminal results and final report/log hashes. This is native architecture
validation, while GPU P&R and physical signoff remain separate requirements.

The first GPU P&R attempt used the original validated adjacency candidate:
`build/ypcb/openxc7-1791266949087985306/report.json`. It accepted the completed
native proof and finished analytical placement, then hit its actual 7,200-second
limit during refinement at iteration 60. The wrapper and continuation exited 1.
No routed design, timing report, FASM, frames or GPU bitstream completed.
The adjacent `execution-result.json` preserves the failed report/log hashes and
exact runner snapshot. The older timeout handler did not record the native
kill/wait returncode; no native exit code is claimed for this failed P&R.

A single retry ran from the unchanged mapped GPU and exact database,
using the indexed executable with its completed full native integrity proof:
`build/ypcb/pnr-retry-1791274468164888359/report.json`.
The explicit placement/routing limit is 28,800 seconds. The updated runner
records live CPU/RSS and actual exit codes, terminates its owned process group
on timeout and reaps its child. All 25 build, placement, process and Vivado
configuration checks pass; CLI out-of-range limits are rejected before launch.
The source-bound review is `build/ypcb/pnr-retry-1791274468164888359/review.json`.
This retry retains the full two-core GPU, 50 MHz, both BRAMs and all routing,
placement, timing and frame gates. It does not repeat synthesis or native
integrity, and no duplicate P&R was launched. The completed indexed proof was
accepted as `REUSED_PASS`; actual P&R completed at
`build/ypcb/openxc7-1791274494013479030/report.json`. Placement and refinement
finished, and routing emitted all four requested artifacts. The estimate was
35.313 MHz against 50 MHz, so native nextpnr and the pipeline exited 1 after
3,198.723 seconds of P&R. No hold violations were reported. This remains a
failed timing result; no frame or bitstream assembly was attempted.

The source/retained-object coverage audit verifies nine native input hashes:
`build/ypcb/native-integrity-coverage-audit.json`. The actual `--test` calls
names, locations, connectivity and buckets; name mismatches and `log_assert`
failures are fatal. These checks have no `NDEBUG` gate. This audits compiled
inputs; completed runtime evidence is recorded separately above.

The P&R runner can now reuse a completed full native integrity record through
`--architecture-report`, preserving all build inputs and recording the local
compiler derivation. The validator checks the exact executable/database/package,
actual exit 0, all five ordered phase markers, log SHA and every input SHA.
Both its direct call and the actual P&R CLI rejected the earlier live incomplete
record. The original waiting continuation stopped with `FAIL_NATIVE_INTEGRITY`
after the timeout; its terminal report is preserved at
`build/ypcb/pnr-after-integrity-1791236273046696614/report.json`.
The existing continuation is
`build/ypcb/pnr-after-integrity-1791241590736398870/report.json`. It observed
the completed native PASS and verified its held runner, queue-source and request
hashes, then started the same 50 MHz two-core GPU P&R/assembly wrapper at
2026-10-06T06:07:24.668698+00:00. Its explicit 30,000-second
wait bound accommodates the longer native run. It stops on an integrity failure. No native check
is skipped or marked passed because it timed out.

The pinned native frame assembler build passes; its executable/source/compiler
provenance is `build/ypcb/frame-assembler-build-manifest.json`. Both actual
exact-part empty-design frame-tool runs pass, including legal-address/101-word
checks, C++ frame-to-bit conversion and the bitstream part/payload header.
Their frame files compare byte for byte: 45,892 supplied frames, 444 missing
legal frames zero-filled by the native assembler. The source-bound proof is
`build/ypcb/frame-grid-cache-check.json`. This is tool verification, not a GPU
bitstream or physical result. A prior 600-second timeout remains preserved.

The project-local adapter caches the read-only per-device Grid while executing
the unchanged pinned converter. Its actual run used 11 lookups / 1 construction;
the cached/reference output equivalence is proved for this complete target.
The tracked reproduction tool is `fpga/tools/check_frame_tools.py`. Assembly
requires the unchanged comparison proof and checks legal nonempty GPU frames.

Mapped UNISIM functional simulation passes both original kernels twice across
external reset, at 3,921 clocks each:
`build/ypcb/recheck-1791211205550980240/mapped-check-1791213013760965322/report.json`.
The completed source/model/input hashes were verified; the run took 1,686
seconds under shared host load. This has no routed delays or physical result.
P&R now requires this matching passing check, preserves its RTL/model hashes
through execution, and rechecks images against the current upstream tests.
The fresh integrity audit verifies 70 current source/artifact hashes:
`build/ypcb/source-reuse-check.json`.

The P&R runner now also requests a physical placement dump and checks all
routed cells, the five actual pads against package sites/tiles, LVCMOS18,
directions and physical BRAM placement. Six directed rejection tests pass:
`build/ypcb/placement-check-tests.log`. These fixtures test the gate; actual
GPU P&R has not run yet. No HDL, workloads or primitive models changed.

The refreshed home inventory found two new directories: LPULite's new YPCB
mailbox and host code were inspected as future transport references;
cpu-fan-diagnostics contains host diagnostic data. New verigpu mailbox/TAP
files were also inspected. No donor transport was connected or treated as
tiny-gpu proof. The old inventory and the comparison are preserved. A new read-only top-level
directory-membership check still matches all 46 entries:
`build/ypcb/home-project-directory-recheck.json`. The 23:46 UTC membership
refresh also finds the same 46 entries, with none added or removed:
`build/ypcb/home-membership-1791243987301786555.json`. Full Vivado remains
unavailable on PATH. This refresh checks directory membership and tool paths,
not all project contents. The 00:59 UTC October 6 membership refresh also
finds the same 46 entries with no additions/removals:
`build/ypcb/home-membership-1791248382567576057.json`. It has the same limited
scope and again finds no full Vivado on PATH. The subsequent donor cache
scan found only the two older rknpu databases already excluded by recorded
integrity failures. The donor DSP-fix compiler has since built; the current
GPU mapping contains no DSP cells and uses its own completed pinned compiler.

The reference pin XML/workbook identify red P30, green M30 and yellow N30
LEDs, and R28 as software reset. The board author's notes identify SW2 as
GPIO reset and SW1 as INIT_B. These are reference facts, not physical-card
observations; `build/ypcb/board-reference-check.json` records the inputs.

A follow-up inspection of tiny-tpu's newer YPCB work exposed a clock-standard
conflict. The original archive member was read directly:
`LC480T/YPCB-00338-1P1/XDMA_480T_n_clear.7z` →
`XDMA_480T_n/XDMA_480T_n.srcs/constrs_1/new/IO.xdc` assigns AA28/clk_50
LVCMOS33; the board XML/XDC and blink reference use LVCMOS18. The extracted
source and hashes are recorded in the board-reference report. Actual bank 14
supply and oscillator output remain unknown, separate from configuration-bank
voltage/CFGBVS. The tested candidate keeps LVCMOS18. P&R retains these reference
hashes when the report is present and explicitly records the unresolved check.

A read-only follow-up lists the local platform, memory-test, XDMA and board-file
archives in `build/ypcb/schematic-archive-filenames.json`. No board schematic
was found in those members. The small `LC_7K480T.rar` opens with libarchive,
although the installed 7-Zip cannot open it; it contains memory/PCIe constraints
and a pin-table screenshot. That screenshot confirms AA28/50 MHz and the LED
pins, but provides no clock or bank supply voltage. This search does not
resolve the electrical conflict.

Full Vivado bitstream emission now requires an explicit
`TINYGPU_CLOCK_IOSTANDARD` and checks that routing retains that selection.
Six tests of the actual pre-build Tcl validation pass:
`build/ypcb/vivado-config-tests.log`. They stop at the first Vivado command;
full Vivado implementation remains unavailable and unverified. No HDL,
tested XDC or workload changed. The donor's newer nextpnr DSP-fix revision
differs from this port's pin; its native assembler source also has an active
parser rejection change. Neither tool is substituted into this preparation.

The pinned open-source timing model uses a DEFAULT speed grade, placeholder
LUT/register/site delays and Artix-7 SDF for Kintex-7 carry/mux/BRAM timing.
A P&R estimate therefore cannot establish XC7K480T-2 timing signoff. Mapped
functional simulation passes; placement/routing and GPU bitstream assembly
remain unfinished. No run-ready tiny-gpu bitstream or physical pass exists yet.
Full Vivado is absent, while Vivado Lab and the staged cable tools are present.
The fresh managed-environment read-only check records `lsusb` exit 1 in
`build/ypcb/board-readonly-1791231285755584921/report.json`; it cannot establish
current device access. A separate read of USB sysfs metadata sees six entries,
no read errors and no DLC10 VID/PID, recorded alongside it in `sysfs.json`.
The checker previously exited before printing its firmware/tool report when
USB enumeration failed. That reporting bug is fixed independently of the
native build. The actual read-only recovery at 22:16 UTC verifies all three
firmware hashes and staged loader/helper, prints USB `UNAVAILABLE` with
`cables=null`, and exits 1 on `unable to initialize libusb: -99`:
`build/ypcb/board-check-recovery-1791238538905919860/report.json`.
The old checker snapshot and new source/report hashes are preserved. No
detection or programming was performed by this check.
The refreshed read-only check at 00:46 UTC on October 6 verifies the same
three firmware hashes and staged loader/helper:
`build/ypcb/board-readonly-1791247605279251721/report.json`. It again records
USB `UNAVAILABLE` (`libusb: -99`), unknown cable state, no full Vivado on PATH
and Vivado Lab present. No detection or programming was performed.
Actual clock-bank supply/oscillator output, configuration-bank voltage/CFGBVS
and physical reset/LED facts remain unverified. No physical programming was
performed.

Next: finish the resumed architecture integrity check; place/route the exact
part at 50 MHz and assemble the candidate; resolve
timing/electrical and physical-board gaps. Preserve the full tiny-gpu scope.
Commands are in [README.md](README.md); donor choices in [PROJECTS.md](PROJECTS.md).


## Preserved R28-dependent candidate status before reset correction

## Previous revision evidence

The records below describe the previous R28-dependent revision; current
verification is recorded above. Its original reports remain unchanged.

# Current YPCB preparation status

Observed UTC: 2026-10-06T10:36:28.484726+00:00.

A candidate bitstream has been assembled for `xc7k480tffg1156-2`:
`build/ypcb/openxc7-finish-1791282033490820387/tiny_gpu_demo.bit`.
It is 18,735,180 bytes, SHA256
`2fc727c675f753364c51141c33971adb7f44c9a14edd720289a62d74e1239491`.
The native assembler and wrapper both exited 0. The independent terminal audit
verifies all 1,749 bound inputs and eight artifacts. The adjacent `report.json`
and `execution-result.json` record `PASS_CANDIDATE_BITSTREAM_NOT_PHYSICAL_SIGNOFF`.
There are no live preparation jobs. No physical FPGA or flash programming was performed.

## Completed evidence

The design uses the real two-core GPU, four threads per block, all four data
channels and all original arithmetic, including DIV. Program and data memory
map to two RAMB18E1 blocks. The autonomous demo loads and verifies the original
matrix-add and matrix-multiply kernels. An external host transport is not connected.

The FPGA-only `PIPELINED_DIV=1` splits DIV across the existing WAIT and EXECUTE
cycles without changing instruction/writeback sequencing; upstream defaults to 0.
This resolves the earlier 35.313 MHz combinational-divider route. The partial-block
scheduler PC fix remains covered at 1/3/5/9/17 threads.

| Evidence | Completed result | Report under `build/ypcb/` |
|---|---|---|
| Exhaustive divider | All 65,280 nonzero operand pairs; zero/X, WAIT stalls, inactive lanes, reset and other arithmetic pass | `divider-check-1791277934293914760/report.json` |
| Preparation | All 19 commands pass: four Icarus benches, two Verilator benches and synthesis with two BRAMs, no generic logic, zero check problems; all 27 source and 27 artifact hashes verified | `20261006T091331Z-1791278011531255368/report.json` |
| Host arithmetic | 40 real-GPU ADD/SUB/MUL/DIV kernels, 280 thread results, 10,240 memory-byte comparisons pass | `arithmetic-check-1791278874755083888/report.json` |
| Mapped functional execution | Pinned UNISIM primitives; both original matrix kernels twice across reset, 3,921 clocks each, pass without routed delays | `20261006T091331Z-1791278011531255368/mapped-check-1791279044298211122/report.json` |
| Downstream proof audit | Actual wrapper exit 0; all 64 bound inputs verified | `post-divider-verification-1791278468090250654/report.json` |
| Exact native database integrity | Actual native/wrapper exit 0; all five ordered integrity phases and 1,633 bound input hashes pass | `architecture-check-1791250929474836590/report.json` |
| Full GPU P&R | Native exit 0, 1,261.082 seconds, all nets routed; estimated 93.197 MHz against 50 MHz | `openxc7-1791279462406736988/report.json` |
| Corrected physical placement reader | Source provenance/ports/PAD connections, all 12,014 cells, both BRAMs and five exact pins/sites/tiles/LVCMOS18 pass | `openxc7-finish-1791282033490820387/report.json` |
| Native conversion | Actual converter exit 0 in 440.232 seconds; 45,892 supplied legal frames, 62,990 nonzero words, 444 legal frames for assembler zero-fill | `openxc7-resume-1791281285801037576/report.json` |
| Native assembly and final hash audit | Native/wrapper exit 0 in 5.070 seconds; exact part/header/full payload and all bound hashes pass | `openxc7-finish-1791282033490820387/execution-result.json` |

The P&R wrapper originally failed on the pinned writer's normalized `top`
name despite native P&R exit 0. The conversion wrapper later failed by matching
`error:` within a handled `ImportError:` warning despite native converter exit 0.
Both original failed reports, actual exits, logs and runner snapshots remain
unchanged. The narrow recovery tools recheck their inputs and reuse completed
route/frames; no duplicate P&R or conversion was needed for the candidate.
Twenty-seven build, placement, process and Vivado configuration tests pass;
two additional warning/error diagnostic tests pass separately.

## Home-project and tool review

The refreshed bounded inventory covers all 47 visible non-hidden top-level
home directories at 2026-10-06T10:23:38.454350+00:00. Root documentation and
candidate filenames were scanned to depth six, excluding generated/dependency
trees, followed by deeper inspection of useful donors. See [PROJECTS.md](PROJECTS.md),
`build/ypcb/home-project-inventory.json` and `build/ypcb/home-project-final-review.json`.
The newly found `ypcb_ref` provides board/pin/configuration and reset
references. Follow-up verification of openTPU confirms its active build reads
`otpu_top_ld.xdc`: AA28 at 50 MHz/LVCMOS18, configuration 1.8 V and CFGBVS GND.
The user selected these values for preparation; they are no longer missing
profile choices. `build/ypcb/opentpu-profile-review.json` records the revision,
source hashes, build wiring and production documentation. ET-SOC, LPULite,
verigpu and Vortex provide separate transport/tool
patterns. Their bitstreams, protocols and hardware results are not TinyGPU proof.
No donor project was modified by this work.

The read-only board check at 2026-10-06T10:23:32.940716+00:00 verifies the existing
loader/helper and all three DLC10 firmware hashes:
`build/ypcb/board-readonly-1791282212235968179/report.json`.
It exits 1 because USB enumeration is unavailable (`libusb: -99`); cable state
is unknown. It performs no cable initialization or chain detection.
Fresh PATH and bounded documented-installation checks find Vivado Lab only:
`build/ypcb/vivado-presence-1791282257861070615.json`.
Full Vivado is unavailable in that scope; Lab cannot implement the design.

## Remaining requirements

- Resolve the candidate's dependency on R28 reset and confirm LED polarity.
  openTPU documents R28 as unwired; its current top omits that port and derives
  reset from MMCM lock and PCIe PERST#. This candidate still depends on R28
  being inactive after configuration. openTPU's docs leave LED polarity unverified.
- Complete independent electrical/configuration DRC and full XC7K480T-2 timing
  signoff. The native estimate uses DEFAULT speed grade, placeholder delays and
  substituted Artix-7 timing; it cannot establish physical setup/hold closure.
- Establish USB/JTAG access and exact chain identity before a later authorized
  volatile load. A physical result needs observed PASS/heartbeat on this card.

The verified candidate is ready for review; physical run readiness is unresolved.
The selected board profile is AA28 at 50 MHz/LVCMOS18, `CONFIG_VOLTAGE=1.8`
and `CFGBVS=GND`, from the active openTPU XDC and the user's direction.
[README.md](README.md) contains repeatable preparation, exact route/recovery
commands and the conditional board-run procedure. The current requirements audit
is `build/ypcb/readiness-audit.json`. Earlier observations and preserved failure
records are described in [PREPARATION_HISTORY.md](PREPARATION_HISTORY.md).


## Reset-corrected revision failures and reference refresh

The first R28-free map (`20261006T123337Z-1791290017399911991`) inferred
SRL16E. Mapped elaboration failed with native compiler exit 3; the parent
`post-reset-verification-1791290592532905810` exited 1. All original sources
were preserved before changing the startup register to keep all four FDREs.
The bounded inference probe showed the baseline SRL and the four-FDRE result:
`reset-revision-1791289965709203869/startup-inference-probe.json`.

The next preparation (`20261006T130045Z-1791291645360594236`) passed mapping
and all 19 commands. Its mapped run passed both kernels at first startup,
then failed an invalid assertion that LED status must clear during GSR.
PASS/FAIL primitive INIT values are unspecified; synchronous startup reset
clears them after GSR release. The failure and source snapshot are preserved
in that directory and
`post-reset-verification-1791291741388761593/execution-result.json`.
Only `tb_mapped.sv` changed. The new converted RTL byte-matched the previous
version (`20261006T132509Z-1791293109938073395/test-correction-review.json`).
The corrected mapped test passed both kernels twice and all four reset stages.

The subsequent launcher exited 1 before native P&R because openTPU's README
changed by two lines linking a new Fedora guide. All seven board/build/profile
sources were unchanged. `pnr-after-reset-1791293126494146665/execution-result.json`
records that failure. `opentpu-reference-snapshot-1791294555808991937/`
preserves the previous review, exact README diff, all eight reference files
and the supplemental Fedora guide/helper. The active profile review now binds
those snapshots, retaining the source revision and observed donor hashes.
No donor file was modified. Fresh native P&R/assembly then passed in
`openxc7-1791294584961856221`; no duplicate completed route was discarded.
