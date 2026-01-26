/**
 * PE Format Header Definitions
 * 
 * Portable Executable (PE) format structures for Windows executables.
 * This file defines all the structures needed to read and write PE files.
 * 
 * PE File Layout:
 * ┌─────────────────────────────────────────────────────────────────┐
 * │ DOS Header (64 bytes)                                          │
 * │   - Magic "MZ" (0x5A4D)                                         │
 * │   - e_lfanew: offset to PE signature                           │
 * ├─────────────────────────────────────────────────────────────────┤
 * │ DOS Stub (optional, typically ~64 bytes)                       │
 * │   - "This program cannot be run in DOS mode"                   │
 * ├─────────────────────────────────────────────────────────────────┤
 * │ PE Signature ("PE\0\0" = 0x00004550)                           │
 * ├─────────────────────────────────────────────────────────────────┤
 * │ COFF File Header (20 bytes)                                    │
 * │   - Machine type (x86=0x14c, x64=0x8664)                       │
 * │   - Number of sections                                          │
 * │   - Size of optional header                                     │
 * ├─────────────────────────────────────────────────────────────────┤
 * │ Optional Header (PE32: 96 bytes, PE32+: 112 bytes)             │
 * │   - Magic (PE32=0x10b, PE32+=0x20b)                            │
 * │   - Entry point RVA                                             │
 * │   - Image base, section alignment, file alignment              │
 * │   + Data Directories (16 entries × 8 bytes = 128 bytes)        │
 * ├─────────────────────────────────────────────────────────────────┤
 * │ Section Headers (40 bytes each)                                 │
 * │   - .text, .data, .rdata, .idata, etc.                         │
 * ├─────────────────────────────────────────────────────────────────┤
 * │ Section Data                                                    │
 * │   - Raw code and data aligned to FileAlignment                 │
 * └─────────────────────────────────────────────────────────────────┘
 */

#ifndef PE_FORMAT_H
#define PE_FORMAT_H

#include <cstdint>
#include <cstring>

// ============================================================================
// DOS Header - The legacy MS-DOS header at the start of every PE file
// ============================================================================

#pragma pack(push, 1)

struct DOSHeader {
    uint16_t e_magic;      // Magic number "MZ" (0x5A4D)
    uint16_t e_cblp;       // Bytes on last page of file
    uint16_t e_cp;         // Pages in file
    uint16_t e_crlc;       // Relocations
    uint16_t e_cparhdr;    // Size of header in paragraphs
    uint16_t e_minalloc;   // Minimum extra paragraphs needed
    uint16_t e_maxalloc;   // Maximum extra paragraphs needed
    uint16_t e_ss;         // Initial (relative) SS value
    uint16_t e_sp;         // Initial SP value
    uint16_t e_csum;       // Checksum
    uint16_t e_ip;         // Initial IP value
    uint16_t e_cs;         // Initial (relative) CS value
    uint16_t e_lfarlc;     // File address of relocation table
    uint16_t e_ovno;       // Overlay number
    uint16_t e_res[4];     // Reserved words
    uint16_t e_oemid;      // OEM identifier
    uint16_t e_oeminfo;    // OEM information
    uint16_t e_res2[10];   // Reserved words
    uint32_t e_lfanew;     // File address of PE header
};

static_assert(sizeof(DOSHeader) == 64, "DOSHeader must be 64 bytes");

// ============================================================================
// PE Signature - "PE\0\0"
// ============================================================================

constexpr uint32_t PE_SIGNATURE = 0x00004550;  // "PE\0\0"
constexpr uint16_t DOS_SIGNATURE = 0x5A4D;     // "MZ"

// ============================================================================
// COFF File Header - Common Object File Format header
// ============================================================================

struct COFFHeader {
    uint16_t Machine;              // Target machine type
    uint16_t NumberOfSections;     // Number of sections
    uint32_t TimeDateStamp;        // Time and date stamp
    uint32_t PointerToSymbolTable; // Deprecated, should be 0
    uint32_t NumberOfSymbols;      // Deprecated, should be 0
    uint16_t SizeOfOptionalHeader; // Size of optional header
    uint16_t Characteristics;      // File characteristics flags
};

static_assert(sizeof(COFFHeader) == 20, "COFFHeader must be 20 bytes");

