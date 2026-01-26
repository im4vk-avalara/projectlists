"""
Element-wise Maximum Test with Branch Divergence
-------------------------------------------------
Computes element-wise maximum of two vectors: C[i] = max(A[i], B[i])

This test demonstrates branch divergence - different threads take different paths
based on whether A[i] >= B[i] or A[i] < B[i].

Assembly:
    MUL R0, %blockIdx, %blockDim
    ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
    CONST R1, #0                   ; baseA
    CONST R2, #8                   ; baseB
    CONST R3, #16                  ; baseC
    ADD R4, R1, R0                 ; addr(A[i])
    LDR R4, R4                     ; load A[i]
    ADD R5, R2, R0                 ; addr(B[i])
    LDR R5, R5                     ; load B[i]
    ; Compare A[i] and B[i]
    CMP R4, R5                     ; compare A[i] - B[i]
    BRzp STORE_A                   ; if A[i] >= B[i], store A
    ; A[i] < B[i], so max = B[i]
    ADD R6, R5, R1                 ; R6 = B[i] (R1 is 0, so this copies B[i])
    BRnzp STORE                    ; jump to store
STORE_A:
    ADD R6, R4, R1                 ; R6 = A[i]
STORE:
    ADD R7, R3, R0                 ; addr(C[i]) = baseC + i
    STR R7, R6                     ; store max in global memory
    RET                            ; end of kernel

ALU NZP bits: bit2=positive (rs>rt), bit1=zero (rs==rt), bit0=negative (rs<rt)
BRzp (zero or positive): nzp = 110
BRnzp (unconditional): nzp = 111
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_vecmax(dut):
    # Program Memory
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    
    # Fixed NZP encoding:
    # ALU sets: bit2=positive, bit1=zero, bit0=negative
    # BRzp (zero or positive) = nzp bits 110
    # BRnzp (unconditional) = nzp bits 111
    
    program = [
        0b0101_0000_1101_1110,  # 0: MUL R0, %blockIdx, %blockDim
        0b0011_0000_0000_1111,  # 1: ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
        0b1001_0001_0000_0000,  # 2: CONST R1, #0                   ; baseA
        0b1001_0010_0000_1000,  # 3: CONST R2, #8                   ; baseB
        0b1001_0011_0001_0000,  # 4: CONST R3, #16                  ; baseC
        0b0011_0100_0001_0000,  # 5: ADD R4, R1, R0                 ; addr(A[i])
        0b0111_0100_0100_0000,  # 6: LDR R4, R4                     ; load A[i]
        0b0011_0101_0010_0000,  # 7: ADD R5, R2, R0                 ; addr(B[i])
        0b0111_0101_0101_0000,  # 8: LDR R5, R5                     ; load B[i]
        0b0010_0000_0100_0101,  # 9: CMP R4, R5                     ; compare A[i] - B[i]
        # BRzp #13: if A[i] >= B[i] (zero or positive), goto 13
        # BRnzp=0001, nzp=110, unused=0, imm=00001101
        0b0001_1100_0000_1101,  # 10: BRzp #13 (STORE_A)
        0b0011_0110_0101_0001,  # 11: ADD R6, R5, R1                ; R6 = B[i] (max = B)
        # BRnzp #14: unconditional jump
        # BRnzp=0001, nzp=111, unused=0, imm=00001110
        0b0001_1110_0000_1110,  # 12: BRnzp #14 (STORE)
        0b0011_0110_0100_0001,  # 13: ADD R6, R4, R1                ; R6 = A[i] (max = A) - STORE_A
        0b0011_0111_0011_0000,  # 14: ADD R7, R3, R0                ; addr(C[i]) = baseC + i - STORE
        0b1000_0000_0111_0110,  # 15: STR R7, R6                    ; store max
        0b1111_0000_0000_0000,  # 16: RET                           ; end of kernel
    ]

    # Data Memory - MIXED: some A[i] >= B[i], some A[i] < B[i] to test divergence!
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        # Vector A: [10, 3, 9, 2, 6, 5, 1, 8]
        10, 3, 9, 2, 6, 5, 1, 8,
        # Vector B: [5,  8, 3, 7, 6, 5, 4, 3]
        5,  8, 3, 7, 6, 5, 4, 3
    ]
    # Expected max: [10, 8, 9, 7, 6, 5, 4, 8]
    # Comparison:
    #   i=0: A=10 >= B=5  → max=10 (Path A)
    #   i=1: A=3  <  B=8  → max=8  (Path B) - DIVERGENCE!
    #   i=2: A=9  >= B=3  → max=9  (Path A)
    #   i=3: A=2  <  B=7  → max=7  (Path B) - DIVERGENCE!
    #   i=4: A=6  >= B=6  → max=6  (Path A - equal)
    #   i=5: A=5  >= B=5  → max=5  (Path A - equal)
    #   i=6: A=1  <  B=4  → max=4  (Path B) - DIVERGENCE!
    #   i=7: A=8  >= B=3  → max=8  (Path A)

    # Device Control
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
    logger.info("ELEMENT-WISE MAXIMUM TEST WITH BRANCH DIVERGENCE")
    logger.info("=" * 60)
    logger.info(f"Vector A: {data[0:8]}")
    logger.info(f"Vector B: {data[8:16]}")
    logger.info("")
    logger.info("Comparison (which causes divergence):")
    for i in range(8):
        a, b = data[i], data[8+i]
        path = "Path A (A>=B)" if a >= b else "Path B (A<B)"
        logger.info(f"  i={i}: A={a}, B={b} → {path}, max={max(a,b)}")
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

    # Read divergence statistics
    logger.info("\n" + "=" * 60)
    logger.info("BRANCH DIVERGENCE STATISTICS")
    logger.info("=" * 60)
    
    total_divergences = 0
    try:
        for core_idx in range(2):  # NUM_CORES = 2
            core = dut.cores[core_idx]
            div_count = int(core.core_instance.scheduler_instance.divergence_count.value)
            logger.info(f"Core {core_idx}: {div_count} divergences detected")
            total_divergences += div_count
    except Exception as e:
        logger.info(f"Could not read divergence stats: {e}")
    
    logger.info(f"Total divergences: {total_divergences}")
    logger.info("=" * 60)

    # Verify results: C[i] = max(A[i], B[i])
    expected_results = [max(a, b) for a, b in zip(data[0:8], data[8:16])]
    actual_results = [data_memory.memory[i + 16] for i in range(8)]
    
    logger.info(f"\nExpected C: {expected_results}")
    logger.info(f"Actual C:   {actual_results}")
    
    all_correct = True
    for i, (expected, actual) in enumerate(zip(expected_results, actual_results)):
        if expected != actual:
            logger.info(f"MISMATCH at index {i}: expected {expected}, got {actual}")
            all_correct = False
    
    if all_correct:
        logger.info("\nAll results correct!")
        logger.info("Branch divergence for max() working properly!")
    
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 16]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    logger.info("\ntest_vecmax PASSED!")
