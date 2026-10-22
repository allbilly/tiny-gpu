#include <linux/completion.h>
#include <linux/fs.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/kref.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

#include "tinygpu_ioctl.h"

#define TINYGPU_REG_THREAD_COUNT 0x0000
#define TINYGPU_REG_START 0x0004
#define TINYGPU_REG_STATUS 0x0008
#define TINYGPU_PROGRAM_BASE 0x1000
#define TINYGPU_DATA_BASE 0x2000
#define TINYGPU_PROGRAM_WORDS 256
#define TINYGPU_DATA_BYTES 256
#define TINYGPU_DEFAULT_TIMEOUT_LOOPS 1000000
#define TINYGPU_STATUS_DONE 1
#define TINYGPU_STATUS_ERROR 2

static bool use_irq = true;
module_param(use_irq, bool, 0444);
MODULE_PARM_DESC(use_irq, "use interrupt completion instead of polling");

struct tinygpu_device {
    void __iomem *regs;
    struct completion done;
    struct mutex lock;
    struct kref refs;
    struct miscdevice miscdev;
    int irq;
    bool irq_registered;
    bool online;
};

static void tinygpu_release_device(struct kref *refs)
{
    struct tinygpu_device *gpu = container_of(refs, struct tinygpu_device, refs);
    kfree(gpu);
}

static irqreturn_t tinygpu_irq_handler(int irq, void *dev_id)
{
    struct tinygpu_device *gpu = dev_id;
    u32 status = ioread32(gpu->regs + TINYGPU_REG_STATUS);

    if (!(status & (TINYGPU_STATUS_DONE | TINYGPU_STATUS_ERROR)))
        return IRQ_NONE;
    complete(&gpu->done);
    return IRQ_HANDLED;
}

static int tinygpu_open(struct inode *inode, struct file *file)
{
    struct tinygpu_device *gpu = container_of(file->private_data,
                                             struct tinygpu_device, miscdev);
    int ret = mutex_lock_interruptible(&gpu->lock);

    if (ret)
        return ret;
    if (!gpu->online) {
        ret = -ENODEV;
    } else {
        kref_get(&gpu->refs);
        file->private_data = gpu;
    }
    mutex_unlock(&gpu->lock);
    return ret;
}

static int tinygpu_release(struct inode *inode, struct file *file)
{
    struct tinygpu_device *gpu = file->private_data;
    kref_put(&gpu->refs, tinygpu_release_device);
    return 0;
}

static long tinygpu_submit_ioctl(struct tinygpu_device *gpu,
                                struct tinygpu_submit __user *argp)
{
    struct tinygpu_submit submit;
    u16 *program = NULL;
    u8 *data = NULL;
    u8 *result = NULL;
    u32 timeout;
    u32 i;
    long ret = 0;

    if (copy_from_user(&submit, argp, sizeof(submit)))
        return -EFAULT;
    if (!submit.program || (submit.data_bytes && !submit.data) ||
        (submit.result_bytes && !submit.result))
        return -EINVAL;
    if (!submit.program_words || submit.program_words > TINYGPU_PROGRAM_WORDS ||
        submit.data_bytes > TINYGPU_DATA_BYTES ||
        submit.result_bytes > TINYGPU_DATA_BYTES ||
        submit.result_offset > TINYGPU_DATA_BYTES ||
        submit.result_bytes > TINYGPU_DATA_BYTES - submit.result_offset ||
        !submit.thread_count || submit.thread_count > 255 ||
        submit.timeout_loops > TINYGPU_DEFAULT_TIMEOUT_LOOPS)
        return -EINVAL;

    program = kmalloc_array(submit.program_words, sizeof(*program), GFP_KERNEL);
    data = kmalloc(submit.data_bytes, GFP_KERNEL);
    result = kmalloc(submit.result_bytes, GFP_KERNEL);
    if (!program || !data || !result) {
        ret = -ENOMEM;
        goto out;
    }
    if (copy_from_user(program, (void __user *)(uintptr_t)submit.program,
                       submit.program_words * sizeof(*program)) ||
        copy_from_user(data, (void __user *)(uintptr_t)submit.data,
                       submit.data_bytes)) {
        ret = -EFAULT;
        goto out;
    }

    ret = mutex_lock_interruptible(&gpu->lock);
    if (ret)
        goto out;
    if (!gpu->online) {
        ret = -ENODEV;
        goto out_unlock;
    }

    /* Each submission owns a fresh address space, including unused tails. */
    for (i = 0; i < TINYGPU_PROGRAM_WORDS; ++i)
        iowrite16(i < submit.program_words ? program[i] : 0,
                  gpu->regs + TINYGPU_PROGRAM_BASE + i * sizeof(u16));
    for (i = 0; i < TINYGPU_DATA_BYTES; ++i)
        iowrite8(i < submit.data_bytes ? data[i] : 0,
                 gpu->regs + TINYGPU_DATA_BASE + i);

