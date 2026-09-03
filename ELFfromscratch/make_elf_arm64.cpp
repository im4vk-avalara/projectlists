/*
 * make_elf_arm64.cpp - Generate a minimal Linux AArch64 ELF executable from scratch
 * 
 * ================================================================================
 * PART 1: ELF FILE LAYOUT EXPLANATION
 * ================================================================================
 * 
 * File Layout:
 * ┌────────────────────────────────────────────────────────────────────┐
 * │ Offset 0x0000 - 0x003F (64 bytes)   : ELF64 Header (Elf64_Ehdr)   │
 * ├────────────────────────────────────────────────────────────────────┤
 * │ Offset 0x0040 - 0x0077 (56 bytes)   : Program Header (Elf64_Phdr) │
 * ├────────────────────────────────────────────────────────────────────┤
 * │ Offset 0x0078 - 0x0FFF (padding)    : Zero padding to 0x1000      │
 * ├────────────────────────────────────────────────────────────────────┤
 * │ Offset 0x1000 - 0x100B (12 bytes)   : AArch64 exit(0) code        │
 * └────────────────────────────────────────────────────────────────────┘
 * 
 * Virtual Address Mapping:
 *   File offset 0x0000 → Virtual address 0x400000
 *   File offset 0x1000 → Virtual address 0x401000 (entry point)
 * 
 * The single PT_LOAD segment maps the entire file (headers + code) into memory
 * starting at virtual address 0x400000 with Read+Execute permissions.
 * 
 * ================================================================================
 * PART 2: AARCH64 INSTRUCTION ENCODINGS FOR exit(0)
 * ================================================================================
 * 
 * We need 3 instructions:
 * 
 * 1. mov x8, #93   (load syscall number: exit = 93 on ARM64 Linux)
 *    Encoding: MOVZ X8, #93, LSL #0
 *    Format:   sf=1 | opc=10 | 100101 | hw=00 | imm16=93 | Rd=8
 *    Binary:   1101_0010_1000_0000_0000_1011_1010_1000
 *    Hex:      0xD2800BA8
 *    Little-endian bytes: A8 0B 80 D2
 * 
 * 2. mov x0, #0    (exit status = 0)
 *    Encoding: MOVZ X0, #0, LSL #0
 *    Format:   sf=1 | opc=10 | 100101 | hw=00 | imm16=0 | Rd=0
 *    Binary:   1101_0010_1000_0000_0000_0000_0000_0000
 *    Hex:      0xD2800000
 *    Little-endian bytes: 00 00 80 D2
 * 
 * 3. svc #0        (supervisor call to invoke syscall)
 *    Encoding: SVC #0
 *    Format:   11010100 | 000 | imm16=0 | 00001
 *    Binary:   1101_0100_0000_0000_0000_0000_0000_0001
 *    Hex:      0xD4000001
 *    Little-endian bytes: 01 00 00 D4
 * 
 * Total code size: 12 bytes
 * 
 * ================================================================================
 * PART 3: ELF HEADER FIELD VALUES (Elf64_Ehdr - 64 bytes)
 * ================================================================================
 * 
 * Offset  Size  Field          Value       Description
 * ------  ----  -----          -----       -----------
 * 0x00    16    e_ident        (see below) ELF identification
 *   0x00   4    magic          7F 45 4C 46 "\x7FELF" magic number
 *   0x04   1    class          02          ELFCLASS64 (64-bit)
 *   0x05   1    data           01          ELFDATA2LSB (little-endian)
 *   0x06   1    version        01          EV_CURRENT
 *   0x07   1    osabi          00          ELFOSABI_NONE (System V)
 *   0x08   1    abiversion     00          ABI version
 *   0x09   7    padding        00...       Padding to 16 bytes
 * 0x10    2     e_type         0x0002      ET_EXEC (executable)
 * 0x12    2     e_machine      0x00B7      EM_AARCH64 (183)
 * 0x14    4     e_version      0x00000001  EV_CURRENT
 * 0x18    8     e_entry        0x00401000  Entry point (BASE + CODE_OFFSET)
 * 0x20    8     e_phoff        0x00000040  Program header offset (64)
 * 0x28    8     e_shoff        0x00000000  No section headers
 * 0x30    4     e_flags        0x00000000  No processor-specific flags
 * 0x34    2     e_ehsize       0x0040      ELF header size (64)
 * 0x36    2     e_phentsize    0x0038      Program header entry size (56)
 * 0x38    2     e_phnum        0x0001      One program header
 * 0x3A    2     e_shentsize    0x0040      Section header entry size (64, unused)
 * 0x3C    2     e_shnum        0x0000      No section headers
 * 0x3E    2     e_shstrndx     0x0000      No section name string table
 * 
 * ================================================================================
 * PART 4: PROGRAM HEADER FIELD VALUES (Elf64_Phdr - 56 bytes)
 * ================================================================================
 * 
 * Offset  Size  Field       Value        Description
 * ------  ----  -----       -----        -----------
 * 0x40    4     p_type      0x00000001   PT_LOAD (loadable segment)
 * 0x44    4     p_flags     0x00000005   PF_R | PF_X (read + execute)
 * 0x48    8     p_offset    0x00000000   Segment starts at file offset 0
 * 0x50    8     p_vaddr     0x00400000   Virtual address 0x400000
 * 0x58    8     p_paddr     0x00400000   Physical address (same as vaddr)
 * 0x60    8     p_filesz    0x0000100C   File size (0x1000 + 12 bytes code)
 * 0x68    8     p_memsz     0x0000100C   Memory size (same as filesz)
 * 0x70    8     p_align     0x00001000   Page alignment (4KB)
 */

