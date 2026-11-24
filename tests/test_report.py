from recompt.models import BuildPlan, InstallProposal, PlanNote, Requirement, RunResult, Source, Step
from recompt.report import RunLog, format_plan, format_result


def st(kind, cmd, source=Source.BUILD_FILE, origin="Cargo.toml"):
    return Step(kind=kind, command=cmd, source=source, origin=origin)


PLAN = BuildPlan(
    project_kind="compiled",
    steps=[st("build", ["cargo", "build", "--release"]), st("build", "make docs", Source.PROSE, "README.md")],
    notes=[
        PlanNote(kind="conflict", message="Using steps from build_file; ignored 2 step(s) from ci"),
        PlanNote(kind="warning", message="Dockerfile exposes port(s) 8080; recompt does not map ports"),
    ],
)


def test_plan_shows_each_step_source_notes_and_installs():
    text = format_plan(PLAN, [InstallProposal(manager="apt", packages=["cmake", "pkg-config"])])
    assert "cargo build --release" in text and "Cargo.toml" in text
    assert "make docs" in text and "README.md" in text and "needs your OK" not in text
    assert "ignored 2 step(s) from ci" in text
    assert "8080" in text
    assert "apt: cmake pkg-config" in text


def test_prose_steps_are_marked_in_plan():
    plan = PLAN.model_copy(deep=True)
    plan.steps[1].needs_confirm = True
    assert "needs your OK" in format_plan(plan, [])


def test_result_ok_program_and_launch():
    assert "/w/target/release/tool" in format_result(RunResult(status="ok", program_path="/w/target/release/tool"))
    assert "npm start" in format_result(RunResult(status="ok", launch_command="cd /w && npm start"))


def test_result_failure_shows_step_output_and_missing():
    result = RunResult(
        status="build_failed",
        failed_step=st("build", ["make"]),
        error_output="cc: error: no input files",
        missing=[Requirement(tool="libfoo", source=Source.BUILD_FILE)],
        log_path="/logs/run.log",
    )
    text = format_result(result)
    assert "make" in text and "no input files" in text and "libfoo" in text and "/logs/run.log" in text


def test_log_has_every_command_and_no_credentials(tmp_path):
    path = tmp_path / "run.log"
    log = RunLog(path)
    log.command(st("build", ["git", "clone", "https://user:secret@example.org/r.git"]))
    log.command(st("build", "make all"))
    log.line("fetching https://bob:pw@example.org/x")
    log.close()
    text = path.read_text()
    assert "$ git clone https://example.org/r.git" in text
    assert "$ make all" in text
    assert "secret" not in text and "pw@" not in text
