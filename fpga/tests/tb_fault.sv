`timescale 1ns/1ps
module tb_fault;
    reg clk=0, reset=1;
    always #10 clk=~clk;
    wire pass, fail;
    wire [7:0] error_code;
    wire [31:0] cycles;
    tiny_gpu_demo dut (.clk(clk), .reset(reset), .pass(pass), .fail(fail), .error_code(error_code), .cycles(cycles));
    integer ticks, attempt;
    initial begin
        for (attempt=0; attempt<2; attempt=attempt+1) begin
            reset=1; repeat(8) @(negedge clk); reset=0;
            ticks=0;
            while (!dut.soc.done && ticks<10000) begin @(negedge clk); ticks=ticks+1; end
            if (ticks==10000) $fatal(1,"no GPU completion before fault injection");
            // Deposit a bad value before the checker reads the first output.
            dut.soc.data_memory[16] = attempt ? 8'hxx : 8'hff;
            ticks=0;
            while (!fail && ticks<50) begin @(negedge clk); ticks=ticks+1; end
            if (fail!==1 || pass!==0 || error_code!==8'h10) $fatal(1,"bad/X result escaped checker");
            repeat(50) @(negedge clk);
            if (fail!==1 || pass!==0) $fatal(1,"failure was not sticky");
            $display("PASS corruption rejection: attempt=%0d (second is four-state X)",attempt);
        end
        reset=1; repeat(8) @(negedge clk); reset=0;
        ticks=0;
        while (!pass && !fail && ticks<10000) begin @(negedge clk); ticks=ticks+1; end
        if (pass!==1 || fail!==0) $fatal(1,"fault reset recovery failed");
        $display("PASS fault reset recovery");
        $finish;
    end
endmodule
