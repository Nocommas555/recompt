import pytest

from recompt.errors import BuildFailedError, DepsMissingError, StepTimeoutError
from recompt.models import Source, Step
from recompt.runners.container import (
    LATEST_IMAGE,
    CmdResult,
    ContainerRunner,
    Runtime,
    detect_runtime,
    image_for,
    image_tag,
    parse_os_release,
    user_options,
)

# --- image mapping (8.6) ---


@pytest.mark.parametrize(
    "release, image",
    [
        ({"ID": "pop", "VERSION_ID": "24.04", "UBUNTU_CODENAME": "noble"}, "docker.io/library/ubuntu:noble"),
        ({"ID": "linuxmint", "VERSION_ID": "22", "UBUNTU_CODENAME": "noble"}, "docker.io/library/ubuntu:noble"),
        ({"ID": "kali", "DEBIAN_CODENAME": "bookworm"}, "docker.io/library/debian:bookworm"),
        ({"ID": "ubuntu", "VERSION_ID": "22.04"}, "docker.io/library/ubuntu:22.04"),
        ({"ID": "debian", "VERSION_ID": "12"}, "docker.io/library/debian:12"),
    ],
)
def test_known_distros_map_to_matching_images(release, image):
    assert image_for(release) == (image, None)


def test_unknown_distro_falls_back_to_latest_lts_with_warning():
    image, warning = image_for({"ID": "fedora", "VERSION_ID": "41"})
    assert image == LATEST_IMAGE
    assert "may not run" in warning


def test_parse_os_release():
    text = 'NAME="Pop!_OS"\nID=pop\nVERSION_ID="24.04"\n# comment\nUBUNTU_CODENAME=noble\n'
    assert parse_os_release(text) == {"NAME": "Pop!_OS", "ID": "pop", "VERSION_ID": "24.04", "UBUNTU_CODENAME": "noble"}


# --- runtime detection and user mapping (8.8) ---


def fake_cmd(responses=None):
    calls = []

    def run(args):
        calls.append(args)
        for prefix, result in (responses or {}).items():
            if tuple(args[: len(prefix)]) == prefix:
                return result(args) if callable(result) else result
        return CmdResult(0, "", "")

    run.calls = calls
    return run


def test_podman_preferred_and_rootless_read_from_info():
    run = fake_cmd({("podman", "info"): CmdResult(0, "true\n", "")})
    rt = detect_runtime(which=lambda n: f"/usr/bin/{n}", run_cmd=run, has_subids=lambda: True)
    assert rt == Runtime("podman", rootless=True)


def test_rootless_podman_without_subuid_ranges_is_deps_missing_with_fix():
    run = fake_cmd({("podman", "info"): CmdResult(0, "true\n", "")})
    with pytest.raises(DepsMissingError) as exc:
        detect_runtime(which=lambda n: f"/usr/bin/{n}", run_cmd=run, has_subids=lambda: False)
    assert "usermod --add-subuids" in exc.value.message
    assert "podman system migrate" in exc.value.message


def test_rootful_podman_does_not_need_subuid_ranges():
    run = fake_cmd({("podman", "info"): CmdResult(0, "false\n", "")})
    rt = detect_runtime(which=lambda n: f"/usr/bin/{n}", run_cmd=run, has_subids=lambda: False)
    assert rt == Runtime("podman", rootless=False)


def test_subid_check_reads_both_files(tmp_path):
    from recompt.runners.container import user_has_subids

    uid, gid = tmp_path / "subuid", tmp_path / "subgid"
    uid.write_text("other:100000:65536\nme:165536:65536\n")
    gid.write_text("me:165536:65536\n")
    assert user_has_subids("me", uid, gid) is True
    gid.write_text("other:1:2\n")
    assert user_has_subids("me", uid, gid) is False
    assert user_has_subids("me", tmp_path / "missing", gid) is False


def test_docker_used_when_no_podman_and_rootless_from_security_options():
    run = fake_cmd({("docker", "info"): CmdResult(0, '["name=seccomp","name=rootless"]', "")})
    rt = detect_runtime(which=lambda n: "/usr/bin/docker" if n == "docker" else None, run_cmd=run)
    assert rt == Runtime("docker", rootless=True)


def test_no_runtime_is_deps_missing():
    with pytest.raises(DepsMissingError) as exc:
        detect_runtime(which=lambda n: None, run_cmd=fake_cmd())
    assert "--host-build" in exc.value.message


@pytest.mark.parametrize(
    "rt, start, build",
    [
        (Runtime("podman", True), ["--userns=keep-id"], []),
        (Runtime("podman", False), [], ["--user", "1000:1001"]),
        (Runtime("docker", False), [], ["--user", "1000:1001"]),
        (Runtime("docker", True), [], []),
    ],
)
def test_user_options_per_runtime_mode(rt, start, build):
    opts = user_options(rt, 1000, 1001)
    assert (opts.start, opts.build, opts.root) == (start, build, ["--user", "0:0"])


# --- lifecycle (8.10) ---


def make_runner(rt=Runtime("docker", False), run_cmd=None, run_process=None, image="docker.io/library/ubuntu:noble"):
    processes = []

    def default_process(argv, **kw):
        processes.append(argv)
        return 0

    r = ContainerRunner(
        workdir="/home/me/proj",
        runtime=rt,
        image=image,
        timeout=30,
        on_output=lambda _: None,
        run_id="abc123",
        uid=1000,
        gid=1001,
        run_cmd=run_cmd or fake_cmd(),
        run_process=run_process or default_process,
    )
    return r, processes


def step(command, kind="build", shell="exec", cwd=".", as_root=False):
    return Step(kind=kind, command=command, shell=shell, cwd=cwd, as_root=as_root, source=Source.BUILD_FILE)


