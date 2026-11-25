# build-instruction-scanner - Task List

## Relevant Files

- [2026-11-24-REC-001-build-instruction-scanner-tech-design.md](2026-11-24-REC-001-build-instruction-scanner-tech-design.md)
  :: Build Instruction Scanner - Technical Design
- [2026-11-24-REC-001-build-instruction-scanner-prd.md](2026-11-24-REC-001-build-instruction-scanner-prd.md)
  :: Build Instruction Scanner - Product Requirements Document
- [pyproject.toml](../../pyproject.toml) :: Package metadata, dependencies,
  extras `claude` / `ollama`, `recompt` console script, pytest markers
- [recompt/models.py](../../recompt/models.py) :: Pydantic models from the
  design's Data Models section
- [recompt/errors.py](../../recompt/errors.py) :: `RecomptError` subclasses
  with exit codes
- [recompt/config.py](../../recompt/config.py) :: Config file and defaults
- [recompt/source.py](../../recompt/source.py) :: SourceResolver
- [recompt/detectors/](../../recompt/detectors/) :: Detector interface,
  registry, one module per ecosystem / file format
- [recompt/llm/](../../recompt/llm/) :: LLM backend interface, Claude and
  Ollama backends, backend selection
- [recompt/planner.py](../../recompt/planner.py) :: Merges findings into a
  BuildPlan
- [recompt/launch.py](../../recompt/launch.py) :: Launch command resolver
- [recompt/deps.py](../../recompt/deps.py) :: Install proposals
- [recompt/pkgmgr/](../../recompt/pkgmgr/) :: apt, brew, winget, toolchain
  table, rustup / Go-archive installers
- [recompt/proc.py](../../recompt/proc.py) :: Cross-OS process start, time
  limit, process-tree kill
- [recompt/runners/](../../recompt/runners/) :: Runner interface, factory,
  ContainerRunner, HostRunner
- [recompt/collect.py](../../recompt/collect.py) :: Finds the built program
- [recompt/pipeline.py](../../recompt/pipeline.py) :: Runs the stages
- [recompt/cli.py](../../recompt/cli.py) :: Arguments, prompts, exit codes
- [recompt/report.py](../../recompt/report.py) :: Console and log output
- [tests/](../../tests/) :: Unit tests mirroring `recompt/`; `fixtures/`,
  `integration/`, `benchmark/`
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml) :: Test matrix
- [README.md](../../README.md) :: User-facing install and usage

## Notes

- Build order: layer by layer (user decision, 2026-11-24). Each layer is
  finished and unit-tested before the next; end-to-end runs start in 9.0.
- Tests live in `tests/`, mirroring the package path
  (`recompt/planner.py` -> `tests/test_planner.py`). `pytest` runs unit
  tests; `pytest tests/test_planner.py` runs one file.
- Markers: `integration` (real builds), `container` (needs Podman or
  Docker), `llm` (needs Claude credentials or a local Ollama), `benchmark`.
  Default `pytest` runs unit tests only.
- Unit tests replace git, runners, package managers, runtimes and LLMs
  with fakes. OS-specific code takes the OS (and `which`, registry
  reader, etc.) as injected parameters, so Windows and macOS branches
  are unit-tested on Linux; real Windows/macOS runs happen in 10.4.
- Domain modules (`detectors`, `planner`, `launch`, `deps`) must not start
  processes or use the network.
- Neither Podman nor Docker is installed on the development machine
  (2026-11-24). Subtask 8.14 is the user installing one; every `docker`
  task comes after it.
- Python 3.11 or later.

## TDD Planning Guidelines

- Test public functions and module interfaces, not internals.
- Alternate: write test -> implement -> write test -> implement.
- Skip TDD for scaffolding, plain models and config files.

## Tasks

