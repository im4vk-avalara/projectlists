"""
Graphics Test: Circle Kernel
============================

Renders a filled circle in the center of the framebuffer.
Uses nested branch divergence for absolute value computation.

NOTE: This kernel uses complex nested branching which may cause
issues with the current divergence stack implementation.
"""

import cocotb
from .helpers.graphics import (
    make_circle_program,
    setup_and_run_kernel,
    display_framebuffer_blocks,
    display_framebuffer_ascii,
    verify_circle,
)


@cocotb.test()
async def test_circle(dut):
    """Test circle kernel - filled circle using distance calculation."""
    
    THREADS = 64
    
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 20 + "CIRCLE KERNEL TEST" + " " * 20 + "║")
    print("║" + " " * 10 + "Filled circle at (4,4) with radius 3" + " " * 11 + "║")
    print("╚" + "═" * 58 + "╝")
    
    program = make_circle_program()
    data = [0] * 256
    
    fb, cycles = await setup_and_run_kernel(dut, program, data, THREADS, "CIRCLE", timeout=200000)
    
    # Display result
    display_framebuffer_blocks(fb, "CIRCLE")
    display_framebuffer_ascii(fb, "CIRCLE")
    
    print(f"\n  First 16 values: {fb[:16]}")
    
    # Verify
    errors, details = verify_circle(fb, THREADS)
    
    if errors == 0:
        print(f"\n  ✓ CIRCLE PASSED ({cycles} cycles)")
    else:
        print(f"\n  ✗ CIRCLE FAILED: {errors} errors")
        for d in details[:10]:
            print(f"    {d}")
    
    assert errors == 0, f"Circle test failed with {errors} errors"
