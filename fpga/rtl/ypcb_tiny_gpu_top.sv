`default_nettype none
`timescale 1ns/1ps
module ypcb_tiny_gpu_top #(
    parameter bit LED_ACTIVE_LOW = 1'b0
) (
    input wire SYS_CLK,
    output wire [2:0] led_3bits_tri_o
);
    // FPGA configuration initializes this pipeline. Four oscillator edges
    // reset the demo before it starts. The openTPU board top leaves R28 unused;
    // this autonomous design uses the oscillator directly, without an MMCM.
    // Keep every stage as an INIT-backed flip-flop; SRLs do not reset on GSR.
    (* keep = "true", SHREG_EXTRACT = "NO" *) reg [3:0] reset_pipe = 0;
    reg [25:0] heartbeat = 0;
    wire reset = !reset_pipe[3];
    wire pass, fail;
    (* MARK_DEBUG="TRUE" *) wire [7:0] error_code;
    (* MARK_DEBUG="TRUE" *) wire [31:0] cycles;
    always @(posedge SYS_CLK) begin
        reset_pipe<={reset_pipe[2:0],1'b1};
    end
    always @(posedge SYS_CLK) begin
        if (reset) heartbeat<=0; else heartbeat<=heartbeat+1'b1;
    end
    tiny_gpu_demo demo (.clk(SYS_CLK), .reset(reset), .pass(pass), .fail(fail),
                        .error_code(error_code), .cycles(cycles));
    // P30: pass, M30: fail, N30: heartbeat. Polarity is configurable.
    assign led_3bits_tri_o = {heartbeat[25],fail,pass} ^ {3{LED_ACTIVE_LOW}};
endmodule
