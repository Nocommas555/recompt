import json

import pytest
from detector_helpers import commands, ctx, make_project

from recompt.detectors.node import detect
from recompt.models import Source


def pkg(**fields):
    return json.dumps({"name": "app", **fields})


def test_no_package_json_gives_no_finding(tmp_path):
    assert detect(make_project(tmp_path, {"README.md": "x"}), ctx()) == []


@pytest.mark.parametrize(
    "lockfile, install",
    [
        ("package-lock.json", ["npm", "ci"]),
        ("yarn.lock", ["yarn", "install"]),
        ("pnpm-lock.yaml", ["pnpm", "install"]),
        (None, ["npm", "install"]),
    ],
)
def test_package_manager_is_picked_by_lockfile(tmp_path, lockfile, install):
    files = {"package.json": pkg()}
    if lockfile:
        files[lockfile] = ""
    [f] = detect(make_project(tmp_path, files), ctx())
    assert f.ecosystem == "node"
    assert f.steps[0].command == install
    assert f.steps[0].kind == "setup"
    assert all(s.source == Source.BUILD_FILE for s in f.steps)
    tools = {r.tool for r in f.requirements}
    assert "node" in tools
    if install[0] != "npm":
        assert install[0] in tools


def test_engines_node_sets_min_version(tmp_path):
    [f] = detect(make_project(tmp_path, {"package.json": pkg(engines={"node": ">=18.17"})}), ctx())
    node = next(r for r in f.requirements if r.tool == "node")
    assert node.min_version == "18.17"
    assert node.origin.startswith("package.json")


def test_build_script_becomes_build_step(tmp_path):
    files = {"package.json": pkg(scripts={"build": "tsc"}), "yarn.lock": ""}
    [f] = detect(make_project(tmp_path, files), ctx())
    assert commands(f) == [["yarn", "install"], ["yarn", "run", "build"]]
    assert f.steps[1].kind == "build"


def test_no_build_script_means_setup_only(tmp_path):
    [f] = detect(make_project(tmp_path, {"package.json": pkg(scripts={"start": "node ."})}), ctx())
    assert [s.kind for s in f.steps] == ["setup"]
