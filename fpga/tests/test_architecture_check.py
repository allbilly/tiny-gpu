"""Exercise cancellation with a tiny child, without running native tools."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"


class ArchitectureCancellation(unittest.TestCase):
    def test_sigint_reaps_native_child_and_finalizes_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "build/ypcb").mkdir(parents=True)
            executable = root / "native-test"
            executable.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
            executable.chmod(0o755)
            database = root / "chipdb"
            database.write_bytes(b"test database")
            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            build = root / "build.json"
            build.write_text(json.dumps(dict(
                status="PASS_LOOKUP_EQUIVALENCE_NOT_ARCHITECTURE_CHECKED",
                source_revision="c68c13582e972292c86a5025140d52e713384cbc",
                base_relink_byte_identical=True,
                inputs={str(path): digest(path) for path in (executable, database)},
                executable=dict(path=str(executable), sha256=digest(executable)),
                database=str(database))))
            runner = ("import sys; from pathlib import Path; "
                      "sys.path.insert(0, sys.argv.pop(1)); import architecture_check as m; "
                      "m.ROOT=Path(sys.argv.pop(1)); sys.exit(m.main())")
            child_pid = None
            wrapper = subprocess.Popen(
                [sys.executable, "-c", runner, str(TOOLS), str(root), str(build), "--timeout", "10"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    receipts = list((root / "build/ypcb").glob("*/report.json"))
                    if receipts:
                        report = json.loads(receipts[0].read_text())
                        child_pid = report.get("command", {}).get("pid")
                        if child_pid:
                            break
                    time.sleep(0.02)
                self.assertIsNotNone(child_pid, "native child did not start")
                wrapper.send_signal(signal.SIGINT)
                stdout, stderr = wrapper.communicate(timeout=10)
                self.assertEqual(wrapper.returncode, 130, (stdout, stderr))
                report = json.loads(receipts[0].read_text())
                self.assertEqual(report["status"], "FAIL_INTERRUPTED")
                self.assertEqual(report["command"]["status"], "FAIL_INTERRUPTED")
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)
            finally:
                if wrapper.poll() is None:
                    wrapper.kill()
                    wrapper.communicate()
                if child_pid:
                    try:
                        os.killpg(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
