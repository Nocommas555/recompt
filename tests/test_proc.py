import os
import sys
import time
from types import SimpleNamespace

import pytest

from recompt import proc
from recompt.errors import StepTimeoutError

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")


def test_output_is_streamed_line_by_line_and_exit_code_returned(tmp_path):
    lines = []
    code = proc.run_process(
        [sys.executable, "-c", "print('one'); print('two'); raise SystemExit(3)"],
        cwd=tmp_path,
        env=dict(os.environ),
        timeout=30,
        on_output=lines.append,
    )
    assert code == 3
    assert lines == ["one", "two"]


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split()[2] != "Z"
    except FileNotFoundError:
        return True


@posix_only
def test_timeout_kills_the_whole_process_tree(tmp_path):
    pidfile = tmp_path / "grandchild.pid"
    script = f"sleep 60 & echo $! > {pidfile}; wait"
    start = time.monotonic()
    with pytest.raises(StepTimeoutError):
        proc.run_process(["sh", "-c", script], cwd=tmp_path, env=dict(os.environ), timeout=1, on_output=lambda _: None)
    assert time.monotonic() - start < 10
    grandchild = int(pidfile.read_text())
    for _ in range(50):
        if not alive(grandchild):
            break
        time.sleep(0.1)
    assert not alive(grandchild)


def test_popen_options_per_os():
    assert proc.popen_options("linux") == {"start_new_session": True}
    assert proc.popen_options("macos") == {"start_new_session": True}
    assert proc.popen_options("windows") == {"creationflags": proc.CREATE_NEW_PROCESS_GROUP}


def test_windows_kill_uses_taskkill_on_the_tree():
    calls = []
    fake = SimpleNamespace(pid=4321, wait=lambda timeout=None: 0, poll=lambda: 0)
    proc.kill_tree(fake, "windows", run=lambda args, **kw: calls.append(args), killpg=None)
    assert calls == [["taskkill", "/T", "/F", "/PID", "4321"]]


def test_posix_kill_signals_the_group_then_force_kills():
    signals = []

    class Stubborn:
        pid = 99

        def wait(self, timeout=None):
            if len(signals) == 1:
                raise proc.subprocess.TimeoutExpired("x", timeout)
            return -9

    proc.kill_tree(Stubborn(), "linux", run=None, killpg=lambda pid, sig: signals.append((pid, sig)))
    assert signals == [(99, proc.signal.SIGTERM), (99, proc.signal.SIGKILL)]
