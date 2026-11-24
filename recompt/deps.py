import re
import shutil
import subprocess
from typing import Callable

from recompt.models import InstallProposal, Requirement, Step
from recompt.pkgmgr import apt, brew, winget
from recompt.pkgmgr.toolchains import TOOLCHAINS

Which = Callable[[str], str | None]
RunVersion = Callable[[list[str]], str]
ADAPTERS = {"linux": apt, "macos": brew, "windows": winget}


def run_version(command: list[str]) -> str:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout + proc.stderr


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _is_satisfied(req: Requirement, host_os: str, which: Which, version_of: RunVersion) -> bool:
    info = TOOLCHAINS.get(req.tool)
    if info is None:
        return False
    binary = info.bin_windows if host_os == "windows" else info.bin_posix
    if not which(binary):
        return False
    if not req.min_version:
        return True
    match = re.search(info.version_regex, version_of([binary, *info.version_cmd]))
    if not match:
        return True
    return _version_tuple(match.group(1)) >= _version_tuple(req.min_version)


def propose(
    requirements: list[Requirement],
    host_os: str,
    *,
    which: Which = shutil.which,
    run_version: RunVersion = run_version,
) -> list[InstallProposal]:
    if host_os != "linux":
        requirements = [r for r in requirements if not _is_satisfied(r, host_os, which, run_version)]
    return ADAPTERS[host_os].propose(requirements)


def install_steps(proposals: list[InstallProposal], *, approved: bool) -> list[Step]:
    if not approved:
        return []
    return [step for p in proposals if p.manager != "report-only" for step in p.commands]


def _windows_registry_path() -> tuple[str, str]:
    import winreg

    def read(root, key):
        try:
            with winreg.OpenKey(root, key) as handle:
                return winreg.QueryValueEx(handle, "Path")[0]
        except OSError:
            return ""

    machine = read(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
    user = read(winreg.HKEY_CURRENT_USER, "Environment")
    return machine, user


def _dedup(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    return [p for p in parts if p and not (p in seen or seen.add(p))]


def refresh_path(
    current: str,
    host_os: str,
    *,
    home: str,
    read_registry_path: Callable[[], tuple[str, str]] = _windows_registry_path,
) -> str:
    if host_os == "windows":
        machine, user = read_registry_path()
        parts = machine.split(";") + user.split(";") + [f"{home}\\.cargo\\bin"] + current.split(";")
        return ";".join(_dedup(parts))
    extra = [f"{home}/.cargo/bin", "/opt/homebrew/bin", "/usr/local/bin", "/usr/local/go/bin"]
    return ":".join(_dedup(extra + current.split(":")))
