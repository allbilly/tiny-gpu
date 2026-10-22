"""Check FPGA logic mapping while distinguishing Yosys scope metadata."""
from collections import Counter


def check_board_netlist(design):
    top = design["modules"]["ypcb_tiny_gpu_top"]
    ports = {name: (value["direction"], len(value["bits"])) for name, value in top["ports"].items()}
    expected = {"SYS_CLK": ("input", 1), "led_3bits_tri_o": ("output", 3)}
    if ports != expected:
        raise ValueError(f"Unexpected board ports: {ports}")
    counts = Counter(cell["type"] for cell in top["cells"].values())
    # $scopeinfo preserves hierarchy/source attributes after flattening. It is
    # metadata that nextpnr's JSON importer ignores, not an unmapped logic cell.
    unmapped = {name: count for name, count in counts.items()
                if name.startswith("$") and name != "$scopeinfo"}
    if unmapped:
        raise ValueError(f"Unmapped synthesis logic: {unmapped}")
    if counts["RAMB18E1"] + counts["RAMB36E1"] < 2:
        raise ValueError("Both on-chip memories must infer BRAM")
    bits = top.get("netnames", {}).get("reset_pipe", {}).get("bits", [])
    if len(bits) != 4 or len(set(bits)) != 4 or any(not isinstance(bit, int) for bit in bits):
        raise ValueError("Reset pipeline must retain four distinct flip-flop outputs")
    clock = None
    for index, bit in enumerate(bits):
        drivers = [cell for cell in top["cells"].values()
                   if cell.get("connections", {}).get("Q") == [bit]]
        if len(drivers) != 1:
            raise ValueError("Reset pipeline must have one flip-flop per stage")
        cell = drivers[0]
        pins = cell.get("connections", {})
        expected_data = ["1"] if index == 0 else [bits[index - 1]]
        if (cell["type"] != "FDRE" or cell.get("parameters", {}).get("INIT") != "0" or
                pins.get("D") != expected_data or pins.get("CE") != ["1"] or pins.get("R") != ["0"] or
                len(pins.get("C", [])) != 1):
            raise ValueError("Reset pipeline must be four INIT=0 FDREs in the original shift chain")
        if clock is None:
            clock = pins["C"]
        elif pins["C"] != clock:
            raise ValueError("Reset pipeline stages must share one clock")
    return dict(counts)
