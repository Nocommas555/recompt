import hashlib
import os
import posixpath
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from recompt import proc
from recompt.errors import BuildFailedError, CancelledError, DepsMissingError, StepTimeoutError
from recompt.models import Step, StepResult
from recompt.runners.base import OutputCallback, OutputTail

LATEST_IMAGE = "docker.io/library/ubuntu:latest"
MOUNT = "/src"
OPT = "/opt/recompt"
FIX_PERMISSIONS = f"chmod -R a+rwX {OPT}"
STEP_ENV = {
    "HOME": f"{OPT}/home",
    "CARGO_HOME": f"{OPT}/cargo",
    "RUSTUP_HOME": f"{OPT}/rustup",
    "GOPATH": f"{OPT}/gopath",
    "npm_config_cache": f"{OPT}/npm-cache",
    "PIP_CACHE_DIR": f"{OPT}/pip-cache",
    "DEBIAN_FRONTEND": "noninteractive",
    "PATH": f"{OPT}/tools/bin:{OPT}/cargo/bin:{OPT}/go/bin:{OPT}/gopath/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
}
BASE_SETUP = (
    "apt-get update && apt-get install -y --no-install-recommends ca-certificates git curl build-essential && "
    f"mkdir -p {OPT}/home && git config --system safe.directory '*' && {FIX_PERMISSIONS}"
)


@dataclass(frozen=True)
class CmdResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Runtime:
    binary: str
    rootless: bool


@dataclass(frozen=True)
class UserOptions:
    start: list[str] = field(default_factory=list)
    build: list[str] = field(default_factory=list)
    root: list[str] = field(default_factory=lambda: ["--user", "0:0"])


RunCmd = Callable[[list[str]], CmdResult]


def run_cmd(args: list[str]) -> CmdResult:
    done = subprocess.run(args, capture_output=True, text=True)
    return CmdResult(done.returncode, done.stdout, done.stderr)


