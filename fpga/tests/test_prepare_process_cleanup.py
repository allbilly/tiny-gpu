"""Exercise preparation's real stage integration without compiling FPGA RTL."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import prepare
from stage_run import run_stage


class PreparationCleanup(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("fpga/generated/workloads.vh", "fpga/generated/workloads.json",
                     "fpga/tools/netlist_check.py", "fpga/tools/stage_run.py", "fpga/ypcb.xdc"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
        self.pidfile = self.root / "descendant.pid"
        self.runner = self.root / "fpga/tools/prepare.py"
        self.runner.write_text(Path(prepare.__file__).read_text())
        descendant = ("import os,signal,time; from pathlib import Path; "
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                      f"Path({str(self.pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)")
        (self.root / "fpga/tools/gen_workloads.py").write_text(
            "import subprocess,sys,time\n"
            f"subprocess.Popen([sys.executable, '-c', {descendant!r}])\n"
            "time.sleep(30)\n")
        self.addCleanup(self.kill_descendant)

    def kill_descendant(self):
        if self.pidfile.exists():
            try:
                os.kill(int(self.pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def run_preparation(self, runner):
        with patch.object(prepare, "ROOT", self.root), patch.object(prepare, "__file__", str(self.runner)), \
             patch.object(prepare, "run_stage", runner), \
             patch.object(sys, "argv", ["prepare.py", "--simulator", "icarus"]), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = prepare.main()
        reports = list((self.root / "build/ypcb").glob("*/report.json"))
        self.assertEqual(len(reports), 1)
        return result, json.loads(reports[0].read_text())

    def test_timeout_stops_compiler_style_descendant_and_finalizes_report(self):
        def bounded(argv, **kwargs):
            kwargs.update(timeout=0.5, termination_grace=0.05, poll_seconds=0.01)
            return run_stage(argv, **kwargs)
        result, report = self.run_preparation(bounded)
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["commands"][0]["status"], "FAIL_TIMEOUT")
        pid = int(self.pidfile.read_text())
        stat = Path(f"/proc/{pid}/stat")
        deadline = time.monotonic() + 1
        while stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] != "Z" and time.monotonic() < deadline:
            time.sleep(0.01)
        if stat.exists():
            self.assertEqual(stat.read_text().rsplit(")", 1)[1].split()[0], "Z")

    def test_interruption_finalizes_both_stage_and_preparation(self):
        def interrupted(argv, **kwargs):
            save = kwargs["save"]
            entry = kwargs["entry"]
            raised = False
            def interrupt_once():
                nonlocal raised
                if entry.get("pid") and not raised:
                    raised = True
                    raise KeyboardInterrupt()
                save()
            kwargs.update(save=interrupt_once, termination_grace=0.05)
            return run_stage(argv, **kwargs)
        result, report = self.run_preparation(interrupted)
        self.assertEqual(result, 130)
        self.assertEqual(report["status"], "FAIL_INTERRUPTED")
        self.assertEqual(report["commands"][0]["status"], "FAIL_INTERRUPTED")
        with self.assertRaises(ChildProcessError):
            os.waitpid(report["commands"][0]["pid"], os.WNOHANG)


if __name__ == "__main__":
    unittest.main()