// Machine types
constexpr uint16_t IMAGE_FILE_MACHINE_UNKNOWN = 0x0000;
constexpr uint16_t IMAGE_FILE_MACHINE_I386    = 0x014C;  // x86
constexpr uint16_t IMAGE_FILE_MACHINE_AMD64   = 0x8664;  // x64
constexpr uint16_t IMAGE_FILE_MACHINE_ARM     = 0x01C0;  // ARM
constexpr uint16_t IMAGE_FILE_MACHINE_ARM64   = 0xAA64;  // ARM64

// Characteristics flags
constexpr uint16_t IMAGE_FILE_RELOCS_STRIPPED         = 0x0001;
constexpr uint16_t IMAGE_FILE_EXECUTABLE_IMAGE        = 0x0002;
constexpr uint16_t IMAGE_FILE_LINE_NUMS_STRIPPED      = 0x0004;
constexpr uint16_t IMAGE_FILE_LOCAL_SYMS_STRIPPED     = 0x0008;
constexpr uint16_t IMAGE_FILE_LARGE_ADDRESS_AWARE     = 0x0020;
constexpr uint16_t IMAGE_FILE_32BIT_MACHINE           = 0x0100;
constexpr uint16_t IMAGE_FILE_DEBUG_STRIPPED          = 0x0200;
constexpr uint16_t IMAGE_FILE_DLL                     = 0x2000;

// ============================================================================
// Data Directory - Entry in the data directory array
// ============================================================================

struct DataDirectory {
    uint32_t VirtualAddress;  // RVA of the data
    uint32_t Size;            // Size of the data
};

static_assert(sizeof(DataDirectory) == 8, "DataDirectory must be 8 bytes");

// Data directory indices
constexpr int IMAGE_DIRECTORY_ENTRY_EXPORT         = 0;
constexpr int IMAGE_DIRECTORY_ENTRY_IMPORT         = 1;
constexpr int IMAGE_DIRECTORY_ENTRY_RESOURCE       = 2;
constexpr int IMAGE_DIRECTORY_ENTRY_EXCEPTION      = 3;
constexpr int IMAGE_DIRECTORY_ENTRY_SECURITY       = 4;
constexpr int IMAGE_DIRECTORY_ENTRY_BASERELOC      = 5;
constexpr int IMAGE_DIRECTORY_ENTRY_DEBUG          = 6;
constexpr int IMAGE_DIRECTORY_ENTRY_ARCHITECTURE   = 7;
constexpr int IMAGE_DIRECTORY_ENTRY_GLOBALPTR      = 8;
constexpr int IMAGE_DIRECTORY_ENTRY_TLS            = 9;
constexpr int IMAGE_DIRECTORY_ENTRY_LOAD_CONFIG    = 10;
constexpr int IMAGE_DIRECTORY_ENTRY_BOUND_IMPORT   = 11;
constexpr int IMAGE_DIRECTORY_ENTRY_IAT            = 12;
constexpr int IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT   = 13;
constexpr int IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR = 14;

constexpr int IMAGE_NUMBEROF_DIRECTORY_ENTRIES = 16;

// ============================================================================
// Optional Header - PE32 (32-bit)
// ============================================================================

struct OptionalHeader32 {
    // Standard fields
    uint16_t Magic;                   // PE32 = 0x10B
    uint8_t  MajorLinkerVersion;
    uint8_t  MinorLinkerVersion;
    uint32_t SizeOfCode;
    uint32_t SizeOfInitializedData;
    uint32_t SizeOfUninitializedData;
    uint32_t AddressOfEntryPoint;     // RVA of entry point
    uint32_t BaseOfCode;
    uint32_t BaseOfData;              // Only in PE32, not PE32+
    
    // Windows-specific fields
    uint32_t ImageBase;               // Preferred load address
    uint32_t SectionAlignment;        // Alignment of sections in memory
    uint32_t FileAlignment;           // Alignment of sections in file
    uint16_t MajorOperatingSystemVersion;
    uint16_t MinorOperatingSystemVersion;
    uint16_t MajorImageVersion;
    uint16_t MinorImageVersion;
    uint16_t MajorSubsystemVersion;
    uint16_t MinorSubsystemVersion;
    uint32_t Win32VersionValue;
    uint32_t SizeOfImage;             // Size of image in memory
    uint32_t SizeOfHeaders;           // Size of headers rounded up
    uint32_t CheckSum;
    uint16_t Subsystem;               // Subsystem (console, GUI, etc.)
    uint16_t DllCharacteristics;
    uint32_t SizeOfStackReserve;
    uint32_t SizeOfStackCommit;
    uint32_t SizeOfHeapReserve;
    uint32_t SizeOfHeapCommit;
    uint32_t LoaderFlags;
    uint32_t NumberOfRvaAndSizes;
    
