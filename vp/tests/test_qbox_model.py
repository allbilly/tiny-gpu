"""Compile QBox memory/ISA methods without booting QBox or replacing their code.

This exercises the model logic shared by its GreenLib adapter. It does not
claim to test GreenLib transaction conversion, IRQ delivery or guest boot.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class QboxModelRegression(unittest.TestCase):
    def test_model_methods(self):
        compiler = shutil.which(os.environ.get("CXX", "c++"))
        if not compiler:
            self.skipTest("C++ compiler is unavailable")
        source = (ROOT / "qbox/src/tiny_gpu_qbox_toplevel.cpp").read_text()
        constants = source[source.index("const uint32_t kRegThreadCount"):source.index("class TinyGpuQboxTarget:")]
        methods = source[source.index("    static bool in_window("):source.index("    void raise_irq()")]
        header = """#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
""" + constants + """
class ExtractedQboxTarget {
public:
    std::array<uint16_t, kProgramRows> program_{};
    std::array<uint8_t, kDataRows> data_{};
    uint32_t thread_count_ = 0;
    bool done_ = false;
    bool failed_ = false;
    const char* name() const { return "qbox_model"; }
    void raise_irq() {}
""" + methods + "};\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qbox_model_under_test.h").write_text(header)
            executable = root / "qbox-model-regression"
            sanitizers = (["-fsanitize=undefined", "-fno-sanitize-recover=all"]
                          if os.environ.get("TINYGPU_TEST_SANITIZERS") == "1" else [])
            compiled = subprocess.run([
                compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                *sanitizers,
                "-DTINY_GPU_QBOX_EXTRACTED_TEST", "-I", str(root),
                str(ROOT / "tests/model_regression.cpp"), "-o", str(executable)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS model regression:", result.stdout)


if __name__ == "__main__":
    unittest.main()
