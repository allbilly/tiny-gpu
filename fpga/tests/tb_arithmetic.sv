`timescale 1ns/1ps
module tb_arithmetic;
    reg clk=0, reset=1, valid=0, write_enable=0;
    always #10 clk=~clk;
    reg [15:0] address=0;
    reg [31:0] wdata=0;
    wire ready, bus_error, busy, done, timed_out;
    wire [31:0] rdata, cycles;
    tiny_gpu_soc #(.WATCHDOG_CYCLES(5000)) dut (
        .clk(clk), .reset(reset), .host_valid(valid), .host_write(write_enable),
        .host_address(address), .host_wdata(wdata), .host_ready(ready),
        .host_error(bus_error), .host_rdata(rdata), .busy(busy), .done(done),
        .timeout(timed_out), .cycles(cycles));
    reg [7:0] operand_a [0:33], operand_b [0:33], results [0:135];
    reg [31:0] value;
    task transaction;
        input wr;
        input [15:0] addr;
        input [31:0] data;
        integer waits;
        begin
            @(negedge clk); valid=1; write_enable=wr; address=addr; wdata=data;
            @(negedge clk); waits=0;
            while (!ready && waits<10) begin @(negedge clk); waits=waits+1; end
            if (ready!==1 || bus_error!==0) $fatal(1,"arithmetic bus error at %h",addr);
            value=rdata;
            @(negedge clk); valid=0;
            @(negedge clk);
            if (ready!==0) $fatal(1,"arithmetic bus response did not release");
        end
    endtask
    task wr;
        input [15:0] addr;
        input [31:0] data;
        begin transaction(1,addr,data); end
    endtask
    task rd;
        input [15:0] addr;
        begin transaction(0,addr,0); end
    endtask
    integer n, operation, iteration, count_case, threads, polls, cases=0;
    reg [7:0] expected;
    initial begin
        $readmemh("operand_a.hex",operand_a);
        $readmemh("operand_b.hex",operand_b);
        $readmemh("results.hex",results);
        for (n=0; n<34; n=n+1)
            if ((^operand_a[n])===1'bx || (^operand_b[n])===1'bx || operand_b[n]===0)
                $fatal(1,"missing or invalid arithmetic operand fixture");
        for (n=0; n<136; n=n+1)
            if ((^results[n])===1'bx) $fatal(1,"missing arithmetic reference result");
        repeat(8) @(negedge clk); reset=0;
        repeat(8) @(negedge clk);
        for (operation=0; operation<4; operation=operation+1)
          for (iteration=0; iteration<2; iteration=iteration+1)
            for (count_case=0; count_case<5; count_case=count_case+1) begin
                threads=(count_case==0) ? 1 : (1<<count_case)+1;
                wr(12,1); repeat(5) @(negedge clk);
                // i=blockIdx*blockDim+threadIdx; load A[i], B[i]; store C[i].
                // Opcodes 3/4/5/6 are upstream ADD/SUB/MUL/DIV respectively.
                wr(16'h1000,16'h50de); wr(16'h1002,16'h300f);
                wr(16'h1004,16'h9100); wr(16'h1006,16'h9240);
                wr(16'h1008,16'h9380); wr(16'h100a,16'h3410);
                wr(16'h100c,16'h7440); wr(16'h100e,16'h3520);
                wr(16'h1010,16'h7550);
                wr(16'h1012,{4'b0,4'(3+operation),4'd6,4'd4,4'd5});
                wr(16'h1014,16'h3730); wr(16'h1016,16'h8076);
                wr(16'h1018,16'hf000);
                for (n=0; n<256; n=n+1) wr(16'h2000+16'(n),32'ha5);
                for (n=0; n<17; n=n+1) begin
                    wr(16'h2000+16'(n),{24'b0,operand_a[iteration*17+n]});
                    wr(16'h2040+16'(n),{24'b0,operand_b[iteration*17+n]});
                end
                wr(0,32'(threads)); wr(4,1);
                polls=0;
                while (busy && polls<1500) begin rd(8); polls=polls+1; end
                if (done!==1 || timed_out!==0) $fatal(1,"arithmetic kernel did not complete");
                // Check every byte, including inactive outputs and untouched inputs.
                for (n=0; n<256; n=n+1) begin
                    expected=8'ha5;
                    if (n<17) expected=operand_a[iteration*17+n];
                    if (n>=64 && n<81) expected=operand_b[iteration*17+n-64];
                    if (n>=128 && n<128+threads) expected=results[operation*34+iteration*17+n-128];
                    rd(16'h2000+16'(n));
                    if (value!=={24'b0,expected}) $fatal(1,
                        "op=%0d iteration=%0d threads=%0d byte=%0d expected=%0d got=%h",
                        3+operation,iteration,threads,n,expected,value);
                end
                cases=cases+1;
                $display("PASS arithmetic opcode=%0d iteration=%0d threads=%0d cycles=%0d",
                         3+operation,iteration,threads,cycles);
            end
        if (cases!=40) $fatal(1,"arithmetic case count mismatch");
        $display("PASS real GPU host arithmetic: 40 kernels, 280 thread results, all 256 bytes per kernel");
        $finish;
    end
    initial begin #100000000; $fatal(1,"arithmetic testbench deadline"); end
endmodule