#include <cstdint>
#include <fstream>
#include <vector>
#include <stdexcept>
#include <iostream>

// ============================================================================
// Fixed-width little-endian writers
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
    if (b.size() > offset) {
        throw std::runtime_error("Already past desired offset");
    }
    b.resize(offset, 0x00);
}

// ============================================================================
// Main: Build and write the ELF file
// ============================================================================

int main() {
    // Layout constants
    constexpr uint64_t BASE_VADDR   = 0x400000;   // Standard executable base
    constexpr uint64_t CODE_OFFSET  = 0x1000;     // Code at 4KB offset (page-aligned)
    constexpr uint64_t ENTRY        = BASE_VADDR + CODE_OFFSET;  // 0x401000

    // ELF header constants
    constexpr uint16_t ET_EXEC      = 2;          // Executable file
    constexpr uint16_t EM_AARCH64   = 183;        // ARM 64-bit (0xB7)
    constexpr uint32_t PT_LOAD      = 1;          // Loadable segment
    constexpr uint32_t PF_X         = 1;          // Execute permission
    constexpr uint32_t PF_R         = 4;          // Read permission

    // AArch64 machine code for exit(0):
    // mov x8, #93    ; syscall number (exit = 93 on arm64 linux)
    // mov x0, #0     ; exit status
    // svc #0         ; invoke syscall
    const std::vector<uint8_t> code = {
        0xA8, 0x0B, 0x80, 0xD2,   // mov x8, #93   (MOVZ X8, #0x5D)
        0x00, 0x00, 0x80, 0xD2,   // mov x0, #0    (MOVZ X0, #0)
        0x01, 0x00, 0x00, 0xD4    // svc #0        (supervisor call)
    };

    const uint64_t FILE_SIZE = CODE_OFFSET + code.size();  // 0x100C

    std::vector<uint8_t> out;
    out.reserve(static_cast<size_t>(FILE_SIZE));

    // ========================================================================
    // ELF Header (Elf64_Ehdr) - 64 bytes starting at offset 0x00
    // ========================================================================

    // e_ident[16]: ELF identification
    put_u8(out, 0x7F);                          // Magic byte 0
    put_u8(out, 'E');                           // Magic byte 1
    put_u8(out, 'L');                           // Magic byte 2
    put_u8(out, 'F');                           // Magic byte 3
    put_u8(out, 2);                             // EI_CLASS: ELFCLASS64
    put_u8(out, 1);                             // EI_DATA: ELFDATA2LSB (little-endian)
    put_u8(out, 1);                             // EI_VERSION: EV_CURRENT
    put_u8(out, 0);                             // EI_OSABI: ELFOSABI_NONE (System V)
    put_u8(out, 0);                             // EI_ABIVERSION
    for (int i = 0; i < 7; i++) put_u8(out, 0); // EI_PAD: padding to 16 bytes

    put_u16le(out, ET_EXEC);                    // e_type: executable file
    put_u16le(out, EM_AARCH64);                 // e_machine: ARM 64-bit
    put_u32le(out, 1);                          // e_version: EV_CURRENT
    put_u64le(out, ENTRY);                      // e_entry: entry point address
    put_u64le(out, 64);                         // e_phoff: program header offset (after ELF header)
    put_u64le(out, 0);                          // e_shoff: no section header table
    put_u32le(out, 0);                          // e_flags: no processor-specific flags
    put_u16le(out, 64);                         // e_ehsize: ELF header size
    put_u16le(out, 56);                         // e_phentsize: program header entry size
    put_u16le(out, 1);                          // e_phnum: one program header
    put_u16le(out, 64);                         // e_shentsize: section header size (conventional)
    put_u16le(out, 0);                          // e_shnum: no section headers
    put_u16le(out, 0);                          // e_shstrndx: no section name string table

    // Sanity check: ELF header should be exactly 64 bytes
    if (out.size() != 64) {
        std::cerr << "Error: ELF header size mismatch (got " << out.size() << ", expected 64)\n";
        return 1;
    }

    // ========================================================================
    // Program Header (Elf64_Phdr) - 56 bytes starting at offset 0x40
    // ========================================================================

    put_u32le(out, PT_LOAD);                    // p_type: loadable segment
    put_u32le(out, PF_R | PF_X);                // p_flags: read + execute
    put_u64le(out, 0);                          // p_offset: segment starts at file offset 0
    put_u64le(out, BASE_VADDR);                 // p_vaddr: virtual address
    put_u64le(out, BASE_VADDR);                 // p_paddr: physical address (same)
    put_u64le(out, FILE_SIZE);                  // p_filesz: size in file
    put_u64le(out, FILE_SIZE);                  // p_memsz: size in memory
    put_u64le(out, 0x1000);                     // p_align: 4KB page alignment

    // Sanity check: should be at offset 120 (64 + 56)
    if (out.size() != 120) {
        std::cerr << "Error: headers size mismatch (got " << out.size() << ", expected 120)\n";
        return 1;
    }

    // ========================================================================
    // Padding to code offset 0x1000
    // ========================================================================

    pad_to(out, static_cast<size_t>(CODE_OFFSET));

    // ========================================================================
    // Machine code at offset 0x1000
    // ========================================================================

    out.insert(out.end(), code.begin(), code.end());

    // Final sanity check
    if (out.size() != FILE_SIZE) {
        std::cerr << "Error: final size mismatch (got " << out.size() 
                  << ", expected " << FILE_SIZE << ")\n";
        return 1;
    }

    // ========================================================================
    // Write the ELF file
    // ========================================================================

    const char* filename = "mini_elf_arm64";
    std::ofstream f(filename, std::ios::binary);
    if (!f) {
        std::cerr << "Error: cannot open " << filename << " for writing\n";
        return 1;
    }
    f.write(reinterpret_cast<const char*>(out.data()), 
            static_cast<std::streamsize>(out.size()));
    f.close();

    std::cout << "Created " << filename << " (" << out.size() << " bytes)\n";
    std::cout << "\nTo test on an ARM64 Linux system:\n";
    std::cout << "  chmod +x " << filename << "\n";
    std::cout << "  ./" << filename << " ; echo $?\n";
    std::cout << "  # Should print: 0\n";
    std::cout << "\nTo verify with readelf:\n";
    std::cout << "  readelf -h -l " << filename << "\n";

    return 0;
}
