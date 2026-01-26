"""
Scalar Multiplication Test
--------------------------
Multiplies each element of a vector by a scalar constant: C[i] = k * A[i]

This test demonstrates using CONST to load a scalar value and multiply.

Assembly:
    MUL R0, %blockIdx, %blockDim
    ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
    CONST R1, #0                   ; baseA (vector A base address)
    CONST R2, #8                   ; baseC (vector C base address)
    CONST R3, #3                   ; scalar k = 3
    ADD R4, R1, R0                 ; addr(A[i]) = baseA + i
    LDR R4, R4                     ; load A[i] from global memory
    MUL R5, R4, R3                 ; C[i] = A[i] * k
    ADD R6, R2, R0                 ; addr(C[i]) = baseC + i
    STR R6, R5                     ; store C[i] in global memory
    RET                            ; end of kernel
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_scalar(dut):
    # Program Memory
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    program = [
        0b0101000011011110,  # MUL R0, %blockIdx, %blockDim
        0b0011000000001111,  # ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
        0b1001000100000000,  # CONST R1, #0                   ; baseA (vector A base address)
        0b1001001000001000,  # CONST R2, #8                   ; baseC (vector C base address)
        0b1001001100000011,  # CONST R3, #3                   ; scalar k = 3
        0b0011010000010000,  # ADD R4, R1, R0                 ; addr(A[i]) = baseA + i
        0b0111010001000000,  # LDR R4, R4                     ; load A[i] from global memory
        0b0101010101000011,  # MUL R5, R4, R3                 ; C[i] = A[i] * k
        0b0011011000100000,  # ADD R6, R2, R0                 ; addr(C[i]) = baseC + i
        0b1000000001100101,  # STR R6, R5                     ; store C[i] in global memory
        0b1111000000000000,  # RET                            ; end of kernel
    ]

    # Data Memory
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        1, 2, 3, 4, 5, 6, 7, 8  # Vector A (1 x 8)
    ]

    # Scalar multiplier
    k = 3

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

    logger.info("=== Scalar Multiplication Test ===")
    logger.info(f"Vector A: {data}")
    logger.info(f"Scalar k: {k}")
    data_memory.display(16)

    cycles = 0
    while dut.done.value != 1:
        data_memory.run()
        program_memory.run()

        await cocotb.triggers.ReadOnly()
        format_cycle(dut, cycles)
        
        await RisingEdge(dut.clk)
        cycles += 1

    logger.info(f"Completed in {cycles} cycles")
    data_memory.display(16)

    # Verify results: C[i] = k * A[i]
    expected_results = [k * a for a in data]
    logger.info(f"Expected C: {expected_results}")
    logger.info(f"Actual C:   {[data_memory.memory[i + 8] for i in range(8)]}")
    
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 8]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    logger.info("All assertions passed!")
