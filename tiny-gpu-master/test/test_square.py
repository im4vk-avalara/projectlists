"""
Element-wise Square Test
------------------------
Squares each element of a vector: C[i] = A[i] * A[i]

This test demonstrates self-multiplication for squaring operation.

Assembly:
    MUL R0, %blockIdx, %blockDim
    ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
    CONST R1, #0                   ; baseA (vector A base address)
    CONST R2, #8                   ; baseC (vector C base address)
    ADD R3, R1, R0                 ; addr(A[i]) = baseA + i
    LDR R3, R3                     ; load A[i] from global memory
    MUL R4, R3, R3                 ; C[i] = A[i] * A[i]
    ADD R5, R2, R0                 ; addr(C[i]) = baseC + i
    STR R5, R4                     ; store C[i] in global memory
    RET                            ; end of kernel
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_square(dut):
    # Program Memory
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    program = [
        0b0101000011011110,  # MUL R0, %blockIdx, %blockDim
        0b0011000000001111,  # ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
        0b1001000100000000,  # CONST R1, #0                   ; baseA (vector A base address)
        0b1001001000001000,  # CONST R2, #8                   ; baseC (vector C base address)
        0b0011001100010000,  # ADD R3, R1, R0                 ; addr(A[i]) = baseA + i
        0b0111001100110000,  # LDR R3, R3                     ; load A[i] from global memory
        0b0101010000110011,  # MUL R4, R3, R3                 ; C[i] = A[i] * A[i]
        0b0011010100100000,  # ADD R5, R2, R0                 ; addr(C[i]) = baseC + i
        0b1000000001010100,  # STR R5, R4                     ; store C[i] in global memory
        0b1111000000000000,  # RET                            ; end of kernel
    ]

    # Data Memory
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        1, 2, 3, 4, 5, 6, 7, 8  # Vector A (1 x 8)
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

    logger.info("=== Element-wise Square Test ===")
    logger.info(f"Vector A: {data}")
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

    # Verify results: C[i] = A[i]^2
    expected_results = [a * a for a in data]
    logger.info(f"Expected C: {expected_results}")
    logger.info(f"Actual C:   {[data_memory.memory[i + 8] for i in range(8)]}")
    
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 8]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    logger.info("All assertions passed!")
