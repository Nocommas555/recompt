import pytest

from recompt.errors import NoPlanError
from recompt.models import Finding, PlanNote, Requirement, Source, Step, Target, WorkingCopy
from recompt.planner import build_plan

COPY = WorkingCopy(path="/nonexistent", in_place=True)


def s(kind, cmd, source, origin="x"):
    return Step(kind=kind, command=cmd, source=source, origin=origin)


def r(tool, source, version=None):
    return Requirement(tool=tool, min_version=version, source=source, origin="x")


RUST = Finding(
    detector="rust",
    ecosystem="rust",
    requirements=[r("cargo", Source.BUILD_FILE, "1.74")],
    steps=[s("build", ["cargo", "build", "--release"], Source.BUILD_FILE, "Cargo.toml")],
    targets=[Target(name="tool", expected_path="target/release/tool")],
)
CI = Finding(
    detector="github_actions",
    requirements=[r("libssl-dev", Source.CI), r("cargo", Source.CI)],
    steps=[
        Step(kind="install", command="apt-get install -y libssl-dev", source=Source.CI, as_root=True, cwd="/"),
        s("build", "cargo build --verbose", Source.CI, "ci.yml:build"),
    ],
    notes=[PlanNote(kind="skipped", message="CI step not needed to build: test")],
)
DOCKER = Finding(detector="dockerfile", requirements=[r("pkg-config", Source.DOCKERFILE)])


def never():
    raise AssertionError("README fallback must not be called")


def plan(findings, readme=never):
    return build_plan(findings, copy=COPY, host_os="linux", readme_fallback=readme)


def test_build_files_win_and_lower_sources_add_requirements_only():
    p = plan([RUST, CI, DOCKER])
    assert [st.command for st in p.steps] == [["cargo", "build", "--release"]]
    assert all(st.kind != "install" for st in p.steps)
    tools = {req.tool: req for req in p.requirements}
    assert set(tools) == {"cargo", "libssl-dev", "pkg-config"}
    assert tools["cargo"].source == Source.BUILD_FILE and tools["cargo"].min_version == "1.74"


def test_conflicting_lower_steps_are_noted_and_finding_notes_copied():
    p = plan([RUST, CI])
    conflict = [n for n in p.notes if n.kind == "conflict"]
    assert len(conflict) == 1
    assert "Cargo.toml" in conflict[0].sources and "ci.yml:build" in conflict[0].sources
    assert any(n.kind == "skipped" for n in p.notes)


def test_missing_build_step_of_compiled_project_is_filled_from_next_source():
    c = Finding(detector="cfamily", ecosystem="cfamily", steps=[s("setup", "./bootstrap", Source.BUILD_FILE)])
    ci = Finding(detector="github_actions", steps=[s("build", "make", Source.CI, "ci.yml:b")])
    p = plan([c, ci])
    assert [st.command for st in p.steps] == ["./bootstrap", "make"]
    assert any(n.kind == "warning" and "ci.yml:b" in n.sources for n in p.notes)


def test_interpreted_project_is_not_filled_with_ci_build_steps():
    node = Finding(
        detector="node",
        ecosystem="node",
        requirements=[r("node", Source.BUILD_FILE)],
        steps=[s("setup", ["npm", "ci"], Source.BUILD_FILE)],
    )
    ci = Finding(detector="github_actions", steps=[s("build", "npm install --ignore-scripts", Source.CI, "ci.yml:b")])
    p = plan([node, ci])
    assert [st.command for st in p.steps] == [["npm", "ci"]]
    assert any(n.kind == "conflict" for n in p.notes)


def test_readme_fallback_only_called_without_build_steps():
    called = []

    def readme():
        called.append(True)
        return [Finding(detector="readme", steps=[s("build", "make", Source.PROSE)])]

    plan([RUST], readme=readme)
    assert called == []
    p = plan([DOCKER], readme=readme)
    assert called == [True]
    assert [st.command for st in p.steps] == ["make"]


def test_no_steps_anywhere_is_no_plan_error_with_notes():
    readme = lambda: [Finding(detector="readme", notes=[PlanNote(kind="unavailable", message="no LLM")])]  # noqa: E731
    with pytest.raises(NoPlanError) as exc:
        plan([DOCKER], readme=readme)
    assert "no LLM" in exc.value.message


def test_no_readme_fallback_given_and_no_steps():
    with pytest.raises(NoPlanError):
        build_plan([DOCKER], copy=COPY, host_os="linux", readme_fallback=None)


@pytest.mark.parametrize(
    "eco, kind",
    [("node", "interpreted"), ("python", "interpreted"), ("rust", "compiled"), ("go", "compiled"), ("cfamily", "compiled")],
)
def test_project_kind_by_ecosystem(eco, kind):
    f = Finding(detector=eco, ecosystem=eco, steps=[s("build", "x", Source.BUILD_FILE)])
    assert plan([f]).project_kind == kind


@pytest.mark.parametrize(
    "kinds, expected",
    [(["build"], "compiled"), (["setup", "launch"], "interpreted"), (["setup"], "interpreted")],
)
def test_project_kind_for_ci_or_prose_only(kinds, expected):
    f = Finding(detector="github_actions", steps=[s(k, f"cmd-{k}", Source.CI) for k in kinds])
    assert plan([f]).project_kind == expected


def test_targets_come_from_the_primary_source_and_several_are_returned():
    f = RUST.model_copy(update={"targets": [Target(name="a"), Target(name="b")]})
    assert [t.name for t in plan([f, CI]).targets] == ["a", "b"]
