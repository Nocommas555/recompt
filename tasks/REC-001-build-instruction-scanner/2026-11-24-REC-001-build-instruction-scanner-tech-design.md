# REC-001: Build Instruction Scanner - Technical Design

**Status**: Approved (2026-11-24)
**PRD**: [2026-11-24-REC-001-build-instruction-scanner-prd.md](2026-11-24-REC-001-build-instruction-scanner-prd.md)
**Created**: 2026-11-24

## Overview

recompt is a Python command-line program. A run is a fixed pipeline:

```
resolve source -> detect findings -> build plan -> dependency proposal
   -> (preview: print and stop) -> confirm -> start runner -> execute
   -> collect result -> stop runner -> report
```

Each stage is a separate module with typed input and output (Pydantic
models), so stages can be tested alone. Ecosystem knowledge lives in
small **detector** classes, one per ecosystem or file format. Where
commands run is hidden behind a **Runner** interface: a container
runner (Linux) and a host runner (macOS, Windows). README prose is read
through an **LLM backend** interface with Claude and Ollama
implementations.

## Current Architecture (verified)

- No code in the repository: one commit, `9b3d117` (empty README and
  `.gitignore`) — verified via: `git log --oneline -10`, 2026-11-24
- No code index — verified via: `rlm_repl status` (exit 2), 2026-11-24
- Development machine has git and Python 3.12 but no Docker or Podman
  — verified via: `--version` checks, 2026-11-24. Integration tests for
  the container runner need one installed.

PRD assumptions resolved here:

| PRD assumption | Resolution |
|---|---|
| FR-1 needs a git client | recompt calls the `git` command; missing git is a missing dependency. |
| FR-2 prose needs an LLM | Pluggable backend below; none available -> prose fallback off, run says so. |
| FR-12 needs a container runtime | Podman, else Docker, found on `PATH`. |
| Built program may not run on host | Image matches the host's distribution release (Container runner). |
| Repo text sent to an LLM | Only with the Claude backend; printed before sending. Ollama stays local. |
| FR-8 exit codes, FR-9 time limit | Defined in Interfaces. |
| Benchmark repo set | Selection rules in Testing Strategy; the pinned list is a task deliverable. |

## Proposed Design

### Layers

| Layer | Modules |
|---|---|
| Interface | `cli` (arguments, prompts, exit codes), `report` (console and log) |
| Application | `pipeline` (stage order, time limit, cancellation) |
| Domain | `models`, `detectors/*`, `planner`, `deps`, `launch` |
| Infrastructure | `source`, `runners/*`, `pkgmgr/*`, `llm/*`, `config`, `proc` |

Domain modules never start processes or use the network; tests replace
infrastructure with fakes. Only `cli` prompts or exits.

### Components

1. **SourceResolver** (`recompt/source.py`)
   - Local folder: used in place; the report warns that build output is
     written there.
   - Git URL normalization: credentials are stripped from the URL before
     it is used in the cache path or any log. A GitHub page URL
     (`/tree/<rest>` or `/blob/<rest>`) is resolved by matching the
     longest prefix of `<rest>` against `git ls-remote` branch and tag
     names, so refs containing `/` work.
   - Fetch: `git init`, `git fetch --depth 1 origin <ref>`,
     `git checkout FETCH_HEAD`. No ref -> the remote's `HEAD`. If the
     server refuses the fetch (some servers reject a bare commit ID) or
     the ref is a short commit ID, fall back to a full fetch and
     checkout. Then
     `git submodule update --init --recursive --depth 1`.
   - Cache: `<user cache dir>/recompt/src/<hash of normalized URL and
     ref>`; an existing copy is fetched and reset (FR-11).
   - Credentials: `git` runs with the user's environment, so their
     credential helper and SSH keys apply; recompt never reads them.

