#include "tinygpu_ioctl.h"

typedef unsigned char u8;
typedef unsigned short u16;
#define SYS_IOCTL 29
#define SYS_OPENAT 56
#define SYS_CLOSE 57
#define SYS_WRITE 64
#define SYS_EXIT 93
#define AT_FDCWD -100
#define O_WRONLY 1
#define O_RDWR 2

static long syscall6(long number, long a0, long a1, long a2, long a3, long a4, long a5)
{
    register long x0 asm("x0") = a0;
    register long x1 asm("x1") = a1;
    register long x2 asm("x2") = a2;
    register long x3 asm("x3") = a3;
    register long x4 asm("x4") = a4;
    register long x5 asm("x5") = a5;
    register long x8 asm("x8") = number;
    asm volatile("svc #0" : "+r"(x0)
                 : "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5), "r"(x8)
                 : "memory");
    return x0;
}

static long syscall3(long number, long a0, long a1, long a2)
{
    return syscall6(number, a0, a1, a2, 0, 0, 0);
}

static void message(const char *text)
{
    long size = 0;
    while (text[size])
        ++size;
    syscall3(SYS_WRITE, 1, (long)text, size);
}

static long open_path(const char *path, long flags)
{
    return syscall6(SYS_OPENAT, AT_FDCWD, (long)path, flags, 0, 0, 0);
}

/* This regression targets the fixed legacy QBox virt-machine device node. */
static int change_binding(const char *path)
{
    static const char device[] = "10200000.nvdla";
    long fd = open_path(path, O_WRONLY);
    long written;
    if (fd < 0)
        return 1;
    written = syscall3(SYS_WRITE, fd, (long)device, sizeof(device) - 1);
    syscall3(SYS_CLOSE, fd, 0, 0);
    return written != sizeof(device) - 1;
}

static long submit(long fd)
{
    /* CONST R1,7; STR R0,R1; RET. R0 starts at zero. */
    static const u16 program[] = {0x9107, 0x8001, 0xf000};
    struct tinygpu_submit request;
    u8 result = 0;
    long ret;
    request.program = (__u64)program;
    request.program_words = sizeof(program) / sizeof(program[0]);
    request.data = 0;
    request.data_bytes = 0;
    request.thread_count = 1;
    request.result_offset = 0;
    request.result_bytes = 1;
    request.result = (__u64)&result;
    request.timeout_loops = 0;
    request.status = 0;
    ret = syscall3(SYS_IOCTL, fd, TINYGPU_IOCTL_SUBMIT, (long)&request);
    if (ret == 0 && (result != 7 || request.status != 1))
        return -5;
    return ret;
}

void _start(void)
{
    const char *unbind = "/sys/bus/platform/drivers/tinygpu/unbind";
    const char *bind = "/sys/bus/platform/drivers/tinygpu/bind";
    long old_fd = open_path("/dev/tinygpu", O_RDWR);
    long new_fd = -1;
    int unbound = 0;
    int failed = 1;

    if (old_fd < 0 || change_binding(unbind)) {
        message("lifecycle: open/unbind failed\n");
        goto out;
    }
    unbound = 1;
    if (submit(old_fd) != -19) {
        message("lifecycle: old FD did not return ENODEV after unbind\n");
        goto out;
    }
    if (change_binding(bind)) {
        message("lifecycle: rebind failed\n");
        goto out;
    }
    unbound = 0;
    new_fd = open_path("/dev/tinygpu", O_RDWR);
    if (new_fd < 0 || submit(new_fd) != 0 || submit(old_fd) != -19) {
        message("lifecycle: fresh/old FD isolation failed after rebind\n");
        goto out;
    }
    failed = 0;
out:
    if (unbound)
        change_binding(bind);
    if (new_fd >= 0)
        syscall3(SYS_CLOSE, new_fd, 0, 0);
    if (old_fd >= 0)
        syscall3(SYS_CLOSE, old_fd, 0, 0);
    message(failed ? "tiny-gpu lifecycle test failed\n" : "tiny-gpu lifecycle test passed\n");
    syscall3(SYS_EXIT, failed, 0, 0);
    for (;;) { }
}
