/**
 * PE Parser - Portable Executable File Analyzer
 * 
 * Parses and displays the complete structure of Windows .exe files.
 * This tool reads PE files byte-by-byte and outputs all headers,
 * sections, imports, exports, and optionally raw data.
 * 
 * Usage: ./pe_parser <file.exe> [options]
 *   -v, --verbose    Show more details including raw bytes
 *   -d, --disasm     Show basic disassembly of code sections
 *   -x, --hex        Dump hex of all sections
 *   -i, --imports    Show detailed import information
 *   -e, --exports    Show detailed export information
 *   -a, --all        Show everything
 */

#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstring>
#include <iomanip>
#include <sstream>
#include <algorithm>
#include "pe_format.h"

// ANSI color codes for terminal output
namespace Color {
    const char* Reset   = "\033[0m";
    const char* Bold    = "\033[1m";
    const char* Red     = "\033[31m";
    const char* Green   = "\033[32m";
    const char* Yellow  = "\033[33m";
    const char* Blue    = "\033[34m";
    const char* Magenta = "\033[35m";
    const char* Cyan    = "\033[36m";
}

// Configuration options
struct ParseOptions {
    bool verbose = false;
    bool hexDump = false;
    bool showImports = false;
    bool showExports = false;
    bool disasm = false;
};

// Helper to print hex dump
void hexDump(const uint8_t* data, size_t size, uint64_t baseAddr = 0, size_t maxLines = 16) {
    size_t lines = 0;
    for (size_t i = 0; i < size && lines < maxLines; i += 16) {
        std::cout << std::hex << std::setfill('0') << std::setw(8) 
                  << (baseAddr + i) << ": ";
        
        // Hex bytes
        for (size_t j = 0; j < 16; j++) {
            if (i + j < size) {
                std::cout << std::setw(2) << (int)data[i + j] << " ";
            } else {
                std::cout << "   ";
            }
            if (j == 7) std::cout << " ";
        }
        
        std::cout << " |";
        
        // ASCII representation
        for (size_t j = 0; j < 16 && i + j < size; j++) {
            char c = data[i + j];
            std::cout << (c >= 32 && c < 127 ? c : '.');
        }
        
        std::cout << "|" << std::endl;
        lines++;
    }
    std::cout << std::dec;
    
    if (size > maxLines * 16) {
        std::cout << "        ... (" << (size - maxLines * 16) << " more bytes)" << std::endl;
    }
}

// Helper to format section characteristics
std::string getSectionFlags(uint32_t flags) {
    std::vector<std::string> flagNames;
    
    if (flags & IMAGE_SCN_CNT_CODE)               flagNames.push_back("CODE");
    if (flags & IMAGE_SCN_CNT_INITIALIZED_DATA)   flagNames.push_back("INIT_DATA");
    if (flags & IMAGE_SCN_CNT_UNINITIALIZED_DATA) flagNames.push_back("UNINIT_DATA");
    if (flags & IMAGE_SCN_MEM_EXECUTE)            flagNames.push_back("EXEC");
    if (flags & IMAGE_SCN_MEM_READ)               flagNames.push_back("READ");
    if (flags & IMAGE_SCN_MEM_WRITE)              flagNames.push_back("WRITE");
    if (flags & IMAGE_SCN_MEM_DISCARDABLE)        flagNames.push_back("DISCARD");
    if (flags & IMAGE_SCN_MEM_SHARED)             flagNames.push_back("SHARED");
    
    std::string result;
    for (size_t i = 0; i < flagNames.size(); i++) {
        if (i > 0) result += " | ";
        result += flagNames[i];
    }
    return result.empty() ? "NONE" : result;
}

// Helper to format COFF characteristics
std::string getCOFFCharacteristics(uint16_t flags) {
    std::vector<std::string> flagNames;
    
    if (flags & IMAGE_FILE_RELOCS_STRIPPED)     flagNames.push_back("RELOCS_STRIPPED");
    if (flags & IMAGE_FILE_EXECUTABLE_IMAGE)    flagNames.push_back("EXECUTABLE");
    if (flags & IMAGE_FILE_LINE_NUMS_STRIPPED)  flagNames.push_back("LINE_NUMS_STRIPPED");
    if (flags & IMAGE_FILE_LOCAL_SYMS_STRIPPED) flagNames.push_back("LOCAL_SYMS_STRIPPED");
    if (flags & IMAGE_FILE_LARGE_ADDRESS_AWARE) flagNames.push_back("LARGE_ADDRESS_AWARE");
    if (flags & IMAGE_FILE_32BIT_MACHINE)       flagNames.push_back("32BIT_MACHINE");
    if (flags & IMAGE_FILE_DEBUG_STRIPPED)      flagNames.push_back("DEBUG_STRIPPED");
    if (flags & IMAGE_FILE_DLL)                 flagNames.push_back("DLL");
    
    std::string result;
    for (size_t i = 0; i < flagNames.size(); i++) {
        if (i > 0) result += " | ";
        result += flagNames[i];
    }
    return result.empty() ? "NONE" : result;
}

