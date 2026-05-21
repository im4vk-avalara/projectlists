#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/cred.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/string.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Avinash");
MODULE_DESCRIPTION("Vulnerable character device - integer overflow (addition wrap)");

#define DEVICE_NAME      "vulndev_int"
#define BUF_SIZE         64
#define IOCTL_TRIGGER    _IO('w',  1)
#define IOCTL_LEAK_ADDR  _IOR('w', 2, unsigned long)

/* ------------------------------------------------------------------ */
/* Per-open heap state. buf and callback are adjacent inside one slab  */
/* object — a linear OOB write past buf[] clobbers callback in place.  */
/* sizeof = 72 bytes → lands in the kmalloc-96 slab.                   */
/* ------------------------------------------------------------------ */
struct dev_state {
	char   buf[BUF_SIZE];   /* offset 0  */
	void (*callback)(void); /* offset 64 — overwrite target */
};

static dev_t         dev_num;
static struct cdev   my_cdev;
static struct class *dev_class;

/* ------------------------------------------------------------------ */
/* Privilege-escalation primitive. Same gotcha as previous box —       */
/* prepare_kernel_cred(NULL) is broken on kernel >= 6.2.               */
/* ------------------------------------------------------------------ */
static void escalate(void)
{
	struct cred *new = prepare_kernel_cred(&init_task);
	if (new)
		commit_creds(new);
}

static void default_callback(void)
{
	printk(KERN_INFO "vulndev_int: default callback fired\n");
}

/* ------------------------------------------------------------------ */
/* open / release — state lives in file->private_data                  */
/* ------------------------------------------------------------------ */
static int dev_open(struct inode *inode, struct file *file)
{
	struct dev_state *st = kmalloc(sizeof(*st), GFP_KERNEL);
	if (!st)
		return -ENOMEM;

	memset(st->buf, 0, BUF_SIZE);
	st->callback = default_callback;
	file->private_data = st;

	printk(KERN_INFO "vulndev_int: opened uid=%d pid=%d state=%px\n",
	       current_uid().val, current->pid, st);
	return 0;
}

static int dev_release(struct inode *inode, struct file *file)
{
	kfree(file->private_data);
	return 0;
}

/* ------------------------------------------------------------------ */
/* write — VULNERABLE: addition wraparound on a u16 size field.        */
/*                                                                     */
/* Wire format:  [u16 user_size][user_size bytes of data]              */
/*                                                                     */
/* The check below intends to ensure the header + data fit in buf[]:   */
/*     total = user_size + sizeof(u16)                                 */
/*     if (total > BUF_SIZE) reject                                    */
/*                                                                     */
/* But u16 arithmetic wraps at 65536. user_size = 0xFFFE makes total   */
/* = 0, sails past the check, and the byte loop below writes user_size */
/* (= 65534) bytes — a linear OOB write through buf[] into callback.   */
/* The loop's get_user faults when user memory runs out; bytes written */
/* before the fault persist in the kernel slab.                        */
/*                                                                     */
/* Why a byte loop and not copy_from_user:                              */
/* Modern kernels have TWO mitigations on copy_from_user that defeat    */
/* the natural exploit shape:                                           */
/*   (1) check_copy_size():       WARN+skip when bytes > INT_MAX        */
/*   (2) __check_heap_object():   BUG() when bytes > slab object size   */
/* This loop sidesteps both. get_user reads ONE byte to a local         */
/* (`b`) — no destination-size check applies. The OOB write happens at  */
/* `st->buf[i] = b`, which is raw C array indexing with no mitigation   */
/* hook on it (KASAN aside, which isn't enabled in production).         */
/* Real driver code uses this exact pattern for protocol parsing, and   */
/* it is precisely how integer-overflow bugs survive into production    */
/* kernels despite the usercopy hardening.                              */
/* ------------------------------------------------------------------ */
static ssize_t dev_write(struct file *file, const char __user *ubuf,
			 size_t count, loff_t *offset)
{
	struct dev_state *st = file->private_data;
	u16 user_size, total;
	u32 i;

	if (count < sizeof(u16))
		return -EINVAL;

	if (copy_from_user(&user_size, ubuf, sizeof(u16)))
		return -EFAULT;

	/* BUG: wraps on u16 */
	total = user_size + sizeof(u16);
	if (total > BUF_SIZE)
		return -EINVAL;

	/* Byte-at-a-time copy. Bypasses both usercopy mitigations. */
	for (i = 0; i < user_size; i++) {
		char b;
		if (get_user(b, ubuf + sizeof(u16) + i))
			return -EFAULT;
		st->buf[i] = b;   /* OOB once i >= BUF_SIZE — clobbers callback */
	}

	printk(KERN_INFO "vulndev_int: wrote user_size=%u total=%u\n",
	       user_size, total);
	return user_size;
}

