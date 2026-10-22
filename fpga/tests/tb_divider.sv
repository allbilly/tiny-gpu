`timescale 1ns/1ns
module tb_divider;
    reg clk=0, reset=1, enable=1;
    reg [2:0] core_state=0;
    reg [1:0] operation=3;
    reg compare_output=0;
    reg [7:0] rs=0, rt=1;
    wire [7:0] pipelined_out, original_out;
    integer checked=0;
    reg [7:0] expected, held;

    alu #(.PIPELINED_DIV(1)) pipelined (
        .clk(clk), .reset(reset), .enable(enable), .core_state(core_state),
        .decoded_alu_arithmetic_mux(operation), .decoded_alu_output_mux(compare_output),
        .rs(rs), .rt(rt), .alu_out(pipelined_out)
    );
    alu original (
        .clk(clk), .reset(reset), .enable(enable), .core_state(core_state),
        .decoded_alu_arithmetic_mux(operation), .decoded_alu_output_mux(compare_output),
        .rs(rs), .rt(rt), .alu_out(original_out)
    );

    task automatic tick;
        begin #5; clk=1; #1; clk=0; #4; end
    endtask

    initial begin
        tick();
        if (pipelined_out !== 0 || original_out !== 0) $fatal(1,"reset failed");
        reset=0;
        // Exhaust every defined unsigned 8-bit DIV pair, with both a single
        // WAIT and stalled WAIT sequences. Compare to integer arithmetic and
        // to the original ALU at the same EXECUTE edge.
        for (integer numerator=0; numerator<256; numerator++) begin
            for (integer denominator=1; denominator<256; denominator++) begin
                rs=8'(numerator); rt=8'(denominator);
                expected=8'(numerator/denominator); held=pipelined_out;
                core_state=3; tick();
                core_state=4;
                repeat (1 + ((numerator + denominator) % 3)) tick();
                if (pipelined_out !== held) $fatal(1,"WAIT changed architectural result");
                core_state=5; tick();
                if (pipelined_out !== expected || original_out !== expected)
                    $fatal(1,"DIV %0d/%0d expected=%0d pipeline=%0d original=%0d",
                           numerator,denominator,expected,pipelined_out,original_out);
                core_state=6; tick();
                checked++;
            end
        end
        if (checked != 65280) $fatal(1,"incomplete DIV coverage");

        // The second half consumes the captured operands, not live changes.
        rs=255; rt=3; core_state=4; tick();
        rs=1; rt=255; core_state=5; tick();
        if (pipelined_out !== 85) $fatal(1,"DIV operands were not captured");

        // Inactive lanes must hold their result through both stages.
        held=pipelined_out; enable=0;
        rs=255; rt=1; core_state=4; tick(); core_state=5; tick();
        if (pipelined_out !== held) $fatal(1,"disabled lane changed result");
        enable=1;

        // Reset between stages must permit a clean subsequent instruction.
        rs=253; rt=7; core_state=4; tick();
        reset=1; tick();
        if (pipelined_out !== 0) $fatal(1,"reset did not clear result");
        reset=0; rs=201; rt=9; core_state=4; tick(); core_state=5; tick();
        if (pipelined_out !== 22) $fatal(1,"reset recovery failed");

        // Preserve the four-state undefined zero-divisor result and reject X.
        for (integer numerator=0; numerator<256; numerator++) begin
            rs=8'(numerator); rt=0; core_state=4; tick(); core_state=5; tick();
            if (pipelined_out !== 8'hxx || original_out !== 8'hxx)
                $fatal(1,"zero DIV became a defined result");
        end
        rs=8'hxx; rt=3; core_state=4; tick(); core_state=5; tick();
        if (pipelined_out !== 8'hxx) $fatal(1,"unknown numerator became known");
        rs=255; rt=8'hxx; core_state=4; tick(); core_state=5; tick();
        if (pipelined_out !== 8'hxx) $fatal(1,"unknown divisor became known");

        // Other arithmetic operations retain their original EXECUTE edge.
        for (integer op=0; op<3; op++) begin
            operation=2'(op);
            for (integer numerator=0; numerator<256; numerator++) begin
                rs=8'(numerator); rt=8'(255-numerator);
                case (op)
                    0: expected=rs+rt;
                    1: expected=rs-rt;
                    2: expected=rs*rt;
                endcase
                core_state=4; tick(); core_state=5; tick();
                if (pipelined_out !== expected || original_out !== expected)
                    $fatal(1,"non-DIV arithmetic changed");
            end
        end
        $display("PASS divider: 65280 nonzero pairs, zero/X, stalls, inactive lane, reset and other arithmetic");
        $finish;
    end
endmodule
