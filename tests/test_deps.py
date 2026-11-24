import pytest

from recompt.deps import install_steps, propose, refresh_path
from recompt.models import Requirement, Source


def reqs(*pairs):
    return [Requirement(tool=t, min_version=v, source=Source.BUILD_FILE) for t, v in pairs]


def forbidden(*_args, **_kwargs):
    raise AssertionError("must not probe on Linux")


def test_linux_proposes_every_requirement_without_probing():
    proposals = propose(reqs(("cmake", None), ("cargo", "1.74")), "linux", which=forbidden, run_version=forbidden)
    managers = {p.manager for p in proposals}
    assert managers == {"apt", "rustup"}


VERSIONS = {"cmake": "cmake version 3.28.3\n", "node": "v18.17.0\n", "git": "git version 2.43.0\n"}


def which(name):
    return f"/usr/bin/{name}" if name in {"cmake", "node", "git"} else None


def run_version(cmd):
    return VERSIONS[cmd[0]]


@pytest.mark.parametrize("host", ["macos", "windows"])
def test_host_present_tools_are_skipped_and_missing_proposed(host):
    proposals = propose(reqs(("cmake", "3.20"), ("ninja", None), ("git", None)), host, which=which, run_version=run_version)
    proposed = {pkg for p in proposals for pkg in p.packages}
    assert proposed and all("cmake" not in pkg.lower() and "git" != pkg.lower() for pkg in proposed)
    assert any("ninja" in pkg.lower() for pkg in proposed)


def test_host_tool_below_min_version_is_proposed():
    proposals = propose(reqs(("node", "20")), "macos", which=which, run_version=run_version)
    assert [p.packages for p in proposals] == [["node"]]


def test_host_unknown_tool_is_report_only():
    [p] = propose(reqs(("libfoo", None)), "macos", which=which, run_version=run_version)
    assert p.manager == "report-only"


def test_windows_uses_windows_binary_names():
    seen = []

    def spy(name):
        seen.append(name)
        return None

    propose(reqs(("python", None), ("c-compiler", None)), "windows", which=spy, run_version=run_version)
    assert "python" in seen and "cl" in seen


def test_declined_or_report_only_proposals_give_no_install_steps():
    proposals = propose(reqs(("cmake", None), ("libfoo", None)), "macos", which=lambda n: None, run_version=run_version)
    assert install_steps(proposals, approved=False) == []
    steps = install_steps(proposals, approved=True)
    assert steps and all(s.kind == "install" for s in steps)
    assert all("libfoo" not in str(s.command) for s in steps)


def test_refresh_path_adds_toolchain_folders_on_posix():
    new = refresh_path("/usr/bin", "macos", home="/Users/me", read_registry_path=forbidden)
    parts = new.split(":")
    assert "/Users/me/.cargo/bin" in parts and "/opt/homebrew/bin" in parts and "/usr/bin" in parts
    assert len(parts) == len(set(parts))


def test_refresh_path_reads_registry_on_windows():
    def registry():
        return "C:\\Machine\\bin;C:\\Shared", "C:\\Users\\me\\AppData\\bin;C:\\Shared"

    new = refresh_path("C:\\Old", "windows", home="C:\\Users\\me", read_registry_path=registry)
    parts = new.split(";")
    assert parts[:2] == ["C:\\Machine\\bin", "C:\\Shared"]
    assert "C:\\Users\\me\\AppData\\bin" in parts and "C:\\Old" in parts
    assert "C:\\Users\\me\\.cargo\\bin" in parts
    assert parts.count("C:\\Shared") == 1
