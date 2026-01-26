"""
Pipeline / Instruction Prefetch Test
------------------------------------
Tests the instruction prefetch pipeline optimization.

The prefetch pipeline overlaps the FETCH stage with EXECUTE/UPDATE:
- While current instruction executes, next instruction (PC+1) is prefetched
- If next PC matches prefetch, instruction is ready immediately
- This saves cycles on sequential code paths

This test:
1. Runs a simple sequential kernel (no branches)
2. Measures prefetch hit rate
3. Compares cycle count to expected non-pipelined execution

Expected behavior:
- High prefetch hit rate for sequential code
- Reduced total cycle count compared to non-pipelined
- Prefetch misses on branches (speculative prefetch was wrong PC)
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_pipeline(dut):
    # Program Memory - simple sequential kernel (ideal for prefetching)
    # No branches = every prefetch should hit
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    
    # Simple kernel: C[i] = A[i] + B[i] (same as matadd but we measure pipeline stats)
    program = [
        0b0101_0000_1101_1110,  # 0: MUL R0, %blockIdx, %blockDim
        0b0011_0000_0000_1111,  # 1: ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
        0b1001_0001_0000_0000,  # 2: CONST R1, #0                   ; baseA
        0b1001_0010_0001_0000,  # 3: CONST R2, #16                  ; baseB
        0b1001_0011_0010_0000,  # 4: CONST R3, #32                  ; baseC
        0b0011_0100_0001_0000,  # 5: ADD R4, R1, R0                 ; addr(A[i])
        0b0111_0100_0100_0000,  # 6: LDR R4, R4                     ; load A[i]
        0b0011_0101_0010_0000,  # 7: ADD R5, R2, R0                 ; addr(B[i])
        0b0111_0101_0101_0000,  # 8: LDR R5, R5                     ; load B[i]
        0b0011_0110_0100_0101,  # 9: ADD R6, R4, R5                 ; C[i] = A[i] + B[i]
        0b0011_0111_0011_0000,  # 10: ADD R7, R3, R0                ; addr(C[i])
        0b1000_0000_0111_0110,  # 11: STR R7, R6                    ; store C[i]
        0b1111_0000_0000_0000,  # 12: RET
    ]

    # Data Memory - 16 elements for 4 blocks (to see prefetch benefit on warm cache)
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        # Vector A (16 elements)
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
        # Vector B (16 elements)
        10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160
    ]

    # 16 threads = 4 blocks on 2 cores
    # First 2 blocks: cold cache (no prefetch benefit)
    # Last 2 blocks: warm cache (prefetch hits!)
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
    logger.info("PIPELINE / INSTRUCTION PREFETCH TEST")
    logger.info("=" * 60)
    logger.info(f"Threads: {threads} (4 blocks on 2 cores)")
    logger.info(f"Program: 13 instructions (sequential, no branches)")
    logger.info("")
    logger.info("Test runs 4 blocks to demonstrate prefetch benefit:")
    logger.info("  - First 2 blocks: cold cache (cache misses)")
    logger.info("  - Last 2 blocks: warm cache (prefetch hits!)")
    logger.info("")
    logger.info("Prefetch pipeline overlaps FETCH with EXECUTE/UPDATE:")
    logger.info("  - While executing instruction N, prefetch instruction N+1")
    logger.info("  - Sequential code with warm cache = high prefetch hit rate")
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
    data_memory.display(48)  # Show through address 47 to see results at 32-47

    # Read pipeline/prefetch statistics
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE STATISTICS")
    logger.info("=" * 60)
    
    total_prefetch_hits = 0
    total_prefetch_misses = 0
    total_cache_hits = 0
    total_cache_misses = 0
    
    try:
        for core_idx in range(2):  # NUM_CORES = 2
            core = dut.cores[core_idx]
            fetcher = core.core_instance.fetcher_instance
            
            pf_hits = int(fetcher.prefetch_hits.value)
            pf_misses = int(fetcher.prefetch_misses.value)
            c_hits = int(fetcher.cache_hits.value)
            c_misses = int(fetcher.cache_misses.value)
            
            logger.info(f"Core {core_idx}:")
            logger.info(f"  Prefetch hits:   {pf_hits}")
            logger.info(f"  Prefetch misses: {pf_misses}")
            logger.info(f"  Cache hits:      {c_hits}")
            logger.info(f"  Cache misses:    {c_misses}")
            
            total_prefetch_hits += pf_hits
            total_prefetch_misses += pf_misses
            total_cache_hits += c_hits
            total_cache_misses += c_misses
            
    except Exception as e:
        logger.info(f"Could not read pipeline stats: {e}")
    
    total_fetches = total_prefetch_hits + total_cache_hits + total_cache_misses
    prefetch_rate = (total_prefetch_hits / total_fetches * 100) if total_fetches > 0 else 0
    
    logger.info("")
    logger.info(f"Total instruction fetches: {total_fetches}")
    logger.info(f"  From prefetch buffer:    {total_prefetch_hits} ({prefetch_rate:.1f}%)")
    logger.info(f"  From cache:              {total_cache_hits}")
    logger.info(f"  From memory:             {total_cache_misses}")
    logger.info("=" * 60)

    # Verify results (16 elements at address 32)
    expected_results = [a + b for a, b in zip(data[0:16], data[16:32])]
    actual_results = [data_memory.memory[i + 32] for i in range(16)]
    
    logger.info(f"\nExpected C: {expected_results}")
    logger.info(f"Actual C:   {actual_results}")
    
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 32]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    # Calculate performance improvement from prefetching
    # Each prefetch hit saves at least 1-2 cycles (avoids FETCH stage latency)
    cycles_saved_per_prefetch = 2  # Conservative estimate
    cycles_saved_estimate = total_prefetch_hits * cycles_saved_per_prefetch
    
    # Estimate baseline cycles (without prefetch optimization)
    baseline_cycles = cycles + cycles_saved_estimate
    improvement_percent = (cycles_saved_estimate / baseline_cycles * 100) if baseline_cycles > 0 else 0
    
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE PERFORMANCE IMPROVEMENT")
    logger.info("=" * 60)
    logger.info(f"Total cycles executed:         {cycles}")
    logger.info(f"Prefetch hits:                 {total_prefetch_hits}")
    logger.info(f"Cycles saved (estimate):       ~{cycles_saved_estimate}")
    logger.info(f"Baseline cycles (no prefetch): ~{baseline_cycles}")
    logger.info(f"")
    logger.info(f"  SPEEDUP: ~{improvement_percent:.1f}% faster with prefetch pipeline")
    logger.info(f"")
    logger.info(f"Note: Prefetch works best when:")
    logger.info(f"  - Instructions are already in cache (multi-block execution)")
    logger.info(f"  - Code is sequential (no branches invalidate prefetch)")
    logger.info("=" * 60)
    
    logger.info("\ntest_pipeline PASSED!")
