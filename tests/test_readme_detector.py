from detector_helpers import ctx, make_project

from recompt.detectors.readme import detect, select_sections
from recompt.llm.base import LLMUnavailable
from recompt.models import ExtractedPlan, ExtractedRequirement, ExtractedStep, Source

README = """# Tool

Some intro text.

## Features

- fast

## Building

You need cmake.

```sh
# configure first
cmake -B build
cmake --build build
```

## Usage

Run `./build/tool`.

## License

MIT
"""


def test_selects_build_and_usage_sections_with_code_blocks(tmp_path):
    copy = make_project(tmp_path, {"README.md": README})
    sections = select_sections(copy)
    assert [s.heading for s in sections] == ["Building", "Usage"]
    assert "cmake --build build" in sections[0].text
    assert sections[0].file == "README.md"


def test_hash_comment_inside_code_block_is_not_a_heading(tmp_path):
    copy = make_project(tmp_path, {"README.md": README})
    building = select_sections(copy)[0]
    assert "# configure first" in building.text


def test_other_files_and_setext_headings(tmp_path):
    files = {
        "INSTALL.rst": "Installation\n============\n\n  make install\n\nHistory\n-------\n\nold\n",
        "docs/build-linux.md": "# Compile on Linux\n\n```\nmake\n```\n",
        "docs/other.md": "# Install\n\nignored file\n",
    }
    sections = select_sections(make_project(tmp_path, files))
    assert {(s.file, s.heading) for s in sections} == {
        ("INSTALL.rst", "Installation"),
        ("docs/build-linux.md", "Compile on Linux"),
    }


def test_getting_started_heading_is_selected(tmp_path):
    sections = select_sections(make_project(tmp_path, {"README.md": "# x\n\n## Getting Started\n\nnpm i\n"}))
    assert [s.heading for s in sections] == ["Getting Started"]


class FakeBackend:
    name = "fake"

    def __init__(self, plan=None, error=None):
        self.plan, self.error, self.seen = plan, error, None

    def extract_plan(self, sections):
        self.seen = sections
        if self.error:
            raise self.error
        return self.plan


PLAN = ExtractedPlan(
    requirements=[ExtractedRequirement(tool="cmake", min_version="3.20")],
    steps=[ExtractedStep(kind="build", command="cmake -B build && cmake --build build")],
)


def test_backend_plan_becomes_prose_finding_needing_confirmation(tmp_path):
    backend = FakeBackend(plan=PLAN)
    [f] = detect(make_project(tmp_path, {"README.md": README}), ctx(llm=backend))
    assert f.detector == "readme"
    assert [s.heading for s in backend.seen] == ["Building", "Usage"]
    assert f.requirements[0].tool == "cmake" and f.requirements[0].source == Source.PROSE
    [step] = f.steps
    assert step.source == Source.PROSE
    assert step.needs_confirm is True
    assert step.shell == "sh"
    assert step.origin == "README.md"


def test_unavailable_backend_gives_note_and_no_steps(tmp_path):
    backend = FakeBackend(error=LLMUnavailable("rate limited"))
    [f] = detect(make_project(tmp_path, {"README.md": README}), ctx(llm=backend))
    assert f.steps == []
    assert any(n.kind == "unavailable" and "rate limited" in n.message for n in f.notes)


def test_no_backend_gives_note(tmp_path):
    [f] = detect(make_project(tmp_path, {"README.md": README}), ctx(llm=None))
    assert f.steps == []
    assert any(n.kind == "unavailable" for n in f.notes)


def test_no_build_sections_gives_no_finding(tmp_path):
    assert detect(make_project(tmp_path, {"README.md": "# x\n\nhello\n"}), ctx(llm=FakeBackend(plan=PLAN))) == []
