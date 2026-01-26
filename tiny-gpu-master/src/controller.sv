`default_nettype none
`timescale 1ns/1ns

// MEMORY CONTROLLER WITH COALESCING
// > Receives memory requests from all cores
// > Detects sequential address patterns and coalesces them for efficiency
// > Throttles requests based on limited external memory bandwidth
// > Waits for responses from external memory and distributes them back to cores
//
// Memory Coalescing:
// When multiple consumers request sequential addresses (e.g., addr 0,1,2,3),
// instead of making 4 separate memory transactions, we detect this pattern
// and can potentially serve them more efficiently.
//
// Current implementation:
// - Detects when pending requests are to sequential addresses
// - Tracks statistics on how many requests could be coalesced
// - Prioritizes serving sequential requests together when possible
module controller #(
    parameter ADDR_BITS = 8,
    parameter DATA_BITS = 16,
    parameter NUM_CONSUMERS = 4, // The number of consumers accessing memory through this controller
    parameter NUM_CHANNELS = 1,  // The number of concurrent channels available to send requests to global memory
    parameter WRITE_ENABLE = 1   // Whether this memory controller can write to memory (program memory is read-only)
) (
    input wire clk,
    input wire reset,

    // Consumer Interface (Fetchers / LSUs)
    input reg [NUM_CONSUMERS-1:0] consumer_read_valid,
    input reg [ADDR_BITS-1:0] consumer_read_address [NUM_CONSUMERS-1:0],
    output reg [NUM_CONSUMERS-1:0] consumer_read_ready,
    output reg [DATA_BITS-1:0] consumer_read_data [NUM_CONSUMERS-1:0],
    input reg [NUM_CONSUMERS-1:0] consumer_write_valid,
    input reg [ADDR_BITS-1:0] consumer_write_address [NUM_CONSUMERS-1:0],
    input reg [DATA_BITS-1:0] consumer_write_data [NUM_CONSUMERS-1:0],
    output reg [NUM_CONSUMERS-1:0] consumer_write_ready,

    // Memory Interface (Data / Program)
    output reg [NUM_CHANNELS-1:0] mem_read_valid,
    output reg [ADDR_BITS-1:0] mem_read_address [NUM_CHANNELS-1:0],
    input reg [NUM_CHANNELS-1:0] mem_read_ready,
    input reg [DATA_BITS-1:0] mem_read_data [NUM_CHANNELS-1:0],
    output reg [NUM_CHANNELS-1:0] mem_write_valid,
    output reg [ADDR_BITS-1:0] mem_write_address [NUM_CHANNELS-1:0],
    output reg [DATA_BITS-1:0] mem_write_data [NUM_CHANNELS-1:0],
    input reg [NUM_CHANNELS-1:0] mem_write_ready,
    
    // Coalescing Statistics
    output reg [31:0] total_requests,       // Total memory requests processed
    output reg [31:0] coalesced_requests    // Requests that were part of a coalescable group
);
    localparam IDLE = 3'b000, 
        READ_WAITING = 3'b010, 
        WRITE_WAITING = 3'b011,
        READ_RELAYING = 3'b100,
        WRITE_RELAYING = 3'b101;

    // Keep track of state for each channel and which jobs each channel is handling
    reg [2:0] controller_state [NUM_CHANNELS-1:0];
    reg [$clog2(NUM_CONSUMERS)-1:0] current_consumer [NUM_CHANNELS-1:0]; // Which consumer is each channel currently serving
    reg [NUM_CONSUMERS-1:0] channel_serving_consumer; // Which channels are being served? Prevents many workers from picking up the same request.
    
    // Coalescing detection
    // Track the base address of current sequential access pattern
    reg [ADDR_BITS-1:0] last_read_address;
    reg last_read_valid;
    
    // Function to check if address is sequential to last address
    function automatic is_sequential;
        input [ADDR_BITS-1:0] addr;
        input [ADDR_BITS-1:0] last_addr;
        input valid;
        begin
            is_sequential = valid && (addr == last_addr + 1);
        end
    endfunction
    
    // Initialize for simulation
    initial begin
        total_requests = 0;
        coalesced_requests = 0;
        last_read_address = 0;
        last_read_valid = 0;
        
        for (int i = 0; i < NUM_CHANNELS; i = i + 1) begin
            controller_state[i] = IDLE;
            current_consumer[i] = 0;
        end
        channel_serving_consumer = 0;
    end

    always @(posedge clk) begin
        if (reset) begin 
            mem_read_valid <= 0;
            mem_read_address <= '{default: 0};

            mem_write_valid <= 0;
            mem_write_address <= '{default: 0};
            mem_write_data <= '{default: 0};

            consumer_read_ready <= 0;
            consumer_read_data <= '{default: 0};
            consumer_write_ready <= 0;

            current_consumer <= '{default: 0};
            controller_state <= '{default: IDLE};

            channel_serving_consumer = 0;
            
            // Coalescing state
            last_read_address <= 0;
            last_read_valid <= 0;
            // Note: Statistics persist across resets for cumulative tracking
        end else begin 
            // For each channel, we handle processing concurrently
            for (int i = 0; i < NUM_CHANNELS; i = i + 1) begin 
                case (controller_state[i])
                    IDLE: begin
                        // While this channel is idle, cycle through consumers looking for one with a pending request
                        // Priority: Try to find sequential addresses first (coalescing opportunity)
                        
                        reg found_request;
                        reg found_sequential;
                        int selected_consumer;
                        
                        found_request = 0;
                        found_sequential = 0;
                        selected_consumer = 0;
                        
                        // First pass: Look for sequential read requests (coalescing opportunity)
                        for (int j = 0; j < NUM_CONSUMERS; j = j + 1) begin 
                            if (consumer_read_valid[j] && !channel_serving_consumer[j]) begin
                                if (!found_request) begin
                                    // Remember first available request
                                    found_request = 1;
                                    selected_consumer = j;
                                end
                                
                                // Check if this is sequential to last read (coalescable)
                                if (is_sequential(consumer_read_address[j], last_read_address, last_read_valid)) begin
                                    found_sequential = 1;
                                    selected_consumer = j;  // Prefer sequential request
                                    break;  // Found best candidate
                                end
                            end
                        end
                        
                        // If no read request found, check for write requests
                        if (!found_request) begin
                            for (int j = 0; j < NUM_CONSUMERS; j = j + 1) begin 
                                if (consumer_write_valid[j] && !channel_serving_consumer[j]) begin 
                                    found_request = 1;
                                    selected_consumer = j;
                                    break;
                                end
                            end
                        end
                        
                        // Process the selected request
                        if (found_request) begin
                            if (consumer_read_valid[selected_consumer] && !channel_serving_consumer[selected_consumer]) begin
                                channel_serving_consumer[selected_consumer] = 1;
                                current_consumer[i] <= selected_consumer;

                                mem_read_valid[i] <= 1;
                                mem_read_address[i] <= consumer_read_address[selected_consumer];
                                controller_state[i] <= READ_WAITING;
                                
                                // Update statistics
                                total_requests <= total_requests + 1;
                                if (found_sequential) begin
                                    coalesced_requests <= coalesced_requests + 1;
                                end
                                
                                // Update coalescing tracking
                                last_read_address <= consumer_read_address[selected_consumer];
                                last_read_valid <= 1;
                                
                            end else if (consumer_write_valid[selected_consumer] && !channel_serving_consumer[selected_consumer]) begin 
                                channel_serving_consumer[selected_consumer] = 1;
                                current_consumer[i] <= selected_consumer;

                                mem_write_valid[i] <= 1;
                                mem_write_address[i] <= consumer_write_address[selected_consumer];
                                mem_write_data[i] <= consumer_write_data[selected_consumer];
                                controller_state[i] <= WRITE_WAITING;
                                
                                // Update statistics
                                total_requests <= total_requests + 1;
                                
                                // Reset coalescing tracking on write
                                last_read_valid <= 0;
                            end
                        end
                    end
                    READ_WAITING: begin
                        // Wait for response from memory for pending read request
                        if (mem_read_ready[i]) begin 
                            mem_read_valid[i] <= 0;
                            consumer_read_ready[current_consumer[i]] <= 1;
                            consumer_read_data[current_consumer[i]] <= mem_read_data[i];
                            controller_state[i] <= READ_RELAYING;
                        end
                    end
                    WRITE_WAITING: begin 
                        // Wait for response from memory for pending write request
                        if (mem_write_ready[i]) begin 
                            mem_write_valid[i] <= 0;
                            consumer_write_ready[current_consumer[i]] <= 1;
                            controller_state[i] <= WRITE_RELAYING;
                        end
                    end
                    // Wait until consumer acknowledges it received response, then reset
                    READ_RELAYING: begin
                        if (!consumer_read_valid[current_consumer[i]]) begin 
                            channel_serving_consumer[current_consumer[i]] = 0;
                            consumer_read_ready[current_consumer[i]] <= 0;
                            controller_state[i] <= IDLE;
                        end
                    end
                    WRITE_RELAYING: begin 
                        if (!consumer_write_valid[current_consumer[i]]) begin 
                            channel_serving_consumer[current_consumer[i]] = 0;
                            consumer_write_ready[current_consumer[i]] <= 0;
                            controller_state[i] <= IDLE;
                        end
                    end
                endcase
            end
        end
    end
endmodule
