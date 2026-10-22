"""Validate the complete source XDC before translating it for nextpnr."""
import re

PINS = {"SYS_CLK": "AA28", "led_3bits_tri_o[0]": "P30",
        "led_3bits_tri_o[1]": "M30", "led_3bits_tri_o[2]": "N30"}
CONFIGURATION = {"CONFIG_VOLTAGE": 1.8, "CFGBVS": "GND"}


def normalized_xdc(source):
    commands = [re.sub(r"\s+", " ", line.strip()) for line in source.splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    expected = [f"set_property PACKAGE_PIN {pin} [get_ports " +
                (port if "[" not in port else "{" + port + "}") + "]"
                for port, pin in PINS.items()]
    expected += [
        "set_property IOSTANDARD LVCMOS18 [get_ports {SYS_CLK led_3bits_tri_o[*]}]",
        "create_clock -name sys_clk -period 20.000 [get_ports SYS_CLK]",
        "set_false_path -to [get_ports {led_3bits_tri_o[*]}]",
        "set_property CONFIG_VOLTAGE 1.8 [current_design]",
        "set_property CFGBVS GND [current_design]",
    ]
    if sorted(commands) != sorted(expected):
        missing = [line for line in expected if line not in commands]
        extra = [line for line in commands if line not in expected]
        raise ValueError(f"Unreviewed/missing/duplicate board constraints: missing={missing}, extra={extra}")
    lines = []
    for port, pin in PINS.items():
        lines += [f"set_property PACKAGE_PIN {pin} [get_ports {{{port}}}]",
                  f"set_property IOSTANDARD LVCMOS18 [get_ports {{{port}}}]"]
    lines.append("create_clock -name sys_clk -period 20.000 [get_ports SYS_CLK]")
    # CONFIG_VOLTAGE/CFGBVS are Vivado configuration/electrical metadata;
    # nextpnr's literal I/O XDC has no implementation for those properties.
    return "\n".join(lines) + "\n", ["set_false_path -to [get_ports {led_3bits_tri_o[*]}]"]
