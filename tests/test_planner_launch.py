import json

from detector_helpers import ctx, make_project

from recompt.detectors import detect_all
from recompt.models import Finding, Source, Step
from recompt.planner import build_plan


def test_interpreted_plan_gets_launch_step_from_resolver(tmp_path):
    copy = make_project(tmp_path, {"package.json": json.dumps({"scripts": {"start": "node ."}}), "yarn.lock": ""})
    plan = build_plan(detect_all(copy, ctx()), copy=copy, host_os="linux", readme_fallback=None)
    assert plan.project_kind == "interpreted"
    assert plan.steps[-1].kind == "launch"
    assert plan.steps[-1].command == ["yarn", "start"]


def test_python_plan_launch_uses_venv(tmp_path):
    copy = make_project(tmp_path, {"requirements.txt": "flask\n", "app.py": ""})
    plan = build_plan(detect_all(copy, ctx()), copy=copy, host_os="linux", readme_fallback=None)
    assert [s.kind for s in plan.steps] == ["setup", "setup", "launch"]
    assert plan.steps[-1].command == [".venv/bin/python", "app.py"]


def test_no_launch_step_when_resolver_finds_nothing(tmp_path):
    copy = make_project(tmp_path, {"package.json": "{}"})
    plan = build_plan(detect_all(copy, ctx()), copy=copy, host_os="linux", readme_fallback=None)
    assert all(s.kind != "launch" for s in plan.steps)


def test_existing_prose_launch_step_is_kept(tmp_path):
    copy = make_project(tmp_path, {})
    prose = Finding(
        detector="readme",
        steps=[
            Step(kind="setup", command="pip install .", source=Source.PROSE, needs_confirm=True),
            Step(kind="launch", command="tool --serve", source=Source.PROSE, needs_confirm=True),
        ],
    )
    plan = build_plan([], copy=copy, host_os="linux", readme_fallback=lambda: [prose])
    assert [s.command for s in plan.steps if s.kind == "launch"] == ["tool --serve"]


def test_compiled_plan_has_no_launch_step(tmp_path):
    copy = make_project(tmp_path, {"Cargo.toml": '[package]\nname = "t"\n', "src/main.rs": ""})
    plan = build_plan(detect_all(copy, ctx()), copy=copy, host_os="linux", readme_fallback=None)
    assert plan.project_kind == "compiled"
    assert all(s.kind != "launch" for s in plan.steps)
