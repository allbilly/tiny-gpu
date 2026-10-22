"""Keep parser fallback warnings distinct from actual converter diagnostics."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from resume_openxc7 import stage_log_has_error


class AssemblyDiagnostics(unittest.TestCase):
    def test_handled_parser_fallback_is_not_error(self):
        text = "RuntimeWarning: Unable to import fast Antlr4 parser implementation.\n"
        text += "  ImportError: cannot import name 'antlr_to_tuple'\n"
        text += "  Falling back to the much slower pure Python textX based parser\n"
        text += "TINYGPU_GRID_CACHE calls=63 constructions=1\n"
        self.assertFalse(stage_log_has_error(text))

    def test_real_errors_remain_fatal(self):
        for text in ("ERROR: Unknown feature\n", "  Fatal: corrupted frame\n",
                     "Traceback (most recent call last):\n", "Invalid word address 0x123\n",
                     "Invalid frame address 0x123\n", "Failed to write bitstream\n"):
            with self.subTest(text=text):
                self.assertTrue(stage_log_has_error(text))


if __name__ == "__main__":
    unittest.main()