2. **Detectors** (`recompt/detectors/`) — read files, return `Finding`s,
   never run anything. Interface: `detect(copy: WorkingCopy, ctx:
   DetectContext) -> list[Finding]`; `ctx` carries the host OS and the
   optional LLM backend, so detectors read no global state. Registry: a
   plain ordered list in `detectors/__init__.py` (build-file detectors,
   then CI, then Dockerfile). The `readme` detector is not in the
   registry; the planner receives it as an injected callable.
   - Build files: `node` (package.json; lockfile picks npm/yarn/pnpm),
     `python` (pyproject.toml, setup.py, requirements.txt; `pip install .`
     only with a `[build-system]` table or setup.py, a `[project]` table
     without one installs just its dependencies, and a pyproject.toml with
     only `[tool.*]` settings is not a Python project), `rust`
     (Cargo.toml), `go` (go.mod), `cfamily` (CMakeLists.txt,
     meson.build, configure / configure.ac, Makefile).
   - CI (`github_actions`, `gitlab_ci`): CI steps are plan steps, with
     these rules:
     - GitHub Actions: pick the job whose `runs-on` matches the host OS
       (else a Linux job), preferring a job named like build/compile;
       in a matrix, the entry matching the host OS.
     - `uses: actions/setup-<lang>` (and `with:` version) becomes a
       `Requirement`; other `uses:` steps are skipped.
     - Steps containing `${{ ... }}` expressions are skipped and listed
       in plan notes.
     - Steps whose name or command is about testing, linting,
       formatting, coverage, uploading, deploying or publishing are
       skipped with a note; they are not needed to build the program.
     - `apt-get update` lines are dropped (base setup already updates).
     - Lines ending in `\` are joined before parsing.
     - `-DNAME=VALUE` options from CI steps that run `cmake` (including
       steps skipped for expressions) are kept when the value is fixed
       text; the planner appends them to the `cmake -S` configure step,
       except names the build file already sets, `CMAKE_BUILD_TYPE` and
       `CMAKE_PREFIX_PATH`.
     - The CI's CMake generator (`-G`) and build folder (`-B`, when fixed
       text) are applied to recompt's configure and build steps; a Ninja
       generator adds `ninja` as a requirement. Some projects only build
       with Ninja, which creates output folders that Make does not.
     - Package-install lines (`apt-get install`, `brew install`,
       `choco`/`winget install`) become one `Requirement` per package;
       on Linux the apt line is also kept as an `install` step (`sudo`
       stripped, `as_root=True`); on other OSes the deps proposal
       decides how to install.
     - A step's `shell:` (or the platform default: bash on Linux/macOS,
       pwsh on Windows) sets `Step.shell`.
     - GitLab CI: the job named like build/compile, else the first job
       with a `script:`; its `image:` is ignored.
   - `dockerfile`: `RUN` package-install lines become `Requirement`s
     only; no Dockerfile step runs (PRD).
   - `readme` (README*, INSTALL*, BUILDING*, docs/build*.md): called by
     the planner only when no other detector produced build steps.
     Selects build-related sections by heading and fenced code blocks,
     then calls the LLM backend.

3. **Planner** (`recompt/planner.py`)
   - Source priority: build files > CI > Dockerfile hints > prose. A
     lower-priority source adds requirements or fills missing steps; on
     conflict the higher source wins and a `PlanNote` records both.
   - Several runnable targets -> returned as choices for the CLI.
   - Project kind: from the highest-priority finding's ecosystem. `node`
     and `python` are `interpreted`; `rust`, `go` and `cfamily` are
     `compiled`. A plan from CI or prose only is `interpreted` when it
     has a launch step, else `compiled` when it has a build step, else
     `interpreted`.
   - Steps come from the highest-priority source that has non-install
     steps. Install steps found in CI files are not copied into the plan;
     their packages are already requirements, and the dependency
     proposal installs them. If
     that source has no build step and is not an interpreted ecosystem
     (node, python), build steps are filled from the next source that
     has them, with a note. Other sources' differing
     steps are recorded as a `conflict` note.
   - Notes from every finding are copied into `BuildPlan.notes`.

4. **Launch resolver** (`recompt/launch.py`) — interpreted projects.
   - Node: `scripts.start` -> `npm start` (or yarn/pnpm); else `bin` ->
     `node <bin>`; else `main` -> `node <main>`.
   - Python: first `[project.scripts]` entry (after `pip install .`);
     else `python -m <package>` if it has `__main__.py`; else
     `python main.py` / `app.py` if present.
   - Nothing found -> `no_runnable_output` (exit 4).

5. **Dependency proposal** (`recompt/deps.py`)
   - Linux (container): the image starts bare, so nothing is probed.
     Every requirement becomes part of the install proposal. Preview
     prints it without starting a container.
   - macOS and Windows (host): each requirement is checked with
     `shutil.which` plus the tool's version command against its minimum
     version; only missing ones are proposed.

6. **Package-manager adapters** (`recompt/pkgmgr/`)
   - Chosen by the *container image family* on Linux (always Debian or
     Ubuntu, so always apt) and by the host on macOS (brew) and Windows
     (winget).
   - apt: package names from CI install lines pass through as written;
     a small table maps about 10 toolchains (node, python, cmake, meson,
     etc.) to apt names. When CMake, Meson or Ninja has a minimum version
     (read from `cmake_minimum_required` / `meson_version`), it is
     installed from PyPI into `/opt/recompt/tools` instead, because the
     distribution's package is often older; that folder is first on
     `PATH` in the container.
   - brew, winget: the same toolchain table only. System libraries
     there are reported as missing, not installed.
   - Rust uses rustup on Linux and macOS and the `Rustlang.Rustup`
     winget package on Windows; Go uses the official archive on Linux
     (distribution packages are often too old) and the Homebrew / winget
     package elsewhere. yarn and pnpm install through `npm install -g`
     (apt's `yarn` is an unrelated program).
   - winget runs without auto-accepting license agreements, so the user
     answers winget's own agreement prompt.
   - Known limit: Ubuntu 24.04's apt `nodejs` is version 18; Node
     projects that need a newer runtime fail in the container (no
     newer-Node installer yet).
   - On Linux the proposal covers every requirement, so CI `install`
     steps are not run separately (they would install the same
     packages again).
   - Native C/C++ toolchains (Xcode command-line tools, MSVC Build
     Tools): installed when the adapter can do so non-interactively
     (winget for MSVC Build Tools), otherwise reported as missing.
   - Elevation: apt runs as root inside the container. brew needs none.
     winget may show its own UAC prompt; recompt never elevates itself.
   - After installs on the host, recompt rebuilds `PATH` for its own
     process: known toolchain folders (cargo, Go, Homebrew prefix) plus,
     on Windows, the user and machine `PATH` from the registry.

7. **Runners** (`recompt/runners/`) — interface: `start()`,
   `run(step) -> StepResult`, `kill()`, `stop()`. The working copy is
   mounted or used in place, so there is no copy-out step.
   - **ContainerRunner** (Linux):
     - Runtime: `podman` on `PATH`, else `docker`. Neither -> exit 3
       unless the user chose the explicit host build.
     - Rootless detection: `podman info` / `docker info`. Rootless Podman
       also needs a subordinate UID/GID range for the user in
       `/etc/subuid` and `/etc/subgid`; without one it cannot unpack
       images, so recompt stops with exit 3 and prints the `usermod`
       fix.
     - Image: from `/etc/os-release`, using `UBUNTU_CODENAME` or
       `DEBIAN_CODENAME` when present (covers Pop!_OS, Mint and other
       derivatives), else `ID` + `VERSION_ID` for Ubuntu and Debian.
       Always fully qualified (`docker.io/library/ubuntu:<codename>`).
       Unknown distro, or a failed pull (for example an end-of-life
       release) -> latest Ubuntu LTS, with a warning that the program
       may not run on the host.
     - Start: `run -d --rm --init --name recompt-<run id>
       --label recompt=1 --security-opt no-new-privileges
       --security-opt label=disable -v <copy>:/src -w /src <image>
       sleep infinity`. `--init` lets the container stop at once;
       the label lets leftovers be found and removed. `label=disable`
       keeps bind mounts working on SELinux hosts without relabelling
       the user's folder.
     - Base setup (first step, root): `DEBIAN_FRONTEND=noninteractive`,
       install `ca-certificates git curl build-essential`, create
       `/opt/recompt/home` (writable by the build user), and
       `git config --system safe.directory '*'`.
     - Environment for every step: `HOME=/opt/recompt/home`;
       `CARGO_HOME`, `RUSTUP_HOME`, `GOPATH`, `npm_config_cache`,
       `PIP_CACHE_DIR` under `/opt/recompt`; their `bin` folders on
       `PATH`. Toolchains installed as root land in `/opt` and are
       readable by the build user.
     - Users: `install` steps run as root with working directory `/`
       and must not write into `/src`. All other steps run as the build
       user, which must map to the host user:

       | Runtime mode | Build-user option | Host owner of new files |
       |---|---|---|
       | Rootless Podman | `--userns=keep-id` at start | host user |
       | Rootful Docker or Podman | `exec --user <uid>:<gid>` | host user |
       | Rootless Docker | no `--user` (container root) | host user |

     - Kill (timeout or Ctrl-C): `rm -f` the container. Killing the
       local `exec` client does not stop the process inside it.
     - Interpreted projects: after setup, the container is committed to
       `recompt/<first 12 hex of sha256(url + ref)>`. The launch command
       runs that image with `--rm -it`, the same mount, user and
       environment, `-w /src`, and the resolved launch command replacing
       the image's idle command. Ports are not mapped in v1; the report
       says so when a Dockerfile `EXPOSE` or a common web framework is
       detected.
   - **HostRunner** (macOS, Windows, explicit host build):
     - Exec form: the program is resolved with `shutil.which` first
       (finds `npm.cmd` on Windows).
     - Shells: `sh`/`bash` on POSIX; on Windows `bash` means Git for
       Windows' bash, found next to `git.exe`, never `System32\bash.exe`
       (WSL); `pwsh` falls back to `powershell`; `cmd` -> `cmd /c`.
   - Process control (`recompt/proc.py`, used by HostRunner and for
     runtime client calls):
     - POSIX: children start in their own session; on timeout or Ctrl-C
       recompt sends SIGTERM, then SIGKILL, to the whole process group.
       Ctrl-C reaches recompt, which forwards it this way.
     - Windows: `CREATE_NEW_PROCESS_GROUP`; on timeout or Ctrl-C,
       `taskkill /T /F /PID <pid>` ends the whole process tree.

8. **Result collector** (`recompt/collect.py`)
   - Compiled: the detector's expected output path when the ecosystem
     defines one (Cargo `target/release/<bin>`, Go `-o`). Otherwise
     executable files modified after the run started, excluding `.git`,
     `node_modules`, `.venv`, `venv`, `vendor`, `__pycache__`,
     `target/debug`, every folder named `CMakeFiles` at any depth (CMake
     compiler-probe executables live there, and CI build folders such as
     `build/release` put it below `build/`), and the toolchain folders
     under `/opt/recompt`. When any candidate sits inside a folder named
     `bin`, only those candidates are kept, so test and helper binaries
     elsewhere in the build tree do not crowd out the app. "Executable" means the
     executable bit on POSIX and `.exe` on Windows. Several candidates
     -> ask; none -> exit 4.
   - Interpreted: the launch resolver's command.

9. **LLM backends** (`recompt/llm/`: `base.py`, `claude.py`, `ollama.py`)
   - Interface: `extract_plan(sections) -> ExtractedPlan`, one Pydantic
     model shared by both backends.
   - Claude: `anthropic.Anthropic().messages.parse(model=<config>,
     output_format=ExtractedPlan, ...)`, result in
     `response.parsed_output`; credentials from the SDK's environment
     lookup. — verified via: claude-api skill,
     `python/claude-api/tool-use.md`, 2026-11-24
   - Ollama: `ollama.chat(model=<config>, format=ExtractedPlan.
     model_json_schema(), options={"temperature": 0})`, then
     `ExtractedPlan.model_validate_json(response.message.content)`.
     — verified via: Context7 `/ollama/ollama-python`, 2026-11-24
   - Model IDs live in config (Claude default `claude-opus-5-5`, Ollama
     default `llama3.1:8b`).
     Selection: `llm.backend = auto | claude | ollama | none`; `auto`
     tries Claude credentials, then a local Ollama server, then none.
   - The model gets no tools; every extracted step has
     `needs_confirm=True` (prompt-injection mitigation).
   - Claude refusals are not retried with server-side fallbacks: that
     option is documented only on the beta client, not with
     `messages.parse`, so a refusal makes the prose fallback unavailable
     for the run. A missing Claude key surfaces from the SDK as a plain
     `TypeError` and is mapped to `LLMUnavailable`.
   - Both SDKs are optional extras (`recompt[claude]`,
     `recompt[ollama]`), imported only when selected.

### Data Models (`recompt/models.py`)

```python
class Source(Enum): BUILD_FILE, CI, DOCKERFILE, PROSE

