#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/cred.h>
#include <linux/sched/task.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Avinash");
MODULE_DESCRIPTION("Vulnerable character device - HTB box");

#define DEVICE_NAME      "vulndev"
#define BUF_SIZE         64
#define IOCTL_TRIGGER    _IO('v',  1)
#define IOCTL_LEAK_ADDR  _IOR('v', 2, unsigned long)

/* ------------------------------------------------------------------ */
/* Vulnerable state: buf and callback are adjacent in memory.          */
/* Overflowing buf overwrites callback — this is the intended bug.     */
/* ------------------------------------------------------------------ */
static struct {
	char   buf[BUF_SIZE];   /* offset 0  */
	void (*callback)(void); /* offset 64 — overwritten on overflow */
} dev_state;

static size_t      data_len;
static dev_t       dev_num;
static struct cdev my_cdev;
static struct class *dev_class;

/* ------------------------------------------------------------------ */
/* escalate() — overwrites current process credentials with root.      */
/* In a real exploit this would be reached via ROP; here it's a        */
/* clean target that simulates commit_creds(prepare_kernel_cred(NULL)) */
/* ------------------------------------------------------------------ */
static void escalate(void)
{
	struct cred *new = prepare_kernel_cred(&init_task);
	if (new)
		commit_creds(new);
}

/* ------------------------------------------------------------------ */
/* open / release                                                       */
/* ------------------------------------------------------------------ */
static int dev_open(struct inode *inode, struct file *file)
{
	printk(KERN_INFO "vulndev: opened by uid=%d pid=%d\n",
	       current_uid().val, current->pid);
	return 0;
}

static int dev_release(struct inode *inode, struct file *file)
{
	printk(KERN_INFO "vulndev: closed\n");
	return 0;
}

/* ------------------------------------------------------------------ */
/* read                                                                 */
/* ------------------------------------------------------------------ */
static ssize_t dev_read(struct file *file, char __user *ubuf,
			size_t count, loff_t *offset)
{
	size_t to_copy = min(count, data_len);

	if (*offset >= data_len)
		return 0;
	if (copy_to_user(ubuf, dev_state.buf, to_copy))
		return -EFAULT;

	*offset += to_copy;
	return to_copy;
}

/* ------------------------------------------------------------------ */
/* write — VULNERABLE: no bounds check on count.                       */
/* Writing > 64 bytes overflows into dev_state.callback.               */
/* ------------------------------------------------------------------ */
static ssize_t dev_write(struct file *file, const char __user *ubuf,
			 size_t count, loff_t *offset)
{
	/* BUG: count is not clamped to BUF_SIZE */
	if (copy_from_user(dev_state.buf, ubuf, count))
		return -EFAULT;

	data_len = count;
	printk(KERN_INFO "vulndev: wrote %zu bytes\n", count);
	return count;
}

/* ------------------------------------------------------------------ */
/* ioctl                                                                */
/*   IOCTL_TRIGGER   — fires dev_state.callback (the exploit trigger)  */
/*   IOCTL_LEAK_ADDR — leaks escalate() address (kernel pointer leak)  */
/* ------------------------------------------------------------------ */
static long dev_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	unsigned long addr;

	switch (cmd) {
	case IOCTL_TRIGGER:
		printk(KERN_INFO "vulndev: trigger fired — callback=%ps\n",
		       dev_state.callback);
		if (dev_state.callback)
			dev_state.callback();
		return 0;

	case IOCTL_LEAK_ADDR:
		/* simulates a kernel pointer leak vulnerability */
		addr = (unsigned long)escalate;
		if (copy_to_user((void __user *)arg, &addr, sizeof(addr)))
			return -EFAULT;
		printk(KERN_INFO "vulndev: leaked escalate @ %px\n", escalate);
		return 0;

	default:
		return -EINVAL;
	}
}

/* ------------------------------------------------------------------ */
/* open device to all users                                             */
/* ------------------------------------------------------------------ */
static char *vulndev_devnode(const struct device *dev, umode_t *mode)
{
	if (mode)
		*mode = 0666;
	return NULL;
}

static const struct file_operations fops = {
	.owner          = THIS_MODULE,
	.open           = dev_open,
	.release        = dev_release,
	.read           = dev_read,
	.write          = dev_write,
	.unlocked_ioctl = dev_ioctl,
};

/* ------------------------------------------------------------------ */
/* init / exit                                                          */
/* ------------------------------------------------------------------ */
static int __init vulndev_init(void)
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

	dev_class->devnode = vulndev_devnode;

	if (IS_ERR(device_create(dev_class, NULL, dev_num, NULL, DEVICE_NAME))) {
		class_destroy(dev_class);
		cdev_del(&my_cdev);
		unregister_chrdev_region(dev_num, 1);
		return -1;
	}

	printk(KERN_INFO "vulndev: loaded — /dev/%s (major %d) [0666]\n",
	       DEVICE_NAME, MAJOR(dev_num));
	return 0;
}

static void __exit vulndev_exit(void)
{
	device_destroy(dev_class, dev_num);
	class_destroy(dev_class);
	cdev_del(&my_cdev);
	unregister_chrdev_region(dev_num, 1);
	printk(KERN_INFO "vulndev: unloaded\n");
}

module_init(vulndev_init);
module_exit(vulndev_exit);