- [X] 1.0 **User Story:** As a developer, I want the project skeleton,
  shared models, errors and config in place so that every later layer
  builds on one set of types [7/7]
  - [X] 1.1 Create `pyproject.toml` (Python >= 3.11; deps pydantic v2,
    PyYAML, platformdirs; extras `claude` = anthropic, `ollama` = ollama;
    dev pytest; console script `recompt = recompt.cli:main`; markers
    `integration`, `container`, `llm`, `benchmark`, deselected by
    default) and add Python build/cache entries to `.gitignore`
    [verify: code-only]
    → setuptools backend; anthropic and ollama left unpinned until 5.6 /
      5.8 check their APIs (2026-11-24)
  - [X] 1.2 Create the package skeleton: `recompt/__init__.py`,
    `recompt/__main__.py` (calls `cli.main`), empty subpackages
    `detectors`, `runners`, `pkgmgr`, `llm`, and `tests/` with one smoke
    test; `pip install -e .[dev]` then `pytest` passes
    [verify: auto-test]
    → smoke tests: 2 passed [live] (2026-11-24)
  - [X] 1.3 Implement `recompt/models.py` with every model and field in
    the design's Data Models section: Source, Requirement, Step (incl.
    `shell`, `as_root`), Target, PlanNote, Finding (incl. `notes`),
    WorkingCopy, DetectContext, StepResult, ExtractedRequirement,
    ExtractedStep, ExtractedPlan, BuildPlan, InstallProposal, RunResult
    (incl. `completed_steps`, `missing`, `prompts_asked`)
    [verify: code-only]
    → models build; ExtractedPlan JSON schema generates [live] (2026-11-24)
  - [X] 1.4 Write tests for `recompt/errors.py`: InvalidInputError 2,
    BuildFailedError 1, DepsMissingError 3, NoRunnableOutputError 4,
    NoPlanError 5, StepTimeoutError 6, CancelledError 130; each carries
    its code and a message [verify: auto-test]
    → 8 tests written, failed before errors.py existed [live] (2026-11-24)
  - [X] 1.5 Implement `recompt/errors.py` to pass 1.4 [verify: auto-test]
    → test_errors: 8 passed [live] (2026-11-24)
  - [X] 1.6 Write tests for `recompt/config.py`: with no file the
    defaults apply (`llm.backend="auto"`, `llm.claude_model=
    "claude-opus-5-5"`, `llm.ollama_model="llama3.1:8b"`,
    `step_timeout=1800`); a TOML file in the platformdirs config folder
    (path injected) overrides them; an invalid value raises
    InvalidInputError [verify: auto-test]
    → 6 tests written, failed before config.py existed [live] (2026-11-24)
  - [X] 1.7 Implement `recompt/config.py` to pass 1.6 [verify: auto-test]
    → full suite: 16 passed, 0 failed [live] (2026-11-24)

- [X] 2.0 **User Story:** As a user, I want recompt to turn a git URL,
  GitHub page link or local folder into a local working copy so that it
  can start from whatever source I have [10/10]
  - [X] 2.1 Write tests for input classification: existing path ->
    local; `https://`, `ssh://`, `git://`, `file://` and scp-style
    `git@host:path` -> git URL; anything else -> InvalidInputError
    [verify: auto-test]
    → 7 classification tests written, failed before source.py existed [live] (2026-11-24)
  - [X] 2.2 Write tests for URL normalization: credentials removed from
    `https://user:token@host/...`; `.git` suffix optional; GitHub
    `/tree/<rest>` and `/blob/<rest>` resolved by the longest prefix of
    `<rest>` matching a ref from a faked `ls-remote` list (refs with `/`
    work); plain repo URL has no ref [verify: auto-test]
    → 14 normalization tests written, failed before source.py existed [live] (2026-11-24)
  - [X] 2.3 Implement classification and normalization in
    `recompt/source.py` to pass 2.1 and 2.2; git calls go through an
    injectable callable [verify: auto-test]
    → test_source_normalize: 21 passed [live] (2026-11-24)
  - [X] 2.4 Write tests for the cache path: same URL + ref -> same
    folder; other ref -> other folder; no credentials in the path
    [verify: auto-test]
    → 2 cache-path tests written, failed before implementation [live] (2026-11-24)
  - [X] 2.5 Implement the cache path (platformdirs cache dir +
    `recompt/src/<hash of normalized URL and ref>`) [verify: auto-test]
    → cache-path tests pass [live] (2026-11-24)
  - [X] 2.6 Write tests, with the git callable faked, for fetching: new
    copy -> `init`, `fetch --depth 1 origin <ref>`, `checkout
    FETCH_HEAD`, `submodule update --init --recursive --depth 1`; no ref
    -> fetches `HEAD`; short commit ID or a refused fetch -> full fetch
    then checkout; existing copy -> fetch and reset, no `init`; unknown
    ref or unreachable URL -> InvalidInputError naming the input
    [verify: auto-test]
    → 8 fetch tests written with a fake git, failed before implementation [live] (2026-11-24)
  - [X] 2.7 Implement fetching to pass 2.6 [verify: auto-test]
    → test_source_fetch: 12 passed; full suite 49 passed [live] (2026-11-24)
  - [X] 2.8 Write tests for local folders: existing folder ->
    WorkingCopy with `in_place=True` and nothing copied; missing folder
    -> InvalidInputError [verify: auto-test]
    → 2 local-folder tests written, failed before implementation [live] (2026-11-24)
  - [X] 2.9 Implement local-folder handling to pass 2.8
    [verify: auto-test]
    → local-folder tests pass [live] (2026-11-24)
  - [X] 2.10 Integration test (marker `integration`): clone a small
    public repo at a tag and at a commit; run again and confirm the same
    folder is reused [verify: auto-test]
    → real clone at a tag and at a commit, then reuse of the same folder: 1 passed [live] (2026-11-24)

