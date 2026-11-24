import json
import os
import uuid

import pytest

from recompt.errors import StepTimeoutError
from recompt.models import Source, Step
from recompt.runners import make_runner
from recompt.runners.container import run_cmd

pytestmark = [pytest.mark.integration, pytest.mark.container]


def runner_for(workdir, timeout=900):
    return make_runner(
        host_os="linux",
        host_build=False,
        workdir=workdir,
        timeout=timeout,
        on_output=print,
        run_id=uuid.uuid4().hex[:8],
        env=dict(os.environ),
    )


def test_c_project_builds_with_only_src_mounted_and_host_owned_output(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "main.c").write_text('#include <stdio.h>\nint main(void){puts("hi");return 0;}\n')
    (project / "Makefile").write_text("hello: main.c\n\tcc -o hello main.c\n")
    canary = tmp_path / "canary"
    canary.mkdir()
    (canary / "file.txt").write_text("untouched")
    before = sorted(p.name for p in canary.iterdir())

    runner = runner_for(project)
    try:
        runner.start()
        mounts = json.loads(run_cmd([runner.rt, "inspect", "--format", "{{json .Mounts}}", runner.name]).stdout)
        assert [m["Destination"] for m in mounts] == ["/src"]
        result = runner.run(Step(kind="build", command=["make"], source=Source.BUILD_FILE))
        assert result.exit_code == 0, result.output_tail
    finally:
        runner.stop()

    built = project / "hello"
    assert built.exists()
    assert built.stat().st_uid == os.getuid()
    assert sorted(p.name for p in canary.iterdir()) == before
    assert (canary / "file.txt").read_text() == "untouched"


def test_timeout_removes_the_container(tmp_path):
    runner = runner_for(tmp_path, timeout=900)
    runner.start()
    runner.timeout = 2
    with pytest.raises(StepTimeoutError):
        runner.run(Step(kind="build", command=["sleep", "60"], source=Source.BUILD_FILE))
    names = run_cmd([runner.rt, "ps", "-a", "--filter", "label=recompt=1", "--format", "{{.Names}}"]).stdout.split()
    assert runner.name not in names