    DataDirectory DataDirectories[IMAGE_NUMBEROF_DIRECTORY_ENTRIES];
};

static_assert(sizeof(OptionalHeader32) == 224, "OptionalHeader32 must be 224 bytes");

// ============================================================================
// Optional Header - PE32+ (64-bit)
// ============================================================================

struct OptionalHeader64 {
    // Standard fields
    uint16_t Magic;                   // PE32+ = 0x20B
    uint8_t  MajorLinkerVersion;
    uint8_t  MinorLinkerVersion;
    uint32_t SizeOfCode;
    uint32_t SizeOfInitializedData;
    uint32_t SizeOfUninitializedData;
    uint32_t AddressOfEntryPoint;
    uint32_t BaseOfCode;
    // Note: No BaseOfData in PE32+
    
    // Windows-specific fields (64-bit values where different)
    uint64_t ImageBase;               // 64-bit image base
    uint32_t SectionAlignment;
    uint32_t FileAlignment;
    uint16_t MajorOperatingSystemVersion;
    uint16_t MinorOperatingSystemVersion;
    uint16_t MajorImageVersion;
    uint16_t MinorImageVersion;
    uint16_t MajorSubsystemVersion;
    uint16_t MinorSubsystemVersion;
    uint32_t Win32VersionValue;
    uint32_t SizeOfImage;
    uint32_t SizeOfHeaders;
    uint32_t CheckSum;
    uint16_t Subsystem;
    uint16_t DllCharacteristics;
    uint64_t SizeOfStackReserve;      // 64-bit
    uint64_t SizeOfStackCommit;       // 64-bit
    uint64_t SizeOfHeapReserve;       // 64-bit
    uint64_t SizeOfHeapCommit;        // 64-bit
    uint32_t LoaderFlags;
    uint32_t NumberOfRvaAndSizes;
    
    DataDirectory DataDirectories[IMAGE_NUMBEROF_DIRECTORY_ENTRIES];
};

static_assert(sizeof(OptionalHeader64) == 240, "OptionalHeader64 must be 240 bytes");

// Magic numbers for optional header
constexpr uint16_t IMAGE_NT_OPTIONAL_HDR32_MAGIC = 0x10B;  // PE32
constexpr uint16_t IMAGE_NT_OPTIONAL_HDR64_MAGIC = 0x20B;  // PE32+

// Subsystem values
constexpr uint16_t IMAGE_SUBSYSTEM_UNKNOWN                  = 0;
constexpr uint16_t IMAGE_SUBSYSTEM_NATIVE                   = 1;
constexpr uint16_t IMAGE_SUBSYSTEM_WINDOWS_GUI              = 2;
constexpr uint16_t IMAGE_SUBSYSTEM_WINDOWS_CUI              = 3;  // Console
constexpr uint16_t IMAGE_SUBSYSTEM_OS2_CUI                  = 5;
constexpr uint16_t IMAGE_SUBSYSTEM_POSIX_CUI                = 7;
constexpr uint16_t IMAGE_SUBSYSTEM_WINDOWS_CE_GUI           = 9;
constexpr uint16_t IMAGE_SUBSYSTEM_EFI_APPLICATION          = 10;
constexpr uint16_t IMAGE_SUBSYSTEM_EFI_BOOT_SERVICE_DRIVER  = 11;
constexpr uint16_t IMAGE_SUBSYSTEM_EFI_RUNTIME_DRIVER       = 12;
constexpr uint16_t IMAGE_SUBSYSTEM_EFI_ROM                  = 13;
constexpr uint16_t IMAGE_SUBSYSTEM_XBOX                     = 14;

// DLL Characteristics flags
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_HIGH_ENTROPY_VA       = 0x0020;
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE          = 0x0040;  // ASLR
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_FORCE_INTEGRITY       = 0x0080;
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_NX_COMPAT             = 0x0100;  // DEP
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_NO_ISOLATION          = 0x0200;
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_NO_SEH                = 0x0400;
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_NO_BIND               = 0x0800;
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_APPCONTAINER          = 0x1000;
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_WDM_DRIVER            = 0x2000;
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_GUARD_CF              = 0x4000;
constexpr uint16_t IMAGE_DLLCHARACTERISTICS_TERMINAL_SERVER_AWARE = 0x8000;