// Helper to format DLL characteristics
std::string getDllCharacteristics(uint16_t flags) {
    std::vector<std::string> flagNames;
    
    if (flags & IMAGE_DLLCHARACTERISTICS_HIGH_ENTROPY_VA) flagNames.push_back("HIGH_ENTROPY_VA");
    if (flags & IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE)    flagNames.push_back("ASLR");
    if (flags & IMAGE_DLLCHARACTERISTICS_FORCE_INTEGRITY) flagNames.push_back("FORCE_INTEGRITY");
    if (flags & IMAGE_DLLCHARACTERISTICS_NX_COMPAT)       flagNames.push_back("DEP/NX");
    if (flags & IMAGE_DLLCHARACTERISTICS_NO_ISOLATION)    flagNames.push_back("NO_ISOLATION");
    if (flags & IMAGE_DLLCHARACTERISTICS_NO_SEH)          flagNames.push_back("NO_SEH");
    if (flags & IMAGE_DLLCHARACTERISTICS_NO_BIND)         flagNames.push_back("NO_BIND");
    if (flags & IMAGE_DLLCHARACTERISTICS_APPCONTAINER)    flagNames.push_back("APPCONTAINER");
    if (flags & IMAGE_DLLCHARACTERISTICS_GUARD_CF)        flagNames.push_back("GUARD_CF");
    if (flags & IMAGE_DLLCHARACTERISTICS_TERMINAL_SERVER_AWARE) flagNames.push_back("TERMINAL_SERVER_AWARE");
    
    std::string result;
    for (size_t i = 0; i < flagNames.size(); i++) {
        if (i > 0) result += " | ";
        result += flagNames[i];
    }
    return result.empty() ? "NONE" : result;
}

// Read a null-terminated string from file data
std::string readString(const std::vector<uint8_t>& data, size_t offset, size_t maxLen = 256) {
    std::string result;
    for (size_t i = 0; i < maxLen && offset + i < data.size(); i++) {
        if (data[offset + i] == 0) break;
        result += static_cast<char>(data[offset + i]);
    }
    return result;
}

// Convert RVA to file offset using section headers
size_t rvaToFileOffset(uint32_t rva, const std::vector<SectionHeader>& sections) {
    for (const auto& section : sections) {
        if (rva >= section.VirtualAddress && 
            rva < section.VirtualAddress + section.VirtualSize) {
            return section.PointerToRawData + (rva - section.VirtualAddress);
        }
    }
    return 0;
}

// Print a horizontal separator
void printSeparator(const char* title = nullptr) {
    if (title) {
        std::cout << "\n" << Color::Bold << Color::Cyan 
                  << "══════════════════════════════════════════════════════════════════════════════" 
                  << Color::Reset << std::endl;
        std::cout << Color::Bold << Color::Yellow << "  " << title << Color::Reset << std::endl;
        std::cout << Color::Bold << Color::Cyan 
                  << "══════════════════════════════════════════════════════════════════════════════" 
                  << Color::Reset << std::endl;
    } else {
        std::cout << Color::Cyan 
                  << "──────────────────────────────────────────────────────────────────────────────" 
                  << Color::Reset << std::endl;
    }
}

// Main PE parser class
class PEParser {
public:
    bool parse(const std::string& filename) {
        // Read entire file
        std::ifstream file(filename, std::ios::binary);
        if (!file) {
            std::cerr << Color::Red << "Error: Cannot open file: " << filename << Color::Reset << std::endl;
            return false;
        }
        
        file.seekg(0, std::ios::end);
        fileSize = file.tellg();
        file.seekg(0, std::ios::beg);
        
        data.resize(fileSize);
        file.read(reinterpret_cast<char*>(data.data()), fileSize);
        file.close();
        
        this->filename = filename;
        return true;
    }
    
