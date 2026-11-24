from detector_helpers import commands, ctx, make_project

from recompt.detectors.python import detect

PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.10"\n'


def test_no_python_files_gives_no_finding(tmp_path):
    assert detect(make_project(tmp_path, {"main.c": ""}), ctx()) == []


def test_pyproject_sets_min_version_and_installs_into_venv(tmp_path):
    [f] = detect(make_project(tmp_path, {"pyproject.toml": PYPROJECT}), ctx())
    assert f.ecosystem == "python"
    py = next(r for r in f.requirements if r.tool == "python")
    assert py.min_version == "3.10"
    assert commands(f) == [
        ["python3", "-m", "venv", ".venv"],
        [".venv/bin/python", "-m", "pip", "install", "."],
    ]
    assert {s.kind for s in f.steps} == {"setup"}


def test_windows_uses_scripts_folder(tmp_path):
    [f] = detect(make_project(tmp_path, {"pyproject.toml": PYPROJECT}), ctx("windows"))
    assert commands(f) == [
        ["python", "-m", "venv", ".venv"],
        [".venv\\Scripts\\python.exe", "-m", "pip", "install", "."],
    ]


def test_setup_py_only_installs_project(tmp_path):
    [f] = detect(make_project(tmp_path, {"setup.py": "from setuptools import setup\nsetup()\n"}), ctx())
    assert commands(f)[-1] == [".venv/bin/python", "-m", "pip", "install", "."]
    py = next(r for r in f.requirements if r.tool == "python")
    assert py.min_version is None


def test_requirements_txt_only_installs_requirements(tmp_path):
    [f] = detect(make_project(tmp_path, {"requirements.txt": "flask\n"}), ctx())
    assert commands(f)[-1] == [".venv/bin/python", "-m", "pip", "install", "-r", "requirements.txt"]


def test_requirements_and_pyproject_install_both(tmp_path):
    files = {"requirements.txt": "flask\n", "pyproject.toml": PYPROJECT}
    [f] = detect(make_project(tmp_path, files), ctx())
    assert commands(f)[1:] == [
        [".venv/bin/python", "-m", "pip", "install", "-r", "requirements.txt"],
        [".venv/bin/python", "-m", "pip", "install", "."],
    ]
