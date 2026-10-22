import copy
from pathlib import Path
import sys
import tempfile
import unittest
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from board_profile import normalized_xdc
from netlist_check import check_board_netlist
from frame_check import check_frames


class BuildChecks(unittest.TestCase):
    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1] / "ypcb.xdc").read_text()
        self.design = {"modules": {"ypcb_tiny_gpu_top": {
            "ports": {"SYS_CLK": {"direction": "input", "bits": [1]},
                      "led_3bits_tri_o": {"direction": "output", "bits": [3, 4, 5]}},
            "cells": {"program": {"type": "RAMB18E1"}, "data": {"type": "RAMB18E1"},
                      "metadata": {"type": "$scopeinfo"}, "logic": {"type": "LUT6"}}
        }}}
        top = self.design["modules"]["ypcb_tiny_gpu_top"]
        top["netnames"] = {"reset_pipe": {"bits": [6, 7, 8, 9]}}
        for index, bit in enumerate((6, 7, 8, 9)):
            top["cells"][f"reset{index}"] = dict(type="FDRE", parameters={"INIT": "0"},
                connections={"Q": [bit], "D": ["1"] if index == 0 else [bit - 1],
                             "C": [1], "CE": ["1"], "R": ["0"]})

    def test_complete_constraints(self):
        literal, exceptions = normalized_xdc(self.source)
        self.assertEqual(literal.count("set_property PACKAGE_PIN"), 4)
        self.assertEqual(literal.count("set_property IOSTANDARD LVCMOS18"), 4)
        self.assertEqual(len(exceptions), 1)
        self.assertIn("20.000", literal)

    def test_constraint_changes_rejected(self):
        clock = "create_clock -name sys_clk -period 20.000 [get_ports SYS_CLK]"
        for source in (self.source.replace("AA28", "AB28"), self.source.replace(clock, ""),
                       self.source + "\n" + clock, self.source.replace("20.000", "40.000"),
                       self.source.replace("CONFIG_VOLTAGE 1.8", "CONFIG_VOLTAGE 3.3"),
                       self.source.replace("CFGBVS GND", "CFGBVS VCCO"),
                       self.source + "\nset_false_path -from [get_clocks sys_clk]"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    normalized_xdc(source)

    def test_obsolete_external_reset_profile_rejected(self):
        with self.assertRaises(ValueError):
            normalized_xdc(self.source + "\nset_property PACKAGE_PIN R28 [get_ports SYS_RSTN]")
        design = copy.deepcopy(self.design)
        design["modules"]["ypcb_tiny_gpu_top"]["ports"]["SYS_RSTN"] = {"direction": "input", "bits": [2]}
        with self.assertRaisesRegex(ValueError, "Unexpected board ports"):
            check_board_netlist(design)

    def test_metadata_is_not_unmapped_logic(self):
        counts = check_board_netlist(self.design)
        self.assertEqual(counts["$scopeinfo"], 1)
        self.assertEqual(counts["RAMB18E1"], 2)

    def test_unmapped_arithmetic_rejected(self):
        design = copy.deepcopy(self.design)
        design["modules"]["ypcb_tiny_gpu_top"]["cells"]["adder"] = {"type": "$add"}
        with self.assertRaisesRegex(ValueError, "Unmapped synthesis logic"):
            check_board_netlist(design)

    def test_missing_memory_rejected(self):
        design = copy.deepcopy(self.design)
        del design["modules"]["ypcb_tiny_gpu_top"]["cells"]["program"]
        with self.assertRaisesRegex(ValueError, "Both on-chip memories"):
            check_board_netlist(design)

    def test_corrupt_configuration_reset_mapping_rejected(self):
        for change in ("init", "chain", "clock", "srl", "missing"):
            with self.subTest(change=change):
                design = copy.deepcopy(self.design)
                cells = design["modules"]["ypcb_tiny_gpu_top"]["cells"]
                if change == "init": cells["reset3"]["parameters"]["INIT"] = "1"
                elif change == "chain": cells["reset3"]["connections"]["D"] = ["1"]
                elif change == "clock": cells["reset3"]["connections"]["C"] = [100]
                elif change == "srl": cells["reset3"]["type"] = "SRL16E"
                else: del cells["reset3"]
                with self.assertRaisesRegex(ValueError, "Reset pipeline"):
                    check_board_netlist(design)

    def test_wrong_pin_direction_or_width_rejected(self):
        for field, value in (("direction", "output"), ("bits", [1, 2])):
            design = copy.deepcopy(self.design)
            design["modules"]["ypcb_tiny_gpu_top"]["ports"]["SYS_CLK"][field] = value
            with self.assertRaisesRegex(ValueError, "Unexpected board ports"):
                check_board_netlist(design)

    def test_frame_file_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            part = root / "part.json"
            part.write_text(json.dumps({"global_clock_regions": {"top": {"rows": {"0": {
                "configuration_buses": {"CLB_IO_CLK": {"configuration_columns": {
                    "0": {"frame_count": 2}}}}}}}}}))
            frames = root / "image.frames"
            valid = "0x00000000 " + ",".join(["0x00000001"] + ["0x00000000"] * 100) + "\n"
            frames.write_text(valid)
            self.assertEqual(check_frames(frames, part)["supplied_frames"], 1)
            for contents in (valid + valid, valid.replace("0x00000000 ", "0x00000002 ", 1),
                             valid.replace("0x00000001", "0x100000000"),
                             valid.replace(",0x00000000", "", 1), ""):
                with self.subTest(contents=contents):
                    frames.write_text(contents)
                    with self.assertRaises(ValueError):
                        check_frames(frames, part)
            frames.write_text(valid.replace("0x00000001", "0x00000000"))
            with self.assertRaisesRegex(ValueError, "Empty configuration"):
                check_frames(frames, part)
            self.assertEqual(check_frames(frames, part, require_nonzero=False)["nonzero_words"], 0)


if __name__ == "__main__":
    unittest.main()