- [X] 3.0 **User Story:** As a user, I want recompt to read the build
  files of Node, Python, Rust, Go and C/C++ projects so that common
  projects get a reliable plan [11/11]
  - [X] 3.1 Define the detector interface in
    `recompt/detectors/__init__.py`: `detect(copy: WorkingCopy, ctx:
    DetectContext) -> list[Finding]`, plus the ordered registry list
    (filled in 3.11 and 4.7; `readme` is never in it)
    [verify: code-only]
    → plain-function interface detect(copy, ctx) plus REGISTRY and detect_all (2026-11-24)
  - [X] 3.2 Write tests for the `node` detector with fixtures: npm, yarn
    and pnpm picked by lockfile; `engines.node` -> Requirement min
    version; install step; `scripts.build` -> build step; no
    `package.json` -> no finding [verify: auto-test]
    → 8 node tests written, failed before node.py existed; fixtures built in tmp folders instead of tests/fixtures [live] (2026-11-24)
  - [X] 3.3 Implement `recompt/detectors/node.py` [verify: auto-test]
    → node tests pass [live] (2026-11-24)
  - [X] 3.4 Write tests for the `python` detector: pyproject with
    `requires-python` -> min version; setup.py only; requirements.txt
    only; setup steps create a virtual environment and install into it
    [verify: auto-test]
    → 6 python tests written, failed before python.py existed [live] (2026-11-24)
  - [X] 3.5 Implement `recompt/detectors/python.py` [verify: auto-test]
    → python tests pass [live] (2026-11-24)
  - [X] 3.6 Write tests for the `rust` detector: one binary -> target
    `target/release/<bin>`; several `[[bin]]` -> several targets;
    `rust-version` -> min version; build step `cargo build --release`
    [verify: auto-test]
    → 5 rust tests written, failed before rust.py existed [live] (2026-11-24)
  - [X] 3.7 Implement `recompt/detectors/rust.py` [verify: auto-test]
    → rust tests pass [live] (2026-11-24)
  - [X] 3.8 Write tests for the `go` detector: `go` directive -> min
    version; one `main` package -> `go build -o <out>` and that target;
    several `cmd/*` mains -> several targets [verify: auto-test]
    → 4 go tests written, failed before go.py existed [live] (2026-11-24)
  - [X] 3.9 Implement `recompt/detectors/go.py` [verify: auto-test]
    → go tests pass [live] (2026-11-24)
  - [X] 3.10 Write tests for the `cfamily` detector: CMake, Meson,
    autotools (`configure` / `configure.ac`) and plain Makefile each
    give the build tool as a Requirement plus configure/build steps;
    CMake wins when several exist, and a note records the others
    [verify: auto-test]
    → 9 cfamily tests written, failed before cfamily.py existed [live] (2026-11-24)
  - [X] 3.11 Implement `recompt/detectors/cfamily.py` and register the
    five build-file detectors in order [verify: auto-test]
    → registry test passes; full suite 82 passed [live] (2026-11-24)

- [X] 4.0 **User Story:** As a user, I want recompt to read GitHub
  Actions, GitLab CI and Dockerfiles so that projects without standard
  build files still get steps and requirements [7/7]
  - [X] 4.1 Write tests for GitHub Actions job selection using
    `ctx.host_os`: job whose `runs-on` matches the host OS, else the
    first Linux job; in a matrix, the entry matching the host OS
    [verify: auto-test]
    → 4 job-selection tests written, failed before github_actions.py existed [live] (2026-11-24)
  - [X] 4.2 Write tests for GitHub Actions step rules: `uses:
    actions/setup-<lang>` + `with:` version -> Requirement; other
    `uses:` skipped; steps with `${{ }}` skipped with a `skipped` note;
    `apt-get install`, `brew install`, `choco install` and `winget
    install` lines -> one Requirement per package; on Linux the apt line
    is also an install Step with `sudo` removed and `as_root=True`;
    `shell:` or the platform default (bash; pwsh on Windows) sets
    `Step.shell`; every step has `source=CI` [verify: auto-test]
    → 7 step-rule tests written; also skips test/lint/upload steps (added to design) [live] (2026-11-24)
  - [X] 4.3 Implement `recompt/detectors/github_actions.py` to pass 4.1
    and 4.2 [verify: auto-test]
    → github_actions tests: 14 passed; live on ripgrep picks the Linux job [live] (2026-11-24)
  - [X] 4.4 Write tests for GitLab CI: job named like build/compile,
    else the first job with `script:`; `image:` ignored; install lines
    handled as in 4.2 [verify: auto-test]
    → 2 GitLab tests written, failed before gitlab_ci.py existed [live] (2026-11-24)
  - [X] 4.5 Implement `recompt/detectors/gitlab_ci.py`
    [verify: auto-test]
    → GitLab tests pass [live] (2026-11-24)
  - [X] 4.6 Write tests for the Dockerfile detector: `RUN` lines with
    `apt-get`, `apk` or `dnf` install -> Requirements only, no steps;
    `EXPOSE` -> a `warning` note that ports are not mapped
    [verify: auto-test]
    → 2 Dockerfile tests written, failed before dockerfile.py existed [live] (2026-11-24)
  - [X] 4.7 Implement `recompt/detectors/dockerfile.py`; register
    `github_actions`, `gitlab_ci`, `dockerfile` after the build-file
    detectors [verify: auto-test]
    → registered after build-file detectors; full suite 102 passed; live ripgrep run found a workspace rust-version bug, fixed with a test [live] (2026-11-24)