def parse_os_release(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"').strip("'")
    return values


def read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    return parse_os_release(path.read_text()) if path.exists() else {}


def image_for(release: dict[str, str]) -> tuple[str, str | None]:
    if release.get("UBUNTU_CODENAME"):
        return f"docker.io/library/ubuntu:{release['UBUNTU_CODENAME']}", None
    if release.get("DEBIAN_CODENAME"):
        return f"docker.io/library/debian:{release['DEBIAN_CODENAME']}", None
    if release.get("ID") in ("ubuntu", "debian") and release.get("VERSION_ID"):
        return f"docker.io/library/{release['ID']}:{release['VERSION_ID']}", None
    name = release.get("PRETTY_NAME") or release.get("ID") or "this distribution"
    return LATEST_IMAGE, f"No matching image for {name}; building on Ubuntu LTS, the program may not run on the host"


def user_has_subids(
    user: str, subuid: Path = Path("/etc/subuid"), subgid: Path = Path("/etc/subgid")
) -> bool:
    def listed(path: Path) -> bool:
        return path.exists() and any(line.split(":", 1)[0] == user for line in path.read_text().splitlines())

    return listed(subuid) and listed(subgid)


def _current_user_has_subids() -> bool:
    import getpass

    return user_has_subids(getpass.getuser())


def detect_runtime(
    which: Callable[[str], str | None] = shutil.which,
    run_cmd: RunCmd = run_cmd,
    has_subids: Callable[[], bool] = _current_user_has_subids,
) -> Runtime:
    if which("podman"):
        info = run_cmd(["podman", "info", "--format", "{{.Host.Security.Rootless}}"])
        rootless = info.stdout.strip() == "true"
        if rootless and not has_subids():
            raise DepsMissingError(
                "Podman has no subordinate UID/GID range for your user, so it cannot unpack images. Run:\n"
                '  sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$USER"\n'
                "  podman system migrate"
            )
        return Runtime("podman", rootless=rootless)
    if which("docker"):
        info = run_cmd(["docker", "info", "--format", "{{json .SecurityOptions}}"])
        return Runtime("docker", rootless="rootless" in info.stdout)
    raise DepsMissingError("No container runtime found: install Podman or Docker, or pass --host-build")


def user_options(runtime: Runtime, uid: int, gid: int) -> UserOptions:
    if runtime.binary == "podman" and runtime.rootless:
        return UserOptions(start=["--userns=keep-id"])
    if runtime.rootless:
        return UserOptions()
    return UserOptions(build=["--user", f"{uid}:{gid}"])


def image_tag(url: str, ref: str | None) -> str:
    return "recompt/" + hashlib.sha256(f"{url}#{ref or ''}".encode()).hexdigest()[:12]


def _env_flags() -> list[str]:
    return [part for key, value in STEP_ENV.items() for part in ("-e", f"{key}={value}")]


class ContainerRunner:
    def __init__(
        self,
        *,
        workdir: Path | str,
        runtime: Runtime,
        image: str,
        timeout: float,
        on_output: OutputCallback,
        run_id: str,
        uid: int,
        gid: int,
        run_cmd: RunCmd = run_cmd,
        run_process=proc.run_process,
    ):
        self.workdir = str(workdir)
        self.runtime = runtime
        self.image = image
        self.timeout = timeout
        self.on_output = on_output
        self.name = f"recompt-{run_id}"
        self.users = user_options(runtime, uid, gid)
        self.run_cmd = run_cmd
        self.run_process = run_process
        self.warnings: list[str] = []

    @property
    def rt(self) -> str:
        return self.runtime.binary

    def _security(self) -> list[str]:
        return ["--security-opt", "no-new-privileges", "--security-opt", "label=disable",
                "-v", f"{self.workdir}:{MOUNT}", "-w", MOUNT]

    def _start_args(self, image: str) -> list[str]:
        return [self.rt, "run", "-d", "--rm", "--init", "--name", self.name, "--label", "recompt=1",
                *self._security(), *self.users.start, image, "sleep", "infinity"]

    def start(self) -> None:
        result = self.run_cmd(self._start_args(self.image))
        if result.returncode != 0 and self.image != LATEST_IMAGE:
            self.warnings.append(
                f"Could not start {self.image} ({result.stderr.strip()}); using {LATEST_IMAGE}, "
                "the program may not run on the host"
            )
            self.image = LATEST_IMAGE
            result = self.run_cmd(self._start_args(self.image))
        if result.returncode != 0:
            raise BuildFailedError(f"Cannot start the build container: {result.stderr.strip()}")
        self.on_output(f"$ {BASE_SETUP}")
        code = self._exec(self.users.root, "/", ["sh", "-c", BASE_SETUP], OutputTail(self.on_output))
        if code != 0:
            raise BuildFailedError("Preparing the build container failed")

    def _exec(self, user: list[str], workdir: str, command: list[str], tail: OutputTail) -> int:
        argv = [self.rt, "exec", *user, *_env_flags(), "-w", workdir, self.name, *command]
        try:
            return self.run_process(argv, cwd=self.workdir, env=dict(os.environ), timeout=self.timeout,
                                    on_output=tail, host_os="linux")
        except (StepTimeoutError, CancelledError):
            self.kill()
            raise

    def _command(self, step: Step) -> list[str]:
        if step.shell in ("cmd", "pwsh"):
            raise BuildFailedError(f"A {step.shell} step cannot run in the Linux build container: {step.origin}")
        if step.as_root:
            script = step.command if isinstance(step.command, str) else shlex.join(step.command)
            return ["sh", "-ec", f"{script}\n{FIX_PERMISSIONS}"]
        if step.shell == "exec":
            return list(step.command)
        script = step.command if isinstance(step.command, str) else shlex.join(step.command)
        return [step.shell, "-c", script]

    def run(self, step: Step) -> StepResult:
        workdir = "/" if step.cwd == "/" else posixpath.normpath(posixpath.join(MOUNT, step.cwd))
        user = self.users.root if step.as_root else self.users.build
        tail = OutputTail(self.on_output)
        started = time.monotonic()
        code = self._exec(user, workdir, self._command(step), tail)
        return StepResult(step=step, exit_code=code, output_tail=tail.text(), duration_s=time.monotonic() - started)

    def kill(self) -> None:
        self.run_cmd([self.rt, "rm", "-f", self.name])

    def stop(self) -> None:
        self.kill()

    def commit(self, url: str | None, ref: str | None) -> str:
        tag = image_tag(url or self.workdir, ref)
        result = self.run_cmd([self.rt, "commit", self.name, tag])
        if result.returncode != 0:
            raise BuildFailedError(f"Cannot save the prepared container: {result.stderr.strip()}")
        return tag

    def launch_command(self, tag: str, argv: list[str] | str) -> list[str]:
        command = list(argv) if isinstance(argv, list) else ["sh", "-c", argv]
        return [self.rt, "run", "--rm", "-it", *self.users.start, *self.users.build, *_env_flags(),
                *self._security(), tag, *command]
