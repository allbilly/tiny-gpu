# tiny-gpu QBox/QEMU VP

This platform runs AArch64 Linux using QEMU/QBox, with a behavioral tiny-gpu accelerator at `0x10200000`. `SimpleCPU`, `tlm2c`, and GreenLib come from an existing built NVDLA VP tree. The reused `libqbox-nvdla.so` provides the CPU bridge; this platform does not instantiate an NVDLA accelerator. It is not RTL co-simulation or physical board validation.

## Dependencies and build

Use a built QBox/VP checkout, its matching SystemC ABI, Lua development files and interpreter, bzip2 development files (plus the libjpeg ABI required by the prebuilt QBox library), CMake, a C++ compiler, Python 3, Make, and SSH on a Linux host. Guest builds require an AArch64 cross compiler and the configured kernel build tree matching the guest image (the original setup uses Linux 4.13.3).

Run from the tiny-gpu checkout:

```bash
cmake -S vp/qbox -B vp/qbox/build -DQBOX_VP_ROOT=/path/to/built/vp
cmake --build vp/qbox/build
make -C vp/qbox/guest all KDIR=/path/to/guest/kernel/build CROSS_COMPILE=/path/to/aarch64-linux-gnu-
```

If present, a sibling `../nvdla/ref/vp` is the default VP tree. The guest Makefile similarly discovers `../nvdla/buildroot-2017.11-rc1-clean`; otherwise set `KDIR` and `CROSS_COMPILE`. `BUILDROOT_ROOT` overrides that discovery. These are dependencies, not copies maintained by tiny-gpu.

`QBOX_LIBRARY` can override the QBox shared library. The generated `vp/qbox/build/aarch64_tiny_gpu.lua` carries the CMake-selected VP and library paths into runtime. Use this generated config when changing CMake paths; the source config also supports environment overrides. `SYSTEMC_HOME` selects a SystemC install prefix at configuration time; it must match the prebuilt VP libraries.

## Isolated guest test

The helper configures/builds the VP and guest artifacts, copies the source rootfs into a new private file, starts the guest, and runs the ioctl test. Existing destination rootfs files are rejected. It checks that its own VP process session owns the loopback SSH listener, then verifies a unique token in a read-only 9p share before loading the driver. Source images and the checkout are not shared writable with the guest. The helper stops the VP process group on completion or failure and retains the run directory and log for inspection.

```bash
SOURCE_ROOTFS=/path/to/rootfs.ext4 KERNEL_IMAGE=/path/to/Image \
  KDIR=/path/to/guest/kernel/build CROSS_COMPILE=/path/to/aarch64-linux-gnu- \
  bash vp/qbox/run_ioctl_test.sh
```

The helper works from any working directory. Environment overrides:

| Variable | Default / meaning |
| --- | --- |
| `QBOX_VP_ROOT`, `QBOX_LIBRARY` | CMake build dependencies and matching runtime library |
| `BUILD_DIR` | `vp/qbox/build` in this checkout |
| `KERNEL_IMAGE` | `../../examples/vp/Image` relative to the VP dependency |
| `SOURCE_ROOTFS` | `../../examples/vp/rootfs.ext4` relative to the VP dependency |
| `ROOTFS` | A fresh `rootfs.ext4` inside a unique run directory under the build directory; an override must not exist |
| `SSH_PORT` | `6677`, bound to `127.0.0.1`; an occupied port fails before launch |
| `LOG` | A new `vp.log` within that run directory; an override must not exist |
| `KDIR`, `CROSS_COMPILE`, `BUILDROOT_ROOT` | Guest build settings described above |

The legacy QBox argument parser cannot represent whitespace, commas, or quotes in kernel, disk, or shared directory paths; the config rejects these paths explicitly. The guest must accept noninteractive root SSH using the host's configured credentials (the original development rootfs permits this). Readiness and execution have bounded timeouts.

The guest client prints `tiny-gpu ioctl tests passed`. The helper also runs four concurrent clients, followed by a focused unbind/rebind regression for QBox node `10200000.nvdla`. It prints `four concurrent ioctl clients passed` and `tiny-gpu lifecycle test passed`; guest output is retained in `guest-test.log` alongside `vp.log`. Tests cover matadd, matmul, invalid thread counts, division-by-zero error reporting, clearing memory between submissions, and serialization under concurrent callers.

For a manual boot, create a **new** private rootfs copy, set `ROOTFS`, and use:

```bash
ROOTFS=/path/to/private-rootfs.ext4 KERNEL_IMAGE=/path/to/Image \
  SC_SIGNAL_WRITE_CHECK=DISABLE vp/qbox/build/tiny-gpu-qbox-vp \
  -c vp/qbox/build/aarch64_tiny_gpu.lua
```

The manual config shares the checkout read-only by default (`SHARE_ROOT` overrides it). In that guest, mount tag `r` and load `vp/qbox/guest/tinygpu.ko`, then run `vp/qbox/guest/tiny_gpu_ioctl_test.aarch64`. The driver accepts QBox device-tree aliases `nvidia,nvdla_os_initial` / `nvidia,nv_full` and `nvidia,nvdla_2` / `nvidia,nv_small`, as well as `tinygpu,qbox-vp`. QBox builds choose different alias pairs; the driver is intended for this simulated guest.

## Submit and memory map

`tinygpu_ioctl.h` defines a fixed 56-byte request with aligned 64-bit user pointers, shared by the driver and no-libc client. The driver serializes submissions and clears all program/data memory for each request. Supported thread counts are 1–255 and programs have 1–256 instructions. `timeout_loops` is a polling iteration budget, at most 1,000,000 (zero chooses that default); interrupt waits are bounded to one second. Execution errors return `-EIO`, with status copied back. Unbound device descriptors return `-ENODEV` and retain safe state until closed.

Offsets from `0x10200000`:

| Offset | Name | Access | Description |
| --- | --- | --- | --- |
| `0x0000` | `THREAD_COUNT` | W, 32 bits | Number of GPU threads, 1–255 |
| `0x0004` | `START` | W, 32 bits | Nonzero runs the loaded kernel and clears prior completion/error status |
| `0x0008` | `STATUS` | R, 32 bits | Bit 0: done; bit 1: execution error |
| `0x1000` | `PROGRAM` | W | 256 aligned 16-bit tiny-gpu instructions |
| `0x2000` | `DATA` | R/W | 256 bytes |

The model reports errors for division by zero, unknown opcodes, and its per-thread instruction budget. Registers R13–R15 retain the RTL's read-only thread identity values. The synchronous behavioral model may complete during START; an ioctl success alone does not prove interrupt delivery.

Offline host regressions (no VM, SSH, or hardware):

```bash
python3 -m unittest discover -s vp/qbox/tests -v
python3 vp/tests/test_qbox_model.py
```

Driver compilation and offline host regressions do not prove live kernel concurrency or platform-unbind behavior. The helper exercises both in its private guest: an open descriptor returns `-ENODEV` after unbind and stays invalid after rebind, while a fresh descriptor successfully submits work.
