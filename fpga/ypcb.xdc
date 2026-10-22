# Selected profile: openTPU boards/ypcb-00338/constraints/otpu_top_ld.xdc.
# Exact target xc7k480tffg1156-2; R28 is unused, reset follows configuration.
set_property PACKAGE_PIN AA28 [get_ports SYS_CLK]
set_property PACKAGE_PIN P30 [get_ports {led_3bits_tri_o[0]}]
set_property PACKAGE_PIN M30 [get_ports {led_3bits_tri_o[1]}]
set_property PACKAGE_PIN N30 [get_ports {led_3bits_tri_o[2]}]
set_property IOSTANDARD LVCMOS18 [get_ports {SYS_CLK led_3bits_tri_o[*]}]
create_clock -name sys_clk -period 20.000 [get_ports SYS_CLK]
# Asynchronous LED observation only; all internal paths remain timed.
set_false_path -to [get_ports {led_3bits_tri_o[*]}]
set_property CONFIG_VOLTAGE 1.8 [current_design]
set_property CFGBVS GND [current_design]