- [ ] 5.0 **User Story:** As a user, I want recompt to fall back to
  README instructions through Claude or Ollama so that projects that
  only document their build in prose still work [12/11]
  - [X] 5.1 Define `recompt/llm/base.py`: `LLMBackend` protocol with
    `name` and `extract_plan(sections) -> ExtractedPlan`;
    `LLMUnavailable` error [verify: code-only]
    → LLMBackend protocol, LLMUnavailable, DocSection, shared prompt (2026-11-24)
  - [X] 5.2 Write tests for README section selection in
    `recompt/detectors/readme.py`: files README*, INSTALL*, BUILDING*,
    docs/build*.md; keep sections whose heading matches
    build/install/compile/usage/getting started, with their fenced code
    blocks; drop the rest [verify: auto-test]
    → 4 section-selection tests written, failed before readme.py existed [live] (2026-11-24)
  - [X] 5.3 Implement section selection to pass 5.2 [verify: auto-test]
    → section selection passes, incl. # comments inside code fences [live] (2026-11-24)
  - [X] 5.4 Write tests for the README detector with a fake backend:
    ExtractedPlan converted to a Finding; every step `source=PROSE`,
    `needs_confirm=True`, `origin` = the README file; backend raising
    `LLMUnavailable` -> a Finding with no steps and an `unavailable`
    note; `ctx.llm` is None -> same note [verify: auto-test]
    → 4 README-detector tests written with a fake backend [live] (2026-11-24)
  - [X] 5.5 Implement the README detector to pass 5.4
    [verify: auto-test]
    → README detector tests pass [live] (2026-11-24)
  - [X] 5.6 Write tests for `recompt/llm/claude.py` with the Anthropic
    client faked: calls `messages.parse` with the configured model,
    `max_tokens=16000`, `output_format=ExtractedPlan`; returns
    `parsed_output`; `RateLimitError`, `APIStatusError`,
    `APIConnectionError`, missing credentials and a missing `anthropic`
    package each raise `LLMUnavailable` [verify: auto-test]
    → 8 Claude backend tests written against anthropic 2.13 error classes [live] (2026-11-24)
  - [X] 5.7 Implement `recompt/llm/claude.py` (lazy import) to pass 5.6
    [verify: auto-test]
    → Claude backend passes; live no-credentials run exposed a TypeError, now mapped to LLMUnavailable [live] (2026-11-24)
  - [X] 5.8 Write tests for `recompt/llm/ollama.py` with the client
    faked: calls `chat(model=<config>, format=ExtractedPlan.
    model_json_schema(), options={"temperature": 0})` and returns
    `ExtractedPlan.model_validate_json(...)`; `ResponseError`, connection
    errors, a missing `ollama` package and `ValidationError` raise
    `LLMUnavailable` [verify: auto-test]
    → 7 Ollama backend tests written [live] (2026-11-24)
  - [X] 5.9 Implement `recompt/llm/ollama.py` (lazy import) to pass 5.8
    [verify: auto-test]
    → Ollama backend passes; live call to a closed port gives LLMUnavailable [live] (2026-11-24)
  - [X] 5.10 Write tests for backend selection in
    `recompt/llm/__init__.py`: `none`, `claude`, `ollama` return that
    backend (or None); `auto` tries Claude credentials, then a reachable
    Ollama server (probe injected), then None [verify: auto-test]
    → 5 selection tests written [live] (2026-11-24)
  - [X] 5.11 Implement backend selection to pass 5.10
    [verify: auto-test]
    → selection passes; full suite 130 passed [live] (2026-11-24)
  - [~] 5.12 Add 4 README fixtures with expected ExtractedPlans and a
    live test (marker `llm`) that runs each available backend against
    them; the user runs it with credentials or a local Ollama
    [verify: manual-run-user]
    → local Ollama (gemma4): 4 passed incl. injection case; Claude not run
      to avoid billing; awaiting user run and confirmation (2026-11-24)

