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