class Requirement(BaseModel):
    tool: str
    min_version: str | None
    source: Source
    origin: str                  # file and line

class Step(BaseModel):
    kind: Literal["install", "setup", "build", "launch"]
    command: list[str] | str     # list = exec form, str = shell script
    shell: Literal["exec", "sh", "bash", "pwsh", "cmd"]
    cwd: str                     # relative to working copy
    as_root: bool                # True only for kind == "install" in the container
    source: Source
    origin: str
    needs_confirm: bool          # True for every PROSE step

class Target(BaseModel):
    name: str
    expected_path: str | None    # relative to working copy; None = find by collector

class PlanNote(BaseModel):
    kind: Literal["conflict", "skipped", "unavailable", "warning"]
    message: str
    sources: list[str]           # origins involved

class Finding(BaseModel):
    detector: str
    ecosystem: str | None
    requirements: list[Requirement]
    steps: list[Step]
    targets: list[Target]
    notes: list[PlanNote]

class WorkingCopy(BaseModel):
    path: str
    in_place: bool               # True for a local folder
    url: str | None              # normalized, credentials removed
    ref: str | None

class DetectContext(BaseModel):
    host_os: Literal["linux", "macos", "windows"]
    llm: Any | None              # LLMBackend, only used by the readme detector

class StepResult(BaseModel):
    step: Step
    exit_code: int
    output_tail: str             # last lines of combined output
    duration_s: float

