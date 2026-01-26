# PE Format Tools - Makefile
# Build PE parser and writer utilities

CXX = c++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2

# Executables
PE_PARSER = pe_parser
PE_WRITER = pe_writer

# Generated PE files
MINIMAL_EXE = minimal.exe
MSGBOX_EXE = msgbox.exe

all: $(PE_PARSER) $(PE_WRITER)

$(PE_PARSER): pe_parser.cpp pe_format.h
	$(CXX) $(CXXFLAGS) -o $@ pe_parser.cpp

$(PE_WRITER): pe_writer.cpp pe_format.h
	$(CXX) $(CXXFLAGS) -o $@ pe_writer.cpp

# Generate sample PE files
samples: $(PE_WRITER)
	./$(PE_WRITER) $(MINIMAL_EXE) minimal
	./$(PE_WRITER) $(MSGBOX_EXE) msgbox

# Parse the generated samples
demo: samples $(PE_PARSER)
	@echo ""
	@echo "============================================="
	@echo "Parsing minimal.exe"
	@echo "============================================="
	./$(PE_PARSER) $(MINIMAL_EXE)
	@echo ""
	@echo "============================================="
	@echo "Parsing msgbox.exe (verbose)"
	@echo "============================================="
	./$(PE_PARSER) $(MSGBOX_EXE) -v

# Parse with full output
demo-full: samples $(PE_PARSER)
	./$(PE_PARSER) $(MINIMAL_EXE) -a
	@echo ""
	./$(PE_PARSER) $(MSGBOX_EXE) -a

# Test by generating and parsing
test: $(PE_PARSER) $(PE_WRITER)
	@echo "=== Generating minimal PE ==="
	./$(PE_WRITER) test_minimal.exe minimal
	@echo ""
	@echo "=== Parsing minimal PE ==="
	./$(PE_PARSER) test_minimal.exe
	@echo ""
	@echo "=== Generating MessageBox PE ==="
	./$(PE_WRITER) test_msgbox.exe msgbox
	@echo ""
	@echo "=== Parsing MessageBox PE ==="
	./$(PE_PARSER) test_msgbox.exe -i
	@echo ""
	@echo "=== Test complete! ==="
	@rm -f test_minimal.exe test_msgbox.exe

# Parse any .exe file provided
parse: $(PE_PARSER)
ifndef FILE
	@echo "Usage: make parse FILE=<path_to_exe>"
	@echo "Example: make parse FILE=/path/to/program.exe"
else
	./$(PE_PARSER) $(FILE) -v -i -e
endif

# Parse with full hex dump
parse-full: $(PE_PARSER)
ifndef FILE
	@echo "Usage: make parse-full FILE=<path_to_exe>"
else
	./$(PE_PARSER) $(FILE) -a
endif

clean:
	rm -f $(PE_PARSER) $(PE_WRITER)
	rm -f $(MINIMAL_EXE) $(MSGBOX_EXE)
	rm -f test_minimal.exe test_msgbox.exe
	rm -f *.exe

help:
	@echo "PE Format Tools - Available targets:"
	@echo ""
	@echo "  make              - Build pe_parser and pe_writer"
	@echo "  make samples      - Generate sample PE files"
	@echo "  make demo         - Generate and parse sample PEs"
	@echo "  make demo-full    - Generate and parse with all details"
	@echo "  make test         - Run full test suite"
	@echo ""
	@echo "  make parse FILE=<path>      - Parse a specific .exe file"
	@echo "  make parse-full FILE=<path> - Parse with full hex dump"
	@echo ""
	@echo "  make clean        - Remove generated files"
	@echo "  make help         - Show this help"
	@echo ""
	@echo "Examples:"
	@echo "  make parse FILE=notepad.exe"
	@echo "  make parse-full FILE=/path/to/program.exe"

.PHONY: all samples demo demo-full test parse parse-full clean help
