"""
4x4 Matrix Multiplication Test
------------------------------
Multiplies two 4x4 matrices: C = A * B

Uses 16 threads (one per output element) to compute in parallel.
Each thread computes one element: C[row][col] = sum(A[row][k] * B[k][col]) for k=0..3

This demonstrates:
- Larger parallel workloads (16 threads across 2 cores with 4 threads each = 4 blocks)
- Loop-based accumulation with CMP and BRn
- More complex address calculations

Assembly (same algorithm as 2x2, but with N=4):
    MUL R0, %blockIdx, %blockDim
    ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
    CONST R1, #1                   ; increment
    CONST R2, #4                   ; N (matrix dimension)
    CONST R3, #0                   ; baseA
    CONST R4, #16                  ; baseB (4*4 = 16)
    CONST R5, #32                  ; baseC (16 + 16 = 32)
    DIV R6, R0, R2                 ; row = i // N
    MUL R7, R6, R2
    SUB R7, R0, R7                 ; col = i % N
    CONST R8, #0                   ; acc = 0
    CONST R9, #0                   ; k = 0
LOOP:
    MUL R10, R6, R2
    ADD R10, R10, R9
    ADD R10, R10, R3               ; addr(A[row][k]) = row * N + k + baseA
    LDR R10, R10                   ; load A[row][k]
    MUL R11, R9, R2
    ADD R11, R11, R7
    ADD R11, R11, R4               ; addr(B[k][col]) = k * N + col + baseB
    LDR R11, R11                   ; load B[k][col]
    MUL R12, R10, R11
    ADD R8, R8, R12                ; acc += A[row][k] * B[k][col]
    ADD R9, R9, R1                 ; k++
    CMP R9, R2
    BRn LOOP                       ; loop while k < N
    ADD R9, R5, R0                 ; addr(C[i]) = baseC + i
    STR R9, R8                     ; store C[i]
    RET
"""
import cocotb
from cocotb.triggers import RisingEdge
from .helpers.setup import setup
from .helpers.memory import Memory
from .helpers.format import format_cycle
from .helpers.logger import logger

@cocotb.test()
async def test_matmul4x4(dut):
    # Program Memory
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    program = [
        0b0101000011011110,  # 0:  MUL R0, %blockIdx, %blockDim
        0b0011000000001111,  # 1:  ADD R0, R0, %threadIdx         ; i = blockIdx * blockDim + threadIdx
        0b1001000100000001,  # 2:  CONST R1, #1                   ; increment
        0b1001001000000100,  # 3:  CONST R2, #4                   ; N (matrix dimension)
        0b1001001100000000,  # 4:  CONST R3, #0                   ; baseA
        0b1001010000010000,  # 5:  CONST R4, #16                  ; baseB (4*4 = 16)
        0b1001010100100000,  # 6:  CONST R5, #32                  ; baseC (16 + 16 = 32)
        0b0110011000000010,  # 7:  DIV R6, R0, R2                 ; row = i // N
        0b0101011101100010,  # 8:  MUL R7, R6, R2
        0b0100011100000111,  # 9:  SUB R7, R0, R7                 ; col = i % N
        0b1001100000000000,  # 10: CONST R8, #0                   ; acc = 0
        0b1001100100000000,  # 11: CONST R9, #0                   ; k = 0
                             # LOOP (PC 12):
        0b0101101001100010,  # 12: MUL R10, R6, R2
        0b0011101010101001,  # 13: ADD R10, R10, R9
        0b0011101010100011,  # 14: ADD R10, R10, R3               ; addr(A[row][k])
        0b0111101010100000,  # 15: LDR R10, R10                   ; load A[row][k]
        0b0101101110010010,  # 16: MUL R11, R9, R2
        0b0011101110110111,  # 17: ADD R11, R11, R7
        0b0011101110110100,  # 18: ADD R11, R11, R4               ; addr(B[k][col])
        0b0111101110110000,  # 19: LDR R11, R11                   ; load B[k][col]
        0b0101110010101011,  # 20: MUL R12, R10, R11
        0b0011100010001100,  # 21: ADD R8, R8, R12                ; acc += A * B
        0b0011100110010001,  # 22: ADD R9, R9, R1                 ; k++
        0b0010000010010010,  # 23: CMP R9, R2 (sets nzp: bit2=(k>N), bit1=(k==N), bit0=(k<N))
        0b0001001000001100,  # 24: BRn #12 (nzp=001 checks bit0=less) ; loop while k < N
        0b0011100101010000,  # 25: ADD R9, R5, R0                 ; addr(C[i]) = baseC + i
        0b1000000010011000,  # 26: STR R9, R8                     ; store C[i]
        0b1111000000000000,  # 27: RET
    ]

    # Data Memory - 4x4 matrices
    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    
    # Matrix A (4x4) - simple values for easy verification
    matrix_a = [
        1, 2, 3, 4,
        5, 6, 7, 8,
        1, 0, 1, 0,
        0, 1, 0, 1
    ]
    
    # Matrix B (4x4)
    matrix_b = [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
    ]
    
    data = matrix_a + matrix_b

    # Device Control - 16 threads for 16 output elements
    threads = 16

    await setup(
        dut=dut,
        program_memory=program_memory,
        program=program,
        data_memory=data_memory,
        data=data,
        threads=threads
    )

    logger.info("=== 4x4 Matrix Multiplication Test ===")
    logger.info("Matrix A (4x4):")
    for i in range(4):
        logger.info(f"  {matrix_a[i*4:(i+1)*4]}")
    logger.info("Matrix B (4x4):")
    for i in range(4):
        logger.info(f"  {matrix_b[i*4:(i+1)*4]}")
    data_memory.display(48)

    cycles = 0
    while dut.done.value != 1:
        data_memory.run()
        program_memory.run()

        await cocotb.triggers.ReadOnly()
        format_cycle(dut, cycles)
        
        await RisingEdge(dut.clk)
        cycles += 1

    logger.info(f"Completed in {cycles} cycles")
    data_memory.display(48)

    # Compute expected results (matrix multiplication)
    def matmul(a, b, n):
        result = []
        for i in range(n):
            for j in range(n):
                val = 0
                for k in range(n):
                    val += a[i * n + k] * b[k * n + j]
                result.append(val)
        return result
    
    expected_results = matmul(matrix_a, matrix_b, 4)
    actual_results = [data_memory.memory[i + 32] for i in range(16)]
    
    logger.info("Expected C (4x4):")
    for i in range(4):
        logger.info(f"  {expected_results[i*4:(i+1)*4]}")
    logger.info("Actual C (4x4):")
    for i in range(4):
        logger.info(f"  {actual_results[i*4:(i+1)*4]}")
    
    for i, expected in enumerate(expected_results):
        result = data_memory.memory[i + 32]
        assert result == expected, f"Result mismatch at index {i}: expected {expected}, got {result}"
    
    logger.info("All assertions passed!")
