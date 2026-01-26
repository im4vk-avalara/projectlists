CXX = c++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2

all: make_elf_arm64 packer compiler

make_elf_arm64: make_elf_arm64.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

packer: packer.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

compiler: compiler.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

# Generate the minimal ELF
mini_elf_arm64: make_elf_arm64
	./make_elf_arm64

# Pack the minimal ELF
packed_elf: packer mini_elf_arm64
	./packer mini_elf_arm64 packed_elf 0x5A

# Compile TinyLang examples
examples: compiler
	@mkdir -p examples
	./compiler examples/hello.tiny examples/hello_bin
	./compiler examples/arithmetic.tiny examples/arithmetic_bin
	./compiler examples/expression.tiny examples/expression_bin
	./compiler examples/negative.tiny examples/negative_bin

# Test packer in Docker
test-packer: packed_elf
	@echo "=== Testing Packer in ARM64 Docker ==="
	docker run --rm --platform linux/arm64 -v "$$(pwd):/work" alpine:latest sh -c '\
		chmod +x /work/mini_elf_arm64 /work/packed_elf && \
		echo "Original: $$(/work/mini_elf_arm64; echo $$?)" && \
		echo "Packed:   $$(/work/packed_elf; echo $$?)"'

# Test compiler in Docker
test-compiler: examples
	@echo "=== Testing Compiler in ARM64 Docker ==="
	docker run --rm --platform linux/arm64 -v "$$(pwd):/work" alpine:latest sh -c '\
		chmod +x /work/examples/*_bin && \
		echo "hello.tiny:      $$(/work/examples/hello_bin; echo $$?) (expected: 42)" && \
		echo "arithmetic.tiny: $$(/work/examples/arithmetic_bin; echo $$?) (expected: 54)" && \
		echo "expression.tiny: $$(/work/examples/expression_bin; echo $$?) (expected: 25)" && \
		echo "negative.tiny:   $$(/work/examples/negative_bin; echo $$?) (expected: 5)"'

# Run all tests
test: test-packer test-compiler
	@echo ""
	@echo "=== All tests completed ==="

# Verify ELF structure
verify: packed_elf
	@echo "=== File types ==="
	file mini_elf_arm64 packed_elf
	@echo ""
	@echo "=== Packed ELF stub (first 80 bytes at 0x1000) ==="
	xxd -s 0x1000 -l 80 packed_elf
	@echo ""
	@echo "=== Encrypted payload ==="
	xxd -s 0x1050 -l 32 packed_elf

clean:
	rm -f make_elf_arm64 packer compiler mini_elf_arm64 packed_elf
	rm -f examples/*_bin

.PHONY: all examples test test-packer test-compiler verify clean
