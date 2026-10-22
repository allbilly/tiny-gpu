# Xilinx functional simulation models

These unmodified files are from [Xilinx/XilinxUnisimLibrary](https://github.com/Xilinx/XilinxUnisimLibrary/tree/1c8e05fd1e9a79ceb8b996a0996674122eed086f), commit `1c8e05fd1e9a79ceb8b996a0996674122eed086f` (the upstream README identifies Vivado 2020.1). Copyright notices and the Apache-2.0 `LICENSE` are preserved.

The XC7 primitives, RAMB18E1/RAMB36E1, DSP48E1 and global startup model were reused from the local `~/rknpu-fpga` verification infrastructure. This is test infrastructure. These files are never passed to FPGA synthesis as implementation sources.

Yosys's installed `xilinx/cells_sim.v` declares RAMB36E1 ports and timing arcs without implementing its memory behavior. Using it alone cannot verify the mapped RAM. `fpga/tools/mapped_check.py` uses these functional models through Icarus's library search and includes `glbl` as a root module. It records all model hashes with the synthesized netlist's provenance.

No routed delays or SDF are supplied. The models' internal functional delays do not establish board setup/hold timing or an operating frequency. Dynamic-register (`XIL_DR`) and timing-backannotation (`XIL_TIMING`) variants are not enabled by this test.