    bool analyze(const ParseOptions& opts) {
        options = opts;
        
        // Parse DOS Header
        if (fileSize < sizeof(DOSHeader)) {
            std::cerr << Color::Red << "Error: File too small for DOS header" << Color::Reset << std::endl;
            return false;
        }
        
        memcpy(&dosHeader, data.data(), sizeof(DOSHeader));
        
        if (dosHeader.e_magic != DOS_SIGNATURE) {
            std::cerr << Color::Red << "Error: Invalid DOS signature. Expected 'MZ' (0x5A4D), got 0x" 
                      << std::hex << dosHeader.e_magic << std::dec << Color::Reset << std::endl;
            return false;
        }
        
        // Parse PE Signature
        if (dosHeader.e_lfanew + sizeof(uint32_t) > fileSize) {
            std::cerr << Color::Red << "Error: Invalid e_lfanew offset" << Color::Reset << std::endl;
            return false;
        }
        
        uint32_t peSignature;
        memcpy(&peSignature, data.data() + dosHeader.e_lfanew, sizeof(uint32_t));
        
        if (peSignature != PE_SIGNATURE) {
            std::cerr << Color::Red << "Error: Invalid PE signature. Expected 'PE\\0\\0' (0x00004550), got 0x"
                      << std::hex << peSignature << std::dec << Color::Reset << std::endl;
            return false;
        }
        
        // Parse COFF Header
        size_t coffOffset = dosHeader.e_lfanew + sizeof(uint32_t);
        if (coffOffset + sizeof(COFFHeader) > fileSize) {
            std::cerr << Color::Red << "Error: File too small for COFF header" << Color::Reset << std::endl;
            return false;
        }
        
        memcpy(&coffHeader, data.data() + coffOffset, sizeof(COFFHeader));
        
        // Determine if PE32 or PE32+
        size_t optionalOffset = coffOffset + sizeof(COFFHeader);
        uint16_t optionalMagic;
        memcpy(&optionalMagic, data.data() + optionalOffset, sizeof(uint16_t));
        
        is64Bit = (optionalMagic == IMAGE_NT_OPTIONAL_HDR64_MAGIC);
        
        // Parse Optional Header
        if (is64Bit) {
            if (optionalOffset + sizeof(OptionalHeader64) > fileSize) {
                std::cerr << Color::Red << "Error: File too small for PE32+ optional header" << Color::Reset << std::endl;
                return false;
            }
            memcpy(&optionalHeader64, data.data() + optionalOffset, sizeof(OptionalHeader64));
        } else {
            if (optionalOffset + sizeof(OptionalHeader32) > fileSize) {
                std::cerr << Color::Red << "Error: File too small for PE32 optional header" << Color::Reset << std::endl;
                return false;
            }
            memcpy(&optionalHeader32, data.data() + optionalOffset, sizeof(OptionalHeader32));
        }
        
        // Parse Section Headers
        size_t sectionOffset = optionalOffset + coffHeader.SizeOfOptionalHeader;
        sections.clear();
        
        for (int i = 0; i < coffHeader.NumberOfSections; i++) {
            if (sectionOffset + sizeof(SectionHeader) > fileSize) {
                std::cerr << Color::Red << "Error: File too small for section header " << i << Color::Reset << std::endl;
                return false;
            }
            
            SectionHeader section;
            memcpy(&section, data.data() + sectionOffset, sizeof(SectionHeader));
            sections.push_back(section);
            sectionOffset += sizeof(SectionHeader);
        }
        
        return true;
    }
    
    void printAll() {
        printHeader();
        printDOSHeader();
        printCOFFHeader();
        printOptionalHeader();
        printDataDirectories();
        printSections();
        
        if (options.showImports || options.verbose) {
            printImports();
        }
        
        if (options.showExports || options.verbose) {
            printExports();
        }
        
        if (options.hexDump) {
            printSectionDumps();
        }
        
        printSummary();
    }
    
private:
    std::string filename;
    std::vector<uint8_t> data;
    size_t fileSize = 0;
    ParseOptions options;
    
    DOSHeader dosHeader;
    COFFHeader coffHeader;
    OptionalHeader32 optionalHeader32;
    OptionalHeader64 optionalHeader64;
    std::vector<SectionHeader> sections;
    bool is64Bit = false;
    
    void printHeader() {
        printSeparator("PE FILE ANALYSIS");
        std::cout << Color::Bold << "  File: " << Color::Reset << filename << std::endl;
        std::cout << Color::Bold << "  Size: " << Color::Reset << fileSize << " bytes (" 
                  << std::fixed << std::setprecision(2) << (fileSize / 1024.0) << " KB)" << std::endl;
        std::cout << Color::Bold << "  Type: " << Color::Reset 
                  << (is64Bit ? "PE32+ (64-bit)" : "PE32 (32-bit)") << std::endl;
    }
    
    void printDOSHeader() {
        printSeparator("DOS HEADER (64 bytes @ offset 0x0000)");
        
        std::cout << std::hex << std::setfill('0');
        std::cout << "  e_magic:      0x" << std::setw(4) << dosHeader.e_magic 
                  << " ('" << (char)(dosHeader.e_magic & 0xFF) << (char)(dosHeader.e_magic >> 8) << "')" << std::endl;
        std::cout << "  e_cblp:       0x" << std::setw(4) << dosHeader.e_cblp 
                  << " (bytes on last page)" << std::endl;
        std::cout << "  e_cp:         0x" << std::setw(4) << dosHeader.e_cp 
                  << " (pages in file)" << std::endl;
        std::cout << "  e_cparhdr:    0x" << std::setw(4) << dosHeader.e_cparhdr 
                  << " (header size in paragraphs)" << std::endl;
        std::cout << "  e_lfanew:     0x" << std::setw(8) << dosHeader.e_lfanew 
                  << " " << Color::Green << "(offset to PE header)" << Color::Reset << std::endl;
        std::cout << std::dec;
        
        if (options.verbose) {
            std::cout << "\n  DOS Header Raw Bytes:" << std::endl << "  ";
            hexDump(data.data(), 64, 0, 4);
        }
        
        // Check for DOS stub
        if (dosHeader.e_lfanew > sizeof(DOSHeader)) {
            size_t stubSize = dosHeader.e_lfanew - sizeof(DOSHeader);
            std::cout << "\n  DOS Stub: " << stubSize << " bytes" << std::endl;
            
            // Look for "This program cannot be run in DOS mode" message
            std::string stubText = readString(data, sizeof(DOSHeader), stubSize);
            if (stubText.find("DOS mode") != std::string::npos || 
                stubText.find("cannot be run") != std::string::npos) {
                std::cout << "  Contains standard DOS stub message" << std::endl;
            }
        }
    }
    
