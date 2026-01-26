"""
Branch Divergence Test
----------------------
Tests the branch divergence feature that allows threads to take different execution paths.

The kernel uses equality comparison (works reliably with unsigned arithmetic):
  for each thread i:
    if (A[i] == 4):
      C[i] = A[i] * 10    # Path A: multiply by 10 if value is 4
    else:
      C[i] = A[i] + 1     # Path B: add 1 otherwise

This causes divergence because:
- Thread 3 (value 4) takes Path A
- All other threads take Path B

Expected results:
- A[0]=1 != 4 → C[0] = 1+1 = 2
- A[1]=2 != 4 → C[1] = 2+1 = 3
- A[2]=3 != 4 → C[2] = 3+1 = 4
- A[3]=4 == 4 → C[3] = 4*10 = 40
- A[4]=5 != 4 → C[4] = 5+1 = 6
- A[5]=6 != 4 → C[5] = 6+1 = 7
- A[6]=7 != 4 → C[6] = 7+1 = 8
- A[7]=8 != 4 → C[7] = 8+1 = 9

ISA (from decoder.sv):
- NOP    = 4'b0000
- BRnzp  = 4'b0001  (branch if NZP condition matches)
- CMP    = 4'b0010  (compare rs - rt, set NZP: bit2=positive, bit1=zero, bit0=negative)
- ADD    = 4'b0011
- SUB    = 4'b0100
- MUL    = 4'b0101
- DIV    = 4'b0110
- LDR    = 4'b0111
- STR    = 4'b1000
- CONST  = 4'b1001

Instruction format: [15:12]=opcode, [11:8]=rd, [7:4]=rs, [3:0]=rt
For CONST: [15:12]=opcode, [11:8]=rd, [7:0]=immediate
For BRnzp: [15:12]=opcode, [11:9]=nzp_condition, [8]=unused, [7:0]=immediate (target PC)
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_diverge(dut):
    # Program Memory - conditional kernel with branch divergence
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    
    # Special registers: %blockIdx=13, %blockDim=14, %threadIdx=15
    
    program = [
        # 0: R0 = blockIdx * blockDim (MUL R0, %blockIdx, %blockDim)
        # MUL=0101, rd=0000, rs=1101(%blockIdx), rt=1110(%blockDim)
        0b0101_0000_1101_1110,
        
        # 1: R0 = R0 + threadIdx (ADD R0, R0, %threadIdx)
        # ADD=0011, rd=0000, rs=0000(R0), rt=1111(%threadIdx)
        0b0011_0000_0000_1111,
        
        # 2: R1 = 0 (baseA) (CONST R1, #0)
        0b1001_0001_0000_0000,
        
        # 3: R4 = R1 + R0 (ADD R4, R1, R0) - &A[i]
        0b0011_0100_0001_0000,
        
        # 4: R4 = mem[R4] (LDR R4, R4) - load A[i]
        0b0111_0100_0100_0000,
        
        # 5: R5 = 4 (threshold) (CONST R5, #4)
        0b1001_0101_0000_0100,
        
        # 6: CMP R4, R5 - compare A[i] with 4
        # CMP=0010, unused=0000, rs=0100(R4), rt=0101(R5)
        # Sets nzp: bit2=(rs-rt>0), bit1=(rs-rt==0), bit0=(rs-rt<0)
        0b0010_0000_0100_0101,
        
        # 7: BRnp #11 - if (A[i] != 4) goto 11 (nzp = 101 = n or p = not zero)
        # BRnzp=0001, nzp=101, unused=0, imm=00001011
        0b0001_1010_0000_1011,
        
        # 8: Path A: R6 = 10 (for A[i] == 4) (CONST R6, #10)
        0b1001_0110_0000_1010,
        
        # 9: R6 = R4 * R6 (MUL R6, R4, R6) - R6 = A[i] * 10
        0b0101_0110_0100_0110,
        
        # 10: BR #13 - unconditional branch to store (nzp = 111 = always)
        0b0001_1110_0000_1101,
        
        # 11: Path B: R6 = 1 (for A[i] != 4) (CONST R6, #1)
        0b1001_0110_0000_0001,
        
        # 12: R6 = R4 + R6 (ADD R6, R4, R6) - R6 = A[i] + 1
        0b0011_0110_0100_0110,
        
        # 13: R7 = 16 (baseC) (CONST R7, #16)
        0b1001_0111_0001_0000,
        
        # 14: R7 = R7 + R0 (ADD R7, R7, R0) - &C[i]
        0b0011_0111_0111_0000,
        
        # 15: STR R7, R6 - store C[i] = result
        0b1000_0000_0111_0110,
        
        # 16: RET
        0b1111_0000_0000_0000,
    ]

    # Data Memory
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        # A[0:7] - one value matches the threshold
        1, 2, 3, 4,   # Thread 3 has value 4 (matches) → Path A
        5, 6, 7, 8,   # All these don't match → Path B
        # Padding
        0, 0, 0, 0, 0, 0, 0, 0,
        # C[0:7] at address 16 - will be filled with results
    ]

    # 8 threads to process 8 elements
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
    logger.info("BRANCH DIVERGENCE TEST")
    logger.info("=" * 60)
    logger.info(f"Threads: {threads}")
    logger.info("")
    logger.info("Kernel logic (using equality check):")
    logger.info("  if (A[i] == 4):")
    logger.info("    C[i] = A[i] * 10    # Path A")
    logger.info("  else:")
    logger.info("    C[i] = A[i] + 1     # Path B")
    logger.info("")
    logger.info("Input A: [1, 2, 3, 4, 5, 6, 7, 8]")
    logger.info("Thread 3: takes Path A (value 4 matches)")
    logger.info("All others: take Path B")
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

    # Calculate expected results
    input_a = data[0:8]
    expected_results = []
    for val in input_a:
        if val == 4:
            expected_results.append(val * 10)  # Path A
        else:
            expected_results.append(val + 1)   # Path B
    
    actual_results = [data_memory.memory[i + 16] for i in range(8)]
    
    logger.info(f"\nInput A:   {input_a}")
    logger.info(f"Expected C: {expected_results}")
    logger.info(f"Actual C:   {actual_results}")
    
    # Verify results
    all_correct = True
    for i, (expected, actual) in enumerate(zip(expected_results, actual_results)):
        if expected != actual:
            logger.info(f"MISMATCH at index {i}: expected {expected}, got {actual}")
            all_correct = False
    
    if all_correct:
        logger.info("\nAll results correct!")
        logger.info("Branch divergence working properly!")
    else:
        logger.info("\nSome results incorrect - divergence may not be working")
        
    # Assert all results match
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 16]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    logger.info(f"\nBranch divergence test PASSED!")
