# Physical TinyGPU test, 2026-10-25 UTC

Result: **PASS** after two volatile FPGA SRAM configurations over DLC10 JTAG.
The real TinyGPU RTL executed its built-in upstream matrix-add and
matrix-multiply kernels, checked their result memories, and asserted its
sticky PASS output. JTAG SAMPLE observed that output, a clear failure output,
and a continuing heartbeat. Flash was not written.

| Configuration | Samples | PASS | FAIL | Heartbeat transitions |
|---|---:|---:|---:|---:|
| 1 | 263 | 263 | 0 | 22 |
| 2 | 264 | 264 | 0 | 22 |

Each observation lasted 15 seconds. All three output drivers were enabled
throughout; INIT and DONE were asserted before and after observation (IR capture
0x35). Independent decoding of all 527 saved raw boundary captures and
verification of the linked load receipts passed. Both owned XVC servers stopped.

Target: XC7K480T-FFG1156, single-device JTAG IDCODE `0x23751093`.
DLC10: USB `03fd:0008`. Requested JTAG 500 kHz, reported actual 750 kHz.
BSDL: AMD XC7K480T-FFG1156, 1395 cells, SAMPLE opcode 000001.
PASS uses P30/output cell 852, FAIL M30/cell 846, heartbeat N30/cell 849.

## Tested source and image

Checkout: `0e4721456212cfcdc5717dc9883ed2ebdb55f528`.
The existing openXC7 image was selected after fresh RTL and mapped-primitive
checks. All 15 RTL files, workload inputs, and pin constraints match the
historical build. A fresh sv2v conversion is byte-identical to its synthesized
input (`dfda172b9356c65d4f79abce38652904d5035890bf7fb64d518e6d90c1c8d030`).
Eight changed build-tool files are explicitly recorded in the local
`preflight.json`; the archived build report remains historical. No fresh
synthesis or routing was performed for the unchanged actual design inputs.

Image, relative to the repository root:
`build/ypcb/openxc7-1791294584961856221/tiny_gpu_demo.bit`.

SHA256: `2b64691f5a0be6deed105fb720e8896310ef246391179aaddae9c55bb9e1bd5b`.

Size: 18,735,173 bytes. Part: `xc7k480tffg1156-2`.
The selected source profile uses the onboard nominal 50 MHz AA28 clock,
LVCMOS18, CONFIG_VOLTAGE 1.8 and CFGBVS GND.

## Local receipts and verification

This document preserves the result from the original local run report:
`build/ypcb/hardware-20261025T144537Z-1792939537980054597/README.md`.
The raw receipts, logs, verification scripts, and bitstream remain local,
ignored build artifacts; they are not bundled with this document.

The run directory contains:

- `manifest.json`: combined physical result and receipt hashes.
- `preflight.json`: fresh RTL/conversion/primitive, package-placement and frame
  checks, original image artifacts, and source/tool bindings.
- `mapped-run.log`: both original kernels after each of two simulated GSR releases.
- `cycle-1/` and `cycle-2/`: USB/detection and SRAM-transfer logs, immutable
  load receipts, full raw boundary captures, and XVC/observer logs.
- `verification.json`: independent offline-verification result.
- `verify_result.py`: checks source/image/receipt hashes and independently
  decodes every raw capture, without contacting JTAG.

With those local artifacts present, run from the repository root:

```sh
python3 build/ypcb/hardware-20261025T144537Z-1792939537980054597/verify_result.py
```

## Scope

The hardware result is the built-in matrix-kernel scoreboard observed through
SAMPLE. There was no direct external readback of result memory, external JTAG
MMIO workload injection, PCIe or DDR test. LED electrical polarity was not
optically measured. The configured clock is not an independent frequency
measurement. This result does not replace full timing/electrical signoff.
The FPGA was left configured with TinyGPU; that volatile state lasts until
reset, power loss, or another load.