    void printCOFFHeader() {
        printSeparator("COFF FILE HEADER (20 bytes)");
        
        std::cout << std::hex << std::setfill('0');
        std::cout << "  Machine:              0x" << std::setw(4) << coffHeader.Machine 
                  << " (" << Color::Yellow << getMachineTypeName(coffHeader.Machine) << Color::Reset << ")" << std::endl;
        std::cout << std::dec;
        std::cout << "  NumberOfSections:     " << coffHeader.NumberOfSections << std::endl;
        std::cout << "  TimeDateStamp:        " << coffHeader.TimeDateStamp;
        if (coffHeader.TimeDateStamp > 0) {
            time_t timestamp = coffHeader.TimeDateStamp;
            std::cout << " (" << std::ctime(&timestamp);
            std::cout << "\b)";  // Remove newline from ctime
        }
        std::cout << std::endl;
        std::cout << std::hex;
        std::cout << "  PointerToSymbolTable: 0x" << std::setw(8) << coffHeader.PointerToSymbolTable << std::endl;
        std::cout << std::dec;
        std::cout << "  NumberOfSymbols:      " << coffHeader.NumberOfSymbols << std::endl;
        std::cout << "  SizeOfOptionalHeader: " << coffHeader.SizeOfOptionalHeader << " bytes" << std::endl;
        std::cout << std::hex;
        std::cout << "  Characteristics:      0x" << std::setw(4) << coffHeader.Characteristics << std::endl;
        std::cout << std::dec;
        std::cout << "    " << Color::Cyan << getCOFFCharacteristics(coffHeader.Characteristics) << Color::Reset << std::endl;
    }
    
    void printOptionalHeader() {
        printSeparator(is64Bit ? "OPTIONAL HEADER - PE32+ (240 bytes)" : "OPTIONAL HEADER - PE32 (224 bytes)");
        
        if (is64Bit) {
            printOptionalHeader64();
        } else {
            printOptionalHeader32();
        }
    }
    
    void printOptionalHeader32() {
        auto& opt = optionalHeader32;
        std::cout << std::hex << std::setfill('0');
        
        std::cout << "  Magic:                       0x" << std::setw(4) << opt.Magic << " (PE32)" << std::endl;
        std::cout << "  LinkerVersion:               " << std::dec << (int)opt.MajorLinkerVersion << "." << (int)opt.MinorLinkerVersion << std::endl;
        std::cout << std::hex;
        std::cout << "  SizeOfCode:                  0x" << std::setw(8) << opt.SizeOfCode << std::endl;
        std::cout << "  SizeOfInitializedData:       0x" << std::setw(8) << opt.SizeOfInitializedData << std::endl;
        std::cout << "  SizeOfUninitializedData:     0x" << std::setw(8) << opt.SizeOfUninitializedData << std::endl;
        std::cout << "  AddressOfEntryPoint:         0x" << std::setw(8) << opt.AddressOfEntryPoint 
                  << Color::Green << " (RVA)" << Color::Reset << std::endl;
        std::cout << "  BaseOfCode:                  0x" << std::setw(8) << opt.BaseOfCode << std::endl;
        std::cout << "  BaseOfData:                  0x" << std::setw(8) << opt.BaseOfData << std::endl;
        std::cout << "  ImageBase:                   0x" << std::setw(8) << opt.ImageBase << std::endl;
        std::cout << "  SectionAlignment:            0x" << std::setw(8) << opt.SectionAlignment 
                  << " (" << std::dec << opt.SectionAlignment << " bytes)" << std::endl;
        std::cout << std::hex;
        std::cout << "  FileAlignment:               0x" << std::setw(8) << opt.FileAlignment 
                  << " (" << std::dec << opt.FileAlignment << " bytes)" << std::endl;
        std::cout << "  OperatingSystemVersion:      " << opt.MajorOperatingSystemVersion << "." << opt.MinorOperatingSystemVersion << std::endl;
        std::cout << "  SubsystemVersion:            " << opt.MajorSubsystemVersion << "." << opt.MinorSubsystemVersion << std::endl;
        std::cout << std::hex;
        std::cout << "  SizeOfImage:                 0x" << std::setw(8) << opt.SizeOfImage << std::endl;
        std::cout << "  SizeOfHeaders:               0x" << std::setw(8) << opt.SizeOfHeaders << std::endl;
        std::cout << "  CheckSum:                    0x" << std::setw(8) << opt.CheckSum << std::endl;
        std::cout << "  Subsystem:                   " << std::dec << opt.Subsystem 
                  << " (" << Color::Yellow << getSubsystemName(opt.Subsystem) << Color::Reset << ")" << std::endl;
        std::cout << std::hex;
        std::cout << "  DllCharacteristics:          0x" << std::setw(4) << opt.DllCharacteristics << std::endl;
        std::cout << "    " << Color::Cyan << getDllCharacteristics(opt.DllCharacteristics) << Color::Reset << std::endl;
        std::cout << "  SizeOfStackReserve:          0x" << std::setw(8) << opt.SizeOfStackReserve << std::endl;
        std::cout << "  SizeOfStackCommit:           0x" << std::setw(8) << opt.SizeOfStackCommit << std::endl;
        std::cout << "  SizeOfHeapReserve:           0x" << std::setw(8) << opt.SizeOfHeapReserve << std::endl;
        std::cout << "  SizeOfHeapCommit:            0x" << std::setw(8) << opt.SizeOfHeapCommit << std::endl;
        std::cout << "  NumberOfRvaAndSizes:         " << std::dec << opt.NumberOfRvaAndSizes << std::endl;
    }
    
