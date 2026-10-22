"""Directed rejection checks; these fixtures are not actual P&R evidence."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from board_profile import PINS
from placement_check import check_placement


class PlacementChecks(unittest.TestCase):
    def setUp(self):
        self.package = {}
        self.cells = {}
        self.placement = {}
        for index, (port, pin) in enumerate(PINS.items()):
            site, tile = f"IOB_X0Y{index}", f"LIOB33_X0Y{index}"
            self.package[pin] = dict(pin=pin, site=site, tile=tile, bank="14")
            self.cells[port] = dict(type="PAD", attributes=dict(
                PACKAGE_PIN=pin, LOC=pin, IOSTANDARD="LVCMOS18",
                X_IO_DIR="IN" if port.startswith("SYS_") else "OUT",
                NEXTPNR_BEL=f"{site}/IOB33.PAD"),
                connections={"PAD": [index+10]})
            self.placement[port] = dict(type="PAD", site=site, tile=tile, bel="IOB33.PAD",
                nextpnr_bel=f"X0Y{index}/IOB_X0Y{index}.IOB33.PAD")
        for index, name in enumerate(("program", "data")):
            self.cells[name] = dict(type="RAMB18E1_RAMB18E1", attributes=dict(NEXTPNR_BEL=f"RAMB18_X0Y{index}/RAMB18E1"))
            self.placement[name] = dict(type="RAMB18E1_RAMB18E1", nextpnr_bel=f"X1Y{index}/RAMB18_X0Y{index}.RAMB18E1",
                                       bel="RAMB18E1",
                                       site=f"RAMB18_X0Y{index}", tile=f"BRAM_L_X1Y{index}")
        attrs = dict(top="00000000000000000000000000000001", src="fixture.sv:1.1-100.10")
        ports = {"SYS_CLK": dict(direction="input", bits=[10]),
                 "led_3bits_tri_o": dict(direction="output", bits=[11,12,13])}
        self.source = {"modules": {"ypcb_tiny_gpu_top": dict(attributes=attrs, ports=ports)}}
        self.routed = {"modules": {"top": dict(cells=self.cells, attributes=copy.deepcopy(attrs),
                                              ports=copy.deepcopy(ports))}}

    def test_consistent_placement(self):
        result = check_placement(self.routed, self.placement, self.package, self.source)
        self.assertEqual(result["placed_cells"], 6)
        self.assertEqual(result["bram_cells"], 2)
        self.assertEqual(len(result["pads"]), 4)

    def test_obsolete_reset_port_rejected(self):
        routed = copy.deepcopy(self.routed)
        routed["modules"]["top"]["ports"]["SYS_RSTN"] = dict(direction="input", bits=[100])
        with self.assertRaisesRegex(ValueError, "Unexpected source or routed board ports"):
            check_placement(routed, self.placement, self.package, self.source)

    def test_normalized_top_requires_source_provenance(self):
        for kind in ("name", "src", "top", "extra"):
            with self.subTest(kind=kind):
                routed = copy.deepcopy(self.routed)
                if kind == "name":
                    routed["modules"]["other"] = routed["modules"].pop("top")
                elif kind == "extra":
                    routed["modules"]["other"] = {}
                else:
                    routed["modules"]["top"]["attributes"][kind] = "wrong"
                with self.assertRaises(ValueError):
                    check_placement(routed, self.placement, self.package, self.source)

    def test_wrong_top_port_or_pad_connection_rejected(self):
        for kind in ("direction", "width", "connection"):
            with self.subTest(kind=kind):
                routed = copy.deepcopy(self.routed)
                top = routed["modules"]["top"]
                if kind == "direction": top["ports"]["SYS_CLK"]["direction"] = "output"
                elif kind == "width": top["ports"]["SYS_CLK"]["bits"].append(100)
                else: top["cells"]["SYS_CLK"]["connections"]["PAD"] = [100]
                with self.assertRaises(ValueError):
                    check_placement(routed, self.placement, self.package, self.source)

    def test_wrong_pad_properties_rejected(self):
        for key, value in (("PACKAGE_PIN", "AB28"), ("LOC", "AB28"),
                           ("IOSTANDARD", "LVCMOS33"), ("X_IO_DIR", "OUT")):
            with self.subTest(key=key):
                routed = copy.deepcopy(self.routed)
                routed["modules"]["top"]["cells"]["SYS_CLK"]["attributes"][key] = value
                with self.assertRaisesRegex(ValueError, "Wrong routed pad"):
                    check_placement(routed, self.placement, self.package, self.source)

    def test_wrong_physical_location_rejected(self):
        for key, value in (("site", "IOB_X0Y999"), ("tile", "OTHER_TILE"), ("bel", "IOB33.INBUF")):
            with self.subTest(key=key):
                placement = copy.deepcopy(self.placement)
                placement["SYS_CLK"][key] = value
                routed = copy.deepcopy(self.routed)
                routed["modules"]["top"]["cells"]["SYS_CLK"]["attributes"]["NEXTPNR_BEL"] = (
                    placement["SYS_CLK"]["site"] + "/" + placement["SYS_CLK"]["bel"])
                with self.assertRaisesRegex(ValueError, "Wrong physical site"):
                    check_placement(routed, placement, self.package, self.source)

    def test_missing_or_inconsistent_placement_rejected(self):
        for change in ("missing", "bel", "type"):
            with self.subTest(change=change):
                placement = copy.deepcopy(self.placement)
                if change == "missing":
                    del placement["data"]
                else:
                    placement["data"]["nextpnr_bel" if change == "bel" else "type"] = "wrong"
                with self.assertRaises(ValueError):
                    check_placement(self.routed, placement, self.package, self.source)

    def test_extra_pad_or_missing_bram_rejected(self):
        for kind in ("extra_pad", "missing_bram"):
            with self.subTest(kind=kind):
                routed, placement = copy.deepcopy(self.routed), copy.deepcopy(self.placement)
                cells = routed["modules"]["top"]["cells"]
                if kind == "extra_pad":
                    cells["extra"] = copy.deepcopy(cells["SYS_CLK"])
                    placement["extra"] = copy.deepcopy(placement["SYS_CLK"])
                else:
                    del cells["data"]
                    del placement["data"]
                with self.assertRaises(ValueError):
                    check_placement(routed, placement, self.package, self.source)

    def test_bram_outside_bram_site_rejected(self):
        placement = copy.deepcopy(self.placement)
        placement["program"]["site"] = "SLICE_X0Y1"
        routed = copy.deepcopy(self.routed)
        routed["modules"]["top"]["cells"]["program"]["attributes"]["NEXTPNR_BEL"] = (
            "SLICE_X0Y1/RAMB18E1")
        with self.assertRaisesRegex(ValueError, "physical BRAM site"):
            check_placement(routed, placement, self.package, self.source)


if __name__ == "__main__":
    unittest.main()