class ExtractedPlan(BaseModel):  # LLM output schema
    requirements: list[ExtractedRequirement]   # tool, min_version
    steps: list[ExtractedStep]                 # kind (setup|build|launch), command, shell, cwd

class BuildPlan(BaseModel):
    project_kind: Literal["compiled", "interpreted"]
    steps: list[Step]
    requirements: list[Requirement]
    targets: list[Target]
    notes: list[PlanNote]

class InstallProposal(BaseModel):
    manager: Literal["apt", "brew", "winget", "rustup", "go-archive", "report-only"]
    packages: list[str]
    commands: list[Step]

class RunResult(BaseModel):
    status: Literal["ok", "build_failed", "invalid_input", "deps_missing",
                    "no_runnable_output", "no_plan", "timeout", "cancelled"]
    program_path: str | None
    launch_command: str | None
    completed_steps: list[Step]
    failed_step: Step | None
    error_output: str | None
    missing: list[Requirement]
    prompts_asked: int           # excludes install and prose confirmations
    log_path: str
```

The README detector converts `ExtractedPlan` into a `Finding`, setting
`source=PROSE`, `needs_confirm=True` and `origin` to the README file.

### Interfaces

- Options: ref, preview, explicit host build, per-step time limit, LLM
  backend, and `--yes` for installs.
- `--yes` approves install proposals only. Prose steps always need an
  interactive confirmation; without a terminal they are refused, and a
  plan that depends on them ends with exit 5.
- Default time limit: 30 minutes per step, install steps included.
- Exit codes:

| Code | Meaning |
|---|---|
| 0 | Runnable result produced |
| 1 | A build step failed |
| 2 | Invalid input |
| 3 | Dependencies not installed (declined, report-only, or no container runtime) |
| 4 | No runnable program or launch command |
| 5 | No plan that can run |
| 6 | Step time limit exceeded |
| 130 | Cancelled |

### Sequence

```
cli ──> pipeline.run(input, options)
          ├─ source.resolve(input) ───────────> WorkingCopy       (2)
          ├─ detectors ───────────────────────> [Finding]
          ├─ planner.build(findings)
          │     └─ no steps? readme + llm ────> [Finding]         (5 if none)
          ├─ several targets? cli.ask_target()
          ├─ deps.propose(plan) ──────────────> [InstallProposal] (no runner needed)
          ├─ preview? report.plan(); exit 0
          ├─ cli.confirm(installs, prose steps)                   (3 / 5)
          ├─ runner.start()                                       (3 if no runtime)
          ├─ for step: runner.run(step)                           (1 / 6 / 130)
          ├─ collect.result(plan) ────────────> RunResult         (4)
          └─ finally: runner.stop(); report.result(); exit code