    reinit_completion(&gpu->done);
    iowrite32(submit.thread_count, gpu->regs + TINYGPU_REG_THREAD_COUNT);
    iowrite32(1, gpu->regs + TINYGPU_REG_START);
    timeout = submit.timeout_loops ? submit.timeout_loops : TINYGPU_DEFAULT_TIMEOUT_LOOPS;
    submit.status = ioread32(gpu->regs + TINYGPU_REG_STATUS);
    if (!(submit.status & (TINYGPU_STATUS_DONE | TINYGPU_STATUS_ERROR))) {
        if (gpu->irq_registered) {
            wait_for_completion_timeout(&gpu->done, msecs_to_jiffies(1000));
            submit.status = ioread32(gpu->regs + TINYGPU_REG_STATUS);
        } else {
            while (timeout-- != 0) {
                submit.status = ioread32(gpu->regs + TINYGPU_REG_STATUS);
                if (submit.status & (TINYGPU_STATUS_DONE | TINYGPU_STATUS_ERROR))
                    break;
                cpu_relax();
                if ((timeout & 255) == 0)
                    cond_resched();
            }
        }
    }
    if (submit.status & TINYGPU_STATUS_ERROR) {
        ret = -EIO;
        goto out_copy_status;
    }
    if (!(submit.status & TINYGPU_STATUS_DONE)) {
        ret = -ETIMEDOUT;
        goto out_copy_status;
    }
    for (i = 0; i < submit.result_bytes; ++i)
        result[i] = ioread8(gpu->regs + TINYGPU_DATA_BASE + submit.result_offset + i);
    if (copy_to_user((void __user *)(uintptr_t)submit.result, result,
                     submit.result_bytes)) {
        ret = -EFAULT;
        goto out_unlock;
    }
out_copy_status:
    if (copy_to_user(argp, &submit, sizeof(submit)))
        ret = -EFAULT;
out_unlock:
    mutex_unlock(&gpu->lock);
out:
    kfree(result);
    kfree(data);
    kfree(program);
    return ret;
}

static long tinygpu_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
    if (cmd != TINYGPU_IOCTL_SUBMIT)
        return -ENOTTY;
    return tinygpu_submit_ioctl(file->private_data,
                                (struct tinygpu_submit __user *)arg);
}

static const struct file_operations tinygpu_fops = {
    .owner = THIS_MODULE,
    .open = tinygpu_open,
    .release = tinygpu_release,
    .unlocked_ioctl = tinygpu_ioctl,
#ifdef CONFIG_COMPAT
    .compat_ioctl = tinygpu_ioctl,
#endif
};

static int tinygpu_probe(struct platform_device *pdev)
{
    struct tinygpu_device *gpu;
    struct resource *res;
    int ret;

    gpu = kzalloc(sizeof(*gpu), GFP_KERNEL);
    if (!gpu)
        return -ENOMEM;
    mutex_init(&gpu->lock);
    init_completion(&gpu->done);
    kref_init(&gpu->refs);
    res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    if (!res || resource_size(res) < TINYGPU_DATA_BASE + TINYGPU_DATA_BYTES) {
        ret = -EINVAL;
        goto out_put;
    }
    gpu->regs = devm_ioremap_resource(&pdev->dev, res);
    if (IS_ERR(gpu->regs)) {
        ret = PTR_ERR(gpu->regs);
        goto out_put;
    }
    gpu->irq = platform_get_irq(pdev, 0);
    if (gpu->irq == -EPROBE_DEFER) {
        ret = -EPROBE_DEFER;
        goto out_put;
    }
    if (use_irq && gpu->irq >= 0) {
        ret = request_irq(gpu->irq, tinygpu_irq_handler, 0, "tinygpu", gpu);
        if (ret)
            dev_warn(&pdev->dev, "request_irq failed (%d), using polling\n", ret);
        else
            gpu->irq_registered = true;
    }
    gpu->miscdev.minor = MISC_DYNAMIC_MINOR;
    gpu->miscdev.name = "tinygpu";
    gpu->miscdev.fops = &tinygpu_fops;
    gpu->miscdev.mode = 0666;
    gpu->miscdev.parent = &pdev->dev;
    gpu->online = true;
    ret = misc_register(&gpu->miscdev);
    if (ret) {
        if (gpu->irq_registered)
            free_irq(gpu->irq, gpu);
        goto out_put;
    }
    platform_set_drvdata(pdev, gpu);
    dev_info(&pdev->dev, "registered /dev/tinygpu at phys 0x%pa\n", &res->start);
    return 0;
out_put:
    kref_put(&gpu->refs, tinygpu_release_device);
    return ret;
}

static int tinygpu_remove(struct platform_device *pdev)
{
    struct tinygpu_device *gpu = platform_get_drvdata(pdev);

    /* Block new opens, then drain submissions before devres unmaps registers. */
    misc_deregister(&gpu->miscdev);
    mutex_lock(&gpu->lock);
    gpu->online = false;
    if (gpu->irq_registered)
        free_irq(gpu->irq, gpu);
    mutex_unlock(&gpu->lock);
    /* Open descriptors retain only this state and subsequently get ENODEV. */
    kref_put(&gpu->refs, tinygpu_release_device);
    return 0;
}

static const struct of_device_id tinygpu_of_match[] = {
    { .compatible = "nvidia,nvdla_os_initial" },
    { .compatible = "nvidia,nv_full" },
    { .compatible = "nvidia,nvdla_2" },
    { .compatible = "nvidia,nv_small" },
    { .compatible = "tinygpu,qbox-vp" },
    { }
};
MODULE_DEVICE_TABLE(of, tinygpu_of_match);

static struct platform_driver tinygpu_platform_driver = {
    .probe = tinygpu_probe,
    .remove = tinygpu_remove,
    .driver = {
        .name = "tinygpu",
        .of_match_table = tinygpu_of_match,
    },
};
module_platform_driver(tinygpu_platform_driver);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("tiny-gpu");
MODULE_DESCRIPTION("tiny-gpu QBox VP ioctl driver");
