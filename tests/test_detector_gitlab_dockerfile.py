import yaml
from detector_helpers import ctx, make_project

from recompt.detectors import dockerfile, gitlab_ci
from recompt.models import Source


def gitlab(tmp_path, data):
    return make_project(tmp_path, {".gitlab-ci.yml": yaml.safe_dump(data)})


def test_gitlab_no_file_gives_no_finding(tmp_path):
    assert gitlab_ci.detect(make_project(tmp_path, {}), ctx()) == []


def test_gitlab_picks_build_job_and_ignores_image(tmp_path):
    data = {
        "image": "rust:1.80",
        "stages": ["test", "build"],
        "lint": {"script": ["cargo fmt --check"]},
        "compile-release": {"image": "x", "script": ["cargo build --release"]},
    }
    [f] = gitlab_ci.detect(gitlab(tmp_path, data), ctx())
    assert [s.command for s in f.steps] == ["cargo build --release"]
    assert all(s.source == Source.CI and s.shell == "sh" for s in f.steps)


def test_gitlab_falls_back_to_first_job_with_script_and_handles_installs(tmp_path):
    data = {
        ".hidden": {"script": ["nope"]},
        "variables": {"A": "1"},
        "job1": {"before_script": ["apt-get update", "apt-get install -y cmake"], "script": ["make"]},
        "job2": {"script": ["other"]},
    }
    [f] = gitlab_ci.detect(gitlab(tmp_path, data), ctx())
    assert "cmake" in {r.tool for r in f.requirements}
    assert [s.kind for s in f.steps] == ["install", "build"]
    assert f.steps[0].command == "apt-get install -y cmake"
    assert f.steps[1].command == "make"


def test_dockerfile_gives_requirements_only_and_expose_note(tmp_path):
    content = (
        "FROM ubuntu:24.04\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
        "    libssl-dev cmake && rm -rf /var/lib/apt/lists/*\n"
        "RUN apk add --no-cache musl-dev\n"
        "RUN dnf install -y zlib-devel\n"
        "EXPOSE 8080\n"
        "RUN make\n"
    )
    [f] = dockerfile.detect(make_project(tmp_path, {"Dockerfile": content}), ctx())
    assert {r.tool for r in f.requirements} == {"libssl-dev", "cmake", "musl-dev", "zlib-devel"}
    assert all(r.source == Source.DOCKERFILE for r in f.requirements)
    assert f.steps == []
    assert any(n.kind == "warning" and "8080" in n.message for n in f.notes)


def test_no_dockerfile_gives_no_finding(tmp_path):
    assert dockerfile.detect(make_project(tmp_path, {}), ctx()) == []
