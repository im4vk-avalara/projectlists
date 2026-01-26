"""
Graphics Kernel Tests for tiny-gpu
==================================

This test demonstrates visual output from the GPU using software rasterization.
The GPU renders to an 8x8 framebuffer (64 pixels) which is displayed as ASCII art.

Available graphics tests (run separately to avoid cache conflicts):
- make test_graphics_gradient      # Linear gradient
- make test_graphics_checkerboard  # Alternating pattern with divergence
- make test_graphics_circle        # Filled circle with single-level divergence

This file runs the gradient test as the default.
"""

import cocotb
from .helpers.graphics import (
    make_gradient_program,
    setup_and_run_kernel,
    display_framebuffer_blocks,
    display_framebuffer_ascii,
    verify_gradient,
)


@cocotb.test()
async def test_gradient(dut):
    """Test gradient kernel - linear brightness ramp."""
    
    THREADS = 64
    
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 18 + "GRADIENT KERNEL TEST" + " " * 20 + "║")
    print("║" + " " * 12 + "Each pixel = thread_id * 4" + " " * 20 + "║")
    print("╚" + "═" * 58 + "╝")
    
    program = make_gradient_program()
    data = [0] * 256
    
    fb, cycles = await setup_and_run_kernel(dut, program, data, THREADS, "GRADIENT")
    
    # Display result
    display_framebuffer_blocks(fb, "GRADIENT")
    display_framebuffer_ascii(fb, "GRADIENT")
    
    print(f"\n  First 16 values: {fb[:16]}")
    print(f"  Last 16 values:  {fb[48:64]}")
    
    # Verify
    errors, details = verify_gradient(fb, THREADS)
    
    if errors == 0:
        print(f"\n  ✓ GRADIENT PASSED ({cycles} cycles)")
    else:
        print(f"\n  ✗ GRADIENT FAILED: {errors} errors")
        for d in details[:10]:
            print(f"    {d}")
    
    assert errors == 0, f"Gradient test failed with {errors} errors"
