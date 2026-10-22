#ifndef TINYGPU_IOCTL_H
#define TINYGPU_IOCTL_H

#include <linux/ioctl.h>
#include <linux/types.h>

/* Explicit alignment keeps ioctl number and field offsets identical for compat. */
struct tinygpu_submit {
    __aligned_u64 program;
    __u32 program_words;
    __aligned_u64 data;
    __u32 data_bytes;
    __u32 thread_count;
    __u32 result_offset;
    __u32 result_bytes;
    __aligned_u64 result;
    __u32 timeout_loops;
    __u32 status;
};

#define TINYGPU_IOCTL_MAGIC 'T'
#define TINYGPU_IOCTL_SUBMIT _IOWR(TINYGPU_IOCTL_MAGIC, 0, struct tinygpu_submit)

#endif
