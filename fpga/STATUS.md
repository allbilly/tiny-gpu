# Current YPCB preparation status

Observed UTC: 2026-10-06T17:26:33.388739+00:00.

This page preserves historical evidence for that source snapshot. Subsequent
working-tree changes require fresh source-bound verification reports; the
recorded hashes do not validate updated tooling.

The reset-corrected candidate is assembled for `xc7k480tffg1156-2`:
`build/ypcb/openxc7-1791294584961856221/tiny_gpu_demo.bit`.
It is 18,735,173 bytes, SHA256
`2b64691f5a0be6deed105fb720e8896310ef246391179aaddae9c55bb9e1bd5b`.
The native assembler and pipeline wrapper exited 0. The independent terminal
audit verifies all 1,729 bound inputs and 13 artifacts, exact part/header and
complete payload. No live build remains. No FPGA or flash programming occurred.

The user-selected active openTPU profile is AA28 at 50 MHz/LVCMOS18,
CONFIG_VOLTAGE 1.8 and CFGBVS GND. The current top uses AA28 and P30/M30/N30;
R28 is unused. Four INIT=0 FDREs hold reset for the first four oscillator edges
after configuration. The full real two-core GPU, four threads per block, all
four data channels, ADD/SUB/MUL/DIV and two RAMB18E1 memories remain.

## Completed evidence

| Check | Result | Report under `build/ypcb/` |
|---|---|---|
| Simulation and mapping | All 19 commands pass: four Icarus benches, two Verilator benches and synthesis; actual exit 0 | `20261006T132509Z-1791293109938073395/report.json` |
| Mapping terminal audit | 27 source and 28 artifact hashes match; four INIT=0 FDREs and verified clock/enable/shift connections | `20261006T132509Z-1791293109938073395/execution-result.json` |
| Divider | 65,280 nonzero 8-bit pairs; zero/X, stalled WAIT, inactive lanes, reset and other arithmetic pass | `20261006T132509Z-1791293109938073395/divider_icarus_run.log` |
| Host arithmetic | 40 kernels, 280 thread results and 10,240 memory-byte comparisons pass | `arithmetic-check-1791293842381716027/report.json` |
| Mapped configuration reset | Both original kernels after two GSR releases, 3,917 clocks each; four startup shift states and clocked status reset pass | `20261006T132509Z-1791293109938073395/mapped-check-1791294029647816110/report.json` |
| Downstream terminal audit | Actual wrapper exit 0; all 63 bound inputs match | `post-reset-verification-1791293126489158153/execution-result.json` |
| Native architecture integrity | Reused native exit 0, five ordered phases and 1,633 source/tool/database hashes | `architecture-check-1791250929474836590/report.json` |
| Full GPU route | Native exit 0, 1,325.215 seconds; final estimate 97.428 MHz against 50 MHz | `openxc7-1791294584961856221/report.json` |
| Placement | All 12,067 cells, two BRAMs and four exact package pins/sites/tiles/port directions with LVCMOS18 pass | `openxc7-1791294584961856221/execution-result.json` |
| Native conversion | Exit 0, 432.155 seconds; 45,892 supplied legal frames, 61,940 nonzero words, 444 legal frames zero-filled by assembler | `openxc7-1791294584961856221/report.json` |
| Native assembly and final audit | Native exit 0, 5.056 seconds; actual wrapper exit 0, complete file/header and all hashes pass | `openxc7-1791294584961856221/execution-result.json` |
| Home projects | Previous 47-directory bounded survey plus current 48-directory delta review; no donor modified | `home-project-inventory.json`, `home-project-delta-review.json` |
| Portable full-Vivado source | Clean extraction passes 86 file hashes, workload verification and make-plan check; source only | `vivado-source-bundle-1791294825793650197/report.json` |

The selected reference review preserves openTPU revision
`5b1e646cdec9de449ba416952ec854b0b2d973d7` and all eight reviewed files as
hash-bound snapshots. All board/build/profile sources matched the earlier
review; only README gained a Fedora guide link. The prior review and diff are
preserved in `opentpu-reference-snapshot-1791294555808991937/`.
Its production/timing results apply to openTPU; they are not TinyGPU proof.
Earlier SRL, reload-test and donor-drift failures remain unchanged and are
explained in [PREPARATION_HISTORY.md](PREPARATION_HISTORY.md).

## Selected flow and remaining board access

The user selected openXC7. The completed candidate was built by Yosys,
nextpnr and Project X-Ray; no Vivado is needed to build or load this image.
Full Vivado is an optional independent cross-check. The native timing model
uses DEFAULT speed grade, placeholder delays and some Artix-7 timing, so
97.428 MHz remains an estimate rather than XC7K480T-2 characterization.

- Working local USB/JTAG access and exact chain identity are still needed.
  The current read-only check verifies the loader/helper and three firmware
  hashes, but USB enumeration returns `libusb: -99`; cable state is unknown.
  No cable initialization or chain detection was performed.
- LED polarity and actual PASS/heartbeat are observed after a later authorized
  volatile load. No physical TinyGPU result is claimed.

The clock/configuration profile choices and R28 dependency are resolved.
The optional full-Vivado source bundle is retained for an independent
cross-check; the openXC7 rebuild command is the primary documented path.
[README.md](README.md) contains the current route/rebuild and conditional board
commands; [PROJECTS.md](PROJECTS.md) records donor choices. The complete
requirements audit is `build/ypcb/readiness-audit.json`.
