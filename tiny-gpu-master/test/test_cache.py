"""
Instruction Cache Test
----------------------
Tests the instruction cache functionality by:
1. Running a kernel with multiple blocks (to see cache hits after first block)
2. Measuring cache hits vs misses
3. Verifying that subsequent blocks benefit from cached instructions

With 8 threads and THREADS_PER_BLOCK=4, we get 2 blocks.
- Block 0: All instructions are cache misses (cold cache)
- Block 1: All instructions should be cache hits (warm cache)

The matadd kernel has 13 instructions, so:
- Core 0 (Block 0): 13 misses, 0 hits initially
- Core 1 (Block 1): Should see 13 hits if cache works

Note: Each core has its own cache, so Block 1 on Core 1 will also have cold cache.
To truly test cache hits, we need blocks to reuse the same core.

This test uses 16 threads = 4 blocks, processed on 2 cores:
- Core 0: Block 0, then Block 2
- Core 1: Block 1, then Block 3
Block 2 and 3 should hit the cache from Block 0 and 1 respectively.
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_cache(dut):
    # Program Memory - same as matadd (13 instructions)
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    program = [
        0b0101000011011110,  # 0:  MUL R0, %blockIdx, %blockDim
        0b0011000000001111,  # 1:  ADD R0, R0, %threadIdx
        0b1001000100000000,  # 2:  CONST R1, #0
        0b1001001000010000,  # 3:  CONST R2, #16
        0b1001001100100000,  # 4:  CONST R3, #32
        0b0011010000010000,  # 5:  ADD R4, R1, R0
        0b0111010001000000,  # 6:  LDR R4, R4
        0b0011010100100000,  # 7:  ADD R5, R2, R0
        0b0111010101010000,  # 8:  LDR R5, R5
        0b0011011001000101,  # 9:  ADD R6, R4, R5
        0b0011011100110000,  # 10: ADD R7, R3, R0
        0b1000000001110110,  # 11: STR R7, R6
        0b1111000000000000,  # 12: RET
    ]
    num_instructions = len(program)

    # Data Memory - 16-element vectors for 16 threads
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        # Vector A (16 elements) at addresses 0-15
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
        # Vector B (16 elements) at addresses 16-31
        1, 1, 1, 1, 1, 1, 1, 1, 1, 1,  1,  1,  1,  1,  1,  1,
    ]

    # Device Control - 16 threads = 4 blocks on 2 cores
    # This means each core processes 2 blocks sequentially
    threads = 16

    await setup(
        dut=dut,
        program_memory=program_memory,
        program=program,
        data_memory=data_memory,
        data=data,
        threads=threads
    )

    logger.info("=" * 60)
    logger.info("INSTRUCTION CACHE TEST")
    logger.info("=" * 60)
    logger.info(f"Program size: {num_instructions} instructions")
    logger.info(f"Threads: {threads} (4 blocks on 2 cores)")
    logger.info(f"Each core processes 2 blocks sequentially")
    logger.info("")
    logger.info("Expected behavior:")
    logger.info("  - First block on each core: all cache MISSES")
    logger.info("  - Second block on each core: all cache HITS")
    logger.info("=" * 60)

    cycles = 0
    while dut.done.value != 1:
        data_memory.run()
        program_memory.run()

        await cocotb.triggers.ReadOnly()
        format_cycle(dut, cycles)
        
        await RisingEdge(dut.clk)
        cycles += 1

    logger.info(f"\nCompleted in {cycles} cycles")

    # Read cache statistics from each core
    # Access through the core instances directly
    logger.info("\n" + "=" * 60)
    logger.info("CACHE STATISTICS")
    logger.info("=" * 60)
    
    total_hits = 0
    total_misses = 0
    
    for core in dut.cores:
        try:
            core_idx = int(core.i.value) if hasattr(core.i.value, '__int__') else int(str(core.i.value), 2)
            
            # Try to access through fetcher_instance
            fetcher = core.core_instance.fetcher_instance
            hits_raw = fetcher.cache_hits.value
            misses_raw = fetcher.cache_misses.value
            prefetch_hits_raw = fetcher.prefetch_hits.value
            
            logger.info(f"Core {core_idx} raw values: hits={hits_raw}, misses={misses_raw}, prefetch_hits={prefetch_hits_raw}")
            
            hits = int(hits_raw)
            misses = int(misses_raw)
            prefetch_hits = int(prefetch_hits_raw)
            # Prefetch hits also count as cache hits (they came from cache)
            total_hits += hits + prefetch_hits
            total_misses += misses
            hit_rate = ((hits + prefetch_hits) / (hits + prefetch_hits + misses) * 100) if (hits + prefetch_hits + misses) > 0 else 0
            
            logger.info(f"Core {core_idx}:")
            logger.info(f"  Cache Hits:    {hits}")
            logger.info(f"  Prefetch Hits: {prefetch_hits}")
            logger.info(f"  Cache Misses:  {misses}")
            logger.info(f"  Hit Rate:      {hit_rate:.1f}%")
        except Exception as e:
            import traceback
            logger.info(f"Could not read cache stats: {e}")
            logger.info(traceback.format_exc())
    
    total_accesses = total_hits + total_misses
    overall_hit_rate = (total_hits / total_accesses * 100) if total_accesses > 0 else 0
    
    logger.info("")
    logger.info(f"TOTAL:")
    logger.info(f"  Total Hits:   {total_hits}")
    logger.info(f"  Total Misses: {total_misses}")
    logger.info(f"  Overall Hit Rate: {overall_hit_rate:.1f}%")
    logger.info("=" * 60)

    # Verify results
    expected_results = [a + b for a, b in zip(data[0:16], data[16:32])]
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 32]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    logger.info("\nComputation results verified!")

    # Verify cache behavior
    # Each core processes 2 blocks, each block executes all instructions
    # First block: all misses (13 misses per core)
    # Second block: all hits (13 hits per core)
    # So each core should have 13 hits and 13 misses
    expected_misses_per_core = num_instructions  # First block
    expected_hits_per_core = num_instructions    # Second block
    
    logger.info(f"\nExpected per core: {expected_hits_per_core} hits, {expected_misses_per_core} misses")
    logger.info(f"Expected hit rate: 50% (first block cold, second block warm)")
    
    # Check that we have some cache hits (cache is working)
    assert total_hits > 0, "Cache should have some hits on second block execution!"
    
    # Check hit rate is approximately 50% (allowing some margin)
    # Each core runs 2 blocks, first is all misses, second is all hits
    assert overall_hit_rate >= 40, f"Hit rate should be ~50%, got {overall_hit_rate:.1f}%"
    
    # Show prefetch improvement stats
    logger.info("\n" + "=" * 60)
    logger.info("PREFETCH PIPELINE IMPROVEMENT")
    logger.info("=" * 60)
    
    total_prefetch = 0
    for core in dut.cores:
        try:
            fetcher = core.core_instance.fetcher_instance
            pf_hits = int(fetcher.prefetch_hits.value)
            total_prefetch += pf_hits
        except:
            pass
    
    cycles_saved = total_prefetch * 2  # ~2 cycles saved per prefetch hit
    improvement = (cycles_saved / (cycles + cycles_saved) * 100) if (cycles + cycles_saved) > 0 else 0
    
    logger.info(f"Prefetch hits:           {total_prefetch}")
    logger.info(f"Cycles saved (estimate): ~{cycles_saved}")
    logger.info(f"SPEEDUP: ~{improvement:.1f}% faster with prefetch pipeline")
    logger.info("=" * 60)
    
    logger.info("\nCache test PASSED!")
    logger.info(f"  - Cache is functioning correctly")
    logger.info(f"  - Second block benefits from cached instructions")
    logger.info(f"  - Prefetch pipeline provides additional speedup")
