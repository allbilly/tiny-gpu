`default_nettype none
`timescale 1ns/1ps
// The upstream GPU with single-port synchronous on-chip memories and a host bus.
// Requests/ready are held until valid drops. The four GPU data channels are
// arbitrated onto one RAM port; no instruction is executed by the host adapter.
module tiny_gpu_soc #(
    parameter integer WATCHDOG_CYCLES = 1000000
) (
    input wire clk, reset,
    input wire host_valid, host_write,
    input wire [15:0] host_address,
    input wire [31:0] host_wdata,
    output reg host_ready, host_error,
    output reg [31:0] host_rdata,
    output wire busy, done, timeout,
    output reg [31:0] cycles
);
    localparam [1:0] IDLE=0, ARM=1, RUN=2, FINISHED=3;
    reg [1:0] state;
    reg [2:0] reset_count;
    reg [7:0] threads;
    reg timed_out;
    wire gpu_done;
    wire gpu_reset = reset || reset_count != 0;
    assign busy = state == ARM || state == RUN;
    assign done = state == FINISHED && !timed_out;
    assign timeout = timed_out;

    wire [0:0] pr_valid;
    wire [7:0] pr_address [0:0];
    reg [0:0] pr_ready;
    wire [15:0] pr_data [0:0];
    wire [3:0] dr_valid, dw_valid;
    wire [7:0] dr_address [3:0], dw_address [3:0], dw_data [3:0];
    reg [3:0] dr_ready, dw_ready;
    reg [7:0] dr_data [3:0];
    gpu #(.NUM_CORES(2), .THREADS_PER_BLOCK(4), .DATA_MEM_NUM_CHANNELS(4),
          .PIPELINED_DIV(1)) gpu_instance (
        .clk(clk), .reset(gpu_reset), .start(state == RUN), .done(gpu_done),
        .device_control_write_enable(state == ARM), .device_control_data(threads),
        .program_mem_read_valid(pr_valid), .program_mem_read_address(pr_address),
        .program_mem_read_ready(pr_ready), .program_mem_read_data(pr_data),
        .data_mem_read_valid(dr_valid), .data_mem_read_address(dr_address),
        .data_mem_read_ready(dr_ready), .data_mem_read_data(dr_data),
        .data_mem_write_valid(dw_valid), .data_mem_write_address(dw_address),
        .data_mem_write_data(dw_data), .data_mem_write_ready(dw_ready)
    );

    (* ram_style="block" *) reg [15:0] program_memory [0:255];
    (* ram_style="block" *) reg [7:0] data_memory [0:255];
    reg [15:0] program_q;
    reg [7:0] data_q;
    assign pr_data[0] = program_q;
    reg host_seen, host_pending, host_pending_program;
    wire request = !reset && host_valid && !host_seen;
    wire program_window = host_address >= 16'h1000 && host_address < 16'h1200 && !host_address[0];
    wire data_window = host_address >= 16'h2000 && host_address < 16'h2100;
    wire host_memory = request && !busy && (program_window || data_window);
    wire host_prog_we = host_memory && program_window && host_write;
    wire host_data_we = host_memory && data_window && host_write;

    reg pr_served, pr_pending;
    wire program_re = (busy && !gpu_reset && pr_valid[0] && !pr_served) ||
                      (host_memory && program_window && !host_write);
    wire [7:0] program_address = busy ? pr_address[0] : host_address[8:1];
    // Single read port and write port with synchronous read (BRAM inference).
    always @(posedge clk) begin
        if (host_prog_we) program_memory[host_address[8:1]] <= host_wdata[15:0];
        if (program_re) program_q <= program_memory[program_address];
    end

    reg [3:0] dr_served, dw_served;
    reg data_pending;
    reg [1:0] data_pending_channel;
    reg grant_valid, grant_write;
    reg [1:0] grant_channel;
    reg [7:0] grant_address, grant_data;
    integer i;
    always @* begin
        grant_valid=0; grant_write=0; grant_channel=0; grant_address=0; grant_data=0;
        for (integer channel=0; channel<4; channel=channel+1) begin
            if (busy && !gpu_reset && !data_pending && !grant_valid) begin
                if (dr_valid[channel] && !dr_served[channel]) begin
                    grant_valid=1; grant_channel=2'(channel); grant_address=dr_address[channel];
                end else if (dw_valid[channel] && !dw_served[channel]) begin
                    grant_valid=1; grant_write=1; grant_channel=2'(channel);
                    grant_address=dw_address[channel]; grant_data=dw_data[channel];
                end
            end
        end
    end
    wire data_re = (grant_valid && !grant_write) || (host_memory && data_window && !host_write);
    wire data_we = (grant_valid && grant_write) || host_data_we;
    wire [7:0] data_address = busy ? grant_address : host_address[7:0];
    wire [7:0] data_wdata = busy ? grant_data : host_wdata[7:0];
    always @(posedge clk) begin
        if (data_we) data_memory[data_address] <= data_wdata;
        if (data_re) data_q <= data_memory[data_address];
    end

    always @(posedge clk) begin
        if (gpu_reset) begin
            pr_ready<=0; pr_served<=0; pr_pending<=0;
            dr_ready<=0; dw_ready<=0; dr_served<=0; dw_served<=0; data_pending<=0;
            data_pending_channel<=0;
            for (i=0; i<4; i=i+1) dr_data[i]<=0;
        end else begin
            if (!pr_valid[0]) begin pr_ready<=0; pr_served<=0; end
            pr_pending <= busy && pr_valid[0] && !pr_served;
            if (busy && pr_valid[0] && !pr_served) pr_served<=1;
            if (pr_pending) pr_ready<=1;
            dr_ready <= dr_ready & dr_valid;
            dw_ready <= dw_ready & dw_valid;
            dr_served <= dr_served & dr_valid;
            dw_served <= dw_served & dw_valid;
            data_pending<=grant_valid && !grant_write;
            if (grant_valid) begin
                if (grant_write) begin
                    dw_served[grant_channel]<=1; dw_ready[grant_channel]<=1;
                end else begin
                    dr_served[grant_channel]<=1; data_pending_channel<=grant_channel;
                end
            end
            if (data_pending) begin
                dr_ready[data_pending_channel]<=1; dr_data[data_pending_channel]<=data_q;
            end
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            state<=IDLE; reset_count<=4; threads<=0; cycles<=0; timed_out<=0;
            host_seen<=0; host_ready<=0; host_error<=0; host_rdata<=0;
            host_pending<=0; host_pending_program<=0;
        end else begin
            if (reset_count!=0) reset_count<=reset_count-1'b1;
            if (state==ARM) state<=RUN;
            if (state==RUN) begin
                cycles<=cycles+1'b1;
                if (gpu_done) state<=FINISHED;
                else if (cycles >= WATCHDOG_CYCLES-1) begin
                    state<=FINISHED; timed_out<=1; reset_count<=4;
                end
            end
            if (!host_valid) begin host_seen<=0; host_ready<=0; host_error<=0; end
            if (host_pending) begin
                host_rdata<=host_pending_program ? {16'b0,program_q} : {24'b0,data_q};
                host_ready<=1; host_pending<=0;
            end
            if (request) begin
                host_seen<=1; host_rdata<=0; host_error<=0; host_ready<=1;
                case (host_address)
                    16'h0000: begin
                        if (host_write) begin
                            if (busy || host_wdata==0 || host_wdata>255) host_error<=1;
                            else threads<=host_wdata[7:0];
                        end else host_rdata<={24'b0,threads};
                    end
                    16'h0004: begin
                        if (!host_write || host_wdata!=1 || busy || reset_count!=0 || threads==0 || state!=IDLE)
                            host_error<=1;
                        else begin state<=ARM; cycles<=0; timed_out<=0; end
                    end
                    16'h0008: begin
                        if (host_write) host_error<=1;
                        else host_rdata<={29'b0,timed_out,busy,done};
                    end
                    16'h000c: begin
                        if (!host_write || host_wdata!=1) host_error<=1;
                        else begin state<=IDLE; reset_count<=4; cycles<=0; timed_out<=0; end
                    end
                    16'h0010: begin
                        if (host_write) host_error<=1; else host_rdata<=cycles;
                    end
                    16'h0014: begin
                        if (host_write) host_error<=1; else host_rdata<=32'h54475001;
                    end
                    default: begin
                        if (!host_memory) host_error<=1;
                        else if (!host_write) begin
                            host_ready<=0; host_pending<=1; host_pending_program<=program_window;
                        end
                    end
                endcase
            end
        end
    end
endmodule