- [X] 6.0 **User Story:** As a user, I want all findings merged into
  one ordered plan with a launch command for interpreted projects so
  that I see exactly what will run and where each step came from [8/8]
  - [X] 6.1 Write tests for `recompt/planner.py` merging: the README
    detector is an injected callable, called only when no registry
    finding has build steps; priority build files > CI > Dockerfile >
    prose; lower sources only add requirements or fill missing steps; a
    conflict keeps the higher source and adds a `conflict` note naming
    both; all finding notes are copied into `BuildPlan.notes`; no steps
    at all -> NoPlanError [verify: auto-test]
    → 7 merge tests written, failed before planner.py existed [live] (2026-11-24)
  - [X] 6.2 Implement merging to pass 6.1 [verify: auto-test]
    → merge passes; build-step fill and conflict rules added to the design [live] (2026-11-24)
  - [X] 6.3 Write tests for project kind and targets: node/python ->
    `interpreted`; rust/go/cfamily -> `compiled`; CI- or prose-only plan
    -> `interpreted` with a launch step, else `compiled` with a build
    step, else `interpreted`; several targets are returned to the caller
    [verify: auto-test]
    → project-kind tests written; CI/prose-only rule corrected in design and task [live] (2026-11-24)
  - [X] 6.4 Implement project kind and targets to pass 6.3
    [verify: auto-test]
    → project kind and targets pass [live] (2026-11-24)
  - [X] 6.5 Write tests for `recompt/launch.py`: Node `scripts.start` ->
    `npm start` (`yarn start` / `pnpm start` by lockfile), else `bin`
    -> `node <bin>`, else `main` -> `node <main>`; Python first
    `[project.scripts]` entry, else `python -m <pkg>` when it has
    `__main__.py`, else `python main.py` / `app.py`; nothing -> None
    [verify: auto-test]
    → 12 launch-resolver tests written, failed before launch.py existed [live] (2026-11-24)
  - [X] 6.6 Implement `recompt/launch.py` to pass 6.5 [verify: auto-test]
    → launch resolver passes [live] (2026-11-24)
  - [X] 6.7 Write tests that the planner adds a `launch` step from the
    resolver for interpreted plans, and none when the resolver returns
    None [verify: auto-test]
    → 5 planner-launch tests written on real detector output [live] (2026-11-24)
  - [X] 6.8 Wire the resolver into the planner to pass 6.7
    [verify: auto-test]
    → wired; full suite 162 passed; live ripgrep plan: cargo build --release, target rg, CI steps noted as ignored [live] (2026-11-24)

- [X] 7.0 **User Story:** As a user, I want missing toolchains listed
  and installed only after I confirm so that nothing is installed
  without my consent [10/10]
  - [X] 7.1 Create `recompt/pkgmgr/toolchains.py`: one table for about 10
    tools (node, python, cmake, meson, ninja, make, gcc/g++, pkg-config,
    autoconf, git) giving apt, brew and winget package names, the
    version command, and the regex that extracts the version
    [verify: code-only]
    → table of 15 tools with apt/brew/winget names, binary names, version command and regex; yarn/pnpm via npm (design updated) (2026-11-24)
  - [X] 7.2 Write tests for the adapters: apt passes CI package names
    through as written and maps toolchains by table; brew and winget map
    toolchains only and mark system libraries `report-only`; Rust ->
    rustup and Go -> Go archive on every OS; MSVC Build Tools via
    winget; Xcode command-line tools `report-only` [verify: auto-test]
    → 6 adapter tests written, failed before adapters existed [live] (2026-11-24)
  - [X] 7.3 Implement `recompt/pkgmgr/{apt,brew,winget}.py` and the
    rustup / Go-archive installers to pass 7.2 [verify: auto-test]
    → adapters pass; apt -s dry run confirms every mapped package name exists [live] (2026-11-24)
  - [X] 7.4 Write tests for `recompt/deps.py` on Linux: every
    requirement goes into the proposal; nothing is probed; no runner or
    process call is made [verify: auto-test]
    → Linux no-probe test written [live] (2026-11-24)
  - [X] 7.5 Write tests for `recompt/deps.py` on macOS/Windows (OS,
    `which` and version-command runner injected): tool present and at or
    above the minimum -> skipped; missing, or below the minimum by the
    parsed version -> proposed; no supported package manager ->
    `report-only` [verify: auto-test]
    → 4 host-probe tests written with injected which/version [live] (2026-11-24)
  - [X] 7.6 Implement `recompt/deps.py` to pass 7.4 and 7.5
    [verify: auto-test]
    → deps passes; real probe here skips git/node/python and proposes cmake/ninja [live] (2026-11-24)
  - [X] 7.7 Write tests for host PATH refresh after installs: cargo, Go
    and Homebrew folders added; on Windows the user and machine PATH
    read through an injected registry reader [verify: auto-test]
    → 2 PATH-refresh tests written (POSIX, Windows registry injected) [live] (2026-11-24)
  - [X] 7.8 Implement PATH refresh to pass 7.7 [verify: auto-test]
    → PATH refresh passes [live] (2026-11-24)
  - [X] 7.9 Write and pass a test that a declined proposal produces no
    install Step in the plan handed to the runner [verify: auto-test]
    → declined and report-only proposals give no install steps: passes; full suite 179 passed [live] (2026-11-24)
  - [X] 7.10 User runs one confirmed install on the current OS (for
    example `cmake` through the adapter) and confirms the tool is found
    afterwards [verify: manual-run-user]
    → run at the user's request inside the Podman container: cmake missing
      (exit 127), apt install exit 0, then cmake 3.28.3 runs as the build
      user [live] (2026-11-24)

