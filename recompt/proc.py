import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from recompt.errors import CancelledError, StepTimeoutError

CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
GRACE_SECONDS = 3


def current_os() -> str:
    if sys.platform == "win32":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def popen_options(host_os: str) -> dict:
    if host_os == "windows":
        return {"creationflags": CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_tree(process, host_os: str, *, run=subprocess.run, killpg=getattr(os, "killpg", None)) -> None:
    if host_os == "windows":
        run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
        return
    try:
        killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=GRACE_SECONDS)


def _pump(stream, on_output: Callable[[str], None]) -> None:
    for line in stream:
        on_output(line.rstrip("\r\n"))


def run_process(
    argv: list[str],
    *,
    cwd: Path | str,
    env: dict[str, str],
    timeout: float,
    on_output: Callable[[str], None],
    host_os: str | None = None,
) -> int:
    host_os = host_os or current_os()
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
        **popen_options(host_os),
    )
    reader = threading.Thread(target=_pump, args=(process.stdout, on_output), daemon=True)
    reader.start()
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process, host_os)
        reader.join(GRACE_SECONDS)
        raise StepTimeoutError(f"Step exceeded the time limit of {timeout:g} seconds") from None
    except KeyboardInterrupt:
        kill_tree(process, host_os)
        reader.join(GRACE_SECONDS)
        raise CancelledError("Cancelled by the user") from None
    reader.join(GRACE_SECONDS)
    return code
