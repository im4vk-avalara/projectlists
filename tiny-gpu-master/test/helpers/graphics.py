"""
Graphics helpers for tiny-gpu tests
===================================

Shared framebuffer configuration, display functions, kernels, and verification.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly
from .memory import Memory

# ============================================================
# FRAMEBUFFER CONFIGURATION
# ============================================================
WIDTH = 8
HEIGHT = 8
FRAMEBUFFER_SIZE = WIDTH * HEIGHT  # 64 pixels


def display_framebuffer_blocks(data_mem, title=""):
    """Display framebuffer using Unicode block characters."""
    blocks = [' ', '░', '▒', '▓', '█']
    
    print("\n╔" + "═" * (WIDTH * 2 + 2) + "╗")
    print(f"║ {title:^{WIDTH * 2}} ║")
    print("╠" + "═" * (WIDTH * 2 + 2) + "╣")
    
    for y in range(HEIGHT):
        row = "║ "
        for x in range(WIDTH):
            addr = y * WIDTH + x
            value = data_mem[addr]
            block_idx = min(int(value / 256 * len(blocks)), len(blocks) - 1)
            row += blocks[block_idx] + " "
        row += "║"
        print(row)
    
    print("╚" + "═" * (WIDTH * 2 + 2) + "╝")


def display_framebuffer_ascii(data_mem, title=""):
    """Display framebuffer as ASCII art."""
    chars = " .:-=+*#%@"
    
    print(f"\n  {title} (ASCII)")
    print("  +" + "-" * (WIDTH * 2) + "+")
    
    for y in range(HEIGHT):
        row = "  |"
        for x in range(WIDTH):
            addr = y * WIDTH + x
            value = data_mem[addr]
            if value == 0:
                char = ' '
            else:
                idx = min(int(value / 256 * len(chars)), len(chars) - 1)
                char = chars[idx]
            row += char + " "
        row += "|"
        print(row)
    
    print("  +" + "-" * (WIDTH * 2) + "+")


# ============================================================
# KERNEL PROGRAMS
# ============================================================

def make_gradient_program():
    """
    Gradient kernel - each pixel = thread_id * 4
    """
    program = [
        0b0101_0000_1101_1110,  # MUL R0, %blockIdx(R13), %blockDim(R14)
        0b0011_0000_0000_1111,  # ADD R0, R0, %threadIdx(R15)
        0b1001_0001_0000_0100,  # CONST R1, #4
        0b0101_0010_0000_0001,  # MUL R2, R0, R1
        0b1000_0000_0000_0010,  # STR R0, R2 (store R2 at address R0)
        0b1111_0000_0000_0000,  # RET
    ]
    return program


def make_checkerboard_program():
    """
    Checkerboard kernel - alternating black/white pattern based on (x+y) % 2
    """
    program = [
        0b0101_0000_1101_1110,  # 0: MUL R0, %blockIdx(R13), %blockDim(R14)
        0b0011_0000_0000_1111,  # 1: ADD R0, R0, %threadIdx(R15)
        0b1001_0001_0000_1000,  # 2: CONST R1, #8
        0b0110_0010_0000_0001,  # 3: DIV R2, R0, R1  (y = i / 8)
        0b0101_0011_0010_0001,  # 4: MUL R3, R2, R1  (y * 8)
        0b0100_0100_0000_0011,  # 5: SUB R4, R0, R3  (x = i % 8)
        0b0011_0101_0100_0010,  # 6: ADD R5, R4, R2  (x + y)
        0b1001_0110_0000_0010,  # 7: CONST R6, #2
        0b0110_0111_0101_0110,  # 8: DIV R7, R5, R6  ((x+y) / 2)
        0b0101_1000_0111_0110,  # 9: MUL R8, R7, R6  (((x+y)/2) * 2)
        0b0100_1001_0101_1000,  # 10: SUB R9, R5, R8 ((x+y) % 2)
        0b1001_1010_0000_0000,  # 11: CONST R10, #0
        0b0010_0000_1001_1010,  # 12: CMP R9, R10 (compare rs=R9 with rt=R10)
        0b0001_010_0_0001_0001,  # 13: BRz to line 17 (even = dark)
        0b1001_1011_1111_1111,  # 14: CONST R11, #255 (odd = bright)
        0b1000_0000_0000_1011,  # 15: STR R0, R11
        0b1111_0000_0000_0000,  # 16: RET
        0b1001_1011_0000_0000,  # 17: CONST R11, #0 (even = dark)
        0b1000_0000_0000_1011,  # 18: STR R0, R11
        0b1111_0000_0000_0000,  # 19: RET
    ]
    return program


def make_circle_program():
    """
    Circle kernel - filled circle in center at (4,4) with radius ~3
    
    SIMPLIFIED VERSION: Uses only ONE branch (inside/outside circle).
    Exploits 8-bit modular arithmetic: (-n)^2 mod 256 = n^2 mod 256
    for small n, so we can compute dx^2 directly without computing |dx|.
    
    Algorithm:
        i = blockIdx * blockDim + threadIdx
        x = i % 8
        y = i / 8
        dx = x - 4  (wraps to 252-255 for x < 4)
        dy = y - 4  (wraps to 252-255 for y < 4)
        dist_sq = dx*dx + dy*dy  (works due to modular math)
        pixel = 255 if dist_sq < 10 else 0
    """
    program = [
        0b0101_0000_1101_1110,  # 0: MUL R0, %blockIdx(R13), %blockDim(R14)
        0b0011_0000_0000_1111,  # 1: ADD R0, R0, %threadIdx(R15) ; i = thread_id
        0b1001_0001_0000_1000,  # 2: CONST R1, #8
        0b0110_0010_0000_0001,  # 3: DIV R2, R0, R1          ; y = i / 8
        0b0101_0011_0010_0001,  # 4: MUL R3, R2, R1          ; y * 8
        0b0100_0100_0000_0011,  # 5: SUB R4, R0, R3          ; x = i % 8
        0b1001_0101_0000_0100,  # 6: CONST R5, #4            ; center = 4
        
        # Compute dx = x - 4 (wraps for x < 4, but dx^2 still correct)
        0b0100_0110_0100_0101,  # 7: SUB R6, R4, R5          ; dx = x - 4
        
        # Compute dy = y - 4 (wraps for y < 4, but dy^2 still correct)
        0b0100_0111_0010_0101,  # 8: SUB R7, R2, R5          ; dy = y - 4
        
        # Compute distance squared
        0b0101_1000_0110_0110,  # 9: MUL R8, R6, R6          ; dx^2
        0b0101_1001_0111_0111,  # 10: MUL R9, R7, R7         ; dy^2
        0b0011_1000_1000_1001,  # 11: ADD R8, R8, R9         ; dist_sq = dx^2 + dy^2
        
        # Compare with radius^2 threshold
        0b1001_1001_0000_1010,  # 12: CONST R9, #10
        0b0010_0000_1000_1001,  # 13: CMP R8, R9 (compare dist_sq with 10)
        0b0001_001_0_0001_0001,  # 14: BRn to 17 (inside - dist_sq < 10)
        
        # Outside circle (dark)
        0b1001_1010_0000_0000,  # 15: CONST R10, #0
        0b0001_111_0_0001_0010,  # 16: BR to 18 (skip to store)
        
        # Inside circle (bright)
        0b1001_1010_1111_1111,  # 17: CONST R10, #255
        
        # Store and return
        0b1000_0000_0000_1010,  # 18: STR R0, R10
        0b1111_0000_0000_0000,  # 19: RET
    ]
    return program


# ============================================================
# VERIFICATION FUNCTIONS
# ============================================================

def verify_gradient(fb, threads):
    """Verify gradient pattern and return (errors, details)."""
    errors = 0
    details = []
    for i in range(threads):
        expected = (i * 4) & 0xFF
        if fb[i] != expected:
            errors += 1
            details.append(f"[{i}] expected={expected} got={fb[i]}")
    return errors, details


def verify_checkerboard(fb, threads):
    """Verify checkerboard pattern and return (errors, details)."""
    errors = 0
    details = []
    for i in range(threads):
        x = i % WIDTH
        y = i // WIDTH
        expected = 255 if (x + y) % 2 == 1 else 0
        if fb[i] != expected:
            errors += 1
            details.append(f"[{i}] x={x} y={y} expected={expected} got={fb[i]}")
    return errors, details


def verify_circle(fb, threads):
    """Verify circle pattern and return (errors, details)."""
    errors = 0
    details = []
    for i in range(threads):
        x = i % WIDTH
        y = i // WIDTH
        dx = abs(x - 4)
        dy = abs(y - 4)
        dist_sq = dx * dx + dy * dy
        expected = 255 if dist_sq < 10 else 0
        if fb[i] != expected:
            errors += 1
            details.append(f"[{i}] x={x} y={y} dist_sq={dist_sq} expected={expected} got={fb[i]}")
    return errors, details


# ============================================================
# KERNEL RUNNER
# ============================================================

async def setup_and_run_kernel(dut, program, data, threads, kernel_name, timeout=100000):
    """
    Complete setup and run for a single kernel.
    Creates fresh memory objects and properly initializes GPU.
    """
    print(f"\n  [LOG] ===== KERNEL: {kernel_name} =====")
    
    # Create fresh memory objects
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    
    # Initialize clock (use 26ns for even period)
    clock = Clock(dut.clk, 26, units="ns")
    cocotb.start_soon(clock.start())
    
    # Log initial GPU state
    print(f"  [LOG] PRE-RESET: reset={dut.reset.value}, start={dut.start.value}, done={dut.done.value}")
    
    # Assert reset
    dut.reset.value = 1
    dut.start.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    print(f"  [LOG] RESET ASSERTED: reset={dut.reset.value}, done={dut.done.value}")
    
    # Release reset
    dut.reset.value = 0
    await RisingEdge(dut.clk)
    
    print(f"  [LOG] RESET RELEASED: done={dut.done.value}")
    
    # Load program memory
    program_memory.load(program)
    print(f"  [LOG] Program loaded: {len(program)} instructions")
    print(f"  [LOG] First 3 instructions: {[hex(p) for p in program[:3]]}")
    
    # Load data memory
    data_memory.load(data)
    print(f"  [LOG] Data memory cleared: first 8 = {data_memory.memory[:8]}")
    
    # Set thread count
    dut.device_control_write_enable.value = 1
    dut.device_control_data.value = threads
    await RisingEdge(dut.clk)
    dut.device_control_write_enable.value = 0
    
    print(f"  [LOG] Thread count set: {threads}")
    
    # Start kernel execution
    dut.start.value = 1
    await RisingEdge(dut.clk)
    
    print(f"  [LOG] KERNEL STARTED: done={dut.done.value}")
    
    # Wait for done to go low
    wait_cycles = 0
    while dut.done.value == 1 and wait_cycles < 100:
        data_memory.run()
        program_memory.run()
        await RisingEdge(dut.clk)
        wait_cycles += 1
    
    if wait_cycles > 0:
        print(f"  [LOG] Waited {wait_cycles} cycles for done to go low")
    
    print(f"  [LOG] Execution starting, done={dut.done.value}")
    
    # Run kernel until completion
    cycles = 0
    while dut.done.value != 1 and cycles < timeout:
        data_memory.run()
        program_memory.run()
        await ReadOnly()
        await RisingEdge(dut.clk)
        cycles += 1
    
    print(f"  [LOG] KERNEL COMPLETE: {cycles} cycles, done={dut.done.value}")
    print(f"  [LOG] Final memory first 8: {data_memory.memory[:8]}")
    
    if cycles >= timeout:
        print(f"  [LOG] ERROR: TIMEOUT after {timeout} cycles!")
    
    return data_memory.memory, cycles