    void printOptionalHeader64() {
        auto& opt = optionalHeader64;
        std::cout << std::hex << std::setfill('0');
        
        std::cout << "  Magic:                       0x" << std::setw(4) << opt.Magic << " (PE32+)" << std::endl;
        std::cout << "  LinkerVersion:               " << std::dec << (int)opt.MajorLinkerVersion << "." << (int)opt.MinorLinkerVersion << std::endl;
        std::cout << std::hex;
        std::cout << "  SizeOfCode:                  0x" << std::setw(8) << opt.SizeOfCode << std::endl;
        std::cout << "  SizeOfInitializedData:       0x" << std::setw(8) << opt.SizeOfInitializedData << std::endl;
        std::cout << "  SizeOfUninitializedData:     0x" << std::setw(8) << opt.SizeOfUninitializedData << std::endl;
        std::cout << "  AddressOfEntryPoint:         0x" << std::setw(8) << opt.AddressOfEntryPoint 
                  << Color::Green << " (RVA)" << Color::Reset << std::endl;
        std::cout << "  BaseOfCode:                  0x" << std::setw(8) << opt.BaseOfCode << std::endl;
        std::cout << "  ImageBase:                   0x" << std::setw(16) << opt.ImageBase << std::endl;
        std::cout << "  SectionAlignment:            0x" << std::setw(8) << opt.SectionAlignment 
                  << " (" << std::dec << opt.SectionAlignment << " bytes)" << std::endl;
        std::cout << std::hex;
        std::cout << "  FileAlignment:               0x" << std::setw(8) << opt.FileAlignment 
                  << " (" << std::dec << opt.FileAlignment << " bytes)" << std::endl;
        std::cout << "  OperatingSystemVersion:      " << opt.MajorOperatingSystemVersion << "." << opt.MinorOperatingSystemVersion << std::endl;
        std::cout << "  SubsystemVersion:            " << opt.MajorSubsystemVersion << "." << opt.MinorSubsystemVersion << std::endl;
        std::cout << std::hex;
        std::cout << "  SizeOfImage:                 0x" << std::setw(8) << opt.SizeOfImage << std::endl;
        std::cout << "  SizeOfHeaders:               0x" << std::setw(8) << opt.SizeOfHeaders << std::endl;
        std::cout << "  CheckSum:                    0x" << std::setw(8) << opt.CheckSum << std::endl;
        std::cout << "  Subsystem:                   " << std::dec << opt.Subsystem 
                  << " (" << Color::Yellow << getSubsystemName(opt.Subsystem) << Color::Reset << ")" << std::endl;
        std::cout << std::hex;
        std::cout << "  DllCharacteristics:          0x" << std::setw(4) << opt.DllCharacteristics << std::endl;
        std::cout << "    " << Color::Cyan << getDllCharacteristics(opt.DllCharacteristics) << Color::Reset << std::endl;
        std::cout << "  SizeOfStackReserve:          0x" << std::setw(16) << opt.SizeOfStackReserve << std::endl;
        std::cout << "  SizeOfStackCommit:           0x" << std::setw(16) << opt.SizeOfStackCommit << std::endl;
        std::cout << "  SizeOfHeapReserve:           0x" << std::setw(16) << opt.SizeOfHeapReserve << std::endl;
        std::cout << "  SizeOfHeapCommit:            0x" << std::setw(16) << opt.SizeOfHeapCommit << std::endl;
        std::cout << "  NumberOfRvaAndSizes:         " << std::dec << opt.NumberOfRvaAndSizes << std::endl;
    }
    
