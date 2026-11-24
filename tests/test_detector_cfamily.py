import pytest
from detector_helpers import commands, ctx, make_project

from recompt.detectors.cfamily import detect


def tools(f):
    return {r.tool for r in f.requirements}


def test_no_build_files_gives_no_finding(tmp_path):
    assert detect(make_project(tmp_path, {"main.c": ""}), ctx()) == []


def test_cmake(tmp_path):
    [f] = detect(make_project(tmp_path, {"CMakeLists.txt": "project(x)"}), ctx())
    assert f.ecosystem == "cfamily"
    assert {"cmake", "c-compiler"} <= tools(f)
    assert commands(f) == [
        ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"],
        ["cmake", "--build", "build", "--config", "Release"],
    ]


@pytest.mark.parametrize(
    "line, version",
    [
        ("cmake_minimum_required(VERSION 3.31)", "3.31"),
        ("CMAKE_MINIMUM_REQUIRED( VERSION 3.20...3.31 FATAL_ERROR )", "3.20"),
        ("project(x)", None),
    ],
)
def test_cmake_minimum_version_is_read(tmp_path, line, version):
    [f] = detect(make_project(tmp_path, {"CMakeLists.txt": f"# comment\n{line}\nproject(x)\n"}), ctx())
    cmake = next(r for r in f.requirements if r.tool == "cmake")
    assert cmake.min_version == version


def test_meson_version_is_read(tmp_path):
    content = "project('x', 'c',\n  version: '1.0',\n  meson_version: '>= 1.3.0')\n"
    [f] = detect(make_project(tmp_path, {"meson.build": content}), ctx())
    meson = next(r for r in f.requirements if r.tool == "meson")
    assert meson.min_version == "1.3.0"


def test_meson(tmp_path):
    [f] = detect(make_project(tmp_path, {"meson.build": "project('x')"}), ctx())
    assert {"meson", "ninja", "c-compiler"} <= tools(f)
    assert commands(f) == [["meson", "setup", "build"], ["meson", "compile", "-C", "build"]]


def test_configure_script(tmp_path):
    [f] = detect(make_project(tmp_path, {"configure": "#!/bin/sh", "Makefile.in": ""}), ctx())
    assert {"make", "c-compiler"} <= tools(f)
    assert commands(f) == ["./configure", "make"]
    assert all(s.shell == "sh" for s in f.steps)


def test_configure_ac_needs_autoreconf(tmp_path):
    [f] = detect(make_project(tmp_path, {"configure.ac": "AC_INIT"}), ctx())
    assert {"autoconf", "automake", "make"} <= tools(f)
    assert commands(f) == ["autoreconf -fi", "./configure", "make"]


def test_plain_makefile(tmp_path):
    [f] = detect(make_project(tmp_path, {"Makefile": "all:\n"}), ctx())
    assert commands(f) == ["make"]


@pytest.mark.parametrize("extra", ["meson.build", "Makefile", "configure"])
def test_cmake_wins_and_note_records_others(tmp_path, extra):
    [f] = detect(make_project(tmp_path, {"CMakeLists.txt": "", extra: ""}), ctx())
    assert commands(f)[0][0] == "cmake"
    assert any(n.kind == "skipped" and extra in n.message for n in f.notes)