// ============================================================================
// Section Header - Describes a section in the PE file
// ============================================================================

struct SectionHeader {
    char     Name[8];                 // Section name (null-padded, not null-terminated if 8 chars)
    uint32_t VirtualSize;             // Size in memory (can be larger than raw data)
    uint32_t VirtualAddress;          // RVA of section in memory
    uint32_t SizeOfRawData;           // Size of section data in file
    uint32_t PointerToRawData;        // File offset of section data
    uint32_t PointerToRelocations;    // File offset of relocations
    uint32_t PointerToLinenumbers;    // File offset of line numbers
    uint16_t NumberOfRelocations;
    uint16_t NumberOfLinenumbers;
    uint32_t Characteristics;         // Section flags
};

static_assert(sizeof(SectionHeader) == 40, "SectionHeader must be 40 bytes");

// Section characteristics flags
constexpr uint32_t IMAGE_SCN_CNT_CODE               = 0x00000020;  // Contains code
constexpr uint32_t IMAGE_SCN_CNT_INITIALIZED_DATA   = 0x00000040;  // Contains initialized data
constexpr uint32_t IMAGE_SCN_CNT_UNINITIALIZED_DATA = 0x00000080;  // Contains uninitialized data
constexpr uint32_t IMAGE_SCN_LNK_INFO               = 0x00000200;  // Section contains comments
constexpr uint32_t IMAGE_SCN_LNK_REMOVE             = 0x00000800;  // Section will not become part of image
constexpr uint32_t IMAGE_SCN_LNK_COMDAT             = 0x00001000;  // Section contains COMDAT data
constexpr uint32_t IMAGE_SCN_GPREL                  = 0x00008000;  // Section contains GP-relative data
constexpr uint32_t IMAGE_SCN_MEM_DISCARDABLE        = 0x02000000;  // Section is discardable
constexpr uint32_t IMAGE_SCN_MEM_NOT_CACHED         = 0x04000000;  // Section is not cacheable
constexpr uint32_t IMAGE_SCN_MEM_NOT_PAGED          = 0x08000000;  // Section is not pageable
constexpr uint32_t IMAGE_SCN_MEM_SHARED             = 0x10000000;  // Section can be shared
constexpr uint32_t IMAGE_SCN_MEM_EXECUTE            = 0x20000000;  // Section is executable
constexpr uint32_t IMAGE_SCN_MEM_READ               = 0x40000000;  // Section is readable
constexpr uint32_t IMAGE_SCN_MEM_WRITE              = 0x80000000;  // Section is writable

// ============================================================================
// Import Directory Entry - For describing imported DLLs
// ============================================================================

struct ImportDescriptor {
    union {
        uint32_t Characteristics;
        uint32_t OriginalFirstThunk;  // RVA to Import Lookup Table
    };
    uint32_t TimeDateStamp;           // 0 if not bound
    uint32_t ForwarderChain;          // -1 if no forwarders
    uint32_t Name;                    // RVA to DLL name string
    uint32_t FirstThunk;              // RVA to Import Address Table
};

static_assert(sizeof(ImportDescriptor) == 20, "ImportDescriptor must be 20 bytes");

// ============================================================================
// Import Lookup/Address Table Entry (32-bit)
// ============================================================================

struct ImportThunk32 {
    union {
        uint32_t AddressOfData;       // RVA to IMAGE_IMPORT_BY_NAME
        struct {
            uint32_t Ordinal : 16;
            uint32_t Reserved : 15;
            uint32_t OrdinalFlag : 1; // If set, import by ordinal
        };
    };
};

// ============================================================================
// Import Lookup/Address Table Entry (64-bit)
// ============================================================================

struct ImportThunk64 {
    union {
        uint64_t AddressOfData;
        struct {
            uint64_t Ordinal : 16;
            uint64_t Reserved : 47;
            uint64_t OrdinalFlag : 1;
        };
    };
};

// ============================================================================
// Import By Name structure
// ============================================================================

struct ImportByName {
    uint16_t Hint;                    // Index into export table (hint)
    char     Name[1];                 // Null-terminated function name (variable length)
};

