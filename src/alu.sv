`default_nettype none
`timescale 1ns/1ns

// ARITHMETIC-LOGIC UNIT
// > Executes computations on register values
// > In this minimal implementation, the ALU supports the 4 basic arithmetic operations
// > Each thread in each core has it's own ALU
// > ADD, SUB, MUL, DIV instructions are all executed here
module alu #(
    parameter PIPELINED_DIV = 0
) (
    input wire clk,
    input wire reset,
    input wire enable, // If current block has less threads then block size, some ALUs will be inactive

    input reg [2:0] core_state,

    input reg [1:0] decoded_alu_arithmetic_mux,
    input reg decoded_alu_output_mux,

    input reg [7:0] rs,
    input reg [7:0] rt,
    output wire [7:0] alu_out
);
    localparam ADD = 2'b00,
        SUB = 2'b01,
        MUL = 2'b10,
        DIV = 2'b11;

    reg [7:0] alu_out_reg;
    assign alu_out = alu_out_reg;

    wire [7:0] divided;
    generate
        if (PIPELINED_DIV) begin : pipelined_div
            // Four quotient bits per stage. REQUEST registers rs/rt, WAIT
            // captures the upper half, and EXECUTE completes the lower half.
            // Every path through the scheduler visits WAIT before EXECUTE.
            function automatic [11:0] divide_half(
                input [7:0] remainder_in,
                input [3:0] dividend,
                input [7:0] divisor
            );
                reg [7:0] remainder_value;
                reg [3:0] quotient;
                reg [8:0] shifted;
                reg [9:0] difference;
                begin
                    remainder_value = remainder_in;
                    quotient = 0;
                    for (int bit_index = 3; bit_index >= 0; bit_index--) begin
                        shifted = {remainder_value, dividend[bit_index]};
                        difference = {1'b0, shifted} - {2'b0, divisor};
                        quotient[bit_index] = ~difference[9];
                        remainder_value = difference[9] ? shifted[7:0] : difference[7:0];
                    end
                    divide_half = {remainder_value, quotient};
                end
            endfunction

            reg [11:0] upper;
            reg [3:0] lower_dividend;
            reg [7:0] divisor_reg;
            wire [11:0] lower = divide_half(upper[11:4], lower_dividend, divisor_reg);
            // Preserve the original four-state undefined result for division
            // by zero instead of inventing an architectural zero-divisor value.
            assign divided = divisor_reg == 0 ? 8'bx : {upper[3:0], lower[3:0]};

            always @(posedge clk) begin
                if (reset) begin
                    upper <= 0;
                    lower_dividend <= 0;
                    divisor_reg <= 0;
                end else if (enable && core_state == 3'b100) begin
                    upper <= divide_half(0, rs[7:4], rt);
                    lower_dividend <= rs[3:0];
                    divisor_reg <= rt;
                end
            end
        end else begin : combinational_div
            assign divided = rs / rt;
        end
    endgenerate

    always @(posedge clk) begin 
        if (reset) begin 
            alu_out_reg <= 8'b0;
        end else if (enable) begin
            // Calculate alu_out when core_state = EXECUTE
            if (core_state == 3'b101) begin 
                if (decoded_alu_output_mux == 1) begin 
                    // Set values to compare with NZP register in alu_out[2:0]
                    alu_out_reg <= {5'b0, (rs - rt > 0), (rs - rt == 0), (rs - rt < 0)};
                end else begin 
                    // Execute the specified arithmetic instruction
                    case (decoded_alu_arithmetic_mux)
                        ADD: begin 
                            alu_out_reg <= rs + rt;
                        end
                        SUB: begin 
                            alu_out_reg <= rs - rt;
                        end
                        MUL: begin 
                            alu_out_reg <= rs * rt;
                        end
                        DIV: begin 
                            alu_out_reg <= divided;
                        end
                    endcase
                end
            end
        end
    end
endmodule
