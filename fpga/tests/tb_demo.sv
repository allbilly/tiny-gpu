`timescale 1ns/1ps
module tb_demo;
    reg clk=0, clock_enabled=1;
    always #10 if (clock_enabled) clk=~clk;
    wire [2:0] leds, inverted_leds;
    ypcb_tiny_gpu_top dut (.SYS_CLK(clk), .led_3bits_tri_o(leds));
    ypcb_tiny_gpu_top #(.LED_ACTIVE_LOW(1)) inverted (
        .SYS_CLK(clk), .led_3bits_tri_o(inverted_leds));
    task run_demo;
        integer ticks;
        begin
            ticks=0;
            while (!leds[0] && !leds[1] && ticks<100000) begin
                @(negedge clk); ticks=ticks+1;
            end
            if (leds[0]!==1 || leds[1]!==0)
                $fatal(1,"board demo failed: error=%h cycles=%d",dut.demo.error_code,dut.demo.cycles);
            if (inverted_leds !== ~leds) $fatal(1,"LED polarity mismatch");
            $display("PASS board RTL matadd + matmul: %0d clocks; matmul GPU cycles=%0d",ticks,dut.demo.cycles);
        end
    endtask
    initial begin
        // Configuration-time initialization must release after four edges,
        // without a physical reset port or a pulse from this testbench.
        if (dut.reset !== 1'b1) $fatal(1,"configuration reset did not start asserted");
        repeat(3) begin
            @(negedge clk);
            if (dut.reset !== 1'b1 || leds[1:0] !== 2'b00)
                $fatal(1,"configuration reset released early");
        end
        @(negedge clk);
        if (dut.reset !== 1'b0 || leds[1:0] !== 2'b00)
            $fatal(1,"configuration reset did not release on fourth edge");
        run_demo();
        repeat(15) @(negedge clk);
        if (leds[1:0]!==2'b01) $fatal(1,"PASS not sticky");
        // Losing oscillator edges must not assert reset or erase PASS.
        clock_enabled=0;
        #200;
        if (leds[1:0]!==2'b01 || dut.reset!==1'b0)
            $fatal(1,"clock pause erased sticky status");
        clock_enabled=1;
        repeat(8) @(negedge clk);
        if (leds[1:0]!==2'b01) $fatal(1,"clock restart erased sticky status");
        $display("PASS configuration reset: four edges, no R28, both LED polarities, clock pause/restart");
        $finish;
    end
endmodule