    void printDataDirectories() {
        printSeparator("DATA DIRECTORIES");
        
        DataDirectory* dirs = is64Bit ? optionalHeader64.DataDirectories : optionalHeader32.DataDirectories;
        uint32_t numDirs = is64Bit ? optionalHeader64.NumberOfRvaAndSizes : optionalHeader32.NumberOfRvaAndSizes;
        
        std::cout << std::left << std::setfill(' ');
        std::cout << "  " << std::setw(25) << "Directory" << std::setw(12) << "RVA" << std::setw(12) << "Size" << "Status" << std::endl;
        std::cout << "  " << std::string(60, '-') << std::endl;
        
        for (uint32_t i = 0; i < numDirs && i < IMAGE_NUMBEROF_DIRECTORY_ENTRIES; i++) {
            std::cout << "  " << std::setw(25) << getDataDirectoryName(i);
            
            if (dirs[i].VirtualAddress != 0 || dirs[i].Size != 0) {
                std::cout << std::hex << std::setfill('0');
                std::cout << "0x" << std::setw(8) << dirs[i].VirtualAddress << "  ";
                std::cout << "0x" << std::setw(8) << dirs[i].Size;
                std::cout << std::setfill(' ') << "  " << Color::Green << "Present" << Color::Reset;
            } else {
                std::cout << std::setfill(' ');
                std::cout << std::setw(12) << "-" << std::setw(12) << "-";
                std::cout << Color::Red << "Empty" << Color::Reset;
            }
            std::cout << std::endl;
        }
        std::cout << std::dec;
    }
    
    void printSections() {
        printSeparator("SECTION HEADERS");
        
        std::cout << std::left << std::setfill(' ');
        std::cout << "  " << std::setw(10) << "Name" 
                  << std::setw(12) << "VirtSize" 
                  << std::setw(12) << "VirtAddr" 
                  << std::setw(12) << "RawSize"
                  << std::setw(12) << "RawPtr"
                  << "Flags" << std::endl;
        std::cout << "  " << std::string(80, '-') << std::endl;
        
        for (const auto& section : sections) {
            // Get section name (may not be null-terminated if 8 chars)
            char name[9] = {0};
            memcpy(name, section.Name, 8);
            
            std::cout << "  " << std::setw(10) << name;
            std::cout << std::hex << std::setfill('0');
            std::cout << "0x" << std::setw(8) << section.VirtualSize << "  ";
            std::cout << "0x" << std::setw(8) << section.VirtualAddress << "  ";
            std::cout << "0x" << std::setw(8) << section.SizeOfRawData << "  ";
            std::cout << "0x" << std::setw(8) << section.PointerToRawData;
            std::cout << std::setfill(' ') << std::endl;
            std::cout << "    " << Color::Cyan << getSectionFlags(section.Characteristics) << Color::Reset << std::endl;
        }
        std::cout << std::dec;
    }
    
