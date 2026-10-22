`timescale 1ns/1ps
// Functional primitive models only; this does not include routed/SDF delays.
module tb_mapped;
    reg clk=0;
    always #10 clk=~clk;
    wire [2:0] leds;
    ypcb_tiny_gpu_top dut (.SYS_CLK(clk), .led_3bits_tri_o(leds));
    integer ticks, iteration, stage;
    initial begin
        // Use the real UNISIM global configuration reset, not an invented
        // external pin. GSR restores primitive INIT values on each reload.
        // The first assertion comes from Xilinx glbl's startup sequence.
        wait (glbl.GSR === 1'b0);
        for (iteration=0; iteration<2; iteration=iteration+1) begin
            if (iteration != 0) begin
                @(negedge clk);
                force glbl.GSR = 1'b1;
                repeat(8) @(negedge clk);
                if (dut.reset_pipe!==4'b0000) $fatal(1,"configuration GSR did not restore all reset INIT values");
                release glbl.GSR;
                #1; // Let the continuous GSR driver settle after release.
                if (glbl.GSR!==1'b0) $fatal(1,"configuration GSR did not release");
            end
            for (stage=0; stage<4; stage=stage+1) begin
                @(posedge clk);
                @(negedge clk);
                if (dut.reset_pipe !== ((1 << (stage+1))-1))
                    $fatal(1,"mapped startup chain failed: iteration=%0d stage=%0d pipeline=%b",iteration,stage,dut.reset_pipe);
                // Status has no specified INIT: the synchronous demo reset
                // clears it on these four edges after configuration.
                if (leds[1:0]!==2'b00)
                    $fatal(1,"mapped startup reset did not clear LED status: iteration=%0d stage=%0d LEDs=%b",iteration,stage,leds);
            end
            ticks=0;
            while (leds[0]!==1'b1 && leds[1]!==1'b1 && ticks<100000) begin
                @(negedge clk); ticks=ticks+1;
            end
            if (leds[1:0]!==2'b01) $fatal(1,"mapped GPU result failure: LEDs=%b ticks=%0d",leds,ticks);
            repeat(20) @(negedge clk);
            if (leds[1:0]!==2'b01) $fatal(1,"mapped status did not remain sticky");
            $display("PASS mapped XC7 primitives: both kernels, configuration iteration=%0d clocks=%0d",iteration,ticks);
        end
        $display("PASS mapped configuration reset: four INIT flip-flops, two GSR releases");
        $finish;
    end
endmodule
