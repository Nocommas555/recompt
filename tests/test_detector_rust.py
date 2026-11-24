from detector_helpers import commands, ctx, make_project

from recompt.detectors.rust import detect

CARGO = '[package]\nname = "tool"\nversion = "0.1.0"\nrust-version = "1.74"\n'


def test_no_cargo_toml_gives_no_finding(tmp_path):
    assert detect(make_project(tmp_path, {"go.mod": ""}), ctx()) == []


def test_single_binary(tmp_path):
    [f] = detect(make_project(tmp_path, {"Cargo.toml": CARGO, "src/main.rs": "fn main(){}"}), ctx())
    assert f.ecosystem == "rust"
    assert commands(f) == [["cargo", "build", "--release"]]
    assert f.steps[0].kind == "build"
    assert [(t.name, t.expected_path) for t in f.targets] == [("tool", "target/release/tool")]
    cargo = next(r for r in f.requirements if r.tool == "cargo")
    assert cargo.min_version == "1.74"


def test_windows_target_has_exe_suffix(tmp_path):
    [f] = detect(make_project(tmp_path, {"Cargo.toml": CARGO, "src/main.rs": ""}), ctx("windows"))
    assert f.targets[0].expected_path == "target/release/tool.exe"


def test_several_bin_targets(tmp_path):
    cargo = CARGO + '\n[[bin]]\nname = "a"\npath = "src/a.rs"\n\n[[bin]]\nname = "b"\npath = "src/b.rs"\n'
    [f] = detect(make_project(tmp_path, {"Cargo.toml": cargo}), ctx())
    assert sorted(t.name for t in f.targets) == ["a", "b"]


def test_workspace_inherited_rust_version(tmp_path):
    cargo = (
        '[package]\nname = "tool"\nrust-version.workspace = true\n\n'
        '[workspace]\nmembers = ["crates/*"]\n\n[workspace.package]\nrust-version = "1.80"\n'
    )
    [f] = detect(make_project(tmp_path, {"Cargo.toml": cargo, "src/main.rs": ""}), ctx())
    assert f.requirements[0].min_version == "1.80"
    assert f.targets[0].name == "tool"


def test_library_has_no_targets(tmp_path):
    [f] = detect(make_project(tmp_path, {"Cargo.toml": CARGO, "src/lib.rs": ""}), ctx())
    assert f.targets == []
