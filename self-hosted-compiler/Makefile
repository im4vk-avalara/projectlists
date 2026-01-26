# ToyLang Self-Hosted Compiler - Makefile
# ========================================

PYTHON = python3
CC = cc
CFLAGS = -O2 -w

# Directories
SRC = src
BUILD = build
EXAMPLES = examples
TESTS = tests

# Seed compiler
SEED = $(PYTHON) $(SRC)/seed_compiler.py

# Build artifacts
TOYCC1_TOY = $(SRC)/toycc1.toy
TOYCC2_TOY = $(SRC)/toycc2.toy
TOYCC1_C = $(BUILD)/toycc1.c
TOYCC2_C = $(BUILD)/toycc2.c
TOYCC2_RECOMPILED_C = $(BUILD)/toycc2_recompiled.c
TOYCC1 = $(BUILD)/toycc1
TOYCC2 = $(BUILD)/toycc2
TOYCC2_RECOMPILED = $(BUILD)/toycc2_recompiled

.PHONY: all clean test demo stage0 stage1 stage2 stage3 hello examples

# Default: build everything
all: stage0 stage1

# Create build directory
$(BUILD):
	mkdir -p $(BUILD)

# ============================================================
# Stage 0: Use seed compiler to compile examples
# ============================================================

stage0: $(BUILD) hello

hello: $(BUILD)
	$(SEED) $(EXAMPLES)/hello.toy --compile -o $(BUILD)/hello
	@echo "Built: $(BUILD)/hello"

examples: $(BUILD)
	$(SEED) $(EXAMPLES)/hello.toy --compile -o $(BUILD)/hello
	$(SEED) $(EXAMPLES)/fibonacci.toy --compile -o $(BUILD)/fibonacci
	$(SEED) $(EXAMPLES)/factorial.toy --compile -o $(BUILD)/factorial
	$(SEED) $(EXAMPLES)/primes.toy --compile -o $(BUILD)/primes
	@echo "Built all examples in $(BUILD)/"

# ============================================================
# Stage 1: Compile ToyCC1 with seed compiler
# ============================================================

stage1: $(TOYCC1)

$(TOYCC1_C): $(TOYCC1_TOY) $(BUILD)
	$(SEED) $(TOYCC1_TOY) -o $(TOYCC1_C) --emit-c
	@echo "Generated: $(TOYCC1_C)"

$(TOYCC1): $(TOYCC1_C)
	$(CC) $(CFLAGS) -o $(TOYCC1) $(TOYCC1_C)
	@echo "Built: $(TOYCC1)"

# ============================================================
# Stage 2: Use ToyCC1 to compile ToyCC2
# ============================================================

stage2: $(TOYCC2)

$(TOYCC2_C): $(TOYCC1) $(TOYCC2_TOY)
	$(TOYCC1) < $(TOYCC2_TOY) > $(TOYCC2_C)
	@echo "Generated: $(TOYCC2_C)"

$(TOYCC2): $(TOYCC2_C)
	$(CC) $(CFLAGS) -o $(TOYCC2) $(TOYCC2_C)
	@echo "Built: $(TOYCC2)"

# ============================================================
# Stage 3: Self-hosting - ToyCC2 compiles itself
# ============================================================

stage3: $(TOYCC2_RECOMPILED)

$(TOYCC2_RECOMPILED_C): $(TOYCC2) $(TOYCC2_TOY)
	$(TOYCC2) < $(TOYCC2_TOY) > $(TOYCC2_RECOMPILED_C)
	@echo "Generated: $(TOYCC2_RECOMPILED_C)"

$(TOYCC2_RECOMPILED): $(TOYCC2_RECOMPILED_C)
	$(CC) $(CFLAGS) -o $(TOYCC2_RECOMPILED) $(TOYCC2_RECOMPILED_C)
	@echo "Built: $(TOYCC2_RECOMPILED)"
	@echo ""
	@echo "=== SELF-HOSTING COMPLETE ==="
	@echo "ToyCC2 has compiled itself!"

# ============================================================
# Verification
# ============================================================

verify: $(TOYCC2) $(TOYCC2_RECOMPILED)
	@echo "Verifying self-hosted compiler..."
	@$(TOYCC2) < $(EXAMPLES)/hello.toy > /tmp/toycc2_out.c
	@$(TOYCC2_RECOMPILED) < $(EXAMPLES)/hello.toy > /tmp/toycc2r_out.c
	@if diff -q /tmp/toycc2_out.c /tmp/toycc2r_out.c > /dev/null; then \
		echo "✓ VERIFIED: Both compilers produce identical output!"; \
	else \
		echo "✗ Outputs differ"; \
	fi
	@rm -f /tmp/toycc2_out.c /tmp/toycc2r_out.c

# ============================================================
# Testing
# ============================================================

test:
	cd $(TESTS) && $(PYTHON) -m pytest -v

test-quick:
	cd $(TESTS) && $(PYTHON) -m pytest test_lexer.py -v

# ============================================================
# Demo
# ============================================================

demo:
	./scripts/demo.sh

# ============================================================
# Utilities
# ============================================================

# Show generated C for a .toy file
%.c: $(EXAMPLES)/%.toy
	$(SEED) $< -o $@

# Run a .toy file
run-%: $(EXAMPLES)/%.toy
	$(SEED) $< --run

# Clean build artifacts
clean:
	rm -rf $(BUILD)/*
	rm -f /tmp/toy*.c
	@echo "Cleaned build directory"

# Show help
help:
	@echo "ToyLang Self-Hosted Compiler"
	@echo "============================"
	@echo ""
	@echo "Targets:"
	@echo "  all       - Build ToyCC1 (default)"
	@echo "  stage0    - Build hello example with seed compiler"
	@echo "  stage1    - Build ToyCC1 with seed compiler"
	@echo "  stage2    - Build ToyCC2 with ToyCC1"
	@echo "  stage3    - Self-host: ToyCC2 compiles itself"
	@echo "  verify    - Verify self-hosting works"
	@echo "  examples  - Build all example programs"
	@echo "  demo      - Run the full bootstrap demo"
	@echo "  test      - Run all tests"
	@echo "  clean     - Remove build artifacts"
	@echo ""
	@echo "Examples:"
	@echo "  make run-hello       - Compile and run hello.toy"
	@echo "  make run-fibonacci   - Compile and run fibonacci.toy"
