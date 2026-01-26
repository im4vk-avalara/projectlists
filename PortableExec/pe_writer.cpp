/**
 * PE Writer - Create Windows Executable from Scratch
 * 
 * Generates minimal valid PE files byte-by-byte without using
 * any assembler or linker. Demonstrates the complete PE format.
 * 
 * This creates two types of executables:
 * 1. Minimal exit-only PE (smallest possible, ~2KB)
 * 2. MessageBox PE (shows a dialog, ~3KB)
 * 
 * Both are x86 (32-bit) executables for simplicity.
 * 
 * Usage: ./pe_writer [output.exe] [type]
 *   type: "minimal" (default) or "msgbox"
 */

#include <iostream>
#include <fstream>
#include <vector>
#include <cstring>
#include <cstdint>
#include "pe_format.h"

// Alignment helper
inline uint32_t align(uint32_t value, uint32_t alignment) {
    return (value + alignment - 1) & ~(alignment - 1);
}

// Write bytes to vector
template<typename T>
void writeStruct(std::vector<uint8_t>& buffer, const T& data) {
    const uint8_t* ptr = reinterpret_cast<const uint8_t*>(&data);
    buffer.insert(buffer.end(), ptr, ptr + sizeof(T));
}

// Pad buffer to alignment
void padTo(std::vector<uint8_t>& buffer, size_t alignment) {
    size_t padding = align(buffer.size(), alignment) - buffer.size();
    buffer.insert(buffer.end(), padding, 0);
}

/**
 * Create a minimal PE that just exits with code 42.
 * This demonstrates the basic PE structure.
 */
