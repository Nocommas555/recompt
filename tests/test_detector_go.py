from detector_helpers import commands, ctx, make_project

from recompt.detectors.go import detect

GOMOD = "module example.com/me/tool\n\ngo 1.22\n"


def test_no_go_mod_gives_no_finding(tmp_path):
    assert detect(make_project(tmp_path, {"main.go": "package main"}), ctx()) == []


def test_root_main_package(tmp_path):
    files = {"go.mod": GOMOD, "main.go": "package main\n\nfunc main() {}\n"}
    [f] = detect(make_project(tmp_path, files), ctx())
    assert f.ecosystem == "go"
    go = next(r for r in f.requirements if r.tool == "go")
    assert go.min_version == "1.22"
    assert commands(f) == [["go", "build", "-o", "bin/tool", "."]]
    assert [(t.name, t.expected_path) for t in f.targets] == [("tool", "bin/tool")]


def test_cmd_folders_give_several_targets(tmp_path):
    files = {
        "go.mod": GOMOD,
        "cmd/server/main.go": "package main\n",
        "cmd/client/main.go": "package main\n",
        "internal/x/x.go": "package x\n",
    }
    [f] = detect(make_project(tmp_path, files), ctx("windows"))
    assert sorted(t.name for t in f.targets) == ["client", "server"]
    assert ["go", "build", "-o", "bin/server.exe", "./cmd/server"] in commands(f)


def test_library_builds_all_packages_without_targets(tmp_path):
    files = {"go.mod": GOMOD, "lib.go": "package tool\n"}
    [f] = detect(make_project(tmp_path, files), ctx())
    assert commands(f) == [["go", "build", "./..."]]
    assert f.targets == []