    void printImports() {
        DataDirectory* dirs = is64Bit ? optionalHeader64.DataDirectories : optionalHeader32.DataDirectories;
        DataDirectory& importDir = dirs[IMAGE_DIRECTORY_ENTRY_IMPORT];
        
        if (importDir.VirtualAddress == 0) {
            return;
        }
        
        printSeparator("IMPORT TABLE");
        
        size_t importOffset = rvaToFileOffset(importDir.VirtualAddress, sections);
        if (importOffset == 0 || importOffset >= fileSize) {
            std::cout << "  " << Color::Red << "Cannot locate import table in file" << Color::Reset << std::endl;
            return;
        }
        
        // Parse import descriptors
        size_t offset = importOffset;
        while (offset + sizeof(ImportDescriptor) <= fileSize) {
            ImportDescriptor desc;
            memcpy(&desc, data.data() + offset, sizeof(ImportDescriptor));
            
            // Check for null terminator
            if (desc.Name == 0 && desc.FirstThunk == 0) {
                break;
            }
            
            // Get DLL name
            size_t nameOffset = rvaToFileOffset(desc.Name, sections);
            std::string dllName = nameOffset < fileSize ? readString(data, nameOffset) : "<unknown>";
            
            std::cout << "\n  " << Color::Bold << Color::Yellow << dllName << Color::Reset << std::endl;
            std::cout << std::hex << std::setfill('0');
            std::cout << "    OriginalFirstThunk (ILT): 0x" << std::setw(8) << desc.OriginalFirstThunk << std::endl;
            std::cout << "    FirstThunk (IAT):         0x" << std::setw(8) << desc.FirstThunk << std::endl;
            std::cout << std::dec;
            
            // Parse import lookup table
            if (desc.OriginalFirstThunk != 0 || desc.FirstThunk != 0) {
                uint32_t thunkRva = desc.OriginalFirstThunk != 0 ? desc.OriginalFirstThunk : desc.FirstThunk;
                size_t thunkOffset = rvaToFileOffset(thunkRva, sections);
                
                if (thunkOffset != 0 && thunkOffset < fileSize) {
                    std::cout << "    Functions:" << std::endl;
                    int count = 0;
                    
                    while (count < 100) {  // Safety limit
                        if (is64Bit) {
                            if (thunkOffset + sizeof(uint64_t) > fileSize) break;
                            uint64_t thunk;
                            memcpy(&thunk, data.data() + thunkOffset, sizeof(uint64_t));
                            if (thunk == 0) break;
                            
                            if (thunk & 0x8000000000000000ULL) {
                                std::cout << "      Ordinal: " << (thunk & 0xFFFF) << std::endl;
                            } else {
                                size_t hintOffset = rvaToFileOffset(static_cast<uint32_t>(thunk), sections);
                                if (hintOffset + 2 < fileSize) {
                                    uint16_t hint;
                                    memcpy(&hint, data.data() + hintOffset, sizeof(uint16_t));
                                    std::string funcName = readString(data, hintOffset + 2);
                                    std::cout << "      [" << std::setw(4) << hint << "] " << funcName << std::endl;
                                }
                            }
                            thunkOffset += sizeof(uint64_t);
                        } else {
                            if (thunkOffset + sizeof(uint32_t) > fileSize) break;
                            uint32_t thunk;
                            memcpy(&thunk, data.data() + thunkOffset, sizeof(uint32_t));
                            if (thunk == 0) break;
                            
                            if (thunk & 0x80000000) {
                                std::cout << "      Ordinal: " << (thunk & 0xFFFF) << std::endl;
                            } else {
                                size_t hintOffset = rvaToFileOffset(thunk, sections);
                                if (hintOffset + 2 < fileSize) {
                                    uint16_t hint;
                                    memcpy(&hint, data.data() + hintOffset, sizeof(uint16_t));
                                    std::string funcName = readString(data, hintOffset + 2);
                                    std::cout << "      [" << std::setw(4) << hint << "] " << funcName << std::endl;
                                }
                            }
                            thunkOffset += sizeof(uint32_t);
                        }
                        count++;
                    }
                }
            }
            
            offset += sizeof(ImportDescriptor);
        }
    }
    
    void printExports() {
        DataDirectory* dirs = is64Bit ? optionalHeader64.DataDirectories : optionalHeader32.DataDirectories;
        DataDirectory& exportDir = dirs[IMAGE_DIRECTORY_ENTRY_EXPORT];
        
        if (exportDir.VirtualAddress == 0) {
            return;
        }
        
        printSeparator("EXPORT TABLE");
        
        size_t exportOffset = rvaToFileOffset(exportDir.VirtualAddress, sections);
        if (exportOffset == 0 || exportOffset + sizeof(ExportDirectory) > fileSize) {
            std::cout << "  " << Color::Red << "Cannot locate export table in file" << Color::Reset << std::endl;
            return;
        }
        
        ExportDirectory expDir;
        memcpy(&expDir, data.data() + exportOffset, sizeof(ExportDirectory));
        
        // Get DLL name
        size_t nameOffset = rvaToFileOffset(expDir.Name, sections);
        std::string dllName = nameOffset < fileSize ? readString(data, nameOffset) : "<unknown>";
        
        std::cout << "  DLL Name:           " << Color::Yellow << dllName << Color::Reset << std::endl;
        std::cout << "  Ordinal Base:       " << expDir.Base << std::endl;
        std::cout << "  Number of Functions:" << expDir.NumberOfFunctions << std::endl;
        std::cout << "  Number of Names:    " << expDir.NumberOfNames << std::endl;
        
        // Parse export names
        if (expDir.NumberOfNames > 0 && expDir.AddressOfNames != 0) {
            std::cout << "\n  Exported Functions:" << std::endl;
            
            size_t namesOffset = rvaToFileOffset(expDir.AddressOfNames, sections);
            size_t ordinalsOffset = rvaToFileOffset(expDir.AddressOfNameOrdinals, sections);
            size_t functionsOffset = rvaToFileOffset(expDir.AddressOfFunctions, sections);
            
            for (uint32_t i = 0; i < expDir.NumberOfNames && i < 100; i++) {
                if (namesOffset + (i + 1) * 4 > fileSize) break;
                
                uint32_t nameRva;
                memcpy(&nameRva, data.data() + namesOffset + i * 4, sizeof(uint32_t));
                
                size_t funcNameOffset = rvaToFileOffset(nameRva, sections);
                std::string funcName = funcNameOffset < fileSize ? readString(data, funcNameOffset) : "<unknown>";
                
                uint16_t ordinal = 0;
                if (ordinalsOffset + (i + 1) * 2 <= fileSize) {
                    memcpy(&ordinal, data.data() + ordinalsOffset + i * 2, sizeof(uint16_t));
                }
                
                uint32_t funcRva = 0;
                if (functionsOffset + (ordinal + 1) * 4 <= fileSize) {
                    memcpy(&funcRva, data.data() + functionsOffset + ordinal * 4, sizeof(uint32_t));
                }
                
                std::cout << std::hex << std::setfill('0');
                std::cout << "    [" << std::setw(4) << (expDir.Base + ordinal) << "] ";
                std::cout << "0x" << std::setw(8) << funcRva << "  " << funcName << std::endl;
            }
            std::cout << std::dec;
        }
    }
    
