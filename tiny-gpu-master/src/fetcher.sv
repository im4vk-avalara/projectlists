`default_nettype none
`timescale 1ns/1ns

// INSTRUCTION FETCHER WITH CACHE AND PREFETCH PIPELINE
// > Retrieves the instruction at the current PC from global program memory
// > Includes a direct-mapped instruction cache to avoid repeated memory accesses
// > PIPELINING: Prefetches next instruction (PC+1) during EXECUTE/UPDATE stages
// > Each core has its own fetcher with its own cache
//
// Cache Design:
// - Direct-mapped cache with CACHE_SIZE entries (default 32)
// - Index = PC[CACHE_INDEX_BITS-1:0]
// - Tag = PC[PROGRAM_MEM_ADDR_BITS-1:CACHE_INDEX_BITS]
// - Each entry: {valid, tag, instruction}
//
// Prefetch Pipeline:
// - While current instruction is in EXECUTE/UPDATE, start fetching next instruction
// - If next PC matches prefetched address, instruction is ready immediately
// - This overlaps FETCH with EXECUTE/UPDATE, saving cycles
//
// On cache hit: instruction available in 1 cycle (no memory access)
// On cache miss: fetch from memory, store in cache for future hits
// On prefetch hit: instruction already ready (0 additional cycles)
module fetcher #(
    parameter PROGRAM_MEM_ADDR_BITS = 8,
    parameter PROGRAM_MEM_DATA_BITS = 16,
    parameter CACHE_SIZE = 32,                                    // Number of cache entries
    parameter CACHE_INDEX_BITS = 5                                // log2(CACHE_SIZE) = 5 for 32 entries
) (
    input wire clk,
    input wire reset,
    
    // Execution State
    input reg [2:0] core_state,
    input reg [7:0] current_pc,

    // Program Memory
    output reg mem_read_valid,
    output reg [PROGRAM_MEM_ADDR_BITS-1:0] mem_read_address,
    input reg mem_read_ready,
    input reg [PROGRAM_MEM_DATA_BITS-1:0] mem_read_data,

    // Fetcher Output
    output reg [2:0] fetcher_state,
    output reg [PROGRAM_MEM_DATA_BITS-1:0] instruction,

    // Cache Statistics
    output reg [31:0] cache_hits,
    output reg [31:0] cache_misses,
    
    // Pipeline Statistics
    output reg [31:0] prefetch_hits,     // Times prefetch avoided waiting
    output reg [31:0] prefetch_misses    // Times prefetch didn't help (branch, etc)
);
    // Fetcher states
    localparam IDLE = 3'b000, 
        FETCHING = 3'b001, 
        FETCHED = 3'b010,
        CACHE_HIT = 3'b011,
        PREFETCH_HIT = 3'b100;   // New state for prefetch hit

    // Cache parameters
    localparam TAG_BITS = PROGRAM_MEM_ADDR_BITS - CACHE_INDEX_BITS;  // 8 - 5 = 3 bits

    // Cache storage
    reg cache_valid [CACHE_SIZE-1:0];
    reg [TAG_BITS-1:0] cache_tag [CACHE_SIZE-1:0];
    reg [PROGRAM_MEM_DATA_BITS-1:0] cache_data [CACHE_SIZE-1:0];

    // Prefetch buffer - stores the next instruction (PC+1)
    reg prefetch_valid;
    reg [PROGRAM_MEM_ADDR_BITS-1:0] prefetch_pc;
    reg [PROGRAM_MEM_DATA_BITS-1:0] prefetch_instruction;
    reg prefetch_in_progress;
    
    // Cache lookup signals
    wire [CACHE_INDEX_BITS-1:0] cache_index;
    wire [TAG_BITS-1:0] pc_tag;
    wire cache_hit;

    // Extract index and tag from current PC
    assign cache_index = current_pc[CACHE_INDEX_BITS-1:0];
    assign pc_tag = current_pc[PROGRAM_MEM_ADDR_BITS-1:CACHE_INDEX_BITS];

    // Cache hit detection: valid entry with matching tag
    assign cache_hit = cache_valid[cache_index] && (cache_tag[cache_index] == pc_tag);
    
    // Prefetch hit: prefetch buffer contains the instruction we need
    wire prefetch_hit = prefetch_valid && (prefetch_pc == current_pc);

    // Track if cache has been initialized
    reg cache_initialized;

    // Cache initialization and operation
    integer i;
    
    // Working variables for prefetch logic (sv2v compatibility)
    reg [7:0] next_pc_calc;
    reg [CACHE_INDEX_BITS-1:0] next_index;
    reg [TAG_BITS-1:0] next_tag;
    reg [CACHE_INDEX_BITS-1:0] pf_index;
    reg [TAG_BITS-1:0] pf_tag;
    
    // Initialize all registers for simulation
    initial begin
        cache_initialized = 0;
        fetcher_state = IDLE;
        mem_read_valid = 0;
        mem_read_address = 0;
        instruction = 0;
        cache_hits = 0;
        cache_misses = 0;
        prefetch_hits = 0;
        prefetch_misses = 0;
        prefetch_valid = 0;
        prefetch_pc = 0;
        prefetch_instruction = 0;
        prefetch_in_progress = 0;
        for (i = 0; i < CACHE_SIZE; i = i + 1) begin
            cache_valid[i] = 0;
            cache_tag[i] = 0;
            cache_data[i] = 0;
        end
    end
    
    always @(posedge clk) begin
        if (reset) begin
            // Always reset fetcher state machine on any reset
            fetcher_state <= IDLE;
            mem_read_valid <= 0;
            mem_read_address <= 0;
            instruction <= {PROGRAM_MEM_DATA_BITS{1'b0}};
            prefetch_valid <= 0;
            prefetch_in_progress <= 0;
            
            // Only invalidate cache on FIRST reset (cold start)
            // This allows cache to persist across blocks within a kernel,
            // but fresh simulation starts have an empty cache.
            // Note: Running multiple different kernels in the same simulation
            // may cause issues as the cache retains old instructions.
            if (!cache_initialized) begin
                cache_initialized <= 1;
                cache_hits <= 0;
                cache_misses <= 0;
                prefetch_hits <= 0;
                prefetch_misses <= 0;
                
                // Invalidate all cache entries on first reset only
                for (i = 0; i < CACHE_SIZE; i = i + 1) begin
                    cache_valid[i] <= 0;
                    cache_tag[i] <= 0;
                    cache_data[i] <= 0;
                end
            end
        end else begin
            case (fetcher_state)
                IDLE: begin
                    // Start fetching when core_state = FETCH
                    if (core_state == 3'b001) begin
                        if (prefetch_hit) begin
                            // PREFETCH HIT: Use prefetched instruction immediately!
                            fetcher_state <= PREFETCH_HIT;
                            instruction <= prefetch_instruction;
                            prefetch_hits <= prefetch_hits + 1;
                            prefetch_valid <= 0;  // Consume the prefetch
                        end else if (cache_hit) begin
                            // CACHE HIT: Use cached instruction
                            fetcher_state <= CACHE_HIT;
                            instruction <= cache_data[cache_index];
                            cache_hits <= cache_hits + 1;
                            // Prefetch didn't help (either wrong PC or not ready)
                            if (prefetch_valid) begin
                                prefetch_misses <= prefetch_misses + 1;
                                prefetch_valid <= 0;
                            end
                        end else begin
                            // CACHE MISS: Need to fetch from program memory
                            fetcher_state <= FETCHING;
                            mem_read_valid <= 1;
                            mem_read_address <= current_pc;
                            cache_misses <= cache_misses + 1;
                            if (prefetch_valid) begin
                                prefetch_misses <= prefetch_misses + 1;
                                prefetch_valid <= 0;
                            end
                        end
                    end
                    
                    // PIPELINING: During REQUEST/WAIT/EXECUTE/UPDATE, prefetch next instruction from CACHE only
                    // This overlaps FETCH with later pipeline stages
                    // Note: We only prefetch from cache to avoid memory conflicts
                    // Memory prefetch would require a dual-port memory or separate prefetch channel
                    if ((core_state == 3'b011 || core_state == 3'b100 || 
                         core_state == 3'b101 || core_state == 3'b110) && 
                        !prefetch_valid) begin
                        // Calculate next likely PC (current + 1) - speculative for sequential code
                        next_pc_calc = current_pc + 1;
                        
                        // Check if next instruction is already in cache
                        next_index = next_pc_calc[CACHE_INDEX_BITS-1:0];
                        next_tag = next_pc_calc[PROGRAM_MEM_ADDR_BITS-1:CACHE_INDEX_BITS];
                        
                        if (cache_valid[next_index] && cache_tag[next_index] == next_tag) begin
                            // Next instruction in cache - prefetch from cache immediately
                            prefetch_valid <= 1;
                            prefetch_pc <= next_pc_calc;
                            prefetch_instruction <= cache_data[next_index];
                        end
                        // If not in cache, don't prefetch - let normal fetch handle it
                    end
                end
                
                PREFETCH_HIT: begin
                    // Prefetch hit path: instruction already loaded, move to FETCHED
                    fetcher_state <= FETCHED;
                end
                
                CACHE_HIT: begin
                    // Cache hit path: instruction already loaded, move to FETCHED
                    fetcher_state <= FETCHED;
                end
                
                FETCHING: begin
                    // Wait for response from program memory
                    if (mem_read_ready) begin
                        fetcher_state <= FETCHED;
                        instruction <= mem_read_data;
                        mem_read_valid <= 0;
                        
                        // Store in cache for future accesses
                        cache_valid[cache_index] <= 1;
                        cache_tag[cache_index] <= pc_tag;
                        cache_data[cache_index] <= mem_read_data;
                    end
                end
                
                FETCHED: begin
                    // Reset when core_state = DECODE
                    if (core_state == 3'b010) begin 
                        fetcher_state <= IDLE;
                    end
                end
            endcase
        end
    end
endmodule
