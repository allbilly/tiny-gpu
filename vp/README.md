# tiny-gpu SystemC VP

This is a small SystemC/TLM virtual platform for tiny-gpu, structured like the NVDLA VP/QBox split:

- `QBoxLikeDriver`: a CPU-side TLM initiator that loads program/data memory, writes MMIO control registers, starts the accelerator, polls status, and checks results.
- `TinyGpuTarget`: a memory-mapped TLM target that models the tiny-gpu ISA behaviorally.
- The target is not RTL co-simulation. It is a fast VP model intended for software-facing integration tests.

## Memory Map

| Address | Name | Access | Description |
| --- | --- | --- | --- |
| `0x0000` | `THREAD_COUNT` | W, 32 bits | Number of GPU threads to launch, 1–255 |
| `0x0004` | `START` | W, 32 bits | Write non-zero to execute the loaded kernel |
| `0x0008` | `STATUS` | R, 32 bits | Bit 0 is done; bit 1 is execution error |
| `0x1000` | `PROGRAM` | W | 256 rows of 16-bit instruction memory |
| `0x2000` | `DATA` | R/W | 256 rows of 8-bit data memory |

## Build

Install SystemC development files, then build with CMake:

```bash
cmake -S vp -B vp/build
cmake --build vp/build
ctest --test-dir vp/build --output-on-failure
```

## Run

```bash
vp/build/tiny-gpu-vp all
vp/build/tiny-gpu-vp matadd
vp/build/tiny-gpu-vp matmul
```

Expected output includes `matadd passed`, `matmul passed`, and `all VP workloads passed`. Division by zero, unknown opcodes, and the per-thread instruction limit report execution errors. R13–R15 are read-only identity registers, matching the RTL.

## How This Maps To NVDLA/QBox

In the NVDLA VP, QBox/QEMU acts as the CPU subsystem and drives devices through TLM sockets. This VP keeps that shape but replaces real QBox with `QBoxLikeDriver`, a minimal initiator that performs the same class of transactions directly from SystemC.

The separate [QBox integration](qbox/README.md) uses a real QEMU CPU and Linux ioctl driver with the same register contract. Both accelerator models are behavioral; neither proves RTL timing or physical hardware execution.
