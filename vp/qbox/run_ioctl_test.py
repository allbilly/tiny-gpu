#!/usr/bin/env python3
"""Build and test a private QBox guest; importing this module performs no actions."""
import os
from pathlib import Path
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]


def require_free_port(port):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def owns_listener(pid, port, proc=Path("/proc")):
    """Verify the listener belongs to the new VP session before invoking SSH."""
    inodes = set()
    try:
        for line in (proc / str(pid) / "net/tcp").read_text().splitlines()[1:]:
            fields = line.split()
            if fields[1] == f"0100007F:{port:04X}" and fields[3] == "0A":
                inodes.add(f"socket:[{fields[9]}]")
    except (OSError, IndexError):
        return False
    if not inodes:
        return False
    for process in proc.iterdir():
        if not process.name.isdecimal():
            continue
        try:
            # Fields after the command's closing ')' begin with state, ppid,
            # process group, session. Children inherit the VP's new session.
            fields = (process / "stat").read_text().rsplit(") ", 1)[1].split()
            if int(fields[3]) != pid:
                continue
            for fd in (process / "fd").iterdir():
                if os.readlink(fd) in inodes:
                    return True
        except (OSError, IndexError, ValueError):
            continue
    return False


def copy_private_rootfs(source, destination):
    if source.resolve() == destination.resolve():
        raise ValueError("ROOTFS must differ from SOURCE_ROOTFS")
    # Exclusive creation rejects existing images and symlinks, including images
    # potentially attached to a different VP. Preserve the source image.
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)


def ssh_command(port):
    return ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=2",
            "-p", str(port), "root@127.0.0.1"]


def wait_for_guest(vp, port, deadline):
    while time.monotonic() < deadline:
        if vp.poll() is not None:
            raise RuntimeError(f"VP exited before SSH readiness (exit {vp.returncode})")
        if owns_listener(vp.pid, port):
            try:
                ready = subprocess.run(ssh_command(port) + ["true"],
                                       stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=4)
                if ready.returncode == 0:
                    return
            except subprocess.TimeoutExpired:
                pass
        time.sleep(1)
    raise RuntimeError("timed out waiting for the launched VP's SSH listener")


def stop_vp(vp):
    # The process was started with a private session; include its descendants.
    try:
        os.killpg(vp.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        vp.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # The leader may already have exited while a descendant ignored SIGTERM.
    try:
        os.killpg(vp.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    vp.wait(timeout=5)


def main():
    env = os.environ.copy()
    build = Path(env.get("BUILD_DIR", REPO / "vp/qbox/build")).resolve()
    port = int(env.get("SSH_PORT", "6677"))
    if not 1 <= port <= 65535:
        raise ValueError("SSH_PORT must be between 1 and 65535")
    require_free_port(port)
    configure = ["cmake", "-S", str(REPO / "vp/qbox"), "-B", str(build)]
    for key in ("QBOX_VP_ROOT", "QBOX_LIBRARY"):
        if env.get(key):
            configure.append(f"-D{key}={env[key]}")
    subprocess.run(configure, check=True)
    subprocess.run(["cmake", "--build", str(build)], check=True)
    subprocess.run(["make", "-C", str(REPO / "vp/qbox/guest"), "all"], check=True)
    cache = {}
    for line in (build / "CMakeCache.txt").read_text().splitlines():
        if line.startswith(("QBOX_VP_ROOT:", "QBOX_LIBRARY:")):
            key, value = line.split("=", 1)
            cache[key.split(":", 1)[0]] = value
    vp_root = Path(cache["QBOX_VP_ROOT"])
    source = Path(env.get("SOURCE_ROOTFS", vp_root / "../../examples/vp/rootfs.ext4")).resolve()
    run_dir = Path(tempfile.mkdtemp(prefix="ioctl-run-", dir=build))
    rootfs = Path(os.path.abspath(env.get("ROOTFS", run_dir / "rootfs.ext4")))
    copy_private_rootfs(source, rootfs)
    share = run_dir / "share"
    share.mkdir()
    for name in ("tinygpu.ko", "tiny_gpu_ioctl_test.aarch64", "tiny_gpu_lifecycle_test.aarch64"):
        shutil.copy2(REPO / "vp/qbox/guest" / name, share / name)
    token = secrets.token_hex(16)
    (share / "run-id").write_text(token + "\n")
    env.update(ROOTFS=str(rootfs), SHARE_ROOT=str(share), SSH_PORT=str(port),
               SC_SIGNAL_WRITE_CHECK="DISABLE")
    config = build / "aarch64_tiny_gpu.lua"
    # Lua validation performs no boot. Also catches unsupported paths before
    # legacy GreenLib's parser can discard a Lua runtime error.
    subprocess.run(["lua", str(config)], env=env, check=True)
    log = Path(env.get("LOG", run_dir / "vp.log"))
    print(f"Private run: {run_dir}\nRootfs: {rootfs}\nLog: {log}", flush=True)
    require_free_port(port)
    with log.open("x") as output:
        vp = subprocess.Popen([str(build / "tiny-gpu-qbox-vp"), "-c", str(config)],
                              env=env, stdin=subprocess.DEVNULL, stdout=output,
                              stderr=subprocess.STDOUT, start_new_session=True)
        try:
            wait_for_guest(vp, port, time.monotonic() + 120)
            if vp.poll() is not None or not owns_listener(vp.pid, port):
                raise RuntimeError("VP no longer owns the SSH listener")
            mount = "/mnt/tinygpu-" + token
            # Verify the per-run share before altering any guest driver state.
            command = (f"set -eu; mkdir -p {mount}; "
                       f"mount -t 9p -o trans=virtio,ro r {mount}; "
                       f"test \"$(cat {mount}/run-id)\" = {shlex.quote(token)}; "
                       "rmmod tinygpu 2>/dev/null || true; "
                       f"insmod {mount}/tinygpu.ko; "
                       "if [ ! -c /dev/tinygpu ]; then "
                       "echo 'tinygpu loaded but no device bound; inspect guest device-tree compatibility'; "
                       "ls -l /sys/bus/platform/drivers/tinygpu; dmesg | tail -30; exit 1; fi; "
                       f"{mount}/tiny_gpu_ioctl_test.aarch64; "
                       "pids=''; "
                       f"for i in 1 2 3 4; do {mount}/tiny_gpu_ioctl_test.aarch64 "
                       f"> /tmp/tinygpu-{token}-$i.log 2>&1 & pids=\"$pids $!\"; done; "
                       "failed=0; for pid in $pids; do wait \"$pid\" || failed=1; done; "
                       f"if [ \"$failed\" != 0 ]; then cat /tmp/tinygpu-{token}-*.log; exit 1; fi; "
                       "echo 'four concurrent ioctl clients passed'; "
                       f"{mount}/tiny_gpu_lifecycle_test.aarch64")
            guest_log = run_dir / "guest-test.log"
            try:
                guest = subprocess.run(ssh_command(port) + [command], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, timeout=60)
            except subprocess.TimeoutExpired as error:
                captured = error.stdout or ""
                if isinstance(captured, bytes):
                    captured = captured.decode(errors="replace")
                guest_log.write_text(captured)
                print(captured, end="", flush=True)
                raise
            guest_log.write_text(guest.stdout)
            print(guest.stdout, end="", flush=True)
            guest.check_returncode()
        finally:
            stop_vp(vp)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f"tiny-gpu QBox test: {error}")
