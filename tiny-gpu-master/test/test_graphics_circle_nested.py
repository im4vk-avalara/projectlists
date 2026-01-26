"""
Graphics Test: Circle Kernel (Nested Branches)
===============================================

Renders a filled circle using NESTED branch divergence for absolute value.
This kernel has THREE levels of divergence at the final inside/outside check.

Note: The absolute value branches (|x-4| and |y-4|) don't actually cause
divergence because threads within a block have similar x or y values.
The real divergence occurs at the inside/outside circle check.

Algorithm:
    i = blockIdx * blockDim + threadIdx
    x = i % 8
    y = i / 8
    dx = |x - 4|  (computed via branch, but typically uniform within block)
    dy = |y - 4|  (computed via branch, but typically uniform within block)
    dist_sq = dx*dx + dy*dy
    pixel = 255 if dist_sq < 10 else 0  <- actual divergence here
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly
from .helpers.memory import Memory
from .helpers.graphics import (
    WIDTH, HEIGHT,
    display_framebuffer_blocks,
    display_framebuffer_ascii,
    verify_circle,
)


def make_circle_nested_program():
    """
    Circle kernel with NESTED branches for absolute value computation.
    
    This kernel has THREE levels of branch divergence:
    1. BRn for |x - 4| computation (lines 8-11)
    2. BRn for |y - 4| computation (lines 13-16)  
    3. BRn for inside/outside circle (lines 22-25)
    """
    program = [
        0b0101_0000_1101_1110,  # 0: MUL R0, %blockIdx(R13), %blockDim(R14)
        0b0011_0000_0000_1111,  # 1: ADD R0, R0, %threadIdx(R15) ; i
        0b1001_0001_0000_1000,  # 2: CONST R1, #8
        0b0110_0010_0000_0001,  # 3: DIV R2, R0, R1          ; y = i / 8
        0b0101_0011_0010_0001,  # 4: MUL R3, R2, R1          ; y * 8
        0b0100_0100_0000_0011,  # 5: SUB R4, R0, R3          ; x = i % 8
        0b1001_0101_0000_0100,  # 6: CONST R5, #4            ; center = 4
        
        # ===== NESTED DIVERGENCE LEVEL 1: dx = |x - 4| =====
        0b0010_0000_0100_0101,  # 7: CMP R4, R5 (compare x with 4)
        0b0001_001_0_0000_1011,  # 8: BRn to 11 (x < 4)
        0b0100_0110_0100_0101,  # 9: SUB R6, R4, R5          ; dx = x - 4
        0b0001_111_0_0000_1100,  # 10: BR to 12 (unconditional)
        0b0100_0110_0101_0100,  # 11: SUB R6, R5, R4         ; dx = 4 - x
        
        # ===== NESTED DIVERGENCE LEVEL 2: dy = |y - 4| =====
        0b0010_0000_0010_0101,  # 12: CMP R2, R5 (compare y with 4)
        0b0001_001_0_0001_0000,  # 13: BRn to 16 (y < 4)
        0b0100_0111_0010_0101,  # 14: SUB R7, R2, R5         ; dy = y - 4
        0b0001_111_0_0001_0001,  # 15: BR to 17 (unconditional)
        0b0100_0111_0101_0010,  # 16: SUB R7, R5, R2         ; dy = 4 - y
        
        # ===== Compute dist_sq = dx^2 + dy^2 =====
        0b0101_1000_0110_0110,  # 17: MUL R8, R6, R6         ; dx^2
        0b0101_1001_0111_0111,  # 18: MUL R9, R7, R7         ; dy^2
        0b0011_1000_1000_1001,  # 19: ADD R8, R8, R9         ; dist_sq
        
        # ===== NESTED DIVERGENCE LEVEL 3: inside/outside circle =====
        0b1001_1001_0000_1010,  # 20: CONST R9, #10
        0b0010_0000_1000_1001,  # 21: CMP R8, R9 (compare dist_sq with 10)
        0b0001_001_0_0001_1001,  # 22: BRn to 25 (inside - dist_sq < 10) [25 = 0b00011001]
        
        # Outside (dark)
        0b1001_1010_0000_0000,  # 23: CONST R10, #0
        0b0001_111_0_0001_1010,  # 24: BR to 26 (skip to store) [26 = 0b00011010]
        
        # Inside (bright)
        0b1001_1010_1111_1111,  # 25: CONST R10, #255
        
        # Store and return
        0b1000_0000_0000_1010,  # 26: STR R0, R10
        0b1111_0000_0000_0000,  # 27: RET
    ]
    return program


async def setup_and_run_kernel(dut, program, data, threads, kernel_name, timeout=10000):
    """
    Complete setup and run for a single kernel with DETAILED debugging.
    """
    print(f"\n  [LOG] ===== KERNEL: {kernel_name} =====")
    
    # Create fresh memory objects
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    
    # Initialize clock
    clock = Clock(dut.clk, 26, unit="ns")
    cocotb.start_soon(clock.start())
    
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
    
    # Load data memory
    data_memory.load(data)
    
    # Set thread count
    dut.device_control_write_enable.value = 1
    dut.device_control_data.value = threads
    await RisingEdge(dut.clk)
    dut.device_control_write_enable.value = 0
    
    print(f"  [LOG] Thread count set: {threads}")
    
    # Start kernel execution
    dut.start.value = 1
    await RisingEdge(dut.clk)
    
    print(f"  [LOG] KERNEL STARTED")
    
    # Wait for done to go low
    wait_cycles = 0
    while dut.done.value == 1 and wait_cycles < 100:
        data_memory.run()
        program_memory.run()
        await RisingEdge(dut.clk)
        wait_cycles += 1
    
    print(f"  [LOG] Execution starting after {wait_cycles} wait cycles")
    
    # Run kernel with DETAILED per-cycle logging for first 500 cycles
    cycles = 0
    last_pc = -1
    last_state = -1
    
    while dut.done.value != 1 and cycles < timeout:
        data_memory.run()
        program_memory.run()
        await ReadOnly()
        
        # Try to read core state from first core
        try:
            # Access internal signals for debugging
            core0 = dut.cores[0]
            current_pc = int(core0.current_pc.value)
            core_state = int(core0.core_state.value)
            thread_active = int(core0.thread_active.value)
            
            # Log state changes for first 500 cycles
            if cycles < 500 and (current_pc != last_pc or core_state != last_state):
                state_names = ["IDLE", "FETCH", "DECODE", "REQUEST", "WAIT", "EXECUTE", "UPDATE", "DONE"]
                state_name = state_names[core_state] if core_state < len(state_names) else f"?{core_state}"
                print(f"  [CYCLE {cycles:4d}] PC={current_pc:2d} State={state_name:7s} Active={thread_active:04b}")
                last_pc = current_pc
                last_state = core_state
                
        except Exception as e:
            if cycles == 0:
                print(f"  [LOG] Cannot access internal signals: {e}")
        
        await RisingEdge(dut.clk)
        cycles += 1
        
        # Progress every 2000 cycles
        if cycles % 2000 == 0:
            print(f"  [LOG] PROGRESS: {cycles} cycles")
    
    print(f"  [LOG] KERNEL COMPLETE: {cycles} cycles, done={dut.done.value}")
    print(f"  [LOG] Final memory first 16: {data_memory.memory[:16]}")
    
    if cycles >= timeout:
        print(f"  [LOG] ERROR: TIMEOUT after {timeout} cycles!")
        non_zero = [(i, data_memory.memory[i]) for i in range(64) if data_memory.memory[i] != 0]
        if non_zero:
            print(f"  [LOG] Non-zero values: {non_zero[:10]}")
        else:
            print(f"  [LOG] ALL MEMORY IS ZERO - kernel never wrote anything")
    
    return data_memory.memory, cycles


@cocotb.test()
async def test_circle_nested(dut):
    """Test circle kernel with nested branch divergence - with detailed debugging."""
    
    THREADS = 64
    
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 14 + "CIRCLE KERNEL (NESTED BRANCHES)" + " " * 13 + "║")
    print("║" + " " * 8 + "Testing 3 levels of branch divergence" + " " * 12 + "║")
    print("╚" + "═" * 58 + "╝")
    
    program = make_circle_nested_program()
    data = [0] * 256
    
    # Use longer timeout for complex divergence
    fb, cycles = await setup_and_run_kernel(dut, program, data, THREADS, "CIRCLE_NESTED", timeout=50000)
    
    # Display result
    display_framebuffer_blocks(fb, "CIRCLE (NESTED)")
    display_framebuffer_ascii(fb, "CIRCLE (NESTED)")
    
    print(f"\n  First 16 values: {fb[:16]}")
    
    # Verify
    errors, details = verify_circle(fb, THREADS)
    
    if errors == 0:
        print(f"\n  ✓ CIRCLE (NESTED) PASSED ({cycles} cycles)")
    else:
        print(f"\n  ✗ CIRCLE (NESTED) FAILED: {errors} errors")
        for d in details[:15]:
            print(f"    {d}")
    
    assert errors == 0, f"Circle (nested) test failed with {errors} errors"