    void printSectionDumps() {
        printSeparator("SECTION HEX DUMPS");
        
        for (const auto& section : sections) {
            char name[9] = {0};
            memcpy(name, section.Name, 8);
            
            std::cout << "\n  " << Color::Bold << name << Color::Reset;
            std::cout << " (file offset 0x" << std::hex << section.PointerToRawData 
                      << ", size 0x" << section.SizeOfRawData << std::dec << ")" << std::endl;
            
            if (section.PointerToRawData < fileSize && section.SizeOfRawData > 0) {
                size_t dumpSize = std::min<size_t>(section.SizeOfRawData, fileSize - section.PointerToRawData);
                std::cout << "  ";
                hexDump(data.data() + section.PointerToRawData, dumpSize, section.PointerToRawData, 8);
            }
        }
    }
    
    void printSummary() {
        printSeparator("SUMMARY");
        
        uint64_t imageBase = is64Bit ? optionalHeader64.ImageBase : optionalHeader32.ImageBase;
        uint32_t entryPoint = is64Bit ? optionalHeader64.AddressOfEntryPoint : optionalHeader32.AddressOfEntryPoint;
        
        std::cout << std::hex << std::setfill('0');
        std::cout << "  Entry Point (VA): 0x" << std::setw(is64Bit ? 16 : 8) << (imageBase + entryPoint) << std::endl;
        std::cout << "  Entry Point (RVA): 0x" << std::setw(8) << entryPoint << std::endl;
        
        // Find which section contains the entry point
        for (const auto& section : sections) {
            if (entryPoint >= section.VirtualAddress && 
                entryPoint < section.VirtualAddress + section.VirtualSize) {
                char name[9] = {0};
                memcpy(name, section.Name, 8);
                std::cout << "  Entry Point Section: " << Color::Yellow << name << Color::Reset << std::endl;
                
                // Calculate file offset of entry point
                size_t epFileOffset = section.PointerToRawData + (entryPoint - section.VirtualAddress);
                std::cout << "  Entry Point (File Offset): 0x" << std::setw(8) << epFileOffset << std::endl;
                
                // Show first few bytes at entry point
                if (epFileOffset < fileSize) {
                    std::cout << "\n  First bytes at entry point:" << std::endl << "  ";
                    size_t dumpSize = std::min<size_t>(48, fileSize - epFileOffset);
                    hexDump(data.data() + epFileOffset, dumpSize, epFileOffset, 3);
                }
                break;
            }
        }
        std::cout << std::dec << std::endl;
    }
};

// Print usage information
void printUsage(const char* progName) {
    std::cout << "PE Parser - Portable Executable Analyzer" << std::endl;
    std::cout << "\nUsage: " << progName << " <file.exe> [options]" << std::endl;
    std::cout << "\nOptions:" << std::endl;
    std::cout << "  -v, --verbose    Show detailed information including raw bytes" << std::endl;
    std::cout << "  -x, --hex        Dump hex of all sections" << std::endl;
    std::cout << "  -i, --imports    Show detailed import information" << std::endl;
    std::cout << "  -e, --exports    Show detailed export information" << std::endl;
    std::cout << "  -a, --all        Show everything (equivalent to -v -x -i -e)" << std::endl;
    std::cout << "  -h, --help       Show this help message" << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        printUsage(argv[0]);
        return 1;
    }
    
    std::string filename;
    ParseOptions options;
    
    // Parse command line arguments
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        
        if (arg == "-h" || arg == "--help") {
            printUsage(argv[0]);
            return 0;
        } else if (arg == "-v" || arg == "--verbose") {
            options.verbose = true;
        } else if (arg == "-x" || arg == "--hex") {
            options.hexDump = true;
        } else if (arg == "-i" || arg == "--imports") {
            options.showImports = true;
        } else if (arg == "-e" || arg == "--exports") {
            options.showExports = true;
        } else if (arg == "-d" || arg == "--disasm") {
            options.disasm = true;
        } else if (arg == "-a" || arg == "--all") {
            options.verbose = true;
            options.hexDump = true;
            options.showImports = true;
            options.showExports = true;
        } else if (arg[0] != '-') {
            filename = arg;
        } else {
            std::cerr << "Unknown option: " << arg << std::endl;
            return 1;
        }
    }
    
    if (filename.empty()) {
        std::cerr << "Error: No input file specified" << std::endl;
        printUsage(argv[0]);
        return 1;
    }
    
    PEParser parser;
    
    if (!parser.parse(filename)) {
        return 1;
    }
    
    if (!parser.analyze(options)) {
        return 1;
    }
    
    parser.printAll();
    
    return 0;
}
