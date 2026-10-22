typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long u64;

#define SYS_OPENAT 56
#define SYS_CLOSE 57
#define SYS_WRITE 64
#define SYS_EXIT 93
#define SYS_MUNMAP 215
#define SYS_MMAP 222

#define AT_FDCWD -100
#define O_RDWR 2
#define PROT_READ 1
#define PROT_WRITE 2
#define MAP_SHARED 1

#define TINY_GPU_BASE 0x10200000ul
#define TINY_GPU_SIZE 0x10000ul

#define REG_THREAD_COUNT 0x0000u
#define REG_START 0x0004u
#define REG_STATUS 0x0008u
#define PROGRAM_BASE 0x1000u
#define DATA_BASE 0x2000u

static const u16 matadd_program[] = {
    0x50de, 0x300f, 0x9100, 0x9208, 0x9310, 0x3410, 0x7440,
    0x3520, 0x7550, 0x3645, 0x3730, 0x8076, 0xf000,
};

static const u8 matadd_data[] = {
    0, 1, 2, 3, 4, 5, 6, 7,
    0, 1, 2, 3, 4, 5, 6, 7,
};

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
    while (text[length] != 0) {
        ++length;
    }
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

void _start(void)
{
    long fd = syscall6(SYS_OPENAT, AT_FDCWD, (long)"/dev/mem", O_RDWR, 0, 0, 0);
    if (fd < 0) {
        write_str("open /dev/mem failed\n");
        exit_now(1);
    }

    volatile u8* gpu = (volatile u8*)syscall6(
        SYS_MMAP, 0, TINY_GPU_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, TINY_GPU_BASE);
    if ((long)gpu < 0) {
        write_str("mmap tiny-gpu failed\n");
        syscall3(SYS_CLOSE, fd, 0, 0);
        exit_now(1);
    }

    for (u32 i = 0; i < sizeof(matadd_program) / sizeof(matadd_program[0]); ++i) {
        *(volatile u16*)(gpu + PROGRAM_BASE + i * sizeof(u16)) = matadd_program[i];
    }

    for (u32 i = 0; i < sizeof(matadd_data); ++i) {
        *(volatile u8*)(gpu + DATA_BASE + i) = matadd_data[i];
    }

    *(volatile u32*)(gpu + REG_THREAD_COUNT) = 8;
    *(volatile u32*)(gpu + REG_START) = 1;

    u32 status = 0;
    for (u32 polls = 0; polls < 1000000; ++polls) {
        status = *(volatile u32*)(gpu + REG_STATUS);
        if (status & 3u)
            break;
    }
    if (!(status & 1u) || (status & 2u)) {
        write_str("tiny-gpu execution failed or timed out\n");
        syscall3(SYS_MUNMAP, (long)gpu, TINY_GPU_SIZE, 0);
        syscall3(SYS_CLOSE, fd, 0, 0);
        exit_now(1);
    }

    int failed = 0;
    for (u32 i = 0; i < 8; ++i) {
        const u8 got = *(volatile u8*)(gpu + DATA_BASE + 16 + i);
        const u8 expected = (u8)(matadd_data[i] + matadd_data[i + 8]);
        write_str("C[");
        write_uint(i);
        write_str("] = ");
        write_uint(got);
        write_str("\n");
        if (got != expected) {
            failed = 1;
        }
    }

    syscall3(SYS_MUNMAP, (long)gpu, TINY_GPU_SIZE, 0);
    syscall3(SYS_CLOSE, fd, 0, 0);

    if (failed) {
        write_str("tiny-gpu MMIO test failed\n");
        exit_now(1);
    }

    write_str("tiny-gpu MMIO test passed\n");
    exit_now(0);
}
