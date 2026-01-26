"""
Vector Subtraction Test
-----------------------
Subtracts two 1x8 vectors element-wise: C[i] = A[i] - B[i]

This test demonstrates basic SIMD parallel subtraction across 8 threads.

Assembly:
    MUL R0, %blockIdx, %blockDim
    ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
    CONST R1, #0                   ; baseA (matrix A base address)
    CONST R2, #8                   ; baseB (matrix B base address)
    CONST R3, #16                  ; baseC (matrix C base address)
    ADD R4, R1, R0                 ; addr(A[i]) = baseA + i
    LDR R4, R4                     ; load A[i] from global memory
    ADD R5, R2, R0                 ; addr(B[i]) = baseB + i
    LDR R5, R5                     ; load B[i] from global memory
    SUB R6, R4, R5                 ; C[i] = A[i] - B[i]
    ADD R7, R3, R0                 ; addr(C[i]) = baseC + i
    STR R7, R6                     ; store C[i] in global memory
    RET                            ; end of kernel
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_vecsub(dut):
    # Program Memory
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    program = [
        0b0101000011011110,  # MUL R0, %blockIdx, %blockDim
        0b0011000000001111,  # ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
        0b1001000100000000,  # CONST R1, #0                   ; baseA (vector A base address)
        0b1001001000001000,  # CONST R2, #8                   ; baseB (vector B base address)
        0b1001001100010000,  # CONST R3, #16                  ; baseC (vector C base address)
        0b0011010000010000,  # ADD R4, R1, R0                 ; addr(A[i]) = baseA + i
        0b0111010001000000,  # LDR R4, R4                     ; load A[i] from global memory
        0b0011010100100000,  # ADD R5, R2, R0                 ; addr(B[i]) = baseB + i
        0b0111010101010000,  # LDR R5, R5                     ; load B[i] from global memory
        0b0100011001000101,  # SUB R6, R4, R5                 ; C[i] = A[i] - B[i]
        0b0011011100110000,  # ADD R7, R3, R0                 ; addr(C[i]) = baseC + i
        0b1000000001110110,  # STR R7, R6                     ; store C[i] in global memory
        0b1111000000000000,  # RET                            ; end of kernel
    ]

    # Data Memory
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        10, 20, 30, 40, 50, 60, 70, 80,  # Vector A (1 x 8)
        1,  2,  3,  4,  5,  6,  7,  8    # Vector B (1 x 8)
    ]

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

    logger.info("=== Vector Subtraction Test ===")
    logger.info(f"Vector A: {data[0:8]}")
    logger.info(f"Vector B: {data[8:16]}")
    data_memory.display(24)

    cycles = 0
    while dut.done.value != 1:
        data_memory.run()
        program_memory.run()

        await cocotb.triggers.ReadOnly()
        format_cycle(dut, cycles)
        
        await RisingEdge(dut.clk)
        cycles += 1

    logger.info(f"Completed in {cycles} cycles")
    data_memory.display(24)

    # Verify results: C[i] = A[i] - B[i]
    expected_results = [a - b for a, b in zip(data[0:8], data[8:16])]
    logger.info(f"Expected C: {expected_results}")
    logger.info(f"Actual C:   {[data_memory.memory[i + 16] for i in range(8)]}")
    
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 16]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    logger.info("All assertions passed!")
