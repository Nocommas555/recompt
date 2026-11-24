import os
import sys
from pathlib import Path

import pytest

from recompt.errors import DepsMissingError, StepTimeoutError
from recompt.models import Source, Step
from recompt.runners.host import HostRunner


def step(command, shell="exec", cwd="."):
    return Step(kind="build", command=command, shell=shell, cwd=cwd, source=Source.BUILD_FILE)


def runner(host_os, tmp_path=Path("/work"), which=None, exists=None, **kw):
    return HostRunner(
        workdir=tmp_path,
        host_os=host_os,
        env={"PATH": "/bin"},
        timeout=30,
        on_output=lambda _: None,
        which=which or (lambda name: None),
        exists=exists or (lambda path: False),
        **kw,
    )


def test_exec_form_resolves_program_with_which():
    r = runner("windows", which=lambda n: {"npm": "C:\\node\\npm.cmd"}.get(n))
    assert r.argv(step(["npm", "ci"])) == ["C:\\node\\npm.cmd", "ci"]


def test_exec_form_keeps_unknown_program_and_resolves_relative_paths(tmp_path):
    r = runner("linux", tmp_path)
    assert r.argv(step(["cargo", "build"])) == ["cargo", "build"]
    assert r.argv(step([".venv/bin/python", "-m", "pip"], cwd="sub")) == [str(tmp_path / "sub" / ".venv/bin/python"), "-m", "pip"]


def test_posix_shells():
    r = runner("macos")
    assert r.argv(step("make all", shell="sh")) == ["sh", "-c", "make all"]
    assert r.argv(step("make all", shell="bash")) == ["bash", "-c", "make all"]


def test_windows_bash_is_git_for_windows_never_wsl():
    git = "C:\\Program Files\\Git\\cmd\\git.exe"
    bash = str(Path(git).parent.parent / "bin" / "bash.exe")
    r = runner(
        "windows",
        which=lambda n: {"git": git, "bash": "C:\\Windows\\System32\\bash.exe"}.get(n),
        exists=lambda p: str(p) == bash,
    )
    argv = r.argv(step("make", shell="bash"))
    assert argv == [bash, "-c", "make"]
    assert "System32" not in argv[0]


def test_windows_bash_missing_git_is_deps_missing():
    r = runner("windows", which=lambda n: "C:\\Windows\\System32\\bash.exe" if n == "bash" else None)
    with pytest.raises(DepsMissingError):
        r.argv(step("make", shell="bash"))


def test_pwsh_falls_back_to_powershell_and_cmd():
    r = runner("windows", which=lambda n: {"powershell": "C:\\ps\\powershell.exe"}.get(n))
    assert r.argv(step("dir", shell="pwsh")) == ["C:\\ps\\powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "dir"]
    assert r.argv(step("dir", shell="cmd")) == ["cmd", "/c", "dir"]


def test_run_uses_cwd_env_and_timeout():
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw, argv=argv)
        kw["on_output"]("hello")
        return 2

    r = HostRunner(
        workdir=Path("/work"), host_os="linux", env={"A": "1"}, timeout=12,
        on_output=lambda _: None, which=lambda n: None, exists=lambda p: False, run_process=fake_run,
    )
    result = r.run(step(["make"], cwd="src"))
    assert seen["cwd"] == Path("/work/src")
    assert seen["env"] == {"A": "1"}
    assert seen["timeout"] == 12
    assert (result.exit_code, result.output_tail) == (2, "hello")


def test_real_command_runs_and_times_out(tmp_path):
    out = []
    r = HostRunner(workdir=tmp_path, host_os="linux" if sys.platform != "win32" else "windows",
                   env=dict(os.environ), timeout=1, on_output=out.append)
    ok = r.run(step([sys.executable, "-c", "print('built')"]))
    assert ok.exit_code == 0 and out == ["built"]
    with pytest.raises(StepTimeoutError):
        r.run(step([sys.executable, "-c", "import time; time.sleep(30)"]))
