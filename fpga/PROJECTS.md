# Home-project reuse audit

Observed UTC: 2026-10-06T10:23:38.454350+00:00.

Inspected every visible top-level home directory: root READMEs/build files,
plus FPGA/JTAG/constraint/tool filenames down to depth six. Generated builds,
dependencies and output archives were excluded from the broad scan; the
promising board/tool/model donors were inspected separately. This is a reuse
audit, not a claim that every file in every checkout was read. No unrelated
project was modified, cleaned, built, or committed by this preparation.

The JSON inventory with the exact observed revisions, documentation hits and
candidate filenames is `build/ypcb/home-project-inventory.json`; regenerate it
with `python3 fpga/tools/inventory_home.py`. Other active projects can change
after the observation. Their generated logs/binaries are not accepted as
evidence for tiny-gpu.

| Directory under ~/ | Finding |
|---|---|
| `ClusterSim` | GPU simulator/build environment; no direct board/RTL donor found. |
| `Desktop` | Personal/data directory; no direct board/RTL/toolchain donor found in the bounded scan. |
| `Documents` | Personal/data directory; no direct board/RTL/toolchain donor found in the bounded scan. |
| `Downloads` | Personal/data directory; no direct board/RTL/toolchain donor found in the bounded scan. |
| `LPULite` | New checkout since the first inventory. Original DE1-SoC/Cyclone V setup is incompatible. Its new YPCB 160-bit USER mailbox and cable host code were inspected; useful transport references, but its LPU protocol/ISA differ and no donor hardware result proves tiny-gpu. |
| `Pictures` | Personal/data directory; no direct board/RTL/toolchain donor found in the bounded scan. |
| `Public` | Personal/data directory; no direct board/RTL/toolchain donor found in the bounded scan. |
| `Templates` | Personal/data directory; no direct board/RTL/toolchain donor found in the bounded scan. |
| `Videos` | Personal/data directory; no direct board/RTL/toolchain donor found in the bounded scan. |
| `cpu-fan-diagnostics` | New host-diagnostic data directory; no FPGA donor found. |
| `et-platform` | ET-SOC simulator/toolchain platform; unrelated ISA and interface. |
| `et-sysemu` | ET-SOC simulation/software; unrelated ISA and interface. |
| `etsoc` | Minion ISA/RTL experiments. Its new YPCB 704-bit ETJ1 USER1 transport and adapter tests are useful future references; its 512-bit ET data contract differs from tiny-gpu and establishes no whole-board tiny-gpu result. |
| `etsoc1-native-matmul-mat-engine-perf-visulization` | ET-SOC measurement/visualization artifacts; unrelated execution target. |
| `go` | Language modules/cache; no direct donor identified. |
| `html` | Visualization/web artifacts; no direct donor found. |
| `llama.cpp-tt` | LLM software integration; no direct YPCB/tiny-gpu donor found. |
| `mgpusim` | GCN simulator/calibration; no direct board/RTL donor found. |
| `miaow_gcn4` | FPGA RAM variants and FPGA build script found; GCN compute units/register widths differ from tiny-gpu. |
| `models` | Model data, not an FPGA shell or toolchain. |
| `multi2sim` | Simulator/software tooling; no direct board donor found. |
| `multi2sim-iiswc2016` | Historical simulator/software tooling; no direct board donor found. |
| `navisim` | RDNA simulator/benchmarks; no direct board/RTL donor found. |
| `navisim-cleanup-backup-20261003T174015Z` | Backup of unrelated simulator work; retained, no direct donor found. |
| `npu` | FPGA/NPU RTL source reference; different interfaces and arithmetic. |
| `nvdla` | Software/RTL and VP references; different accelerator/register interface, no ready tiny-gpu board shell. |
| `nvgpu` | NVIDIA software/driver sources; not a tiny-gpu FPGA implementation. |
| `onnc` | Compiler and NVDLA software/VP references; no direct tiny-gpu hardware donor. |
| `otpu-build` | Added since the 47-directory survey. Contains only an empty `tmp/` directory; no source, toolchain or generated evidence to reuse. |
| `qbox` | QEMU/SystemC software platform; useful for future software transport testing, not Kintex bitstream generation. |
| `rknpu-fpga` | Direct donor: reset/LED conventions, Vivado gates, pinned UNISIM primitive models, Eigen install. Older openXC7 chipdb integrity failures exclude its P&R binary/database from adoption. |
| `soDLA` | Related YPCB AXI/BRAM bring-up files inspected; AXI and NVDLA compute contracts are different. |
| `somnia` | Related YPCB constraints/build/reset shell inspected; model/RTL is a different accelerator. |
| `tiny-gpu` | Target project: upstream real GPU and kernels. Existing SystemC/QBox MMIO/ioctl code is behavioral software integration, not FPGA execution. |
| `tiny-tpu` | Original Intel/Quartus designs and DE1-SoC pinout are incompatible. Its newer YPCB demo and generated tool sources were inspected: they exposed the vendor clock-standard disagreement. Its separately built nextpnr DSP-fix variant differs from this port's pin; this GPU's verified mapping contains no DSP cells, so it is not needed. No new compatible chipdb was found in the follow-up scan. A native assembler baseline exists, but the working source has a parser rejection change; no donor binary/database is adopted. |
| `tinygrad` | Related ML/accelerator project; no directly compatible tiny-gpu/YPCB shell or toolchain donor found in the bounded scan. |
| `tinygrad_nvdla` | Related ML/accelerator project; no directly compatible tiny-gpu/YPCB shell or toolchain donor found in the bounded scan. |
| `tinynvdla` | Related ML/accelerator project; no directly compatible tiny-gpu/YPCB shell or toolchain donor found in the bounded scan. |
| `tinytenstorrent` | Related ML/accelerator project; no directly compatible tiny-gpu/YPCB shell or toolchain donor found in the bounded scan. |
| `tt` | Related ML/accelerator project; no directly compatible tiny-gpu/YPCB shell or toolchain donor found in the bounded scan. |
| `tt-metal` | Related ML/accelerator project; no directly compatible tiny-gpu/YPCB shell or toolchain donor found in the bounded scan. |
| `verigpu` | Related YPCB preparation and host bridge files inspected. The refreshed scan also found a USER1 serial mailbox, TAP tests and cable host runner. These are transport references with a different GPU protocol/ISA; their generated P&R outputs are not tiny-gpu evidence. |
| `vivado` | Fresh PATH and documented-installation checks find Vivado Lab; no full Vivado executable found in that scope. Lab cannot perform synthesis/implementation. |
| `vortex` | Related GPU/toolchain with new YPCB clock, lookup and VREF compiler variants. These were inspected; the current GPU needs no DSP/VREF variant and uses its own completely checked native compiler/database. Vortex ISA/RTL and generated results are separate. |
| `vortex-tools-v3.0.1` | Potential simulator/SV converter tool bundle; PATH already supplies compatible native tools. |
| `vpn` | Host network tooling; no direct FPGA donor. |
| `ypcb` | Direct donor: exact device/package, 50 MHz pins, reference designs, staged DLC10 initialization and firmware. |
| `ypcb_ref` | Reference collection: TiferKing board/Fedora notes, Inspur blink, Bonetto and openTPU. The active openTPU build reads its AA28/50 MHz/LVCMOS18 and configuration 1.8/GND XDC; the user selected this preparation profile. Its current top omits R28 and resets from MMCM lock/PCIe; LED polarity remains undocumented as verified. Other accelerators, transports, bitstreams and timing results are separate. |

