`timescale 1ns/1ps
module tb_soc;
    `include "workloads.vh"
    reg clk=0, reset=1;
    always #10 clk=~clk;
    reg valid=0, write_enable=0;
    reg [15:0] address=0;
    reg [31:0] wdata=0;
    wire ready, bus_error, busy, done, timed_out;
    wire [31:0] rdata, cycles;
    tiny_gpu_soc #(.WATCHDOG_CYCLES(5000)) dut (
        .clk(clk), .reset(reset), .host_valid(valid), .host_write(write_enable),
        .host_address(address), .host_wdata(wdata), .host_ready(ready),
        .host_error(bus_error), .host_rdata(rdata), .busy(busy), .done(done),
        .timeout(timed_out), .cycles(cycles));
    reg [31:0] value;
    task transaction;
        input wr;
        input [15:0] addr;
        input [31:0] data;
        input expected_error;
        integer waits;
        begin
            @(negedge clk); valid=1; write_enable=wr; address=addr; wdata=data;
            waits=0;
            @(negedge clk);
            while (!ready && waits<10) begin @(negedge clk); waits=waits+1; end
            if (ready!==1 || bus_error!==expected_error)
                $fatal(1,"bus addr %h ready=%b error=%b expected=%b",addr,ready,bus_error,expected_error);
            value=rdata;
            // Ready and read data must remain stable while the request is held.
            repeat(2) begin
                @(negedge clk);
                if (ready!==1 || rdata!==value || bus_error!==expected_error)
                    $fatal(1,"unstable host response");
            end
            valid=0;
            @(negedge clk);
            if (ready!==0) $fatal(1,"host ready did not release");
        end
    endtask
    task wr;
        input [15:0] addr;
        input [31:0] data;
        begin transaction(1,addr,data,0); end
    endtask
    task rd;
        input [15:0] addr;
        begin transaction(0,addr,0,0); end
    endtask
    task clear_gpu;
        begin wr(12,1); repeat(5) @(negedge clk); end
    endtask
    integer n, kernel, iteration, polls, expected;
    reg [7:0] input_data [0:15];
    initial begin
        repeat(8) @(negedge clk);
        reset=0;
        repeat(8) @(negedge clk);
        rd(20);
        if (value!==32'h54475001) $fatal(1,"wrong identity");
        transaction(1,0,0,1);
        transaction(1,0,256,1);
        transaction(1,4,1,1);
        transaction(0,16'h1001,0,1);
        transaction(0,16'h2100,0,1);
        transaction(1,8,1,1);
        for (kernel=0; kernel<2; kernel=kernel+1) begin
            for (iteration=0; iteration<3; iteration=iteration+1) begin
                clear_gpu();
                for (n=0; n<256; n=n+1) begin
                    wr(16'h1000+16'(n*2),{16'b0,demo_program(1'(kernel),8'(n))});
                    wr(16'h2000+16'(n),0);
                end
                for (n=0; n<16; n=n+1) begin
                    input_data[n]=8'(n*17 + iteration*113 + kernel*7);
                    wr(16'h2000+16'(n),{24'b0,input_data[n]});
                end
                rd(16'h1000);
                if (value!=={16'b0,demo_program(1'(kernel),0)}) $fatal(1,"program readback mismatch");
                wr(0,{24'b0,demo_threads(1'(kernel))});
                wr(4,1);
                transaction(1,16'h2000,99,1);
                transaction(1,16'h1000,0,1);
                transaction(1,4,1,1);
                polls=0;
                while (busy && polls<1500) begin rd(8); polls=polls+1; end
                if (done!==1 || timed_out!==0) $fatal(1,"kernel failed or timed out");
                for (n=0; n<demo_result_count(1'(kernel)); n=n+1) begin
                    if (kernel==0) expected=(int'(input_data[n])+int'(input_data[8+n]))&255;
                    else expected=(int'(input_data[(n/2)*2])*int'(input_data[4+n%2])+
                                   int'(input_data[(n/2)*2+1])*int'(input_data[6+n%2]))&255;
                    rd(16'h2000+{8'b0,demo_result_base(1'(kernel))}+16'(n));
                    if (value!==32'(expected)) $fatal(1,"kernel %0d iteration %0d result %0d expected=%0d got=%0d",
                        kernel,iteration,n,expected,value);
                end
                $display("PASS host RTL kernel=%0d varied-input iteration=%0d cycles=%0d",kernel,iteration,cycles);
            end
        end
        // 1, 3, 5, 9, and 17 threads: partial blocks and repeated dispatch.
        for (iteration=0; iteration<5; iteration=iteration+1) begin
            clear_gpu();
            wr(16'h1000,16'h50de); wr(16'h1002,16'h300f);
            wr(16'h1004,16'h9140); wr(16'h1006,16'h3110);
            wr(16'h1008,16'h925a); wr(16'h100a,16'h8012); wr(16'h100c,16'hf000);
            for (n=64; n<96; n=n+1) wr(16'h2000+16'(n),0);
            n=(iteration==0) ? 1 : (1<<iteration)+1;
            wr(0,32'(n)); wr(4,1);
            polls=0;
            while (busy && polls<1500) begin rd(8); polls=polls+1; end
            if (done!==1) $fatal(1,"partial-block execution failed: %0d threads",n);
            for (expected=0; expected<n; expected=expected+1) begin
                rd(16'h2040+16'(expected));
                if (value!==32'h5a) $fatal(1,"partial-block result missing");
            end
            rd(16'h2040+16'(n));
            if (value!==0) $fatal(1,"inactive thread wrote a result");
            $display("PASS partial blocks: %0d threads",n);
        end
        clear_gpu();
        wr(16'h1000,16'h9000); wr(16'h1002,16'h2000); wr(16'h1004,16'h1400);
        wr(0,1); wr(4,1);
        polls=0;
        while (busy && polls<1500) begin rd(8); polls=polls+1; end
        if (timed_out!==1 || done!==0 || cycles!==5000) $fatal(1,"watchdog failed");
        clear_gpu();
        if (timed_out!==0 || done!==0) $fatal(1,"watchdog reset failed");
        wr(16'h1000,16'hf000); wr(0,1); wr(4,1);
        while (busy) rd(8);
        if (done!==1) $fatal(1,"watchdog recovery failed");
        $display("PASS host protocol, 6 varied kernels, 5 partial blocks, watchdog and recovery");
        $finish;
    end
    initial begin #100000000; $fatal(1,"testbench deadline"); end
endmodule
