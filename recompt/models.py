from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Source(str, Enum):
    BUILD_FILE = "build_file"
    CI = "ci"
    DOCKERFILE = "dockerfile"
    PROSE = "prose"


HostOS = Literal["linux", "macos", "windows"]
Shell = Literal["exec", "sh", "bash", "pwsh", "cmd"]
StepKind = Literal["install", "setup", "build", "launch"]


class Requirement(BaseModel):
    tool: str
    min_version: str | None = None
    source: Source
    origin: str = ""


class Step(BaseModel):
    kind: StepKind
    command: list[str] | str
    shell: Shell = "exec"
    cwd: str = "."
    as_root: bool = False
    source: Source
    origin: str = ""
    needs_confirm: bool = False


class Target(BaseModel):
    name: str
    expected_path: str | None = None


class PlanNote(BaseModel):
    kind: Literal["conflict", "skipped", "unavailable", "warning"]
    message: str
    sources: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    detector: str
    ecosystem: str | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    targets: list[Target] = Field(default_factory=list)
    notes: list[PlanNote] = Field(default_factory=list)
    cmake_options: list[str] = Field(default_factory=list)
    cmake_generator: str | None = None
    cmake_build_dir: str | None = None


class WorkingCopy(BaseModel):
    path: str
    in_place: bool
    url: str | None = None
    ref: str | None = None


class DetectContext(BaseModel):
    host_os: HostOS
    llm: Any | None = None


class StepResult(BaseModel):
    step: Step
    exit_code: int
    output_tail: str = ""
    duration_s: float = 0.0


class ExtractedRequirement(BaseModel):
    tool: str
    min_version: str | None = None


class ExtractedStep(BaseModel):
    kind: Literal["setup", "build", "launch"]
    command: str
    shell: Literal["sh", "bash", "pwsh", "cmd"] = "sh"
    cwd: str = "."


class ExtractedPlan(BaseModel):
    requirements: list[ExtractedRequirement] = Field(default_factory=list)
    steps: list[ExtractedStep] = Field(default_factory=list)


class BuildPlan(BaseModel):
    project_kind: Literal["compiled", "interpreted"]
    steps: list[Step] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    targets: list[Target] = Field(default_factory=list)
    notes: list[PlanNote] = Field(default_factory=list)


class InstallProposal(BaseModel):
    manager: Literal["apt", "brew", "winget", "rustup", "go-archive", "npm", "pip", "report-only"]
    packages: list[str] = Field(default_factory=list)
    commands: list[Step] = Field(default_factory=list)


class RunResult(BaseModel):
    status: Literal[
        "ok",
        "build_failed",
        "invalid_input",
        "deps_missing",
        "no_runnable_output",
        "no_plan",
        "timeout",
        "cancelled",
    ]
    program_path: str | None = None
    launch_command: str | None = None
    completed_steps: list[Step] = Field(default_factory=list)
    failed_step: Step | None = None
    error_output: str | None = None
    missing: list[Requirement] = Field(default_factory=list)
    prompts_asked: int = 0
    log_path: str = ""
