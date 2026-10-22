#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#define TINY_GPU_BASE 0x10200000u
#define TINY_GPU_SIZE 0x10000u

#define REG_THREAD_COUNT 0x0000u
#define REG_START 0x0004u
#define REG_STATUS 0x0008u
#define PROGRAM_BASE 0x1000u
#define DATA_BASE 0x2000u

static const uint16_t matadd_program[] = {
    0x50de, 0x300f, 0x9100, 0x9208, 0x9310, 0x3410, 0x7440,
    0x3520, 0x7550, 0x3645, 0x3730, 0x8076, 0xf000,
};

static const uint8_t matadd_data[] = {
    0, 1, 2, 3, 4, 5, 6, 7,
    0, 1, 2, 3, 4, 5, 6, 7,
};

static void write32(volatile uint8_t *base, uint32_t offset, uint32_t value)
{
    *(volatile uint32_t *)(base + offset) = value;
}

static uint32_t read32(volatile uint8_t *base, uint32_t offset)
{
    return *(volatile uint32_t *)(base + offset);
}

int main(void)
{
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open /dev/mem");
        return 1;
    }

    volatile uint8_t *gpu = mmap(NULL, TINY_GPU_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, TINY_GPU_BASE);
    if (gpu == MAP_FAILED) {
        perror("mmap tiny-gpu");
        close(fd);
        return 1;
    }

    for (unsigned i = 0; i < sizeof(matadd_program) / sizeof(matadd_program[0]); ++i) {
        *(volatile uint16_t *)(gpu + PROGRAM_BASE + i * sizeof(uint16_t)) = matadd_program[i];
    }

    for (unsigned i = 0; i < sizeof(matadd_data); ++i) {
        *(volatile uint8_t *)(gpu + DATA_BASE + i) = matadd_data[i];
    }

    write32(gpu, REG_THREAD_COUNT, 8);
    write32(gpu, REG_START, 1);

    uint32_t status = 0;
    for (unsigned polls = 0; polls < 1000000; ++polls) {
        status = read32(gpu, REG_STATUS);
        if (status & 3u)
            break;
    }
    if (!(status & 1u) || (status & 2u)) {
        fprintf(stderr, "tiny-gpu execution failed or timed out\n");
        munmap((void *)gpu, TINY_GPU_SIZE);
        close(fd);
        return 1;
    }

    int failed = 0;
    for (unsigned i = 0; i < 8; ++i) {
        uint8_t got = *(volatile uint8_t *)(gpu + DATA_BASE + 16 + i);
        uint8_t expected = (uint8_t)(matadd_data[i] + matadd_data[i + 8]);
        printf("C[%u] = %u\n", i, got);
        if (got != expected) {
            fprintf(stderr, "mismatch at %u: expected %u got %u\n", i, expected, got);
            failed = 1;
        }
    }

    munmap((void *)gpu, TINY_GPU_SIZE);
    close(fd);
    return failed;
}