std::vector<uint8_t> createMinimalPE() {
    std::vector<uint8_t> pe;
    
    // Layout constants
    const uint32_t FILE_ALIGNMENT = 0x200;     // 512 bytes
    const uint32_t SECTION_ALIGNMENT = 0x1000; // 4096 bytes
    const uint32_t IMAGE_BASE = 0x00400000;    // Default for EXE
    
    // Headers sizes
    const uint32_t DOS_HEADER_SIZE = sizeof(DOSHeader);
    const uint32_t DOS_STUB_SIZE = 64;  // Minimal stub
    const uint32_t PE_SIG_SIZE = 4;
    const uint32_t COFF_HEADER_SIZE = sizeof(COFFHeader);
    const uint32_t OPTIONAL_HEADER_SIZE = sizeof(OptionalHeader32);
    const uint32_t SECTION_HEADER_SIZE = sizeof(SectionHeader);
    const uint32_t NUM_SECTIONS = 2;  // .text and .idata
    
    // Calculate offsets
    const uint32_t PE_OFFSET = DOS_HEADER_SIZE + DOS_STUB_SIZE;
    const uint32_t HEADERS_END = PE_OFFSET + PE_SIG_SIZE + COFF_HEADER_SIZE + 
                                  OPTIONAL_HEADER_SIZE + (NUM_SECTIONS * SECTION_HEADER_SIZE);
    const uint32_t HEADERS_SIZE = align(HEADERS_END, FILE_ALIGNMENT);
    
    // Section calculations
    const uint32_t TEXT_RVA = SECTION_ALIGNMENT;  // .text at 0x1000
    const uint32_t TEXT_SIZE = 0x100;  // Enough for our code
    const uint32_t TEXT_RAW_SIZE = align(TEXT_SIZE, FILE_ALIGNMENT);
    const uint32_t TEXT_FILE_OFFSET = HEADERS_SIZE;
    
    const uint32_t IDATA_RVA = TEXT_RVA + SECTION_ALIGNMENT;  // .idata at 0x2000
    const uint32_t IDATA_SIZE = 0x200;  // Import table
    const uint32_t IDATA_RAW_SIZE = align(IDATA_SIZE, FILE_ALIGNMENT);
    const uint32_t IDATA_FILE_OFFSET = TEXT_FILE_OFFSET + TEXT_RAW_SIZE;
    
    const uint32_t IMAGE_SIZE = align(IDATA_RVA + SECTION_ALIGNMENT, SECTION_ALIGNMENT);
    
    // ========================================================================
    // DOS Header
    // ========================================================================
    DOSHeader dos = {};
    dos.e_magic = DOS_SIGNATURE;  // "MZ"
    dos.e_cblp = 0x90;
    dos.e_cp = 0x03;
    dos.e_cparhdr = 0x04;
    dos.e_maxalloc = 0xFFFF;
    dos.e_sp = 0xB8;
    dos.e_lfarlc = 0x40;
    dos.e_lfanew = PE_OFFSET;
    writeStruct(pe, dos);
    
    // ========================================================================
    // DOS Stub - "This program cannot be run in DOS mode"
    // ========================================================================
    // Minimal stub: print message and exit
    uint8_t dosStub[] = {
        // Simple DOS program that prints message and exits
        0x0E,                   // push cs
        0x1F,                   // pop ds
        0xBA, 0x0E, 0x00,       // mov dx, offset message (0x0E relative to start)
        0xB4, 0x09,             // mov ah, 9 (print string)
        0xCD, 0x21,             // int 21h
        0xB8, 0x01, 0x4C,       // mov ax, 4C01h (exit with code 1)
        0xCD, 0x21,             // int 21h
        // Message: "This program cannot be run in DOS mode.\r\n$"
        'T','h','i','s',' ','p','r','o','g','r','a','m',' ',
        'c','a','n','n','o','t',' ','b','e',' ','r','u','n',' ',
        'i','n',' ','D','O','S',' ','m','o','d','e','.','\r','\n','$'
    };
    pe.insert(pe.end(), dosStub, dosStub + sizeof(dosStub));
    
    // Pad to PE offset
    while (pe.size() < PE_OFFSET) {
        pe.push_back(0);
    }
    
    // ========================================================================
    // PE Signature
    // ========================================================================
    uint32_t peSig = PE_SIGNATURE;
    writeStruct(pe, peSig);
    
    // ========================================================================
    // COFF Header
    // ========================================================================
    COFFHeader coff = {};
    coff.Machine = IMAGE_FILE_MACHINE_I386;
    coff.NumberOfSections = NUM_SECTIONS;
    coff.TimeDateStamp = 0x5F5F5F5F;  // Some timestamp
    coff.PointerToSymbolTable = 0;
    coff.NumberOfSymbols = 0;
    coff.SizeOfOptionalHeader = sizeof(OptionalHeader32);
    coff.Characteristics = IMAGE_FILE_EXECUTABLE_IMAGE | 
                           IMAGE_FILE_32BIT_MACHINE |
                           IMAGE_FILE_RELOCS_STRIPPED;
    writeStruct(pe, coff);
    
    // ========================================================================
    // Optional Header (PE32)
    // ========================================================================
    OptionalHeader32 opt = {};
    opt.Magic = IMAGE_NT_OPTIONAL_HDR32_MAGIC;
    opt.MajorLinkerVersion = 1;
    opt.MinorLinkerVersion = 0;
    opt.SizeOfCode = TEXT_RAW_SIZE;
    opt.SizeOfInitializedData = IDATA_RAW_SIZE;
    opt.SizeOfUninitializedData = 0;
    opt.AddressOfEntryPoint = TEXT_RVA;  // Entry point at start of .text
    opt.BaseOfCode = TEXT_RVA;
    opt.BaseOfData = IDATA_RVA;
    opt.ImageBase = IMAGE_BASE;
    opt.SectionAlignment = SECTION_ALIGNMENT;
    opt.FileAlignment = FILE_ALIGNMENT;
    opt.MajorOperatingSystemVersion = 6;  // Windows Vista+
    opt.MinorOperatingSystemVersion = 0;
    opt.MajorImageVersion = 1;
    opt.MinorImageVersion = 0;
    opt.MajorSubsystemVersion = 6;
    opt.MinorSubsystemVersion = 0;
    opt.Win32VersionValue = 0;
    opt.SizeOfImage = IMAGE_SIZE;
    opt.SizeOfHeaders = HEADERS_SIZE;
    opt.CheckSum = 0;  // Not required for EXE
    opt.Subsystem = IMAGE_SUBSYSTEM_WINDOWS_CUI;  // Console application
    opt.DllCharacteristics = IMAGE_DLLCHARACTERISTICS_NX_COMPAT |
                             IMAGE_DLLCHARACTERISTICS_TERMINAL_SERVER_AWARE;
    opt.SizeOfStackReserve = 0x100000;   // 1MB
    opt.SizeOfStackCommit = 0x1000;      // 4KB
    opt.SizeOfHeapReserve = 0x100000;    // 1MB
    opt.SizeOfHeapCommit = 0x1000;       // 4KB
    opt.LoaderFlags = 0;
    opt.NumberOfRvaAndSizes = IMAGE_NUMBEROF_DIRECTORY_ENTRIES;
    
    // Set import directory
    opt.DataDirectories[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress = IDATA_RVA;
    opt.DataDirectories[IMAGE_DIRECTORY_ENTRY_IMPORT].Size = sizeof(ImportDescriptor) * 2;  // One entry + null terminator
    
    // Set IAT directory
    opt.DataDirectories[IMAGE_DIRECTORY_ENTRY_IAT].VirtualAddress = IDATA_RVA + 0x80;
    opt.DataDirectories[IMAGE_DIRECTORY_ENTRY_IAT].Size = 8;  // Two thunks
    
    writeStruct(pe, opt);
    
    // ========================================================================
    // Section Headers
    // ========================================================================
    
    // .text section
    SectionHeader textSection = {};
    memcpy(textSection.Name, ".text", 5);
    textSection.VirtualSize = TEXT_SIZE;
    textSection.VirtualAddress = TEXT_RVA;
    textSection.SizeOfRawData = TEXT_RAW_SIZE;
    textSection.PointerToRawData = TEXT_FILE_OFFSET;
    textSection.PointerToRelocations = 0;
    textSection.PointerToLinenumbers = 0;
    textSection.NumberOfRelocations = 0;
    textSection.NumberOfLinenumbers = 0;
    textSection.Characteristics = IMAGE_SCN_CNT_CODE | 
                                  IMAGE_SCN_MEM_EXECUTE | 
                                  IMAGE_SCN_MEM_READ;
    writeStruct(pe, textSection);
    
    // .idata section (imports)
    SectionHeader idataSection = {};
    memcpy(idataSection.Name, ".idata", 6);
    idataSection.VirtualSize = IDATA_SIZE;
    idataSection.VirtualAddress = IDATA_RVA;
    idataSection.SizeOfRawData = IDATA_RAW_SIZE;
    idataSection.PointerToRawData = IDATA_FILE_OFFSET;
    idataSection.PointerToRelocations = 0;
    idataSection.PointerToLinenumbers = 0;
    idataSection.NumberOfRelocations = 0;
    idataSection.NumberOfLinenumbers = 0;
    idataSection.Characteristics = IMAGE_SCN_CNT_INITIALIZED_DATA | 
                                   IMAGE_SCN_MEM_READ |
                                   IMAGE_SCN_MEM_WRITE;
    writeStruct(pe, idataSection);
    
    // Pad headers to alignment
    padTo(pe, FILE_ALIGNMENT);
    
    // ========================================================================
    // .text Section - Our Code
    // ========================================================================
    // We need to call ExitProcess(42)
    // The IAT entry for ExitProcess will be at IMAGE_BASE + IDATA_RVA + 0x80
    
    size_t textStart = pe.size();
    
    // x86 machine code to call ExitProcess(42)
    // 
    // push 42           ; exit code
    // call [ExitProcess]  ; call ExitProcess via IAT
    // 
    // Encoding:
    // 6A 2A             push 42
    // FF 15 XX XX XX XX call dword ptr [ExitProcess IAT]
    
    uint32_t exitProcessIAT = IMAGE_BASE + IDATA_RVA + 0x80;  // Address of IAT entry
    
    pe.push_back(0x6A);                      // push imm8
    pe.push_back(42);                        // 42 = exit code
    pe.push_back(0xFF);                      // call
    pe.push_back(0x15);                      // ModR/M: call dword ptr [disp32]
    pe.push_back(exitProcessIAT & 0xFF);
    pe.push_back((exitProcessIAT >> 8) & 0xFF);
    pe.push_back((exitProcessIAT >> 16) & 0xFF);
    pe.push_back((exitProcessIAT >> 24) & 0xFF);
    
    // Fill rest of .text section
    while (pe.size() < textStart + TEXT_RAW_SIZE) {
        pe.push_back(0xCC);  // INT 3 (breakpoint) as padding
    }
    
    // ========================================================================
    // .idata Section - Import Table
    // ========================================================================
    // Layout:
    // 0x00: Import Descriptor for kernel32.dll
    // 0x14: Null Import Descriptor (terminator)
    // 0x28: Reserved space
    // 0x60: Import Lookup Table (ILT) - thunk pointing to hint/name
    // 0x68: Null terminator for ILT
    // 0x80: Import Address Table (IAT) - same as ILT initially
    // 0x88: Null terminator for IAT
    // 0xA0: Hint/Name for ExitProcess
    // 0xC0: "kernel32.dll" string
    
    size_t idataStart = pe.size();
    
    // Import Descriptor for kernel32.dll
    ImportDescriptor impDesc = {};
    impDesc.OriginalFirstThunk = IDATA_RVA + 0x60;  // RVA of ILT
    impDesc.TimeDateStamp = 0;
    impDesc.ForwarderChain = 0;
    impDesc.Name = IDATA_RVA + 0xC0;                 // RVA of "kernel32.dll"
    impDesc.FirstThunk = IDATA_RVA + 0x80;           // RVA of IAT
    writeStruct(pe, impDesc);
    
    // Null terminator Import Descriptor
    ImportDescriptor nullDesc = {};
    writeStruct(pe, nullDesc);
    
    // Padding to ILT offset (0x60)
    while (pe.size() < idataStart + 0x60) {
        pe.push_back(0);
    }
    
    // Import Lookup Table (ILT) - points to Hint/Name
    uint32_t hintNameRVA = IDATA_RVA + 0xA0;
    pe.push_back(hintNameRVA & 0xFF);
    pe.push_back((hintNameRVA >> 8) & 0xFF);
    pe.push_back((hintNameRVA >> 16) & 0xFF);
    pe.push_back((hintNameRVA >> 24) & 0xFF);
    
    // Null terminator for ILT
    pe.push_back(0); pe.push_back(0); pe.push_back(0); pe.push_back(0);
    
    // Padding to IAT offset (0x80)
    while (pe.size() < idataStart + 0x80) {
        pe.push_back(0);
    }
    
    // Import Address Table (IAT) - same as ILT initially
    pe.push_back(hintNameRVA & 0xFF);
    pe.push_back((hintNameRVA >> 8) & 0xFF);
    pe.push_back((hintNameRVA >> 16) & 0xFF);
    pe.push_back((hintNameRVA >> 24) & 0xFF);
    
    // Null terminator for IAT
    pe.push_back(0); pe.push_back(0); pe.push_back(0); pe.push_back(0);
    
    // Padding to Hint/Name offset (0xA0)
    while (pe.size() < idataStart + 0xA0) {
        pe.push_back(0);
    }
    
    // Hint/Name for ExitProcess
    pe.push_back(0);  // Hint low byte
    pe.push_back(0);  // Hint high byte
    const char* exitProcess = "ExitProcess";
    for (size_t i = 0; exitProcess[i]; i++) {
        pe.push_back(exitProcess[i]);
    }
    pe.push_back(0);  // Null terminator
    
    // Padding to DLL name offset (0xC0)
    while (pe.size() < idataStart + 0xC0) {
        pe.push_back(0);
    }
    
    // DLL name
    const char* kernel32 = "kernel32.dll";
    for (size_t i = 0; kernel32[i]; i++) {
        pe.push_back(kernel32[i]);
    }
    pe.push_back(0);  // Null terminator
    
    // Fill rest of .idata section
    while (pe.size() < idataStart + IDATA_RAW_SIZE) {
        pe.push_back(0);
    }
    
    return pe;
}

/**
 * Create a PE that shows a MessageBox and exits.
 * Demonstrates importing multiple functions from multiple DLLs.
 */
std::vector<uint8_t> createMessageBoxPE() {
    std::vector<uint8_t> pe;
    
    // Layout constants
    const uint32_t FILE_ALIGNMENT = 0x200;
    const uint32_t SECTION_ALIGNMENT = 0x1000;
    const uint32_t IMAGE_BASE = 0x00400000;
    
    // Headers
    const uint32_t PE_OFFSET = 0x80;  // After DOS header + stub
    const uint32_t HEADERS_SIZE = 0x400;  // Aligned headers
    
    // Sections
    const uint32_t TEXT_RVA = 0x1000;
    const uint32_t TEXT_SIZE = 0x200;
    const uint32_t TEXT_FILE_OFFSET = HEADERS_SIZE;
    
    const uint32_t IDATA_RVA = 0x2000;
    const uint32_t IDATA_SIZE = 0x400;
    const uint32_t IDATA_FILE_OFFSET = TEXT_FILE_OFFSET + TEXT_SIZE;
    
    const uint32_t RDATA_RVA = 0x3000;
    const uint32_t RDATA_SIZE = 0x200;
    const uint32_t RDATA_FILE_OFFSET = IDATA_FILE_OFFSET + IDATA_SIZE;
    
    const uint32_t IMAGE_SIZE = 0x4000;
    
    // String locations in .rdata
    const uint32_t TITLE_RVA = RDATA_RVA;
    const uint32_t MSG_RVA = RDATA_RVA + 0x20;
    
    // ========================================================================
    // DOS Header
    // ========================================================================
    DOSHeader dos = {};
    dos.e_magic = DOS_SIGNATURE;
    dos.e_cblp = 0x90;
    dos.e_cp = 0x03;
    dos.e_cparhdr = 0x04;
    dos.e_maxalloc = 0xFFFF;
    dos.e_sp = 0xB8;
    dos.e_lfarlc = 0x40;
    dos.e_lfanew = PE_OFFSET;
    writeStruct(pe, dos);
    
    // DOS Stub
    uint8_t dosStub[] = {
        0x0E, 0x1F, 0xBA, 0x0E, 0x00, 0xB4, 0x09, 0xCD, 0x21,
        0xB8, 0x01, 0x4C, 0xCD, 0x21,
        'T','h','i','s',' ','p','r','o','g','r','a','m',' ',
        'c','a','n','n','o','t',' ','b','e',' ','r','u','n',' ',
        'i','n',' ','D','O','S',' ','m','o','d','e','.','\r','\n','$'
    };
    pe.insert(pe.end(), dosStub, dosStub + sizeof(dosStub));
    
    while (pe.size() < PE_OFFSET) pe.push_back(0);
    
    // ========================================================================
    // PE Signature
    // ========================================================================
    uint32_t peSig = PE_SIGNATURE;
    writeStruct(pe, peSig);
    
    // ========================================================================
    // COFF Header
    // ========================================================================
    COFFHeader coff = {};
    coff.Machine = IMAGE_FILE_MACHINE_I386;
    coff.NumberOfSections = 3;  // .text, .idata, .rdata
    coff.TimeDateStamp = 0x5F5F5F5F;
    coff.SizeOfOptionalHeader = sizeof(OptionalHeader32);
    coff.Characteristics = IMAGE_FILE_EXECUTABLE_IMAGE | IMAGE_FILE_32BIT_MACHINE;
    writeStruct(pe, coff);
    
    // ========================================================================
    // Optional Header
    // ========================================================================
    OptionalHeader32 opt = {};
    opt.Magic = IMAGE_NT_OPTIONAL_HDR32_MAGIC;
    opt.MajorLinkerVersion = 1;
    opt.SizeOfCode = TEXT_SIZE;
    opt.SizeOfInitializedData = IDATA_SIZE + RDATA_SIZE;
    opt.AddressOfEntryPoint = TEXT_RVA;
    opt.BaseOfCode = TEXT_RVA;
    opt.BaseOfData = RDATA_RVA;
    opt.ImageBase = IMAGE_BASE;
    opt.SectionAlignment = SECTION_ALIGNMENT;
    opt.FileAlignment = FILE_ALIGNMENT;
    opt.MajorOperatingSystemVersion = 6;
    opt.MajorSubsystemVersion = 6;
    opt.SizeOfImage = IMAGE_SIZE;
    opt.SizeOfHeaders = HEADERS_SIZE;
    opt.Subsystem = IMAGE_SUBSYSTEM_WINDOWS_GUI;  // GUI app
    opt.DllCharacteristics = IMAGE_DLLCHARACTERISTICS_NX_COMPAT;
    opt.SizeOfStackReserve = 0x100000;
    opt.SizeOfStackCommit = 0x1000;
    opt.SizeOfHeapReserve = 0x100000;
    opt.SizeOfHeapCommit = 0x1000;
    opt.NumberOfRvaAndSizes = IMAGE_NUMBEROF_DIRECTORY_ENTRIES;
    opt.DataDirectories[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress = IDATA_RVA;
    opt.DataDirectories[IMAGE_DIRECTORY_ENTRY_IMPORT].Size = sizeof(ImportDescriptor) * 3;
    opt.DataDirectories[IMAGE_DIRECTORY_ENTRY_IAT].VirtualAddress = IDATA_RVA + 0x100;
    opt.DataDirectories[IMAGE_DIRECTORY_ENTRY_IAT].Size = 16;
    writeStruct(pe, opt);
    
    // ========================================================================
    // Section Headers
    // ========================================================================
    
    // .text
    SectionHeader textSection = {};
    memcpy(textSection.Name, ".text", 5);
    textSection.VirtualSize = TEXT_SIZE;
    textSection.VirtualAddress = TEXT_RVA;
    textSection.SizeOfRawData = TEXT_SIZE;
    textSection.PointerToRawData = TEXT_FILE_OFFSET;
    textSection.Characteristics = IMAGE_SCN_CNT_CODE | IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_READ;
    writeStruct(pe, textSection);
    
    // .idata
    SectionHeader idataSection = {};
    memcpy(idataSection.Name, ".idata", 6);
    idataSection.VirtualSize = IDATA_SIZE;
    idataSection.VirtualAddress = IDATA_RVA;
    idataSection.SizeOfRawData = IDATA_SIZE;
    idataSection.PointerToRawData = IDATA_FILE_OFFSET;
    idataSection.Characteristics = IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ | IMAGE_SCN_MEM_WRITE;
    writeStruct(pe, idataSection);
    
    // .rdata
    SectionHeader rdataSection = {};
    memcpy(rdataSection.Name, ".rdata", 6);
    rdataSection.VirtualSize = RDATA_SIZE;
    rdataSection.VirtualAddress = RDATA_RVA;
    rdataSection.SizeOfRawData = RDATA_SIZE;
    rdataSection.PointerToRawData = RDATA_FILE_OFFSET;
    rdataSection.Characteristics = IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ;
    writeStruct(pe, rdataSection);
    
    // Pad headers
    padTo(pe, HEADERS_SIZE);
    
    // ========================================================================
    // .text Section - Code
    // ========================================================================
    // 
    // push MB_OK (0)
    // push title_ptr
    // push msg_ptr  
    // push NULL (0)
    // call [MessageBoxA]
    // push eax        ; exit code = MessageBox return
    // call [ExitProcess]
    //
    
    size_t textStart = pe.size();
    
    uint32_t messageBoxIAT = IMAGE_BASE + IDATA_RVA + 0x100;
    uint32_t exitProcessIAT = IMAGE_BASE + IDATA_RVA + 0x104;
    uint32_t titleAddr = IMAGE_BASE + TITLE_RVA;
    uint32_t msgAddr = IMAGE_BASE + MSG_RVA;
    
    // push 0 (MB_OK)
    pe.push_back(0x6A); pe.push_back(0x00);
    
    // push title_ptr
    pe.push_back(0x68);
    pe.push_back(titleAddr & 0xFF);
    pe.push_back((titleAddr >> 8) & 0xFF);
    pe.push_back((titleAddr >> 16) & 0xFF);
    pe.push_back((titleAddr >> 24) & 0xFF);
    
    // push msg_ptr
    pe.push_back(0x68);
    pe.push_back(msgAddr & 0xFF);
    pe.push_back((msgAddr >> 8) & 0xFF);
    pe.push_back((msgAddr >> 16) & 0xFF);
    pe.push_back((msgAddr >> 24) & 0xFF);
    
    // push 0 (NULL hwnd)
    pe.push_back(0x6A); pe.push_back(0x00);
    
    // call [MessageBoxA]
    pe.push_back(0xFF); pe.push_back(0x15);
    pe.push_back(messageBoxIAT & 0xFF);
    pe.push_back((messageBoxIAT >> 8) & 0xFF);
    pe.push_back((messageBoxIAT >> 16) & 0xFF);
    pe.push_back((messageBoxIAT >> 24) & 0xFF);
    
    // push eax (return value from MessageBox as exit code)
    pe.push_back(0x50);
    
    // call [ExitProcess]
    pe.push_back(0xFF); pe.push_back(0x15);
    pe.push_back(exitProcessIAT & 0xFF);
    pe.push_back((exitProcessIAT >> 8) & 0xFF);
    pe.push_back((exitProcessIAT >> 16) & 0xFF);
    pe.push_back((exitProcessIAT >> 24) & 0xFF);
    
    // Pad .text
    while (pe.size() < textStart + TEXT_SIZE) pe.push_back(0xCC);
    
    // ========================================================================
    // .idata Section - Imports
    // ========================================================================
    // Layout:
    // 0x00-0x3F: Import Descriptors (kernel32.dll, user32.dll, null)
    // 0x80: ILT for kernel32 (ExitProcess)
    // 0x90: ILT for user32 (MessageBoxA)
    // 0x100: IAT for user32 (MessageBoxA) - aligned for code
    // 0x104: IAT for kernel32 (ExitProcess)
    // 0x140: Hint/Name for ExitProcess
    // 0x160: Hint/Name for MessageBoxA  
    // 0x180: "kernel32.dll"
    // 0x1A0: "user32.dll"
    
    size_t idataStart = pe.size();
    
    // Import Descriptor for user32.dll (first, for MessageBoxA)
    ImportDescriptor user32Desc = {};
    user32Desc.OriginalFirstThunk = IDATA_RVA + 0x90;
    user32Desc.Name = IDATA_RVA + 0x1A0;
    user32Desc.FirstThunk = IDATA_RVA + 0x100;  // IAT at 0x100
    writeStruct(pe, user32Desc);
    
    // Import Descriptor for kernel32.dll
    ImportDescriptor kernel32Desc = {};
    kernel32Desc.OriginalFirstThunk = IDATA_RVA + 0x80;
    kernel32Desc.Name = IDATA_RVA + 0x180;
    kernel32Desc.FirstThunk = IDATA_RVA + 0x104;  // IAT at 0x104
    writeStruct(pe, kernel32Desc);
    
    // Null terminator
    ImportDescriptor nullDesc = {};
    writeStruct(pe, nullDesc);
    
    // Pad to ILT for kernel32 (0x80)
    while (pe.size() < idataStart + 0x80) pe.push_back(0);
    
    // ILT for kernel32 (ExitProcess)
    uint32_t exitProcHintRVA = IDATA_RVA + 0x140;
    pe.push_back(exitProcHintRVA & 0xFF);
    pe.push_back((exitProcHintRVA >> 8) & 0xFF);
    pe.push_back((exitProcHintRVA >> 16) & 0xFF);
    pe.push_back((exitProcHintRVA >> 24) & 0xFF);
    pe.push_back(0); pe.push_back(0); pe.push_back(0); pe.push_back(0);  // Null terminator
    
    // Pad to ILT for user32 (0x90)
    while (pe.size() < idataStart + 0x90) pe.push_back(0);
    
    // ILT for user32 (MessageBoxA)
    uint32_t msgBoxHintRVA = IDATA_RVA + 0x160;
    pe.push_back(msgBoxHintRVA & 0xFF);
    pe.push_back((msgBoxHintRVA >> 8) & 0xFF);
    pe.push_back((msgBoxHintRVA >> 16) & 0xFF);
    pe.push_back((msgBoxHintRVA >> 24) & 0xFF);
    pe.push_back(0); pe.push_back(0); pe.push_back(0); pe.push_back(0);  // Null terminator
    
    // Pad to IAT (0x100)
    while (pe.size() < idataStart + 0x100) pe.push_back(0);
    
    // IAT for user32 (MessageBoxA) - at 0x100
    pe.push_back(msgBoxHintRVA & 0xFF);
    pe.push_back((msgBoxHintRVA >> 8) & 0xFF);
    pe.push_back((msgBoxHintRVA >> 16) & 0xFF);
    pe.push_back((msgBoxHintRVA >> 24) & 0xFF);
    
    // IAT for kernel32 (ExitProcess) - at 0x104
    pe.push_back(exitProcHintRVA & 0xFF);
    pe.push_back((exitProcHintRVA >> 8) & 0xFF);
    pe.push_back((exitProcHintRVA >> 16) & 0xFF);
    pe.push_back((exitProcHintRVA >> 24) & 0xFF);
    
    // Null terminators for IAT
    pe.push_back(0); pe.push_back(0); pe.push_back(0); pe.push_back(0);
    pe.push_back(0); pe.push_back(0); pe.push_back(0); pe.push_back(0);
    
    // Pad to Hint/Name for ExitProcess (0x140)
    while (pe.size() < idataStart + 0x140) pe.push_back(0);
    
    // Hint/Name for ExitProcess
    pe.push_back(0); pe.push_back(0);  // Hint
    const char* exitProc = "ExitProcess";
    for (size_t i = 0; exitProc[i]; i++) pe.push_back(exitProc[i]);
    pe.push_back(0);
    
    // Pad to Hint/Name for MessageBoxA (0x160)
    while (pe.size() < idataStart + 0x160) pe.push_back(0);
    
    // Hint/Name for MessageBoxA
    pe.push_back(0); pe.push_back(0);  // Hint
    const char* msgBox = "MessageBoxA";
    for (size_t i = 0; msgBox[i]; i++) pe.push_back(msgBox[i]);
    pe.push_back(0);
    
    // Pad to kernel32.dll name (0x180)
    while (pe.size() < idataStart + 0x180) pe.push_back(0);
    
    // "kernel32.dll"
    const char* k32 = "kernel32.dll";
    for (size_t i = 0; k32[i]; i++) pe.push_back(k32[i]);
    pe.push_back(0);
    
    // Pad to user32.dll name (0x1A0)
    while (pe.size() < idataStart + 0x1A0) pe.push_back(0);
    
    // "user32.dll"
    const char* u32 = "user32.dll";
    for (size_t i = 0; u32[i]; i++) pe.push_back(u32[i]);
    pe.push_back(0);
    
    // Pad .idata
    while (pe.size() < idataStart + IDATA_SIZE) pe.push_back(0);
    
    // ========================================================================
    // .rdata Section - Read-only Data (strings)
    // ========================================================================
    size_t rdataStart = pe.size();
    
    // Title string at offset 0
    const char* title = "PE From Scratch";
    for (size_t i = 0; title[i]; i++) pe.push_back(title[i]);
    pe.push_back(0);
    
    // Pad to message at 0x20
    while (pe.size() < rdataStart + 0x20) pe.push_back(0);
    
    // Message string
    const char* message = "Hello, World!\n\nThis executable was created byte-by-byte\nwithout using any assembler or linker!";
    for (size_t i = 0; message[i]; i++) pe.push_back(message[i]);
    pe.push_back(0);
    
    // Pad .rdata
    while (pe.size() < rdataStart + RDATA_SIZE) pe.push_back(0);
    
    return pe;
}

void printUsage(const char* progName) {
    std::cout << "PE Writer - Create Windows Executables from Scratch" << std::endl;
    std::cout << "\nUsage: " << progName << " [output.exe] [type]" << std::endl;
    std::cout << "\nTypes:" << std::endl;
    std::cout << "  minimal    Create minimal PE that exits with code 42 (default)" << std::endl;
    std::cout << "  msgbox     Create PE that shows a MessageBox" << std::endl;
    std::cout << "\nExamples:" << std::endl;
    std::cout << "  " << progName << "                    # Creates minimal.exe" << std::endl;
    std::cout << "  " << progName << " hello.exe msgbox   # Creates hello.exe with MessageBox" << std::endl;
}

int main(int argc, char* argv[]) {
    std::string outputFile = "minimal.exe";
    std::string type = "minimal";
    
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "-h" || arg == "--help") {
            printUsage(argv[0]);
            return 0;
        } else if (arg == "minimal" || arg == "msgbox") {
            type = arg;
        } else {
            outputFile = arg;
        }
    }
    
    std::cout << "PE Writer - Creating " << type << " PE executable" << std::endl;
    std::cout << "Output: " << outputFile << std::endl;
    
    std::vector<uint8_t> pe;
    
    if (type == "msgbox") {
        pe = createMessageBoxPE();
        std::cout << "\nCreated MessageBox PE:" << std::endl;
        std::cout << "  - Shows a message box with 'Hello, World!'" << std::endl;
        std::cout << "  - Imports: kernel32.dll (ExitProcess), user32.dll (MessageBoxA)" << std::endl;
    } else {
        pe = createMinimalPE();
        std::cout << "\nCreated minimal PE:" << std::endl;
        std::cout << "  - Calls ExitProcess(42)" << std::endl;
        std::cout << "  - Exit code will be 42" << std::endl;
    }
    
    // Write to file
    std::ofstream file(outputFile, std::ios::binary);
    if (!file) {
        std::cerr << "Error: Cannot create output file: " << outputFile << std::endl;
        return 1;
    }
    
    file.write(reinterpret_cast<const char*>(pe.data()), pe.size());
    file.close();
    
    std::cout << "\nFile size: " << pe.size() << " bytes" << std::endl;
    std::cout << "\nTo run on Windows:" << std::endl;
    std::cout << "  " << outputFile << std::endl;
    std::cout << "  echo %ERRORLEVEL%" << std::endl;
    
    std::cout << "\nTo analyze the PE structure:" << std::endl;
    std::cout << "  ./pe_parser " << outputFile << std::endl;
    
    return 0;
}
