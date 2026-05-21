obj-m += hello.o
obj-m += vulndev.o
obj-m += vulndev_int.o

KDIR := /lib/modules/$(shell uname -r)/build

all:
	make -C $(KDIR) M=$(PWD) modules

clean:
	make -C $(KDIR) M=$(PWD) clean
