"""Check actual nextpnr placement against the complete YPCB pin profile."""
from collections import Counter
import re

from board_profile import PINS


def check_placement(routed, placement, package_rows, source_netlist):
    source_modules = source_netlist.get("modules", {})
    source_top = source_modules.get("ypcb_tiny_gpu_top", {})
    source_attrs = source_top.get("attributes", {})
    if source_attrs.get("top") != "00000000000000000000000000000001" or not source_attrs.get("src"):
        raise ValueError("Missing verified synthesis top provenance")
    # The pinned JSON writer uses ctx.attrs['module'], or 'top' when absent.
    expected_name = source_attrs.get("module", "top")
    modules = routed.get("modules", {})
    if set(modules) != {expected_name}:
        raise ValueError("Unexpected routed top module")
    top = modules[expected_name]
    attrs = top.get("attributes", {})
    if attrs.get("top") != source_attrs["top"] or attrs.get("src") != source_attrs["src"]:
        raise ValueError("Routed top provenance differs from verified synthesis")
    if attrs.get("module") != source_attrs.get("module"):
        raise ValueError("Routed module-name attribute differs from synthesis")
    expected_ports = {"SYS_CLK": ("input", 1),
                      "led_3bits_tri_o": ("output", 3)}
    for description in (source_top, top):
        ports = {name: (p.get("direction"), len(p.get("bits", [])))
                 for name, p in description.get("ports", {}).items()}
        if ports != expected_ports:
            raise ValueError("Unexpected source or routed board ports")
    cells = top["cells"]
    if set(cells) != set(placement):
        raise ValueError("Placement must cover every routed cell")
    for name, cell in cells.items():
        physical = placement[name]
        bel = cell.get("attributes", {}).get("NEXTPNR_BEL")
        raw_bel = physical.get("nextpnr_bel", "")
        # postRouteArchInfo writes physical site/BEL names into routed JSON;
        # the placement dump separately retains the raw himbaechel name.
        if not isinstance(raw_bel, str) or not re.fullmatch(r"X\d+Y\d+/[^/]+", raw_bel):
            raise ValueError(f"Missing or malformed raw placement: {name}")
        expected_bel = (physical.get("site", "") + "/" + physical.get("bel", "")
                        if physical.get("site") else raw_bel)
        if not bel or bel != expected_bel:
            raise ValueError(f"Missing or inconsistent actual placement: {name}")
        if cell["type"] != physical.get("type"):
            raise ValueError(f"Placement cell type differs: {name}")
    pads = {name: cell for name, cell in cells.items() if cell["type"] == "PAD"}
    if set(pads) != set(PINS):
        raise ValueError("Expected exactly the four YPCB pads")
    checked = {}
    for port, pin in PINS.items():
        attrs = pads[port]["attributes"]
        physical = placement[port]
        package = package_rows[pin]
        direction = "IN" if port == "SYS_CLK" else "OUT"
        port_name = port.split("[", 1)[0]
        bit_index = int(port.split("[", 1)[1][:-1]) if "[" in port else 0
        if pads[port].get("connections", {}).get("PAD") != [top["ports"][port_name]["bits"][bit_index]]:
            raise ValueError(f"Routed pad is disconnected from its top port: {port}")
        if (attrs.get("PACKAGE_PIN") != pin or attrs.get("LOC") != pin or
                attrs.get("IOSTANDARD") != "LVCMOS18" or attrs.get("X_IO_DIR") != direction):
            raise ValueError(f"Wrong routed pad properties: {port}")
        if (physical.get("site") != package["site"] or
                physical.get("tile") != package["tile"] or
                not physical.get("bel", "").endswith(".PAD")):
            raise ValueError(f"Wrong physical site for package pin {pin}: {port}")
        checked[port] = dict(pin=pin, bank=package["bank"], site=physical["site"],
                             tile=physical["tile"], bel=physical["bel"],
                             iostandard=attrs["IOSTANDARD"], direction=direction)
    counts = Counter(cell["type"] for cell in cells.values())
    memories = sum(count for kind, count in counts.items()
                   if kind.startswith(("RAMB18", "RAMB36")))
    if memories < 2:
        raise ValueError("Both GPU memories must have physical BRAM placement")
    for name, cell in cells.items():
        if cell["type"].startswith(("RAMB18", "RAMB36")):
            physical = placement[name]
            if (not physical.get("site", "").startswith(cell["type"][:6]) or
                    not physical.get("tile", "").startswith("BRAM_")):
                raise ValueError(f"BRAM cell is not placed at a physical BRAM site: {name}")
    return dict(source_top="ypcb_tiny_gpu_top", routed_top=expected_name,
                source_location=source_attrs["src"],
                placed_cells=len(cells), bram_cells=memories, pads=checked,
                cell_types=dict(sorted(counts.items())))
