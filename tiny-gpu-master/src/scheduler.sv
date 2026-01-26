`default_nettype none
`timescale 1ns/1ns

// SCHEDULER WITH BRANCH DIVERGENCE
// > Manages the entire control flow of a single compute core processing 1 block
// 1. FETCH - Retrieve instruction at current program counter (PC) from program memory
// 2. DECODE - Decode the instruction into the relevant control signals
// 3. REQUEST - If we have an instruction that accesses memory, trigger the async memory requests from LSUs
// 4. WAIT - Wait for all async memory requests to resolve (if applicable)
// 5. EXECUTE - Execute computations on retrieved data from registers / memory
// 6. UPDATE - Update register values (including NZP register) and program counter
//
// BRANCH DIVERGENCE SUPPORT:
// > When threads take different branches, we track which threads are "active"
// > The execution mask indicates which threads should execute the current instruction
// > Divergent threads are masked off until reconvergence
// > Uses a simple SIMT stack approach with max 4 levels of nesting
module scheduler #(
    parameter THREADS_PER_BLOCK = 4
) (
    input wire clk,
    input wire reset,
    input wire start,
    
    // Control Signals
    input reg decoded_mem_read_enable,
    input reg decoded_mem_write_enable,
    input reg decoded_ret,
    input reg decoded_sync,              // Barrier synchronization instruction
    input reg decoded_pc_mux,            // Whether this is a branch instruction

    // Memory Access State
    input reg [2:0] fetcher_state,
    input reg [1:0] lsu_state [THREADS_PER_BLOCK-1:0],

    // Current & Next PC
    output reg [7:0] current_pc,
    input reg [7:0] next_pc [THREADS_PER_BLOCK-1:0],

    // Execution State
    output reg [2:0] core_state,
    output reg done,
    
    // Thread Execution Mask (for divergence)
    output reg [THREADS_PER_BLOCK-1:0] thread_active,
    
    // Barrier Statistics
    output reg [31:0] barrier_count,
    
    // Divergence Statistics
    output reg [31:0] divergence_count   // Number of times threads diverged
);
    localparam IDLE = 3'b000, // Waiting to start
        FETCH = 3'b001,       // Fetch instructions from program memory
        DECODE = 3'b010,      // Decode instructions into control signals
        REQUEST = 3'b011,     // Request data from registers or memory
        WAIT = 3'b100,        // Wait for response from memory if necessary
        EXECUTE = 3'b101,     // Execute ALU and PC calculations
        UPDATE = 3'b110,      // Update registers, NZP, and PC
        DONE = 3'b111;        // Done executing this block
    
    // SIMT Divergence Stack
    localparam STACK_DEPTH = 4;
    reg [7:0] stack_reconverge_pc [STACK_DEPTH-1:0];
    reg [THREADS_PER_BLOCK-1:0] stack_active_mask [STACK_DEPTH-1:0];
    reg [THREADS_PER_BLOCK-1:0] stack_pending_mask [STACK_DEPTH-1:0];
    reg [1:0] stack_ptr;
    
    // Working variables (declared at module level for sv2v compatibility)
    reg any_lsu_waiting;
    reg [7:0] taken_pc;
    reg [7:0] not_taken_pc;
    reg [THREADS_PER_BLOCK-1:0] taken_mask;
    reg [THREADS_PER_BLOCK-1:0] not_taken_mask;
    reg [7:0] new_pc;
    reg [7:0] first_pc;
    reg found_first;
    reg is_uniform_result;
    integer k;
    
    // Initialize for simulation
    initial begin
        current_pc = 0;
        core_state = IDLE;
        done = 0;
        barrier_count = 0;
        divergence_count = 0;
        thread_active = {THREADS_PER_BLOCK{1'b1}};
        stack_ptr = 0;
        
        for (k = 0; k < STACK_DEPTH; k = k + 1) begin
            stack_reconverge_pc[k] = 0;
            stack_active_mask[k] = 0;
            stack_pending_mask[k] = 0;
        end
    end
    
    always @(posedge clk) begin 
        if (reset) begin
            current_pc <= 0;
            core_state <= IDLE;
            done <= 0;
            thread_active <= {THREADS_PER_BLOCK{1'b1}};
            stack_ptr <= 0;
        end else begin 
            case (core_state)
                IDLE: begin
                    if (start) begin 
                        core_state <= FETCH;
                        thread_active <= {THREADS_PER_BLOCK{1'b1}};
                    end
                end
                FETCH: begin 
                    if (fetcher_state == 3'b010) begin 
                        core_state <= DECODE;
                    end
                end
                DECODE: begin
                    core_state <= REQUEST;
                end
                REQUEST: begin 
                    core_state <= WAIT;
                end
                WAIT: begin
                    any_lsu_waiting = 1'b0;
                    for (k = 0; k < THREADS_PER_BLOCK; k = k + 1) begin
                        if (thread_active[k] && (lsu_state[k] == 2'b01 || lsu_state[k] == 2'b10)) begin
                            any_lsu_waiting = 1'b1;
                        end
                    end

                    if (!any_lsu_waiting) begin
                        core_state <= EXECUTE;
                    end
                end
                EXECUTE: begin
                    core_state <= UPDATE;
                end
                UPDATE: begin 
                    if (decoded_ret) begin 
                        // Check if there are pending threads on the stack
                        if (stack_ptr > 0 && stack_pending_mask[stack_ptr - 1] != 0) begin
                            // Pop stack and execute pending (divergent) threads
                            stack_ptr <= stack_ptr - 1;
                            thread_active <= stack_pending_mask[stack_ptr - 1];
                            stack_pending_mask[stack_ptr - 1] <= 0;
                            current_pc <= stack_reconverge_pc[stack_ptr - 1];
                            core_state <= FETCH;
                        end else begin
                            // All threads done
                            done <= 1;
                            core_state <= DONE;
                        end
                    end else begin 
                        // Handle SYNC instruction
                        if (decoded_sync) begin
                            barrier_count <= barrier_count + 1;
                        end
                        
                        // Check if all active threads have uniform next_pc
                        found_first = 0;
                        is_uniform_result = 1;
                        first_pc = 0;
                        taken_pc = 0;
                        
                        for (k = 0; k < THREADS_PER_BLOCK; k = k + 1) begin
                            if (thread_active[k]) begin
                                if (!found_first) begin
                                    first_pc = next_pc[k];
                                    taken_pc = next_pc[k];
                                    found_first = 1;
                                end else if (next_pc[k] != first_pc) begin
                                    is_uniform_result = 0;
                                end
                            end
                        end
                        
                        // Check for branch divergence
                        if (decoded_pc_mux && !is_uniform_result) begin
                            // DIVERGENCE DETECTED!
                            divergence_count <= divergence_count + 1;
                            
                            // Build taken and not-taken masks
                            taken_mask = 0;
                            not_taken_mask = 0;
                            not_taken_pc = 0;
                            
                            for (k = 0; k < THREADS_PER_BLOCK; k = k + 1) begin
                                if (thread_active[k]) begin
                                    if (next_pc[k] == taken_pc) begin
                                        taken_mask[k] = 1;
                                    end else begin
                                        not_taken_mask[k] = 1;
                                        not_taken_pc = next_pc[k];
                                    end
                                end
                            end
                            
                            // Push to divergence stack
                            if (stack_ptr < STACK_DEPTH) begin
                                stack_reconverge_pc[stack_ptr] <= not_taken_pc;
                                stack_pending_mask[stack_ptr] <= not_taken_mask;
                                stack_active_mask[stack_ptr] <= thread_active;
                                stack_ptr <= stack_ptr + 1;
                            end
                            
                            // Execute "taken" path first
                            thread_active <= taken_mask;
                            current_pc <= taken_pc;
                        end else begin
                            // No divergence - all active threads go to same PC
                            new_pc = taken_pc;  // Use the first active thread's PC
                            current_pc <= new_pc;
                            
                            // Check for reconvergence with pending threads
                            if (stack_ptr > 0 && stack_pending_mask[stack_ptr - 1] != 0) begin
                                if (stack_reconverge_pc[stack_ptr - 1] == new_pc) begin
                                    // Reconverge: merge active threads with pending
                                    thread_active <= thread_active | stack_pending_mask[stack_ptr - 1];
                                    stack_pending_mask[stack_ptr - 1] <= 0;
                                    stack_ptr <= stack_ptr - 1;
                                end
                            end
                        end

                        core_state <= FETCH;
                    end
                end
                DONE: begin 
                    // no-op
                end
            endcase
        end
    end
endmodule
