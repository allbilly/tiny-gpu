"""Run the real pre-build Tcl checks, stopping at the first Vivado command.

These tests cover caller configuration only. They do not substitute for
Vivado synthesis, routing, electrical DRC or timing signoff.
"""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
TCLSH = shutil.which("tclsh")
PREAMBLE = r"""
proc create_project {args} {
    puts "CONFIG_GATE_REACHED clock=$::clock_iostandard emit=$::emit"
    exit 0
}
set input [open $::env(TINYGPU_GATE_TEST_SCRIPT) r]
set source_text [read $input]
close $input
if {![info complete $source_text]} { puts stderr "Incomplete Tcl script"; exit 2 }
if {[catch {source $::env(TINYGPU_GATE_TEST_SCRIPT)} reason]} {
    puts stderr $reason
    exit 2
}
puts stderr "Expected the first Vivado command boundary"
exit 2
"""


@unittest.skipUnless(TCLSH, "tclsh is required for the configuration checks")
class VivadoConfigurationChecks(unittest.TestCase):
    def run_gate(self, values):
        environment = {k: v for k, v in os.environ.items() if not k.startswith("TINYGPU_")}
        environment.update(values)
        environment["TINYGPU_GATE_TEST_SCRIPT"] = str(ROOT / "fpga/build.tcl")
        return subprocess.run([TCLSH], input=PREAMBLE, text=True, capture_output=True,
                              env=environment, cwd=ROOT, timeout=30)

    def test_report_only_defaults(self):
        result = self.run_gate({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CONFIG_GATE_REACHED clock=LVCMOS18 emit=0", result.stdout)

    def test_explicit_compatible_selections(self):
        for voltage, strap, clock in (("1.8", "GND", "LVCMOS18"),
                                      ("3.3", "VCCO", "LVCMOS33")):
            with self.subTest(clock=clock):
                result = self.run_gate(dict(TINYGPU_EMIT_BITSTREAM="1",
                    TINYGPU_CONFIG_VOLTAGE=voltage, TINYGPU_CFGBVS=strap,
                    TINYGPU_CLOCK_IOSTANDARD=clock))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"CONFIG_GATE_REACHED clock={clock} emit=1", result.stdout)

    def test_missing_clock_selection_rejected(self):
        result = self.run_gate(dict(TINYGPU_EMIT_BITSTREAM="1",
            TINYGPU_CONFIG_VOLTAGE="1.8", TINYGPU_CFGBVS="GND"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Supply board-verified TINYGPU_CLOCK_IOSTANDARD", result.stderr)

    def test_missing_configuration_bank_values_rejected(self):
        values = dict(TINYGPU_EMIT_BITSTREAM="1", TINYGPU_CONFIG_VOLTAGE="1.8",
                      TINYGPU_CFGBVS="GND", TINYGPU_CLOCK_IOSTANDARD="LVCMOS18")
        for name in ("TINYGPU_CONFIG_VOLTAGE", "TINYGPU_CFGBVS"):
            with self.subTest(name=name):
                missing = dict(values)
                del missing[name]
                result = self.run_gate(missing)
                self.assertEqual(result.returncode, 2)
                self.assertIn(f"Supply board-verified {name}", result.stderr)

    def test_invalid_clock_selection_rejected(self):
        for clock in ("LVCMOS25", ""):
            with self.subTest(clock=clock):
                result = self.run_gate(dict(TINYGPU_CLOCK_IOSTANDARD=clock))
                self.assertEqual(result.returncode, 2)
                self.assertIn("must be LVCMOS18 or LVCMOS33", result.stderr)

    def test_incompatible_configuration_pairs_rejected(self):
        for voltage, strap in (("1.8", "VCCO"), ("3.3", "GND")):
            with self.subTest(voltage=voltage):
                result = self.run_gate(dict(TINYGPU_EMIT_BITSTREAM="1",
                    TINYGPU_CONFIG_VOLTAGE=voltage, TINYGPU_CFGBVS=strap,
                    TINYGPU_CLOCK_IOSTANDARD="LVCMOS18"))
                self.assertEqual(result.returncode, 2)
                self.assertIn("Incompatible configuration voltage/CFGBVS pair", result.stderr)


if __name__ == "__main__":
    unittest.main()
