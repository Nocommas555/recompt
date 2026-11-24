import os
from pathlib import Path
from typing import Callable

from recompt.runners.base import OutputCallback, Runner
from recompt.runners.container import ContainerRunner, Runtime, detect_runtime, image_for, read_os_release
from recompt.runners.host import HostRunner


def make_runner(
    *,
    host_os: str,
    host_build: bool,
    workdir: Path | str,
    timeout: float,
    on_output: OutputCallback,
    run_id: str,
    env: dict[str, str],
    detect: Callable[[], Runtime] = detect_runtime,
    os_release: Callable[[], dict[str, str]] = read_os_release,
    uid: int | None = None,
    gid: int | None = None,
) -> Runner:
    if host_os != "linux" or host_build:
        return HostRunner(workdir=Path(workdir), host_os=host_os, env=env, timeout=timeout, on_output=on_output)
    runtime = detect()
    image, warning = image_for(os_release())
    runner = ContainerRunner(
        workdir=workdir,
        runtime=runtime,
        image=image,
        timeout=timeout,
        on_output=on_output,
        run_id=run_id,
        uid=os.getuid() if uid is None else uid,
        gid=os.getgid() if gid is None else gid,
    )
    if warning:
        runner.warnings.append(warning)
    return runner
