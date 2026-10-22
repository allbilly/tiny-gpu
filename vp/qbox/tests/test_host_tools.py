import importlib.util
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import tempfile
import unittest
from unittest import mock

QBOX = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runner", QBOX / "run_ioctl_test.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class HostToolsTest(unittest.TestCase):
    def setUp(self):
        # Keep all review/test artifacts within the ignored build directory.
        (QBOX / "build").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=QBOX / "build")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_private_rootfs_never_reuses_or_changes_source(self):
        source = self.root / "source"
        source.write_bytes(b"original disk data")
        destination = self.root / "private"
        runner.copy_private_rootfs(source, destination)
        self.assertEqual(destination.read_bytes(), source.read_bytes())
        destination.write_bytes(b"guest wrote disk")
        with self.assertRaises(FileExistsError):
            runner.copy_private_rootfs(source, destination)
        with self.assertRaises(ValueError):
            runner.copy_private_rootfs(source, source)
        self.assertEqual(source.read_bytes(), b"original disk data")
        link = self.root / "link"
        link.symlink_to(source)
        with self.assertRaises(ValueError):
            runner.copy_private_rootfs(source, link)
        dangling = self.root / "dangling"
        target = self.root / "missing-target"
        dangling.symlink_to(target)
        with self.assertRaises(FileExistsError):
            runner.copy_private_rootfs(source, Path(os.path.abspath(dangling)))
        self.assertFalse(target.exists())

    def test_occupied_port_fails_before_build_or_ssh(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            port = server.getsockname()[1]
            with mock.patch.dict(os.environ, {"SSH_PORT": str(port)}), \
                    mock.patch.object(subprocess, "run") as run:
                with self.assertRaises(OSError):
                    runner.main()
                run.assert_not_called()

    def test_listener_must_belong_to_launched_session(self):
        process = self.root / "123"
        (process / "net").mkdir(parents=True)
        (process / "fd").mkdir()
        (process / "net/tcp").write_text(
            "header\n0: 0100007F:1A15 00000000:0000 0A 0 0 0 0 0 987\n")
        (process / "stat").write_text("123 (VP name) S 1 123 999 0\n")
        (process / "fd/5").symlink_to("socket:[987]")
        self.assertFalse(runner.owns_listener(123, 6677, self.root))
        (process / "stat").write_text("123 (VP name) S 1 123 123 0\n")
        self.assertTrue(runner.owns_listener(123, 6677, self.root))
        self.assertFalse(runner.owns_listener(123, 6678, self.root))

    def test_dead_vp_never_attempts_ssh(self):
        vp = mock.Mock(pid=123, returncode=1)
        vp.poll.return_value = 1
        with mock.patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "VP exited"):
                runner.wait_for_guest(vp, 6677, float("inf"))
            run.assert_not_called()

    def test_unowned_listener_never_attempts_ssh(self):
        vp = mock.Mock(pid=123)
        vp.poll.return_value = None
        with mock.patch.object(runner, "owns_listener", return_value=False), \
                mock.patch.object(runner.time, "monotonic", side_effect=[0, 2]), \
                mock.patch.object(runner.time, "sleep"), \
                mock.patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                runner.wait_for_guest(vp, 6677, 1)
            run.assert_not_called()

    def test_cleanup_kills_descendant_after_leader_exits(self):
        marker = self.root / "child-pid"
        child = ("import os,signal,time; from pathlib import Path; "
                 "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                 f"Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)")
        parent = ("import subprocess,sys,time; "
                  f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(60)")
        vp = subprocess.Popen([sys.executable, "-c", parent], start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.exists(), "test child did not start")
            pid = int(marker.read_text())
            runner.stop_vp(vp)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    state = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[0]
                    if state == "Z":
                        break
                except FileNotFoundError:
                    break
                time.sleep(0.01)
            else:
                self.fail("SIGTERM-ignoring descendant survived cleanup")
        finally:
            runner.stop_vp(vp)

    @unittest.skipUnless(shutil.which("lua"), "Lua interpreter unavailable")
    def test_lua_uses_overrides_and_loopback_forwarding(self):
        library, kernel, disk = [self.root / name for name in ("lib.so", "Image", "disk")]
        for path in (library, kernel, disk):
            path.touch()
        env = os.environ.copy()
        env.update(QBOX_LIBRARY=str(library), KERNEL_IMAGE=str(kernel), ROOTFS=str(disk),
                   SHARE_ROOT=str(self.root), SSH_PORT="19745", TINYGPU_REPO_ROOT=str(QBOX.parents[1]))
        script = ('dofile(arg[1]); assert(CPU.library == os.getenv("QBOX_LIBRARY")); '
                  'assert(CPU.extra_arguments:find("hostfwd=tcp:127.0.0.1:19745-:22", 1, true)); '
                  'assert(CPU.extra_arguments:find("file=" .. os.getenv("ROOTFS"), 1, true)); '
                  'assert(CPU.extra_arguments:find("path=" .. os.getenv("SHARE_ROOT"), 1, true)); '
                  'assert(CPU.extra_arguments:find("readonly=on", 1, true))')
        subprocess.run(["lua", "-", str(QBOX / "conf/aarch64_tiny_gpu.lua")],
                       input=script, text=True, env=env, check=True)
        env["SSH_PORT"] = "0"
        bad = subprocess.run(["lua", str(QBOX / "conf/aarch64_tiny_gpu.lua")],
                             env=env, capture_output=True)
        self.assertNotEqual(bad.returncode, 0)

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_uapi_accepts_linux_headers_and_has_stable_layout(self):
        source = '''#include <linux/types.h>
#include <stddef.h>
#include "tinygpu_ioctl.h"
_Static_assert(sizeof(struct tinygpu_submit) == 56, "size");
_Static_assert(offsetof(struct tinygpu_submit, data) == 16, "data offset");
_Static_assert(offsetof(struct tinygpu_submit, result) == 40, "result offset");
_Static_assert(offsetof(struct tinygpu_submit, status) == 52, "status offset");
_Static_assert(TINYGPU_IOCTL_SUBMIT == 0xc0385400U, "command");
'''
        subprocess.run(["cc", "-x", "c", "-fsyntax-only", "-I", str(QBOX / "guest"), "-"],
                       input=source, text=True, check=True)


if __name__ == "__main__":
    unittest.main()
