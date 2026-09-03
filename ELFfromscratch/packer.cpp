/*
 * packer.cpp - ARM64 ELF Packer/Protector
 * 
 * Creates a packed ELF that:
 * 1. XOR-encrypts the original payload
 * 2. Embeds a decryption stub that unpacks at runtime
 * 3. Uses mmap to allocate RWX memory, decrypts there, and jumps
 * 
 * Usage: ./packer <input_shellcode_or_elf> <output_packed_elf> [xor_key]
 * 
 * ================================================================================
 * PACKED ELF LAYOUT
 * ================================================================================
 * 
 * ┌──────────────────────────────────────────────────────────────────────────────┐
 * │ Offset 0x0000      ELF Header (64 bytes)                                     │
 * ├──────────────────────────────────────────────────────────────────────────────┤
 * │ Offset 0x0040      Program Header (56 bytes) - PT_LOAD RWX                   │
 * ├──────────────────────────────────────────────────────────────────────────────┤
 * │ Offset 0x0078      Padding (zeros to 0x1000)                                 │
 * ├──────────────────────────────────────────────────────────────────────────────┤
 * │ Offset 0x1000      Decryption Stub (variable, ~60-80 bytes)                  │
 * │                    - Calculates payload address                              │
 * │                    - mmap(NULL, size, RWX, PRIVATE|ANON, -1, 0)              │
 * │                    - XOR decrypts payload into mmap'd region                 │
 * │                    - Branches to decrypted code                              │
 * ├──────────────────────────────────────────────────────────────────────────────┤
 * │ Offset STUB_END    XOR-Encrypted Payload (original code)                     │
 * └──────────────────────────────────────────────────────────────────────────────┘
 * 
 * ================================================================================
 * ARM64 STUB PSEUDOCODE
 * ================================================================================
 * 
 * _start:
 *     adr     x10, payload            // Get address of encrypted payload
 *     mov     x1, #PAYLOAD_SIZE       // Size (patched by packer)
 *     
 *     // mmap syscall
 *     mov     x0, #0                  // addr = NULL
 *     mov     x2, #7                  // PROT_READ|PROT_WRITE|PROT_EXEC
 *     mov     x3, #0x22               // MAP_PRIVATE|MAP_ANONYMOUS  
 *     mov     x4, #-1                 // fd = -1 (MOVN encoding)
 *     mov     x5, #0                  // offset = 0
 *     mov     x8, #222                // __NR_mmap on arm64
 *     svc     #0
 *     
 *     // x0 = mmap'd address (our decrypted code destination)
 *     mov     x9, x0                  // Save for later jump
 *     mov     x11, x0                 // x11 = write pointer
 *     mov     x12, x10                // x12 = read pointer (encrypted)
 *     mov     x13, x1                 // x13 = bytes remaining
 *     mov     x14, #XOR_KEY           // x14 = XOR key (patched)
 *     
 * loop:
 *     ldrb    w15, [x12], #1          // Load encrypted byte, post-increment
 *     eor     w15, w15, w14           // XOR decrypt
 *     strb    w15, [x11], #1          // Store decrypted byte, post-increment
 *     subs    x13, x13, #1            // Decrement counter
 *     b.ne    loop                    // Continue if not zero
 *     
 *     br      x9                      // Jump to decrypted code!
 *     
 * payload:
 *     .byte   <encrypted bytes...>
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <vector>
#include <string>

// ============================================================================
// Little-endian byte writers
// ============================================================================

static void put_u8(std::vector<uint8_t>& b, uint8_t v) {
    b.push_back(v);
}

static void put_u16le(std::vector<uint8_t>& b, uint16_t v) {
    b.push_back(static_cast<uint8_t>(v & 0xFF));
    b.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
}

static void put_u32le(std::vector<uint8_t>& b, uint32_t v) {
    b.push_back(static_cast<uint8_t>(v & 0xFF));
    b.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
    b.push_back(static_cast<uint8_t>((v >> 16) & 0xFF));
    b.push_back(static_cast<uint8_t>((v >> 24) & 0xFF));
}

static void put_u64le(std::vector<uint8_t>& b, uint64_t v) {
    for (int i = 0; i < 8; i++) {
        b.push_back(static_cast<uint8_t>((v >> (8 * i)) & 0xFF));
    }
}

static void pad_to(std::vector<uint8_t>& b, size_t offset) {
    if (b.size() < offset) {
        b.resize(offset, 0x00);
    }
}

// ============================================================================
// ARM64 Instruction Encoders
// ============================================================================

// MOVZ Xd, #imm16 - Move wide with zero
// Format: 1 10 100101 00 [imm16:16] [Rd:5]
static uint32_t arm64_movz(uint8_t rd, uint16_t imm16, uint8_t shift = 0) {
    uint32_t hw = (shift / 16) & 3;
    return 0xD2800000 | (hw << 21) | (static_cast<uint32_t>(imm16) << 5) | rd;
}

// MOVN Xd, #imm16 - Move wide with NOT (for negative numbers)
// Format: 1 00 100101 00 [imm16:16] [Rd:5]
static uint32_t arm64_movn(uint8_t rd, uint16_t imm16, uint8_t shift = 0) {
    uint32_t hw = (shift / 16) & 3;
    return 0x92800000 | (hw << 21) | (static_cast<uint32_t>(imm16) << 5) | rd;
}

// MOV Xd, Xm (alias for ORR Xd, XZR, Xm)
// Format: 1 01 01010 00 0 [Rm:5] 000000 11111 [Rd:5]
static uint32_t arm64_mov_reg(uint8_t rd, uint8_t rm) {
    return 0xAA0003E0 | (static_cast<uint32_t>(rm) << 16) | rd;
}

// ADR Xd, label (PC-relative address, ±1MB range)
// Format: 0 [immlo:2] 10000 [immhi:19] [Rd:5]
static uint32_t arm64_adr(uint8_t rd, int32_t offset) {
    uint32_t immlo = (offset & 0x3);
    uint32_t immhi = ((offset >> 2) & 0x7FFFF);
    return 0x10000000 | (immlo << 29) | (immhi << 5) | rd;
}

// LDRB Wt, [Xn], #imm9 (post-index load byte)
// Format: 00 111 0 00 01 0 [imm9:9] 01 [Rn:5] [Rt:5]
static uint32_t arm64_ldrb_post(uint8_t rt, uint8_t rn, int16_t imm9) {
    uint32_t imm = static_cast<uint32_t>(imm9) & 0x1FF;
    return 0x38400400 | (imm << 12) | (static_cast<uint32_t>(rn) << 5) | rt;
}

// STRB Wt, [Xn], #imm9 (post-index store byte)
// Format: 00 111 0 00 00 0 [imm9:9] 01 [Rn:5] [Rt:5]
static uint32_t arm64_strb_post(uint8_t rt, uint8_t rn, int16_t imm9) {
    uint32_t imm = static_cast<uint32_t>(imm9) & 0x1FF;
    return 0x38000400 | (imm << 12) | (static_cast<uint32_t>(rn) << 5) | rt;
}

// EOR Wd, Wn, Wm (XOR 32-bit)
// Format: 0 10 01010 00 0 [Rm:5] 000000 [Rn:5] [Rd:5]
static uint32_t arm64_eor32(uint8_t rd, uint8_t rn, uint8_t rm) {
    return 0x4A000000 | (static_cast<uint32_t>(rm) << 16) | 
           (static_cast<uint32_t>(rn) << 5) | rd;
}

// SUBS Xd, Xn, #imm12 (subtract immediate, set flags)
// Format: 1 11 100010 0 [imm12:12] [Rn:5] [Rd:5]
static uint32_t arm64_subs_imm(uint8_t rd, uint8_t rn, uint16_t imm12) {
    return 0xF1000000 | (static_cast<uint32_t>(imm12 & 0xFFF) << 10) |
           (static_cast<uint32_t>(rn) << 5) | rd;
}

// B.NE label (branch if not equal, PC-relative)
// Format: 0101010 0 [imm19:19] 0 0001 (cond=NE=0001)
static uint32_t arm64_bne(int32_t offset) {
    // offset is in bytes, instruction uses offset/4
    int32_t imm19 = (offset >> 2) & 0x7FFFF;
    return 0x54000001 | (static_cast<uint32_t>(imm19) << 5);
}

// BR Xn (branch to register)
// Format: 1101011 0 0 00 11111 0000 0 0 [Rn:5] 00000
static uint32_t arm64_br(uint8_t rn) {
    return 0xD61F0000 | (static_cast<uint32_t>(rn) << 5);
}

// SVC #imm16 (supervisor call)
// Format: 11010100 000 [imm16:16] 00001
static uint32_t arm64_svc(uint16_t imm16) {
    return 0xD4000001 | (static_cast<uint32_t>(imm16) << 5);
}

// Helper to append instruction to buffer (little-endian)
static void emit(std::vector<uint8_t>& buf, uint32_t insn) {
    put_u32le(buf, insn);
}

// ============================================================================
// Build the decryption stub
// ============================================================================

static std::vector<uint8_t> build_stub(uint32_t payload_size, uint8_t xor_key) {
    std::vector<uint8_t> stub;
    
    // We'll calculate the ADR offset after we know stub size
    // For now, emit placeholder, we'll patch it
    size_t adr_patch_offset = stub.size();
    emit(stub, 0);  // Placeholder for: adr x10, payload
    
    // mov x1, #payload_size (might need MOVK for sizes > 65535)
    if (payload_size <= 0xFFFF) {
        emit(stub, arm64_movz(1, static_cast<uint16_t>(payload_size)));
    } else {
        // For larger payloads, use MOVZ + MOVK
        emit(stub, arm64_movz(1, static_cast<uint16_t>(payload_size & 0xFFFF)));
        emit(stub, 0xF2A00001 | ((payload_size >> 16) << 5)); // MOVK x1, #hi, LSL #16
    }
    
    // mmap syscall setup
    emit(stub, arm64_movz(0, 0));           // mov x0, #0 (addr = NULL)
    emit(stub, arm64_movz(2, 7));           // mov x2, #7 (PROT_RWX)
    emit(stub, arm64_movz(3, 0x22));        // mov x3, #0x22 (MAP_PRIVATE|MAP_ANON)
    emit(stub, arm64_movn(4, 0));           // mov x4, #-1 (fd)
    emit(stub, arm64_movz(5, 0));           // mov x5, #0 (offset)
    emit(stub, arm64_movz(8, 222));         // mov x8, #222 (__NR_mmap)
    emit(stub, arm64_svc(0));               // svc #0
    
    // Setup for decrypt loop
    emit(stub, arm64_mov_reg(9, 0));        // mov x9, x0 (save mmap addr for jump)
    emit(stub, arm64_mov_reg(11, 0));       // mov x11, x0 (write pointer)
    emit(stub, arm64_mov_reg(12, 10));      // mov x12, x10 (read pointer)
    emit(stub, arm64_mov_reg(13, 1));       // mov x13, x1 (counter)
    emit(stub, arm64_movz(14, xor_key));    // mov x14, #xor_key
    
    // Decrypt loop (4 instructions = 16 bytes)
    emit(stub, arm64_ldrb_post(15, 12, 1)); // ldrb w15, [x12], #1
    emit(stub, arm64_eor32(15, 15, 14));    // eor w15, w15, w14
    emit(stub, arm64_strb_post(15, 11, 1)); // strb w15, [x11], #1
    emit(stub, arm64_subs_imm(13, 13, 1));  // subs x13, x13, #1
    
    // b.ne loop (offset = -(4 instructions * 4 bytes) = -16)
    int32_t branch_offset = -16;
    emit(stub, arm64_bne(branch_offset));   // b.ne loop
    
    // Jump to decrypted code
    emit(stub, arm64_br(9));                // br x9
    
    // Now patch the ADR instruction with correct offset
    // ADR offset = stub.size() (payload starts right after stub)
    int32_t adr_offset = static_cast<int32_t>(stub.size() - adr_patch_offset);
    uint32_t adr_insn = arm64_adr(10, adr_offset);
    
    // Patch in place
    stub[adr_patch_offset + 0] = static_cast<uint8_t>(adr_insn & 0xFF);
    stub[adr_patch_offset + 1] = static_cast<uint8_t>((adr_insn >> 8) & 0xFF);
    stub[adr_patch_offset + 2] = static_cast<uint8_t>((adr_insn >> 16) & 0xFF);
    stub[adr_patch_offset + 3] = static_cast<uint8_t>((adr_insn >> 24) & 0xFF);
    
    return stub;
}

// ============================================================================
// XOR encrypt payload
// ============================================================================

static std::vector<uint8_t> xor_encrypt(const std::vector<uint8_t>& data, uint8_t key) {
    std::vector<uint8_t> encrypted;
    encrypted.reserve(data.size());
    for (uint8_t byte : data) {
        encrypted.push_back(byte ^ key);
    }
    return encrypted;
}

// ============================================================================
// Read file into vector
// ============================================================================

static std::vector<uint8_t> read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    if (!f) {
        fprintf(stderr, "Error: Cannot open %s\n", path.c_str());
        exit(1);
    }
    
    size_t size = f.tellg();
    f.seekg(0);
    
    std::vector<uint8_t> data(size);
    f.read(reinterpret_cast<char*>(data.data()), size);
    return data;
}

// ============================================================================
// Extract code from ELF (or use raw shellcode)
// ============================================================================

static std::vector<uint8_t> extract_payload(const std::vector<uint8_t>& input) {
    // Check if it's an ELF
    if (input.size() >= 64 && 
        input[0] == 0x7F && input[1] == 'E' && input[2] == 'L' && input[3] == 'F') {
        
        // Parse ELF to find code
        // For simplicity, extract from offset 0x1000 to end (our mini_elf layout)
        if (input.size() > 0x1000) {
            printf("Detected ELF, extracting code from offset 0x1000\n");
            return std::vector<uint8_t>(input.begin() + 0x1000, input.end());
        } else {
            fprintf(stderr, "Warning: ELF too small, using entire file as payload\n");
            return input;
        }
    }
    
    // Not ELF, treat as raw shellcode
    printf("Treating input as raw shellcode (%zu bytes)\n", input.size());
    return input;
}

// ============================================================================
// Build packed ELF
// ============================================================================

static std::vector<uint8_t> build_packed_elf(
    const std::vector<uint8_t>& payload,
    uint8_t xor_key
) {
    // Layout constants
    constexpr uint64_t BASE_VADDR = 0x400000;
    constexpr uint64_t CODE_OFFSET = 0x1000;
    constexpr uint64_t ENTRY = BASE_VADDR + CODE_OFFSET;
    
    // Build stub
    std::vector<uint8_t> stub = build_stub(static_cast<uint32_t>(payload.size()), xor_key);
    printf("Stub size: %zu bytes (%zu instructions)\n", stub.size(), stub.size() / 4);
    
    // Encrypt payload
    std::vector<uint8_t> encrypted = xor_encrypt(payload, xor_key);
    printf("Encrypted payload: %zu bytes with XOR key 0x%02X\n", encrypted.size(), xor_key);
    
    // Total file size
    uint64_t file_size = CODE_OFFSET + stub.size() + encrypted.size();
    
    std::vector<uint8_t> out;
    out.reserve(static_cast<size_t>(file_size));
    
    // ========================================================================
    // ELF Header
    // ========================================================================
    
    // e_ident
    put_u8(out, 0x7F); put_u8(out, 'E'); put_u8(out, 'L'); put_u8(out, 'F');
    put_u8(out, 2);    // ELFCLASS64
    put_u8(out, 1);    // ELFDATA2LSB
    put_u8(out, 1);    // EV_CURRENT
    put_u8(out, 0);    // ELFOSABI_NONE
    for (int i = 0; i < 8; i++) put_u8(out, 0);  // padding
    
    put_u16le(out, 2);              // e_type = ET_EXEC
    put_u16le(out, 183);            // e_machine = EM_AARCH64
    put_u32le(out, 1);              // e_version
    put_u64le(out, ENTRY);          // e_entry
    put_u64le(out, 64);             // e_phoff
    put_u64le(out, 0);              // e_shoff
    put_u32le(out, 0);              // e_flags
    put_u16le(out, 64);             // e_ehsize
    put_u16le(out, 56);             // e_phentsize
    put_u16le(out, 1);              // e_phnum
    put_u16le(out, 64);             // e_shentsize
    put_u16le(out, 0);              // e_shnum
    put_u16le(out, 0);              // e_shstrndx
    
    // ========================================================================
    // Program Header - PT_LOAD with RWX (needed for self-modifying code area)
    // ========================================================================
    
    put_u32le(out, 1);              // p_type = PT_LOAD
    put_u32le(out, 7);              // p_flags = PF_R | PF_W | PF_X (RWX for mmap)
    put_u64le(out, 0);              // p_offset
    put_u64le(out, BASE_VADDR);     // p_vaddr
    put_u64le(out, BASE_VADDR);     // p_paddr
    put_u64le(out, file_size);      // p_filesz
    put_u64le(out, file_size);      // p_memsz
    put_u64le(out, 0x1000);         // p_align
    
    // ========================================================================
    // Pad to code offset
    // ========================================================================
    
    pad_to(out, static_cast<size_t>(CODE_OFFSET));
    
    // ========================================================================
    // Append stub + encrypted payload
    // ========================================================================
    
    out.insert(out.end(), stub.begin(), stub.end());
    out.insert(out.end(), encrypted.begin(), encrypted.end());
    
    return out;
}

// ============================================================================
// Print hex dump for debugging
// ============================================================================

static void hexdump(const char* label, const std::vector<uint8_t>& data, size_t offset, size_t len) {
    printf("%s (offset 0x%zX, %zu bytes):\n", label, offset, len);
    for (size_t i = 0; i < len && (offset + i) < data.size(); i++) {
        if (i % 16 == 0) printf("  %04zX: ", offset + i);
        printf("%02X ", data[offset + i]);
        if (i % 16 == 15 || i == len - 1) printf("\n");
    }
}

// ============================================================================
// Main
// ============================================================================

int main(int argc, char* argv[]) {
    printf("=== ARM64 ELF Packer ===\n\n");
    
    if (argc < 3) {
        printf("Usage: %s <input> <output> [xor_key]\n", argv[0]);
        printf("\n");
        printf("  input    : Input file (ELF or raw shellcode)\n");
        printf("  output   : Output packed ELF\n");
        printf("  xor_key  : XOR encryption key 0-255 (default: 0x42)\n");
        printf("\n");
        printf("Example:\n");
        printf("  %s mini_elf_arm64 packed_elf 0x5A\n", argv[0]);
        return 1;
    }
    
    const char* input_path = argv[1];
    const char* output_path = argv[2];
    uint8_t xor_key = (argc > 3) ? static_cast<uint8_t>(strtol(argv[3], nullptr, 0)) : 0x42;
    
    printf("Input:   %s\n", input_path);
    printf("Output:  %s\n", output_path);
    printf("XOR Key: 0x%02X\n\n", xor_key);
    
    // Read input
    std::vector<uint8_t> input_data = read_file(input_path);
    printf("Read %zu bytes from input\n", input_data.size());
    
    // Extract payload (code section from ELF, or raw shellcode)
    std::vector<uint8_t> payload = extract_payload(input_data);
    printf("Payload size: %zu bytes\n\n", payload.size());
    
    if (payload.empty()) {
        fprintf(stderr, "Error: Empty payload\n");
        return 1;
    }
    
    // Build packed ELF
    std::vector<uint8_t> packed = build_packed_elf(payload, xor_key);
    printf("\nPacked ELF size: %zu bytes\n\n", packed.size());
    
    // Debug: show stub and encrypted payload
    hexdump("Stub", packed, 0x1000, 80);
    printf("\n");
    hexdump("Encrypted payload", packed, 0x1000 + 80, payload.size());
    
    // Write output
    std::ofstream f(output_path, std::ios::binary);
    if (!f) {
        fprintf(stderr, "Error: Cannot write to %s\n", output_path);
        return 1;
    }
    f.write(reinterpret_cast<const char*>(packed.data()), packed.size());
    f.close();
    
    printf("\n=== Packed ELF written to %s ===\n", output_path);
    printf("\nTo test:\n");
    printf("  chmod +x %s\n", output_path);
    printf("  ./%s ; echo $?\n", output_path);
    printf("  # Should output: 0\n");
    
    return 0;
}
