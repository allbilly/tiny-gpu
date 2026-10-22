"""Exercise real child exits, telemetry, output isolation and timeout cleanup."""
import copy
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from stage_run import run_stage, stop_group


class StageRuns(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.log = self.root / "stage.log"
        self.entry = {"status": "RUNNING"}
        self.snapshots = []

    def run_code(self, code, timeout=5, stdout=None):
        return run_stage([sys.executable, "-u", "-c", code], cwd=self.root,
            log=self.log, entry=self.entry,
            save=lambda: self.snapshots.append(copy.deepcopy(self.entry)),
            timeout=timeout, stdout=stdout, termination_grace=0.1,
            poll_seconds=0.01, heartbeat_seconds=0.05)

    def assert_reaped(self):
        with self.assertRaises(ChildProcessError):
            os.waitpid(self.entry["pid"], os.WNOHANG)

    def test_success_and_live_telemetry(self):
        self.assertEqual(self.run_code("import time; print('done'); time.sleep(0.15)"), 0)
        self.assertEqual(self.entry["status"], "PASS")
        self.assertIn("done", self.log.read_text())
        self.assertTrue(any(s.get("telemetry", {}).get("rss_bytes", 0) > 0 for s in self.snapshots))
        self.assertEqual(self.entry["process_group"], self.entry["pid"])
        self.assert_reaped()

    def test_nonzero_exit_preserved(self):
        self.assertEqual(self.run_code("raise SystemExit(7)"), 7)
        self.assertEqual(self.entry["status"], "FAIL")
        self.assertEqual(self.entry["returncode"], 7)
        self.assert_reaped()

    def test_artifact_stdout_separate_from_stderr(self):
        artifact = self.root / "artifact"
        self.run_code("import sys; print('data'); print('diagnostic', file=sys.stderr)", stdout=artifact)
        self.assertEqual(artifact.read_text(), "data\n")
        self.assertEqual(self.log.read_text(), "diagnostic\n")

    def test_stubborn_child_killed_and_reaped(self):
        code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready'); time.sleep(30)"
        with self.assertRaises(TimeoutError):
            self.run_code(code, timeout=1)
        self.assertIn("ready", self.log.read_text())
        self.assertEqual(self.entry["status"], "FAIL_TIMEOUT")
        self.assertEqual(self.entry["returncode"], -signal.SIGKILL)
        self.assert_reaped()

    def test_descendant_killed_when_leader_exits_on_term(self):
        code = ("import subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-u','-c',"
                "\"import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('descendant-ready',flush=True); time.sleep(30)\"]); "
                "print(p.pid,flush=True); time.sleep(30)")
        with self.assertRaises(TimeoutError):
            self.run_code(code, timeout=3)
        lines = self.log.read_text().splitlines()
        self.assertIn("descendant-ready", lines)
        descendant = int(lines[0])
        stat = Path(f"/proc/{descendant}/stat")
        deadline = time.monotonic() + 1
        while stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] != "Z" and time.monotonic() < deadline:
            time.sleep(0.01)
        if stat.exists():
            self.assertEqual(stat.read_text().rsplit(")", 1)[1].split()[0], "Z")
        self.assertEqual(self.entry["returncode"], -signal.SIGTERM)
        self.assert_reaped()

    def test_invalid_bounds_rejected_before_launch(self):
        for timeout in (0, -1, 28801):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.run_code("raise SystemExit(0)", timeout=timeout)
        self.assertNotIn("pid", self.entry)
        self.assertFalse(self.log.exists())

    def test_explicit_environment(self):
        run_stage([sys.executable, "-c", "import os; print(os.environ['TINYGPU_STAGE_TEST'])"],
            cwd=self.root, log=self.log, entry=self.entry, save=lambda: None,
            timeout=5, env={**os.environ, "TINYGPU_STAGE_TEST": "isolated"}, poll_seconds=0.01)
        self.assertEqual(self.log.read_text(), "isolated\n")

    def test_interrupt_records_terminal_receipt_and_reaps(self):
        def interrupt():
            if self.entry.get("pid") and self.entry["status"] == "RUNNING":
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            run_stage([sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=self.root, log=self.log, entry=self.entry, save=interrupt,
                timeout=5, termination_grace=0.1)
        self.assertEqual(self.entry["status"], "FAIL_INTERRUPTED")
        self.assertIn("completed_utc", self.entry)
        self.assert_reaped()

    def test_cleanup_when_leader_already_exited(self):
        pidfile = self.root / "descendant.pid"
        code = ("import subprocess,sys; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "Path(sys.argv[1]).write_text(str(p.pid))")
        leader = subprocess.Popen([sys.executable, "-c", code, str(pidfile)], start_new_session=True)
        leader.wait(timeout=5)
        descendant = int(pidfile.read_text())
        self.addCleanup(lambda: self.kill_if_present(descendant))
        stop_group(leader, 0.1)
        stat = Path(f"/proc/{descendant}/stat")
        deadline = time.monotonic() + 1
        while stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] != "Z" and time.monotonic() < deadline:
            time.sleep(0.01)
        if stat.exists():
            self.assertEqual(stat.read_text().rsplit(")", 1)[1].split()[0], "Z")

    @staticmethod
    def kill_if_present(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    unittest.main()
