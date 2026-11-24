from detector_helpers import ctx, make_project

from recompt.detectors import REGISTRY, detect_all


def test_registry_order_and_combined_detection(tmp_path):
    assert [d.__module__.rsplit(".", 1)[-1] for d in REGISTRY] == [
        "node", "python", "rust", "go", "cfamily", "github_actions", "gitlab_ci", "dockerfile",
    ]
    copy = make_project(
        tmp_path,
        {"Cargo.toml": '[package]\nname = "x"\n', "src/main.rs": "", "Makefile": "all:\n"},
    )
    assert [f.detector for f in detect_all(copy, ctx())] == ["rust", "cfamily"]
