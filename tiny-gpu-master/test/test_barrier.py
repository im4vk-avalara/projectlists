"""
Barrier Synchronization Test
----------------------------
Tests the SYNC instruction which provides barrier synchronization.

All threads in a block must reach the barrier (SYNC instruction) before
any can proceed. In tiny-gpu's lockstep execution, threads are always
synchronized, but the SYNC instruction is tracked for statistics and
demonstrates the infrastructure for future warp scheduling.

This test:
1. Runs a kernel with SYNC instructions
2. Verifies barrier_count is incremented correctly
3. Verifies correct computation despite barriers

Kernel: Element-wise operation with barrier in the middle
    i = blockIdx * blockDim + threadIdx
    R4 = A[i]              ; Load first value
    SYNC                   ; Barrier - wait for all threads
    R5 = B[i]              ; Load second value
    SYNC                   ; Another barrier
    C[i] = R4 + R5         ; Store result
    RET

SYNC opcode = 1010 (0xA)
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_barrier(dut):
    # Program Memory
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    
    # SYNC instruction: opcode=1010, rest zeros = 0b1010_0000_0000_0000 = 0xA000
    SYNC_INSTR = 0b1010000000000000
    
    program = [
        0b0101000011011110,  # 0:  MUL R0, %blockIdx, %blockDim
        0b0011000000001111,  # 1:  ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
        0b1001000100000000,  # 2:  CONST R1, #0                   ; baseA
        0b1001001000001000,  # 3:  CONST R2, #8                   ; baseB
        0b1001001100010000,  # 4:  CONST R3, #16                  ; baseC
        0b0011010000010000,  # 5:  ADD R4, R1, R0                 ; addr(A[i])
        0b0111010001000000,  # 6:  LDR R4, R4                     ; load A[i]
        SYNC_INSTR,          # 7:  SYNC                           ; barrier 1
        0b0011010100100000,  # 8:  ADD R5, R2, R0                 ; addr(B[i])
        0b0111010101010000,  # 9:  LDR R5, R5                     ; load B[i]
        SYNC_INSTR,          # 10: SYNC                           ; barrier 2
        0b0011011001000101,  # 11: ADD R6, R4, R5                 ; C[i] = A[i] + B[i]
        0b0011011100110000,  # 12: ADD R7, R3, R0                 ; addr(C[i])
        0b1000000001110110,  # 13: STR R7, R6                     ; store C[i]
        0b1111000000000000,  # 14: RET
    ]

    # Data Memory
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        1, 2, 3, 4, 5, 6, 7, 8,  # Vector A (1 x 8)
        10, 20, 30, 40, 50, 60, 70, 80  # Vector B (1 x 8)
    ]

    # 8 threads = 2 blocks on 2 cores
    threads = 8

    await setup(
        dut=dut,
        program_memory=program_memory,
        program=program,
        data_memory=data_memory,
        data=data,
        threads=threads
    )

    logger.info("=" * 60)
    logger.info("BARRIER SYNCHRONIZATION TEST")
    logger.info("=" * 60)
    logger.info(f"Program has 2 SYNC (barrier) instructions per block")
    logger.info(f"Threads: {threads} (2 blocks on 2 cores)")
    logger.info(f"Each core runs 1 block with 2 barriers = 2 barrier_count per core")
    logger.info("=" * 60)
    
    data_memory.display(24)

    cycles = 0
    while dut.done.value != 1:
        data_memory.run()
        program_memory.run()

        await cocotb.triggers.ReadOnly()
        format_cycle(dut, cycles)
        
        await RisingEdge(dut.clk)
        cycles += 1

    logger.info(f"\nCompleted in {cycles} cycles")
    data_memory.display(24)

    # Read barrier statistics from each core
    logger.info("\n" + "=" * 60)
    logger.info("BARRIER STATISTICS")
    logger.info("=" * 60)
    
    total_barriers = 0
    
    for core in dut.cores:
        try:
            core_idx = int(core.i.value) if hasattr(core.i.value, '__int__') else int(str(core.i.value), 2)
            
            # Access barrier_count through scheduler_instance
            scheduler = core.core_instance.scheduler_instance
            barrier_raw = scheduler.barrier_count.value
            
            logger.info(f"Core {core_idx} barrier_count raw: {barrier_raw}")
            
            barriers = int(barrier_raw)
            total_barriers += barriers
            
            logger.info(f"Core {core_idx}: {barriers} barriers executed")
        except Exception as e:
            import traceback
            logger.info(f"Could not read barrier stats: {e}")
            logger.info(traceback.format_exc())
    
    logger.info(f"\nTotal barriers executed: {total_barriers}")
    logger.info("=" * 60)

    # Verify computation results
    expected_results = [a + b for a, b in zip(data[0:8], data[8:16])]
    actual_results = [data_memory.memory[i + 16] for i in range(8)]
    
    logger.info(f"\nExpected C: {expected_results}")
    logger.info(f"Actual C:   {actual_results}")
    
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 16]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    logger.info("\nComputation results verified!")

    # Verify barrier count
    # Each block has 2 SYNC instructions
    # 2 blocks total (8 threads / 4 threads_per_block)
    # But each core processes 1 block, so each core should have 2 barriers
    expected_barriers_per_core = 2
    
    logger.info(f"\nExpected barriers per core: {expected_barriers_per_core}")
    logger.info(f"Expected total barriers: {expected_barriers_per_core * 2}")
    
    assert total_barriers == expected_barriers_per_core * 2, \
        f"Expected {expected_barriers_per_core * 2} total barriers, got {total_barriers}"
    
    logger.info("\nBarrier test PASSED!")
    logger.info(f"  - SYNC instruction recognized correctly")
    logger.info(f"  - Barrier count tracked: {total_barriers} total")
    logger.info(f"  - Computation correct despite barriers")
