REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)
BUILDROOT_ROOT ?= $(REPO_ROOT)/../nvdla/buildroot-2017.11-rc1-clean
KDIR ?= $(BUILDROOT_ROOT)/output/build/linux-4.13.3
CROSS_COMPILE ?= $(if $(wildcard $(BUILDROOT_ROOT)/output/host/bin/aarch64-linux-gnu-gcc),$(BUILDROOT_ROOT)/output/host/bin/aarch64-linux-gnu-,aarch64-linux-gnu-)
ARCH ?= arm64

obj-m += tinygpu.o
tinygpu-y := tinygpu_drv.o

.PHONY: all module user clean
all: module user
module:
	@test -f "$(KDIR)/Makefile" || { echo 'Set KDIR to the configured guest kernel build tree.' >&2; exit 1; }
	$(MAKE) -C "$(KDIR)" M="$(CURDIR)" ARCH=$(ARCH) CROSS_COMPILE="$(CROSS_COMPILE)" modules
user: tiny_gpu_mmio_test.aarch64 tiny_gpu_ioctl_test.aarch64 tiny_gpu_lifecycle_test.aarch64

tiny_gpu_mmio_test.aarch64: tiny_gpu_mmio_test_nolibc.c
	$(CROSS_COMPILE)gcc -Wall -Wextra -nostdlib -static -fno-builtin $< -o $@

tiny_gpu_ioctl_test.aarch64: tiny_gpu_ioctl_test_nolibc.c tinygpu_ioctl.h
	$(CROSS_COMPILE)gcc -Wall -Wextra -nostdlib -static -fno-builtin $< -o $@
tiny_gpu_lifecycle_test.aarch64: tiny_gpu_lifecycle_test_nolibc.c tinygpu_ioctl.h
	$(CROSS_COMPILE)gcc -Wall -Wextra -nostdlib -static -fno-builtin $< -o $@

clean:
	$(MAKE) -C "$(KDIR)" M="$(CURDIR)" ARCH=$(ARCH) CROSS_COMPILE="$(CROSS_COMPILE)" clean
	rm -f tiny_gpu_mmio_test.aarch64 tiny_gpu_ioctl_test.aarch64 tiny_gpu_lifecycle_test.aarch64