- [X] 8.0 **User Story:** As a user, I want steps to run in a Linux
  container, or on the host on macOS and Windows, with time limits and
  Ctrl-C handling so that builds are contained and can be stopped [17/17]
  - [X] 8.1 Write tests for `recompt/proc.py` with real child
    processes: output streamed to a callback line by line; a step past
    its time limit raises StepTimeoutError and its whole process tree,
    including a grandchild, is gone; the Windows branch
    (`CREATE_NEW_PROCESS_GROUP`, `taskkill /T /F /PID`) is tested with
    the OS and process API injected [verify: auto-test]
    → 5 process tests written with real child processes, failed before proc.py existed [live] (2026-11-24)
  - [X] 8.2 Implement `recompt/proc.py` to pass 8.1 (POSIX: new session,
    SIGTERM then SIGKILL to the group) [verify: auto-test]
    → proc tests pass; a real grandchild is gone after the timeout [live] (2026-11-24)
  - [X] 8.3 Define `recompt/runners/base.py`: `start()`,
    `run(step) -> StepResult`, `kill()`, `stop()` [verify: code-only]
    → Runner protocol plus OutputTail helper (2026-11-24)
  - [X] 8.4 Write tests for HostRunner (OS and `which` injected): exec
    form resolved with `which` (`npm.cmd` on Windows); Windows `bash` =
    Git for Windows bash next to `git.exe`, never `System32\bash.exe`;
    `pwsh` falls back to `powershell`; `cmd` -> `cmd /c`; `run()` uses
    the step's `cwd`, the given environment and the time limit
    [verify: auto-test]
    → 8 host-runner tests written [live] (2026-11-24)
  - [X] 8.5 Implement `recompt/runners/host.py` on `proc.py` to pass 8.4
    [verify: auto-test]
    → host runner passes incl. a real command and a real timeout [live] (2026-11-24)
  - [X] 8.6 Write tests for the os-release to image mapping: Pop!_OS and
    Mint via `UBUNTU_CODENAME`; Debian derivatives via
    `DEBIAN_CODENAME`; Ubuntu/Debian via `ID` + `VERSION_ID`; unknown
    distro -> latest Ubuntu LTS with a warning; names always
    `docker.io/library/...` [verify: auto-test]
    → 6 image-mapping tests written [live] (2026-11-24)
  - [X] 8.7 Implement the image mapping in `recompt/runners/container.py`
    to pass 8.6 [verify: auto-test]
    → mapping passes; this host (Pop!_OS 24.04) maps to ubuntu:noble [live] (2026-11-24)
  - [X] 8.8 Write tests for runtime detection (runtime command faked):
    `podman` on PATH wins over `docker`; neither -> DepsMissingError;
    rootless mode read from `podman info` / `docker info`; the user
    option per mode: rootless Podman -> `--userns=keep-id` at start,
    rootful Docker/Podman -> `exec --user <uid>:<gid>`, rootless Docker
    -> no `--user`; install steps always root with working directory `/`
    [verify: auto-test]
    → 7 runtime-detection and user-mapping tests written [live] (2026-11-24)
  - [X] 8.9 Implement runtime detection and the user mapping to pass 8.8
    [verify: auto-test]
    → runtime detection passes [live] (2026-11-24)
  - [X] 8.10 Write tests (runtime faked) for the container lifecycle:
    start command has `-d --rm --init`, name `recompt-<run id>`,
    `--label recompt=1`, `no-new-privileges`, `label=disable`, one mount
    at `/src`; a failed image pull retries with the latest Ubuntu LTS
    and a warning; base-setup step; every step's environment (`HOME`,
    `CARGO_HOME`, `RUSTUP_HOME`, `GOPATH`, npm and pip caches under
    `/opt/recompt`, PATH); a step past its limit -> `kill()` (`rm -f`)
    then StepTimeoutError [verify: auto-test]
    → 10 lifecycle tests written with a faked runtime [live] (2026-11-24)
  - [X] 8.11 Implement the container lifecycle to pass 8.10
    [verify: auto-test]
    → lifecycle passes; root installs run with sh -e so a failed install is not masked [live] (2026-11-24)
  - [X] 8.12 Write tests for the interpreted-project image: tag
    `recompt/<12 hex of sha256(url + ref)>`; launch command has `--rm
    -it`, the same mount, user and environment, `-w /src`, and the
    launch command in place of the idle command [verify: auto-test]
    → 2 image-tag and launch tests written [live] (2026-11-24)
  - [X] 8.13 Implement the commit and launch command to pass 8.12
    [verify: auto-test]
    → commit and launch command pass; container runner tests 25 passed [live] (2026-11-24)
  - [X] 8.14 User installs Podman (preferred) or Docker on the
    development machine and confirms `podman info` or `docker info`
    works [verify: manual-run-user]
    → Podman 4.9.3 rootless installed; image pull fails without a subuid
      range; recompt now detects this and prints the fix; awaiting the
      user's usermod step (2026-11-24)
    → user added the subuid/subgid range; detection returns rootless
      Podman [live] (2026-11-24)
  - [X] 8.15 Write tests for `recompt/runners/__init__.py` runner factory
    (OS injected): Linux -> ContainerRunner; macOS/Windows ->
    HostRunner; Linux with `host_build=True` -> HostRunner; Linux with
    no runtime and no `host_build` -> DepsMissingError; then implement
    it [verify: auto-test]
    → 5 factory tests written then implemented; full suite 223 passed [live] (2026-11-24)
  - [X] 8.16 Container integration test (markers `integration`,
    `container`): build a tiny C project; assert only `/src` is mounted,
    new files belong to the host user, a host canary folder is unchanged
    [verify: docker]
    → Podman: C project built, only /src mounted, output owned by host
      user, canary unchanged: 1 passed [live] (2026-11-24)
  - [X] 8.17 Container integration test: a step that sleeps past a short
    limit -> StepTimeoutError and no container with label `recompt=1`
    remains [verify: docker]
    → Podman: timeout raised and no recompt=1 container left: 1 passed
      [live] (2026-11-24)

