import json

import pytest
from detector_helpers import make_project

from recompt.launch import resolve_launch


def node(tmp_path, lock=None, **fields):
    files = {"package.json": json.dumps({"name": "app", **fields})}
    if lock:
        files[lock] = ""
    return make_project(tmp_path, files)


@pytest.mark.parametrize(
    "lock, expected",
    [(None, ["npm", "start"]), ("yarn.lock", ["yarn", "start"]), ("pnpm-lock.yaml", ["pnpm", "start"])],
)
def test_node_start_script(tmp_path, lock, expected):
    assert resolve_launch(node(tmp_path, lock, scripts={"start": "node ."}), "node", "linux") == expected


def test_node_bin_string_and_dict(tmp_path):
    assert resolve_launch(node(tmp_path, bin="cli.js"), "node", "linux") == ["node", "cli.js"]
    assert resolve_launch(node(tmp_path, bin={"tool": "bin/tool.js"}), "node", "linux") == ["node", "bin/tool.js"]


def test_node_main_then_nothing(tmp_path):
    assert resolve_launch(node(tmp_path, main="server.js"), "node", "linux") == ["node", "server.js"]
    assert resolve_launch(node(tmp_path / "empty"), "node", "linux") is None


BUILD = '[build-system]\nrequires = ["setuptools"]\n'


def test_python_project_scripts(tmp_path):
    copy = make_project(tmp_path, {"pyproject.toml": BUILD + '[project]\nname = "x"\n[project.scripts]\nmytool = "x.cli:main"\nother = "x:o"\n'})
    assert resolve_launch(copy, "python", "linux") == [".venv/bin/mytool"]
    assert resolve_launch(copy, "python", "windows") == [".venv\\Scripts\\mytool.exe"]


def test_python_scripts_ignored_when_project_is_not_installed(tmp_path):
    copy = make_project(tmp_path, {"pyproject.toml": '[project]\nname = "x"\n[project.scripts]\nmytool = "x:m"\n', "main.py": ""})
    assert resolve_launch(copy, "python", "linux") == [".venv/bin/python", "main.py"]


@pytest.mark.parametrize("layout", ["pkg/__main__.py", "src/pkg/__main__.py"])
def test_python_package_with_main_module(tmp_path, layout):
    copy = make_project(tmp_path, {"pyproject.toml": '[project]\nname = "pkg"\n', layout: ""})
    assert resolve_launch(copy, "python", "linux") == [".venv/bin/python", "-m", "pkg"]


@pytest.mark.parametrize("script", ["main.py", "app.py"])
def test_python_entry_script(tmp_path, script):
    copy = make_project(tmp_path, {"requirements.txt": "flask\n", script: ""})
    assert resolve_launch(copy, "python", "linux") == [".venv/bin/python", script]


def test_python_nothing_found(tmp_path):
    assert resolve_launch(make_project(tmp_path, {"requirements.txt": ""}), "python", "linux") is None


def test_other_ecosystems_have_no_launch(tmp_path):
    assert resolve_launch(make_project(tmp_path, {}), "rust", "linux") is None
