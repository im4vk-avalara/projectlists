# Top-level orchestrator for shadowfox + lighthouse.
# Each module has its own kbuild Makefile under modules/<name>/.
#
# Usage (run from the host or inside the lab VM with a sources checkout):
#   make            # build both modules
#   make shadowfox  # build only the rootkit module
#   make lighthouse # build only the detector module
#   make clean      # clean both

.PHONY: all shadowfox lighthouse clean

all: shadowfox lighthouse

shadowfox:
	$(MAKE) -C modules/shadowfox

lighthouse:
	$(MAKE) -C modules/lighthouse

clean:
	$(MAKE) -C modules/shadowfox clean
	$(MAKE) -C modules/lighthouse clean