// ============================================================================
// Export Directory - For describing exported functions
// ============================================================================

struct ExportDirectory {
    uint32_t Characteristics;
    uint32_t TimeDateStamp;
    uint16_t MajorVersion;
    uint16_t MinorVersion;
    uint32_t Name;                    // RVA to DLL name
    uint32_t Base;                    // Ordinal base
    uint32_t NumberOfFunctions;       // Number of entries in EAT
    uint32_t NumberOfNames;           // Number of entries in name table
    uint32_t AddressOfFunctions;      // RVA to Export Address Table
    uint32_t AddressOfNames;          // RVA to Export Name Table
    uint32_t AddressOfNameOrdinals;   // RVA to ordinal table
};

static_assert(sizeof(ExportDirectory) == 40, "ExportDirectory must be 40 bytes");

// ============================================================================
// Base Relocation Block
// ============================================================================

struct BaseRelocationBlock {
    uint32_t VirtualAddress;          // RVA of block
    uint32_t SizeOfBlock;             // Size including this header
    // Followed by variable number of uint16_t entries
    // High 4 bits = type, low 12 bits = offset
};

// Base relocation types
constexpr uint16_t IMAGE_REL_BASED_ABSOLUTE       = 0;   // Padding (skip)
constexpr uint16_t IMAGE_REL_BASED_HIGH           = 1;   // High 16 bits
constexpr uint16_t IMAGE_REL_BASED_LOW            = 2;   // Low 16 bits
constexpr uint16_t IMAGE_REL_BASED_HIGHLOW        = 3;   // Full 32-bit
constexpr uint16_t IMAGE_REL_BASED_HIGHADJ        = 4;   // High 16 bits, adjusted
constexpr uint16_t IMAGE_REL_BASED_DIR64          = 10;  // 64-bit address

#pragma pack(pop)

// ============================================================================
// Helper Functions
// ============================================================================

inline const char* getMachineTypeName(uint16_t machine) {
    switch (machine) {
        case IMAGE_FILE_MACHINE_UNKNOWN: return "Unknown";
        case IMAGE_FILE_MACHINE_I386:    return "Intel 386 (x86)";
        case IMAGE_FILE_MACHINE_AMD64:   return "AMD64 (x64)";
        case IMAGE_FILE_MACHINE_ARM:     return "ARM";
        case IMAGE_FILE_MACHINE_ARM64:   return "ARM64";
        default:                         return "Other";
    }
}

inline const char* getSubsystemName(uint16_t subsystem) {
    switch (subsystem) {
        case IMAGE_SUBSYSTEM_UNKNOWN:                  return "Unknown";
        case IMAGE_SUBSYSTEM_NATIVE:                   return "Native";
        case IMAGE_SUBSYSTEM_WINDOWS_GUI:              return "Windows GUI";
        case IMAGE_SUBSYSTEM_WINDOWS_CUI:              return "Windows Console (CUI)";
        case IMAGE_SUBSYSTEM_OS2_CUI:                  return "OS/2 Console";
        case IMAGE_SUBSYSTEM_POSIX_CUI:                return "POSIX Console";
        case IMAGE_SUBSYSTEM_WINDOWS_CE_GUI:           return "Windows CE GUI";
        case IMAGE_SUBSYSTEM_EFI_APPLICATION:          return "EFI Application";
        case IMAGE_SUBSYSTEM_EFI_BOOT_SERVICE_DRIVER:  return "EFI Boot Service Driver";
        case IMAGE_SUBSYSTEM_EFI_RUNTIME_DRIVER:       return "EFI Runtime Driver";
        case IMAGE_SUBSYSTEM_EFI_ROM:                  return "EFI ROM";
        case IMAGE_SUBSYSTEM_XBOX:                     return "Xbox";
        default:                                       return "Other";
    }
}

inline const char* getDataDirectoryName(int index) {
    static const char* names[] = {
        "Export Table",
        "Import Table",
        "Resource Table",
        "Exception Table",
        "Certificate Table",
        "Base Relocation Table",
        "Debug",
        "Architecture",
        "Global Ptr",
        "TLS Table",
        "Load Config Table",
        "Bound Import",
        "IAT",
        "Delay Import Descriptor",
        "CLR Runtime Header",
        "Reserved"
    };
    if (index >= 0 && index < 16) return names[index];
    return "Unknown";
}

#endif // PE_FORMAT_H
