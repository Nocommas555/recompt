import pytest
import yaml
from detector_helpers import ctx, make_project

from recompt.detectors.github_actions import detect
from recompt.models import Source


def workflow(jobs: dict) -> str:
    return yaml.safe_dump({"name": "ci", "on": "push", "jobs": jobs})


def project(tmp_path, jobs, name="ci.yml"):
    return make_project(tmp_path, {f".github/workflows/{name}": workflow(jobs)})


def run_lines(f):
    return [s.command for s in f.steps if s.kind == "build"]


def test_no_workflows_gives_no_finding(tmp_path):
    assert detect(make_project(tmp_path, {"README.md": ""}), ctx()) == []


JOBS = {
    "mac": {"runs-on": "macos-14", "steps": [{"run": "make mac"}]},
    "linux": {"runs-on": "ubuntu-latest", "steps": [{"run": "make linux"}]},
    "win": {"runs-on": "windows-2022", "steps": [{"run": "make win"}]},
}


@pytest.mark.parametrize("host, expected", [("linux", "make linux"), ("macos", "make mac"), ("windows", "make win")])
def test_job_matching_host_os_is_picked(tmp_path, host, expected):
    [f] = detect(project(tmp_path, JOBS), ctx(host))
    assert run_lines(f) == [expected]
    assert all(s.source == Source.CI for s in f.steps)


def test_build_named_job_is_preferred_among_matching_jobs(tmp_path):
    jobs = {
        "check": {"runs-on": "ubuntu-latest", "steps": [{"run": "npm install --ignore-scripts"}]},
        "release-build": {"runs-on": "ubuntu-latest", "steps": [{"run": "make release"}]},
    }
    [f] = detect(project(tmp_path, jobs), ctx())
    assert run_lines(f) == ["make release"]


def test_runs_on_expression_with_quoted_labels_is_recognised(tmp_path):
    jobs = {
        "a-mac": {"runs-on": "macos-14", "steps": [{"run": "make mac"}]},
        "build": {
            "runs-on": "${{ matrix.arch == 'aarch64' && 'ubuntu-24.04-arm' || 'ubuntu-24.04' }}",
            "steps": [{"run": "make"}],
        },
    }
    [f] = detect(project(tmp_path, jobs), ctx("linux"))
    assert run_lines(f) == ["make"]


def test_workflow_file_named_for_host_os_wins(tmp_path):
    copy = make_project(
        tmp_path,
        {
            ".github/workflows/audit.yml": workflow({"tidy": {"runs-on": "ubuntu-latest", "steps": [{"run": "echo tidy"}]}}),
            ".github/workflows/build-linux.yml": workflow({"job": {"runs-on": "ubuntu-24.04", "steps": [{"run": "make"}]}}),
            ".github/workflows/build-macos.yml": workflow({"job": {"runs-on": "macos-14", "steps": [{"run": "make mac"}]}}),
        },
    )
    [f] = detect(copy, ctx("linux"))
    assert run_lines(f) == ["make"]
    [f] = detect(copy, ctx("macos"))
    assert run_lines(f) == ["make mac"]


def test_backslash_continued_install_line_keeps_every_package(tmp_path):
    script = (
        "sudo apt-get update\n"
        "sudo apt-get install -y --no-install-recommends \\\n"
        "  cmake g++ libx11-dev \\\n"
        "  qt6-base-private-dev zlib1g-dev\n"
        "make"
    )
    jobs = {"b": {"runs-on": "ubuntu-latest", "steps": [{"run": script}]}}
    [f] = detect(project(tmp_path, jobs), ctx())
    assert {"cmake", "g++", "libx11-dev", "qt6-base-private-dev", "zlib1g-dev"} <= {r.tool for r in f.requirements}
    [install] = [s for s in f.steps if s.kind == "install"]
    assert "\\" not in install.command and "zlib1g-dev" in install.command
    assert run_lines(f) == ["make"]


def test_falls_back_to_first_linux_job(tmp_path):
    jobs = {"a": {"runs-on": "macos-latest", "steps": [{"run": "x"}]}, "b": {"runs-on": "ubuntu-22.04", "steps": [{"run": "y"}]}}
    [f] = detect(project(tmp_path, jobs), ctx("windows"))
    assert run_lines(f) == ["y"]


