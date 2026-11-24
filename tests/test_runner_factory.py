import pytest

from recompt.errors import DepsMissingError
from recompt.runners import make_runner
from recompt.runners.container import ContainerRunner, Runtime
from recompt.runners.host import HostRunner


def build(host_os, host_build=False, detect=None, release=None):
    return make_runner(
        host_os=host_os,
        host_build=host_build,
        workdir="/work",
        timeout=60,
        on_output=lambda _: None,
        run_id="r1",
        env={"PATH": "/bin"},
        detect=detect or (lambda: Runtime("podman", True)),
        os_release=lambda: release or {"ID": "pop", "UBUNTU_CODENAME": "noble"},
        uid=1000,
        gid=1000,
    )


def test_linux_gets_container_runner_with_host_matching_image():
    r = build("linux")
    assert isinstance(r, ContainerRunner)
    assert r.image == "docker.io/library/ubuntu:noble"
    assert r.warnings == []


def test_linux_unknown_distro_warning_is_kept():
    r = build("linux", release={"ID": "fedora"})
    assert r.warnings and "may not run" in r.warnings[0]


@pytest.mark.parametrize("host_os", ["macos", "windows"])
def test_macos_and_windows_get_host_runner(host_os):
    r = build(host_os, detect=lambda: pytest.fail("no runtime detection off Linux"))
    assert isinstance(r, HostRunner) and r.host_os == host_os


def test_linux_host_build_gets_host_runner_without_runtime():
    r = build("linux", host_build=True, detect=lambda: pytest.fail("no runtime needed"))
    assert isinstance(r, HostRunner)


def test_linux_without_runtime_is_deps_missing():
    def none():
        raise DepsMissingError("No container runtime found: install Podman or Docker, or pass --host-build")

    with pytest.raises(DepsMissingError):
        build("linux", detect=none)