Selected reuse is intentionally narrow: exact board facts and working cable
initialization from `ypcb`, reset/build conventions and licensed primitive
models from `rknpu-fpga`, and the native Eigen installation for the new
project-local nextpnr build. The upstream tiny-gpu compute RTL and programs
remain the execution engine. `tiny-tpu` supplies patterns, not copied
Intel-specific interfaces. The maintained openXC7 backend and a matching
database are fetched into this project without changing any donor checkout.

The preserved refreshed inventory covers 47 visible top-level directories, up from
46 in the preceding scan and 44 in the first scan. The preceding inventory is
`build/ypcb/home-project-inventory-before-final-review-1791282213435655832.json`;
the final delta and selected source hashes are recorded in
`build/ypcb/home-project-final-review.json`. The follow-up openTPU review is
`build/ypcb/opentpu-profile-review.json`: its active clock and configuration
settings are now the selected board profile. The TinyGPU top now also omits R28, using four startup oscillator edges
instead of openTPU's MMCM/PCIe reset sources. LED polarity remains unverified.
A later membership check covers 48 directories: `otpu-build` was added and
inspected read-only. The delta and its complete bounded listing are recorded
in `build/ypcb/home-project-delta-review.json`; the membership snapshot is
`build/ypcb/home-membership-current.json`. No donor bitstream is adopted.
The first inventory is preserved at
`build/ypcb/home-project-inventory-20261005T133431.746496Z.json`; the comparison
is `build/ypcb/home-project-inventory-delta.json`. The new LPULite mailbox
reuses the verigpu sampling approach, with raw 32-bit read/write commands,
retry sequence numbers and error responses. Integrating it would require
adapting tiny-gpu's held-valid/ready/error contract and verifying its clock
crossing and physical scan path. The current tested autonomous demo already
uses that host bus internally; these references do not constitute an external
transport for this bitstream.