- [ ] 9.0 **User Story:** As a user, I want one `recompt` command that
  runs the whole pipeline, previews the plan, and reports the program
  location or launch command with clear exit codes [15/13]
  - [X] 9.1 Write tests for `recompt/collect.py`: compiled -> expected
    target path when given; otherwise executables modified after run
    start, excluding `.git`, `node_modules`, `.venv`, `venv`, `vendor`,
    `__pycache__`, `target/debug`, `build/CMakeFiles` (`.exe` on
    Windows, executable bit on POSIX); several -> candidates; none ->
    NoRunnableOutputError; interpreted -> the plan's launch command, or
    NoRunnableOutputError when there is none [verify: auto-test]
    → 7 collector tests written, failed before collect.py existed [live] (2026-11-24)
  - [X] 9.2 Implement `recompt/collect.py` to pass 9.1
    [verify: auto-test]
    → collector passes [live] (2026-11-24)
  - [X] 9.3 Write tests for `recompt/pipeline.py` with all stages faked:
    stage order matches the design's Sequence; preview returns after the
    proposal with zero runner and process calls; the runner comes from
    the factory and `start()` runs only after confirmation; `stop()`
    runs in `finally`; timeout and Ctrl-C call `kill()` first; a
    declined install proposal -> DepsMissingError and no install step
    runs; `RunResult` carries completed steps, missing requirements and
    `prompts_asked` [verify: auto-test]
    → 16 pipeline tests written with all stages faked [live] (2026-11-24)
  - [X] 9.4 Implement `recompt/pipeline.py` to pass 9.3
    [verify: auto-test]
    → pipeline passes; install, report-only and host-build rules added to the design [live] (2026-11-24)
  - [X] 9.5 Write tests for confirmation rules in `recompt/cli.py`: on
    Linux, installs are listed but not prompted; on macOS/Windows they
    are prompted and `--yes` approves them; prose steps always need an
    interactive yes, `--yes` does not cover them; with no terminal,
    prose steps are refused -> NoPlanError; several targets -> asks
    which one [verify: auto-test]
    → 5 confirmation tests written; Linux no-prompt rule covered in pipeline tests [live] (2026-11-24)
  - [X] 9.6 Write tests for `recompt/cli.py` arguments and exit codes:
    source, `--ref`, `--preview`, `--host-build`, `--timeout`, `--llm`,
    `--yes` parsed; each RecomptError subclass -> its exit code (one test
    per code); Ctrl-C -> 130; errors caught once in `main`
    [verify: auto-test]
    → 13 argument and exit-code tests written [live] (2026-11-24)
  - [X] 9.7 Implement `recompt/cli.py` to pass 9.5 and 9.6
    [verify: auto-test]
    → cli passes [live] (2026-11-24)
  - [X] 9.8 Write tests for `recompt/report.py`: plan printout shows each
    step's source and every note; local-folder runs warn that output is
    written there; a notice is printed before README text is sent to
    Claude; a ports-not-mapped warning when the plan has that note;
    final result shows program path or launch command, or the failing
    step and its error output [verify: auto-test]
    → 4 report tests written [live] (2026-11-24)
  - [X] 9.9 Write tests for the run log: every executed command is
    written; credentials are stripped from URLs in the log
    [verify: auto-test]
    → log test written: commands logged, credentials stripped [live] (2026-11-24)
  - [X] 9.10 Implement `recompt/report.py` and the log to pass 9.8 and
    9.9 [verify: auto-test]
    → report and log pass; full suite 272 passed [live] (2026-11-24)
  - [X] 9.11 Run `recompt --preview` on a real Rust and a real Node repo;
    confirm the plan, sources and install list are printed and no
    container was started [verify: manual-run-claude]
    → preview on ripgrep and express prints plan, sources and installs, no container started; found and fixed CI job choice and interpreted build-fill bugs [live] (2026-11-24)
  - [X] 9.12 Run `recompt` on a real repo and press Ctrl-C mid-build;
    confirm exit 130, completed steps listed, no `recompt=1` container
    left [verify: docker]
    → real ripgrep run interrupted: exit 130, no recompt container left; an uninterrupted run built rg, which runs on the host [live] (2026-11-24)
  - [X] 9.13 Run `recompt --host-build` on Linux on a small repo and
    confirm it builds on the host without a container
    [verify: manual-run-claude]
    → --host-build on a local C project built with host make and no container; program runs [live] (2026-11-24)
  - [~] 9.14 User runs `recompt` end to end on one compiled and one
    interpreted repo on Linux and confirms the program runs and the
    launch command starts the app [verify: manual-run-user]
    → povesma/embo: not buildable (Claude Code plugin); after the Python
      fix recompt correctly exits 5, no plan (2026-11-24)
    → Eglantine (C++/CMake): build succeeds (exit 0, bin/eglantine and
      bin/eden-cli) after five fixes found on the way, all in the design:
      tool-config-only pyproject, CMake minimum version via PyPI, CI
      runs-on expressions / backslash lines / OS-named workflow files,
      CI -D options, CI generator and build folder; but the reported
      program is a CMake probe file, see 9.15 (2026-11-25)
    → open: no interpreted repo confirmed by the user yet; Claude-backed
      Node app check done only by Claude (2026-11-25)
  - [X] 9.15 Fix program detection: skip every folder named
    `CMakeFiles` (not only `build/CMakeFiles`) and prefer executables in
    a `bin/` folder over other candidates; regression test with a build
    tree like Eglantine's (`build/release/CMakeFiles/<ver>/*.bin` plus
    `build/release/bin/<app>`) [verify: auto-test]
    → 2 regression tests added; 292 passed, 0 failed [live] (2026-11-25)
    → on the real Eglantine build folder the old code listed 5 CMake
      probe files first, the fix lists only bin/eden-cli and bin/eglantine [live] (2026-11-25)

