import os
import shutil
import time
from pathlib import Path
from typing import Callable

from recompt import proc
from recompt.errors import DepsMissingError
from recompt.models import Step, StepResult
from recompt.runners.base import OutputCallback, OutputTail


class HostRunner:
    def __init__(
        self,
        *,
        workdir: Path,
        host_os: str,
        env: dict[str, str],
        timeout: float,
        on_output: OutputCallback,
        which: Callable[[str], str | None] = shutil.which,
        exists: Callable[[Path], bool] = os.path.exists,
        run_process=proc.run_process,
    ):
        self.workdir = Path(workdir)
        self.host_os = host_os
        self.env = env
        self.timeout = timeout
        self.on_output = on_output
        self.which = which
        self.exists = exists
        self.run_process = run_process

    def start(self) -> None:
        pass

    def kill(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def _git_bash(self) -> str:
        git = self.which("git")
        if git:
            git_root = Path(git).parent.parent
            for candidate in (git_root / "bin" / "bash.exe", Path(git).parent / "bash.exe"):
                if self.exists(candidate):
                    return str(candidate)
        raise DepsMissingError("This step needs bash; install Git for Windows (its bash is used, not WSL)")

    def argv(self, step: Step) -> list[str]:
        if step.shell == "exec":
            program, *rest = step.command
            if "/" in program or "\\" in program:
                return [str(self.workdir / step.cwd / program), *rest]
            return [self.which(program) or program, *rest]
        script = step.command if isinstance(step.command, str) else " ".join(step.command)
        if step.shell == "cmd":
            return ["cmd", "/c", script]
        if step.shell == "pwsh":
            exe = self.which("pwsh") or self.which("powershell")
            if not exe:
                raise DepsMissingError("This step needs PowerShell (pwsh or powershell)")
            return [exe, "-NoProfile", "-NonInteractive", "-Command", script]
        if step.shell == "bash" and self.host_os == "windows":
            return [self._git_bash(), "-c", script]
        return [step.shell, "-c", script]

    def run(self, step: Step) -> StepResult:
        tail = OutputTail(self.on_output)
        started = time.monotonic()
        code = self.run_process(
            self.argv(step),
            cwd=self.workdir / step.cwd,
            env=self.env,
            timeout=self.timeout,
            on_output=tail,
            host_os=self.host_os,
        )
        return StepResult(step=step, exit_code=code, output_tail=tail.text(), duration_s=time.monotonic() - started)
