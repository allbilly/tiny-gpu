typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long u64;

#define SYS_IOCTL 29
#define SYS_OPENAT 56
#define SYS_CLOSE 57
#define SYS_WRITE 64
#define SYS_EXIT 93

#define AT_FDCWD -100
#define O_RDWR 2

#include "tinygpu_ioctl.h"

static const u16 matadd_program[] = {
    0x50de, 0x300f, 0x9100, 0x9208, 0x9310, 0x3410, 0x7440,
    0x3520, 0x7550, 0x3645, 0x3730, 0x8076, 0xf000,
};

static const u16 matmul_program[] = {
    0x50de, 0x300f, 0x9101, 0x9202, 0x9300, 0x9404, 0x9508,
    0x6602, 0x5762, 0x4707, 0x9800, 0x9900, 0x5a62, 0x3aa9,
    0x3aa3, 0x7aa0, 0x5b92, 0x3bb7, 0x3bb4, 0x7bb0, 0x5cab,
    0x388c, 0x3991, 0x2092, 0x180c, 0x3950, 0x8098, 0xf000,
};

static u8 matadd_data[] = {
    0, 1, 2, 3, 4, 5, 6, 7,
    0, 1, 2, 3, 4, 5, 6, 7,
};

static u8 matmul_data[] = {
    1, 2, 3, 4,
    1, 2, 3, 4,
};

static u8 result[256];

static long syscall6(long number, long arg0, long arg1, long arg2, long arg3, long arg4, long arg5)
{
    register long x0 asm("x0") = arg0;
    register long x1 asm("x1") = arg1;
    register long x2 asm("x2") = arg2;
    register long x3 asm("x3") = arg3;
    register long x4 asm("x4") = arg4;
    register long x5 asm("x5") = arg5;
    register long x8 asm("x8") = number;

    asm volatile("svc #0"
                 : "+r"(x0)
                 : "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5), "r"(x8)
                 : "memory");
    return x0;
}

static long syscall3(long number, long arg0, long arg1, long arg2)
{
    return syscall6(number, arg0, arg1, arg2, 0, 0, 0);
}

static void write_str(const char* text)
{
    long length = 0;
    while (text[length] != 0)
        ++length;
    syscall3(SYS_WRITE, 1, (long)text, length);
}

static void write_uint(u32 value)
{
    char buffer[11];
    int index = 10;
    buffer[index] = 0;
    if (value == 0) {
        write_str("0");
        return;
    }
    while (value != 0 && index > 0) {
        buffer[--index] = (char)('0' + (value % 10));
        value /= 10;
    }
    write_str(&buffer[index]);
}

static void exit_now(int code)
{
    syscall3(SYS_EXIT, code, 0, 0);
    for (;;) {
    }
}

static int run_submit(long fd, const char* name, const u16* program, u32 program_words,
                      u8* data, u32 data_bytes, u32 thread_count,
                      u32 result_offset, u32 result_bytes, const u8* expected)
{
    struct tinygpu_submit submit;
    int failed = 0;

    submit.program = (u64)program;
    submit.program_words = program_words;
    submit.data = (u64)data;
    submit.data_bytes = data_bytes;
    submit.thread_count = thread_count;
    submit.result_offset = result_offset;
    submit.result_bytes = result_bytes;
    submit.result = (u64)result;
    submit.timeout_loops = 1000000;
    submit.status = 0;

    if (syscall3(SYS_IOCTL, fd, TINYGPU_IOCTL_SUBMIT, (long)&submit) < 0) {
        write_str("TINYGPU_IOCTL_SUBMIT failed\n");
        return 1;
    }

    write_str(name);
    write_str(" result\n");
    for (u32 i = 0; i < result_bytes; ++i) {
        if (result_bytes <= 8 || result[i] != expected[i]) {
            write_str("C[");
            write_uint(i);
            write_str("] = ");
            write_uint(result[i]);
            write_str("\n");
        }
        if (result[i] != expected[i])
            failed = 1;
    }

    if (failed) {
        write_str(name);
        write_str(" failed\n");
        return 1;
    }

    write_str(name);
    write_str(" passed\n");
    return 0;
}

static int check_rejected(long fd, const u16 *program, u32 threads, long error)
{
    struct tinygpu_submit submit;
    submit.program = (u64)program;
    submit.program_words = 2;
    submit.data = 0;
    submit.data_bytes = 0;
    submit.thread_count = threads;
    submit.result_offset = 0;
    submit.result_bytes = 0;
    submit.result = 0;
    submit.timeout_loops = 0;
    submit.status = 0;
    if (syscall3(SYS_IOCTL, fd, TINYGPU_IOCTL_SUBMIT, (long)&submit) != -error ||
        (error == 5 && !(submit.status & 2))) {
        write_str("invalid submission regression failed\n");
        return 1;
    }
    return 0;
}

void _start(void)
{
    static const u8 matadd_expected[] = {0, 2, 4, 6, 8, 10, 12, 14};
    static const u8 matmul_expected[] = {7, 10, 15, 22};
    int failed = 0;
    long fd = syscall6(SYS_OPENAT, AT_FDCWD, (long)"/dev/tinygpu", O_RDWR, 0, 0, 0);
    if (fd < 0) {
        write_str("open /dev/tinygpu failed\n");
        exit_now(1);
    }

    failed |= run_submit(fd, "matadd", matadd_program,
                         sizeof(matadd_program) / sizeof(matadd_program[0]),
                         matadd_data, sizeof(matadd_data), 8, 16,
                         sizeof(matadd_expected), matadd_expected);

    failed |= run_submit(fd, "matmul", matmul_program,
                         sizeof(matmul_program) / sizeof(matmul_program[0]),
                         matmul_data, sizeof(matmul_data), 4, 8,
                         sizeof(matmul_expected), matmul_expected);

    {
        static const u16 ret_program[] = {0xf000, 0xf000};
        static const u16 div_zero_program[] = {0x6000, 0xf000};
        static const u8 zeros[256] = {0};
        failed |= check_rejected(fd, ret_program, 0, 22);
        failed |= check_rejected(fd, ret_program, 256, 22);
        failed |= check_rejected(fd, div_zero_program, 1, 5);
        /* Empty input must not reveal a preceding submission's memory. */
        failed |= run_submit(fd, "cleared memory", ret_program, 2,
                             (u8 *)zeros, 0, 1, 0, 256, zeros);
    }
    syscall3(SYS_CLOSE, fd, 0, 0);

    if (failed) {
        write_str("tiny-gpu ioctl test failed\n");
        exit_now(1);
    }

    write_str("tiny-gpu ioctl tests passed\n");
    exit_now(0);
}
