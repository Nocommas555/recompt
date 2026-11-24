import pytest

from recompt.models import Requirement, Source
from recompt.pkgmgr import apt, brew, winget
from recompt.pkgmgr.toolchains import TOOLCHAINS


def reqs(*tools):
    return [Requirement(tool=t, source=Source.BUILD_FILE) for t in tools]


def by_manager(proposals):
    return {p.manager: p for p in proposals}


def test_toolchain_table_covers_core_tools():
    for tool in ("node", "python", "cmake", "meson", "ninja", "make", "c-compiler", "pkg-config", "autoconf", "git"):
        info = TOOLCHAINS[tool]
        assert info.apt and info.version_cmd and info.version_regex


def test_apt_maps_toolchains_and_passes_ci_packages_through():
    [p] = apt.propose(reqs("cmake", "c-compiler", "libssl-dev"))
    assert p.manager == "apt"
    assert set(p.packages) == {"cmake", "build-essential", "libssl-dev"}
    [step] = p.commands
    assert step.as_root is True and step.kind == "install" and step.cwd == "/"
    assert step.command.startswith("apt-get install -y --no-install-recommends ")


def test_apt_uses_rustup_go_archive_and_npm_for_special_tools():
    found = by_manager(apt.propose(reqs("cargo", "go", "yarn", "make")))
    assert set(found) == {"apt", "rustup", "go-archive", "npm"}
    assert "sh.rustup.rs" in found["rustup"].commands[0].command
    assert "go.dev/dl" in found["go-archive"].commands[0].command
    assert found["npm"].commands[0].command == ["npm", "install", "-g", "yarn"]
    assert found["npm"].commands[0].as_root is True
    assert "node" in found["apt"].packages or "nodejs" in found["apt"].packages


def test_brew_maps_toolchains_and_reports_unknown_and_xcode():
    found = by_manager(brew.propose(reqs("cmake", "pkg-config", "libssl-dev", "c-compiler", "go", "cargo")))
    assert set(found["brew"].packages) == {"cmake", "pkgconf", "go"}
    assert found["brew"].commands[0].command == ["brew", "install", "cmake", "pkgconf", "go"]
    assert set(found["report-only"].packages) == {"libssl-dev", "c-compiler"}
    assert found["report-only"].commands == []
    assert "sh.rustup.rs" in found["rustup"].commands[0].command


def test_winget_maps_toolchains_msvc_and_rustup_and_reports_unknown():
    found = by_manager(winget.propose(reqs("cmake", "c-compiler", "cargo", "go", "libfoo")))
    ids = set(found["winget"].packages)
    assert {"Kitware.CMake", "Microsoft.VisualStudio.2022.BuildTools", "Rustlang.Rustup", "GoLang.Go"} <= ids
    for step in found["winget"].commands:
        assert step.command[:3] == ["winget", "install", "--id"]
        assert not any("accept" in part for part in step.command)
    assert found["report-only"].packages == ["libfoo"]


@pytest.mark.parametrize("adapter", [apt, brew, winget])
def test_empty_requirements_give_no_proposals(adapter):
    assert adapter.propose([]) == []
