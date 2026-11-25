import os
import time

import pytest

from recompt.collect import collect
from recompt.errors import NoRunnableOutputError
from recompt.models import BuildPlan, Source, Step, Target


def write_exe(path, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    if mtime:
        os.utime(path, (mtime, mtime))


def compiled(targets=()):
    return BuildPlan(project_kind="compiled", targets=list(targets))


def test_expected_target_path_is_used(tmp_path):
    write_exe(tmp_path / "target/release/tool")
    write_exe(tmp_path / "other")
    got = collect(compiled([Target(name="tool", expected_path="target/release/tool")]), tmp_path, 0, "linux")
    assert got.programs == [str(tmp_path / "target/release/tool")]


def test_scan_finds_new_executables_only_outside_excluded_folders(tmp_path):
    start = time.time()
    write_exe(tmp_path / "old-script", mtime=start - 100)
    write_exe(tmp_path / "build/app")
    for excluded in (".git/hooks/x", "node_modules/.bin/y", ".venv/bin/python", "venv/bin/p", "vendor/v",
                     "__pycache__/c", "target/debug/dbg", "build/CMakeFiles/probe"):
        write_exe(tmp_path / excluded)
    write_exe(tmp_path / "build/libthing.so")
    (tmp_path / "build/notes.txt").write_text("not executable")
    got = collect(compiled(), tmp_path, start - 1, "linux")
    assert got.programs == [str(tmp_path / "build/app")]


def test_windows_executables_are_exe_files(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out/app.exe").write_text("MZ")
    (tmp_path / "out/readme.txt").write_text("x")
    got = collect(compiled(), tmp_path, 0, "windows")
    assert got.programs == [str(tmp_path / "out/app.exe")]


def test_several_candidates_are_all_returned(tmp_path):
    write_exe(tmp_path / "bin/a")
    write_exe(tmp_path / "bin/b")
    got = collect(compiled(), tmp_path, 0, "linux")
    assert sorted(got.programs) == [str(tmp_path / "bin/a"), str(tmp_path / "bin/b")]


def test_cmake_probe_files_in_any_build_folder_are_skipped_and_bin_is_preferred(tmp_path):
    release = tmp_path / "build/release"
    write_exe(release / "CMakeFiles/3.31.6/CompilerIdCXX/a.out")
    write_exe(release / "CMakeFiles/3.31.6/CMakeDetermineCompilerABI_CXX.bin")
    write_exe(release / "src/tests/unit_tests")
    write_exe(release / "bin/eglantine")
    write_exe(release / "bin/eden-cli")
    got = collect(compiled(), tmp_path, 0, "linux")
    assert got.programs == [str(release / "bin/eden-cli"), str(release / "bin/eglantine")]


def test_candidates_outside_bin_are_kept_when_no_bin_folder_has_one(tmp_path):
    write_exe(tmp_path / "out/CMakeFiles/probe.bin")
    write_exe(tmp_path / "out/app")
    write_exe(tmp_path / "out/helper")
    got = collect(compiled(), tmp_path, 0, "linux")
    assert got.programs == [str(tmp_path / "out/app"), str(tmp_path / "out/helper")]


def test_no_program_is_an_error(tmp_path):
    with pytest.raises(NoRunnableOutputError):
        collect(compiled(), tmp_path, 0, "linux")


def test_interpreted_returns_launch_step_command(tmp_path):
    plan = BuildPlan(
        project_kind="interpreted",
        steps=[Step(kind="launch", command=["npm", "start"], source=Source.BUILD_FILE)],
    )
    assert collect(plan, tmp_path, 0, "linux").launch == ["npm", "start"]


def test_interpreted_without_launch_step_is_an_error(tmp_path):
    with pytest.raises(NoRunnableOutputError):
        collect(BuildPlan(project_kind="interpreted"), tmp_path, 0, "linux")