/* ------------------------------------------------------------------ */
/* ioctl                                                                */
/*   IOCTL_TRIGGER   — fires st->callback (the exploit trigger)        */
/*   IOCTL_LEAK_ADDR — leaks escalate() address                        */
/* ------------------------------------------------------------------ */
static long dev_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct dev_state *st = file->private_data;
	unsigned long addr;

	switch (cmd) {
	case IOCTL_TRIGGER:
		printk(KERN_INFO "vulndev_int: trigger — callback=%ps\n",
		       st->callback);
		if (st->callback)
			st->callback();
		return 0;

	case IOCTL_LEAK_ADDR:
		addr = (unsigned long)escalate;
		if (copy_to_user((void __user *)arg, &addr, sizeof(addr)))
			return -EFAULT;
		printk(KERN_INFO "vulndev_int: leaked escalate @ %px\n", escalate);
		return 0;

	default:
		return -EINVAL;
	}
}

/* ------------------------------------------------------------------ */
/* Device node 0666 — any user can open                                */
/* ------------------------------------------------------------------ */
static char *vulndev_int_devnode(const struct device *dev, umode_t *mode)
{
	if (mode)
		*mode = 0666;
	return NULL;
}

static const struct file_operations fops = {
	.owner          = THIS_MODULE,
	.open           = dev_open,
	.release        = dev_release,
	.write          = dev_write,
	.unlocked_ioctl = dev_ioctl,
};

/* ------------------------------------------------------------------ */
/* init / exit                                                          */
/* ------------------------------------------------------------------ */
static int __init vulndev_int_init(void)
{
	if (alloc_chrdev_region(&dev_num, 0, 1, DEVICE_NAME) < 0)
		return -1;

	cdev_init(&my_cdev, &fops);
	if (cdev_add(&my_cdev, dev_num, 1) < 0) {
		unregister_chrdev_region(dev_num, 1);
		return -1;
	}

	dev_class = class_create(DEVICE_NAME);
	if (IS_ERR(dev_class)) {
		cdev_del(&my_cdev);
		unregister_chrdev_region(dev_num, 1);
		return -1;
	}

	dev_class->devnode = vulndev_int_devnode;

	if (IS_ERR(device_create(dev_class, NULL, dev_num, NULL, DEVICE_NAME))) {
		class_destroy(dev_class);
		cdev_del(&my_cdev);
		unregister_chrdev_region(dev_num, 1);
		return -1;
	}

	printk(KERN_INFO "vulndev_int: loaded — /dev/%s (major %d) [0666]\n",
	       DEVICE_NAME, MAJOR(dev_num));
	return 0;
}

static void __exit vulndev_int_exit(void)
{
	device_destroy(dev_class, dev_num);
	class_destroy(dev_class);
	cdev_del(&my_cdev);
	unregister_chrdev_region(dev_num, 1);
	printk(KERN_INFO "vulndev_int: unloaded\n");
}

module_init(vulndev_int_init);
module_exit(vulndev_int_exit);
