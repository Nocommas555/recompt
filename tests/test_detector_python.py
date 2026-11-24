from detector_helpers import commands, ctx, make_project

from recompt.detectors.python import detect

BUILD_SYSTEM = '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n'
PYPROJECT = BUILD_SYSTEM + '[project]\nname = "app"\nrequires-python = ">=3.10"\n'


def test_tool_config_only_pyproject_is_not_a_python_project(tmp_path):
    config = '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    assert detect(make_project(tmp_path, {"pyproject.toml": config}), ctx()) == []


def test_project_without_build_system_installs_only_its_dependencies(tmp_path):
    pyproject = '[project]\nname = "app"\nrequires-python = ">=3.11"\ndependencies = ["flask>=3", "click"]\n'
    [f] = detect(make_project(tmp_path, {"pyproject.toml": pyproject}), ctx())
    assert commands(f) == [
        ["python3", "-m", "venv", ".venv"],
        [".venv/bin/python", "-m", "pip", "install", "flask>=3", "click"],
    ]
    assert f.requirements[0].min_version == "3.11"


def test_project_without_build_system_or_dependencies_only_creates_venv(tmp_path):
    [f] = detect(make_project(tmp_path, {"pyproject.toml": '[project]\nname = "app"\n'}), ctx())
    assert commands(f) == [["python3", "-m", "venv", ".venv"]]


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
