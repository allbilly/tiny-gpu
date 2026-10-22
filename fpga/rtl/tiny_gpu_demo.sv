`default_nettype none
`timescale 1ns/1ps
// Load and verify BOTH upstream kernels on the real GPU. Restart with reset.
module tiny_gpu_demo (
    input wire clk, reset,
    output reg pass, fail,
    output reg [7:0] error_code,
    output wire [31:0] cycles
);
    `include "workloads.vh"
    localparam [3:0] CLEAR=0, LOAD_PROGRAM=1, LOAD_DATA=2, THREADS=3,
                     START=4, WAIT_DONE=5, CHECK=6, HALT=7;
    reg [3:0] state;
    reg kernel;
    reg [7:0] index;
    reg gap;
    reg [31:0] wait_cycles;
    reg [15:0] address;
    reg [31:0] wdata;
    reg write_enable;
    wire ready, bus_error;
    wire [31:0] rdata;
    wire busy, done, timeout;
    tiny_gpu_soc soc (
        .clk(clk), .reset(reset), .host_valid(!gap && state!=HALT),
        .host_write(write_enable), .host_address(address), .host_wdata(wdata),
        .host_ready(ready), .host_error(bus_error), .host_rdata(rdata),
        .busy(busy), .done(done), .timeout(timeout), .cycles(cycles)
    );
    always @* begin
        address=0; wdata=0; write_enable=1;
        case (state)
            CLEAR: begin address=16'h000c; wdata=1; end
            LOAD_PROGRAM: begin address=16'h1000+{7'b0,index,1'b0}; wdata={16'b0,demo_program(kernel,index)}; end
            LOAD_DATA: begin address=16'h2000+{8'b0,index}; wdata={24'b0,demo_data(kernel,index)}; end
            THREADS: begin address=0; wdata={24'b0,demo_threads(kernel)}; end
            START: begin address=4; wdata=1; end
            WAIT_DONE: begin address=8; write_enable=0; end
            CHECK: begin address=16'h2000+{8'b0,demo_result_base(kernel)}+{8'b0,index}; write_enable=0; end
            default: begin write_enable=0; end
        endcase
    end
    always @(posedge clk) begin
        if (reset) begin
            state<=CLEAR; kernel<=0; index<=0; gap<=0;
            pass<=0; fail<=0; error_code<=0; wait_cycles<=0;
        end else if (state!=HALT) begin
            wait_cycles<=wait_cycles+1'b1;
            if (wait_cycles==32'd2000000) begin
                fail<=1; error_code<=8'he0; state<=HALT;
            end else if (gap) gap<=0;
            else if (ready) begin
                gap<=1;
                if (bus_error) begin fail<=1; error_code<=8'hb0|{4'b0,state}; state<=HALT; end
                else case (state)
                    CLEAR: begin state<=LOAD_PROGRAM; index<=0; end
                    LOAD_PROGRAM: begin
                        index<=index+1'b1;
                        if (index==255) begin state<=LOAD_DATA; index<=0; end
                    end
                    LOAD_DATA: begin
                        index<=index+1'b1;
                        if (index==255) begin state<=THREADS; index<=0; end
                    end
                    THREADS: state<=START;
                    START: state<=WAIT_DONE;
                    WAIT_DONE: begin
                        if (rdata[2]) begin fail<=1; error_code<=8'he1; state<=HALT; end
                        else if (rdata[0]) begin state<=CHECK; index<=0; end
                    end
                    CHECK: begin
                        // Case inequality also fails on X readback in four-state simulation.
                        if (rdata !== {24'b0,demo_expected(kernel,index)}) begin
                            fail<=1; error_code<=8'h10+{3'b0,kernel,4'b0}+index; state<=HALT;
                        end else if (index==demo_result_count(kernel)-1'b1) begin
                            if (kernel) begin pass<=1; state<=HALT; end
                            else begin kernel<=1; state<=CLEAR; end
                        end else index<=index+1'b1;
                    end
                    default: begin fail<=1; error_code<=8'hff; state<=HALT; end
                endcase
            end
        end
    end
endmodule