def test_start_command_and_base_setup():
    run = fake_cmd()
    r, processes = make_runner(run_cmd=run)
    r.start()
    start = run.calls[0]
    assert start[:2] == ["docker", "run"]
    for flag in ("-d", "--rm", "--init"):
        assert flag in start
    assert start[start.index("--name") + 1] == "recompt-abc123"
    assert start[start.index("--label") + 1] == "recompt=1"
    sec = [start[i + 1] for i, a in enumerate(start) if a == "--security-opt"]
    assert sec == ["no-new-privileges", "label=disable"]
    mounts = [start[i + 1] for i, a in enumerate(start) if a == "-v"]
    assert mounts == ["/home/me/proj:/src"]
    assert start[-3:] == ["docker.io/library/ubuntu:noble", "sleep", "infinity"]

    [setup] = processes
    assert setup[:2] == ["docker", "exec"]
    assert setup[setup.index("--user") + 1] == "0:0"
    script = setup[-1]
    assert "ca-certificates" in script and "build-essential" in script
    assert "safe.directory" in script and "/opt/recompt/home" in script


def test_failed_pull_retries_with_latest_lts_and_warns():
    def run_result(args):
        return CmdResult(125, "", "manifest unknown") if "docker.io/library/ubuntu:mantic" in args else CmdResult(0, "", "")

    run = fake_cmd({("docker", "run"): run_result})
    r, _ = make_runner(run_cmd=run, image="docker.io/library/ubuntu:mantic")
    r.start()
    assert run.calls[1][-3] == LATEST_IMAGE
    assert any("mantic" in w for w in r.warnings)


def test_container_that_cannot_start_is_build_failure():
    run = fake_cmd({("docker", "run"): CmdResult(125, "", "boom")})
    r, _ = make_runner(run_cmd=run)
    with pytest.raises(BuildFailedError):
        r.start()


def env_of(argv):
    return {argv[i + 1].split("=", 1)[0]: argv[i + 1].split("=", 1)[1] for i, a in enumerate(argv) if a == "-e"}


def test_build_step_exec_user_env_and_workdir():
    r, processes = make_runner()
    r.run(step(["cargo", "build"], cwd="crates/x"))
    argv = processes[-1]
    assert argv[argv.index("--user") + 1] == "1000:1001"
    assert argv[argv.index("-w") + 1] == "/src/crates/x"
    env = env_of(argv)
    assert env["HOME"] == "/opt/recompt/home"
    assert env["CARGO_HOME"] == "/opt/recompt/cargo" and env["RUSTUP_HOME"] == "/opt/recompt/rustup"
    assert env["GOPATH"] == "/opt/recompt/gopath"
    assert env["npm_config_cache"].startswith("/opt/recompt") and env["PIP_CACHE_DIR"].startswith("/opt/recompt")
    assert env["PATH"].startswith("/opt/recompt/cargo/bin:")
    assert argv[-2:] == ["cargo", "build"]
    assert argv[argv.index("recompt-abc123") + 1 :] == ["cargo", "build"]


def test_rootless_podman_build_step_has_no_user_flag():
    r, processes = make_runner(rt=Runtime("podman", True))
    r.run(step("make", shell="sh"))
    assert "--user" not in processes[-1]
    assert processes[-1][-3:] == ["sh", "-c", "make"]


def test_install_step_runs_as_root_in_slash_and_fixes_permissions():
    r, processes = make_runner()
    r.run(step("apt-get install -y cmake", kind="install", shell="sh", cwd="/", as_root=True))
    argv = processes[-1]
    assert argv[argv.index("--user") + 1] == "0:0"
    assert argv[argv.index("-w") + 1] == "/"
    assert argv[-1].startswith("apt-get install -y cmake")
    assert argv[-1].endswith("chmod -R a+rwX /opt/recompt")


def test_windows_shells_are_rejected_in_container():
    r, _ = make_runner()
    with pytest.raises(BuildFailedError):
        r.run(step("dir", shell="cmd"))


def test_timeout_removes_container_then_raises():
    def slow(argv, **kw):
        raise StepTimeoutError("too slow")

    run = fake_cmd()
    r, _ = make_runner(run_cmd=run, run_process=slow)
    with pytest.raises(StepTimeoutError):
        r.run(step(["make"]))
    assert ["docker", "rm", "-f", "recompt-abc123"] in run.calls


def test_stop_removes_container():
    run = fake_cmd()
    r, _ = make_runner(run_cmd=run)
    r.stop()
    assert run.calls[-1] == ["docker", "rm", "-f", "recompt-abc123"]


# --- interpreted image (8.12) ---


def test_image_tag_is_stable_lowercase_hex():
    tag = image_tag("https://github.com/o/r", "main")
    assert tag == image_tag("https://github.com/o/r", "main")
    assert tag != image_tag("https://github.com/o/r", "dev")
    prefix, digest = tag.split("/")
    assert prefix == "recompt" and len(digest) == 12 and digest == digest.lower()


def test_commit_and_launch_command():
    run = fake_cmd()
    r, _ = make_runner(run_cmd=run)
    tag = r.commit("https://github.com/o/r", "main")
    assert run.calls[-1] == ["docker", "commit", "recompt-abc123", tag]
    cmd = r.launch_command(tag, ["npm", "start"])
    assert cmd[:4] == ["docker", "run", "--rm", "-it"]
    assert cmd[cmd.index("--user") + 1] == "1000:1001"
    assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"] == ["/home/me/proj:/src"]
    assert cmd[cmd.index("-w") + 1] == "/src"
    assert env_of(cmd)["HOME"] == "/opt/recompt/home"
    assert cmd[-3:] == [tag, "npm", "start"]
    assert "sleep" not in cmd
