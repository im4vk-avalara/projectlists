"""
Graphics Test: Checkerboard Kernel
==================================

Renders an alternating black/white checkerboard pattern.
Uses conditional branching based on (x + y) % 2.
Demonstrates branch divergence handling.
"""

import cocotb
from .helpers.graphics import (
    make_checkerboard_program,
    setup_and_run_kernel,
    display_framebuffer_blocks,
    display_framebuffer_ascii,
    verify_checkerboard,
)


@cocotb.test()
async def test_checkerboard(dut):
    """Test checkerboard kernel - alternating pattern."""
    
    THREADS = 64
    
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 16 + "CHECKERBOARD KERNEL TEST" + " " * 18 + "║")
    print("║" + " " * 12 + "Pattern based on (x+y) % 2" + " " * 20 + "║")
    print("╚" + "═" * 58 + "╝")
    
    program = make_checkerboard_program()
    data = [0] * 256
    
    fb, cycles = await setup_and_run_kernel(dut, program, data, THREADS, "CHECKERBOARD")
    
    # Display result
    display_framebuffer_blocks(fb, "CHECKERBOARD")
    display_framebuffer_ascii(fb, "CHECKERBOARD")
    
    print(f"\n  First 16 values: {fb[:16]}")
    
    # Verify
    errors, details = verify_checkerboard(fb, THREADS)
    
    if errors == 0:
        print(f"\n  ✓ CHECKERBOARD PASSED ({cycles} cycles)")
    else:
        print(f"\n  ✗ CHECKERBOARD FAILED: {errors} errors")
        for d in details[:10]:
            print(f"    {d}")
    
    assert errors == 0, f"Checkerboard test failed with {errors} errors"
