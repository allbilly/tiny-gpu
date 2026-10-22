"""Run a bounded build stage and retain its actual process result."""
from contextlib import ExitStack
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import subprocess
import time


def stop_group(child, grace):
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return child.wait()
    try:
        child.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    # The leader may exit on TERM while a descendant ignores it.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return child.wait()


def run_stage(argv, *, cwd, log, entry, save, timeout, stdout=None,
              termination_grace=5, poll_seconds=1, heartbeat_seconds=15, env=None):
    if not 0 < timeout <= 28800:
        raise ValueError("Stage timeout must be positive and at most 28800 seconds")
    start = time.monotonic()
    child = None
    timed_out = False
    entry.update(timeout_seconds=timeout,
                 started_utc=datetime.now(timezone.utc).isoformat())
    try:
        with ExitStack() as stack:
            output = stack.enter_context(Path(log).open("w"))
            target = stack.enter_context(Path(stdout).open("w")) if stdout else output
            child = subprocess.Popen(list(map(str, argv)), cwd=cwd, stdout=target,
                                     stderr=output if stdout else subprocess.STDOUT,
                                     start_new_session=True, env=env)
            entry.update(pid=child.pid, process_group=child.pid)
            save()
            last_save = -heartbeat_seconds
            while child.poll() is None:
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    timed_out = True
                    stop_group(child, termination_grace)
                    break
                if elapsed - last_save >= heartbeat_seconds:
                    telemetry = dict(observed_utc=datetime.now(timezone.utc).isoformat(),
                                     elapsed_seconds=round(elapsed, 3))
                    try:
                        fields = Path(f"/proc/{child.pid}/stat").read_text().rsplit(")", 1)[1].split()
                        telemetry.update(state=fields[0],
                            cpu_seconds=round((int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK"), 3),
                            rss_bytes=int(fields[21]) * os.sysconf("SC_PAGE_SIZE"))
                    except (OSError, IndexError, ValueError):
                        pass
                    entry["telemetry"] = telemetry
                    save()
                    last_save = elapsed
                time.sleep(min(poll_seconds, max(0, timeout - elapsed)))
            result = child.wait()
    except BaseException as exc:
        if child is not None:
            entry["returncode"] = stop_group(child, termination_grace)
        entry.update(status="FAIL" if isinstance(exc, Exception) else "FAIL_INTERRUPTED",
                     reason=str(exc) or type(exc).__name__, seconds=round(time.monotonic() - start, 3),
                     completed_utc=datetime.now(timezone.utc).isoformat())
        save()
        raise
    entry.update(returncode=result, seconds=round(time.monotonic() - start, 3),
                 completed_utc=datetime.now(timezone.utc).isoformat(),
                 status="FAIL_TIMEOUT" if timed_out else "PASS" if result == 0 else "FAIL")
    if timed_out:
        entry["reason"] = f"Command exceeded {timeout} seconds; process group terminated and child reaped"
    save()
    if timed_out:
        raise TimeoutError(entry["reason"])
    return result