def test_matrix_entry_matching_host_os(tmp_path):
    jobs = {
        "build": {
            "runs-on": "${{ matrix.os }}",
            "strategy": {"matrix": {"os": ["ubuntu-latest", "windows-latest"]}},
            "steps": [{"run": "cargo build --release"}],
        }
    }
    [f] = detect(project(tmp_path, jobs), ctx("windows"))
    assert run_lines(f) == ["cargo build --release"]
    assert f.steps[0].shell == "pwsh"


def test_setup_actions_become_requirements_and_other_uses_are_skipped(tmp_path):
    jobs = {
        "b": {
            "runs-on": "ubuntu-latest",
            "steps": [
                {"uses": "actions/checkout@v4"},
                {"uses": "actions/setup-node@v4", "with": {"node-version": "20.x"}},
                {"uses": "actions/setup-python@v5", "with": {"python-version": "3.12"}},
                {"uses": "some/other-action@v1"},
                {"run": "npm ci"},
            ],
        }
    }
    [f] = detect(project(tmp_path, jobs), ctx())
    reqs = {(r.tool, r.min_version) for r in f.requirements}
    assert ("node", "20") in reqs and ("python", "3.12") in reqs
    assert run_lines(f) == ["npm ci"]


def test_expression_steps_are_skipped_with_note(tmp_path):
    jobs = {"b": {"runs-on": "ubuntu-latest", "steps": [{"run": "echo ${{ secrets.X }}\necho two\necho three"}, {"run": "make"}]}}
    [f] = detect(project(tmp_path, jobs), ctx())
    assert run_lines(f) == ["make"]
    [note] = [n for n in f.notes if n.kind == "skipped"]
    assert "secrets.X" in note.message and "\n" not in note.message


def test_test_and_upload_steps_are_skipped_with_note(tmp_path):
    jobs = {
        "b": {
            "runs-on": "ubuntu-latest",
            "steps": [
                {"run": "make"},
                {"name": "Run tests", "run": "make check"},
                {"run": "cargo test"},
                {"name": "Upload", "run": "aws s3 cp x y"},
            ],
        }
    }
    [f] = detect(project(tmp_path, jobs), ctx())
    assert run_lines(f) == ["make"]
    assert sum(n.kind == "skipped" for n in f.notes) == 3


def test_apt_lines_become_requirements_and_root_install_step_on_linux(tmp_path):
    jobs = {
        "b": {
            "runs-on": "ubuntu-latest",
            "steps": [{"run": "sudo apt-get update\nsudo apt-get install -y libssl-dev pkg-config\nmake"}],
        }
    }
    [f] = detect(project(tmp_path, jobs), ctx())
    assert {r.tool for r in f.requirements} >= {"libssl-dev", "pkg-config"}
    install = [s for s in f.steps if s.kind == "install"]
    assert len(install) == 1
    assert install[0].command == "apt-get install -y libssl-dev pkg-config"
    assert install[0].as_root is True
    assert run_lines(f) == ["make"]


@pytest.mark.parametrize(
    "runs_on, host, line, packages",
    [
        ("macos-latest", "macos", "brew install cmake ninja", {"cmake", "ninja"}),
        ("windows-latest", "windows", "choco install nasm -y", {"nasm"}),
        ("windows-latest", "windows", "winget install --id Kitware.CMake", {"Kitware.CMake"}),
    ],
)
def test_other_package_managers_give_requirements_only(tmp_path, runs_on, host, line, packages):
    jobs = {"b": {"runs-on": runs_on, "steps": [{"run": line}, {"run": "make"}]}}
    [f] = detect(project(tmp_path, jobs), ctx(host))
    assert {r.tool for r in f.requirements} >= packages
    assert not any(s.kind == "install" for s in f.steps)
    assert run_lines(f) == ["make"]


def test_shell_and_working_directory(tmp_path):
    jobs = {
        "b": {
            "runs-on": "ubuntu-latest",
            "steps": [
                {"run": "make", "shell": "sh", "working-directory": "src"},
                {"run": "make two"},
            ],
        }
    }
    [f] = detect(project(tmp_path, jobs), ctx())
    assert (f.steps[0].shell, f.steps[0].cwd) == ("sh", "src")
    assert (f.steps[1].shell, f.steps[1].cwd) == ("bash", ".")