- [ ] 10.0 **User Story:** As a maintainer, I want end-to-end tests on
  all three OSes, a pinned benchmark set and a README so that success
  targets are measurable and users can install and run recompt [9/0]
  - [ ] 10.1 Add small fixture projects for the compiled ecosystems
    (Rust, Go, C/C++) under `tests/integration/projects/` and an
    integration test building each through the pipeline with the runner
    for the current OS [verify: docker]
  - [ ] 10.2 Add small fixture projects for the interpreted ecosystems
    (Node, Python) and an integration test that checks each returned
    launch command starts the app [verify: docker]
  - [ ] 10.3 Create `.github/workflows/ci.yml`: matrix `ubuntu-latest`,
    `macos-latest`, `windows-latest`; Python 3.11; unit and
    `integration` tests on all three, `container` tests on Ubuntu only
    [verify: code-only]
  - [ ] 10.4 Push and confirm all three CI jobs pass
    [verify: observation]
  - [ ] 10.5 Create `tests/benchmark/repos.yaml`: a separate list of 15
    public repos for each OS, 3 per ecosystem, each a command-line or
    desktop app with a documented build, pinned to a commit
    [verify: code-only]
  - [ ] 10.6 Write and pass a test that every pinned commit in
    `repos.yaml` exists on its remote (marker `integration`)
    [verify: auto-test]
  - [ ] 10.7 Implement the benchmark runner (marker `benchmark`): runs
    each repo for the current OS and writes a report with the success
    rate against the targets (Linux >= 14/15, macOS and Windows >=
    11/15) and average `prompts_asked`; unit-test the report math with
    faked results [verify: auto-test]
  - [ ] 10.8 User runs the benchmark on each OS and the results are
    recorded in the task folder [verify: manual-run-user]
  - [ ] 10.9 Write `README.md`: what recompt does, install with `pipx`
    and the `claude` / `ollama` extras, usage, exit codes, the Linux
    container requirement, what recompt leaves behind and how to remove
    it [verify: code-only]
