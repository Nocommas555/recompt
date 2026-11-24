from dataclasses import dataclass, field
from typing import Literal

from recompt.models import Source, Step

Installer = Literal["package", "rustup", "go-archive", "npm"]


@dataclass(frozen=True)
class ToolInfo:
    apt: list[str] = field(default_factory=list)
    brew: str | None = None
    winget: str | None = None
    bin_posix: str = ""
    bin_windows: str = ""
    version_cmd: list[str] = field(default_factory=lambda: ["--version"])
    version_regex: str = r"(\d+(?:\.\d+)+)"
    installer: Installer = "package"
    pypi: str | None = None


def _tool(name, apt, brew, winget, bin_windows=None, **kw) -> ToolInfo:
    return ToolInfo(apt=apt, brew=brew, winget=winget, bin_posix=name, bin_windows=bin_windows or name, **kw)


TOOLCHAINS: dict[str, ToolInfo] = {
    "node": _tool("node", ["nodejs", "npm"], "node", "OpenJS.NodeJS.LTS", version_regex=r"v?(\d+(?:\.\d+)+)"),
    "python": _tool("python3", ["python3", "python3-venv", "python3-pip"], "python", "Python.Python.3.12", "python"),
    "cmake": _tool("cmake", ["cmake"], "cmake", "Kitware.CMake", pypi="cmake"),
    "meson": _tool("meson", ["meson"], "meson", "mesonbuild.meson", pypi="meson"),
    "ninja": _tool("ninja", ["ninja-build"], "ninja", "Ninja-build.Ninja", pypi="ninja"),
    "make": _tool("make", ["make"], "make", "ezwinports.make"),
    "c-compiler": _tool(
        "cc", ["build-essential"], None, "Microsoft.VisualStudio.2022.BuildTools", "cl", version_cmd=["--version"]
    ),
    "pkg-config": _tool("pkg-config", ["pkg-config"], "pkgconf", None),
    "autoconf": _tool("autoconf", ["autoconf"], "autoconf", None),
    "automake": _tool("automake", ["automake"], "automake", None),
    "git": _tool("git", ["git"], "git", "Git.Git"),
    "cargo": _tool("cargo", [], None, "Rustlang.Rustup", installer="rustup"),
    "go": _tool("go", [], "go", "GoLang.Go", version_cmd=["version"], version_regex=r"go(\d+(?:\.\d+)+)",
                installer="go-archive"),
    "yarn": _tool("yarn", [], None, None, "yarn.cmd", installer="npm"),
    "pnpm": _tool("pnpm", [], None, None, "pnpm.cmd", installer="npm"),
}
TOOLCHAINS["rust"] = TOOLCHAINS["rustc"] = TOOLCHAINS["cargo"]

RUSTUP = (
    "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | "
    "sh -s -- -y --no-modify-path --profile minimal"
)
GO_ARCHIVE = (
    "set -e; arch=$(uname -m); case $arch in x86_64) arch=amd64;; aarch64|arm64) arch=arm64;; esac; "
    "v=$(curl -fsSL 'https://go.dev/VERSION?m=text' | head -n1); "
    "curl -fsSL \"https://go.dev/dl/$v.linux-$arch.tar.gz\" | tar -C /opt/recompt -xz"
)


TOOLS_VENV = "/opt/recompt/tools"


def install_step(command, *, as_root: bool, shell: str = "exec") -> Step:
    return Step(
        kind="install",
        command=command,
        shell=shell,
        cwd="/" if as_root else ".",
        as_root=as_root,
        source=Source.BUILD_FILE,
        origin="dependency installer",
    )