```

### Pipeline rules

- Install steps come only from the dependency proposal; a plan's own
  `install` steps (CI package lines) are never run directly.
- Report-only dependencies are listed as a warning and the run
  continues; a later build failure shows whether they mattered.
- With `--host-build` on Linux, missing tools are only reported;
  recompt never runs apt as root on the host.
- Launch steps are never run; v1 returns the launch command.

### Error Handling

- Each stage raises a `RecomptError` subclass carrying its exit code
  and message; `cli` catches it once. No other module calls `sys.exit`.
- `runner.stop()` runs in `finally`; on timeout and Ctrl-C the
  pipeline calls `runner.kill()` first.
- LLM errors (no credentials, rate limit, server down, invalid output)
  turn the prose fallback off for the run; the run ends with exit 5 if
  nothing else produced a plan. Claude errors are caught
  most-specific first (`RateLimitError`, `APIStatusError`,
  `APIConnectionError`); Ollama `ResponseError` and Pydantic
  `ValidationError` are handled the same way.
- Installed packages and partial output are not undone; the log lists
  every command run.

### Testing Strategy

- **Unit** (`pytest`): every detector against fixture projects in
  `tests/fixtures/<ecosystem>/<case>/`, including CI rule cases (job
  selection, skipped `${{ }}` steps, `sudo` stripping); planner merge
  and conflict rules; launch resolver; URL normalization and ref
  resolution; os-release to image mapping; runtime-mode to user-option
  table; exit-code mapping. Runners, git and LLMs are fakes.
- **LLM fixtures**: README fixtures with expected `ExtractedPlan`s;
  recorded responses in unit tests; a live test (marker `llm`) runs
  both backends when available.
- **Integration**: one small real project per ecosystem built end to
  end, container runner on Linux and host runner on macOS and Windows.
  Container tests also check: only the working copy is mounted, new
  files belong to the host user, no container is left after a timeout
  or Ctrl-C, and a canary folder on the host is unchanged (NFR-3).
- **Benchmark** (marker `benchmark`): per OS, 3 public repositories per
  ecosystem (15 total), each a command-line or desktop app with a
  documented build and at least moderate use, pinned to a commit. The
  pinned list is produced in the task phase. The report gives success
  rate against the PRD targets and average `prompts_asked`.
- **CI**: GitHub Actions matrix on `ubuntu-latest`, `macos-latest`,
  `windows-latest` running unit and integration tests (NFR-4).

### Verification Approach

| Requirement | Method | Scope | Expected Evidence |
|-------------|--------|-------|-------------------|
| FR-1: inputs, refs, GitHub page URLs, submodules | `auto-test` | unit + integration | pytest: source tests pass |
| FR-2: detectors incl. CI rules and prose fallback | `auto-test` | unit | pytest: one passing test per fixture |
| FR-3: plan with sources; preview runs nothing | `auto-test` | unit | pytest: preview test records zero runner and process calls |
| FR-4: compiled build, program path | `auto-test` | integration | pytest: per-ecosystem builds pass on each OS |
| FR-5: interpreted setup and launch command | `auto-test` | integration | pytest: Node and Python fixtures return a working launch command |
| FR-6: install only after confirm | `auto-test` | unit + integration | pytest: decline -> exit 3, no install step run |
| FR-7: three OSes | `auto-test` | CI matrix | GitHub Actions: three green jobs |
| FR-8: exit codes | `auto-test` | unit | pytest: one test per code |
| FR-9: time limit | `auto-test` | unit + integration | pytest: sleeping step -> exit 6, process tree gone |
| FR-10: Ctrl-C | `manual-run-claude` | integration | interrupted run exits 130, lists completed steps, no container left |
| FR-11: reuse working copy | `auto-test` | integration | pytest: second run fetches into the same folder |
| FR-12: Linux sandbox | `docker` | integration | pytest: mount list, file ownership, canary folder unchanged |
| Benchmark targets | `manual-run-user` | benchmark | report: Linux ≥ 14/15, macOS ≥ 11/15, Windows ≥ 11/15 |

## Trade-offs

1. **One container per run (chosen) vs one per step**: per-step gives
   clean state but needs an image rebuilt between steps to keep
   installed tools; one container is simpler and faster.
2. **Build-files-first, prose as fallback (chosen, per PRD) vs
   LLM-first**: deterministic for the common case; the LLM, with its
   cost, variance and injection risk, runs only when nothing else does.
3. **Plain detector list (chosen) vs entry-point plugins**: plugins
   would let third parties add ecosystems, which nobody needs yet.
4. **Probe-free Linux proposal (chosen) vs probing inside the
   container**: a fresh image has no toolchains, so probing would only
   start a container to learn that; skipping it keeps preview free of
   side effects.
5. Language (Python) and image strategy (host-distro image) are user
   decisions; see Decisions Taken.

## Implementation Constraints

- Python 3.11 or later (`tomllib`).
- Domain modules read only files in the working copy.
- Only `cli` prompts or exits.

## Files to Create

- `pyproject.toml` — metadata, dependencies, extras, `recompt` console
  script, pytest markers
- `recompt/{__init__,__main__,cli,report,pipeline,models,errors,config,proc}.py`
- `recompt/{source,planner,deps,launch,collect}.py`
- `recompt/detectors/{__init__,node,python,rust,go,cfamily,github_actions,gitlab_ci,dockerfile,readme}.py`
- `recompt/runners/{__init__,base,container,host}.py`
- `recompt/pkgmgr/{__init__,apt,brew,winget,toolchains}.py`
- `recompt/llm/{__init__,base,claude,ollama}.py`
- `tests/` (unit, `fixtures/`, `integration/`, `benchmark/repos.yaml`)
- `.github/workflows/ci.yml`

**Modify**: `README.md`, `.gitignore` (Python build and cache output).

## Dependencies

- `pydantic` v2, `PyYAML`, `platformdirs`; optional `anthropic`,
  `ollama`; dev `pytest`. Standard library: `argparse`, `tomllib`,
  `subprocess`, `shutil`, `signal`, `logging`. Versions are pinned in
  `pyproject.toml` during implementation.
- System: `git`; on Linux `podman` or `docker`.

## Security Considerations

- macOS and Windows: no isolation in v1 (PRD decision).
- Linux: only the working copy is mounted; no privileged mode,
  `no-new-privileges`, build steps as the mapped host user. Network is
  on for dependency downloads, so the container limits damage but is
  not a full security boundary.
- LLM output never runs without interactive confirmation; the model
  has no tools. With Claude, selected README sections leave the
  machine, and the run says so first.
- Credentials are stripped from URLs in logs and paths; recompt never
  reads git credentials or API keys itself.

## Performance Considerations

- Shallow fetch of exactly one ref keeps downloads small.
- Toolchain installs in a fresh container dominate run time (minutes
  for Rust or C++). Caching prepared images per distro and ecosystem is
  a later improvement, not v1.

## Rollback Plan

First code in the repository; rollback is reverting the implementation
commits. On a user's machine recompt leaves its cache folder, committed
images (label `recompt=1`), and any confirmed host installs.

## Decisions Taken

- Python (user, 2026-11-24).
- Pluggable LLM, Claude and Ollama (user, 2026-11-24).
- Podman preferred, Docker fallback (user, 2026-11-24).
- Image matches host distribution release (user, 2026-11-24).
- From the review (Claude, 2026-11-24): `pipx` distribution for v1;
  30-minute default step limit including installs; native C/C++
  toolchains on macOS/Windows installed when possible, else reported;
  3 benchmark repos per ecosystem per OS; `--json` output dropped (not
  in the PRD); no copy-out step (mount is read-write); one container
  per run.

---

**Next Steps**:
1. Review and approve design
2. Run `/embo:tasks` for task breakdown
