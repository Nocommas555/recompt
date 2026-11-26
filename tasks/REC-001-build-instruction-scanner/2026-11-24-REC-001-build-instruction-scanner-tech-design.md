# REC-001: Build Instruction Scanner - Technical Design

**Status**: Approved (2026-11-24); amended 2026-11-26 for the PRD
amendment (system-package sources, Linux distributions, plan review,
configure loop) and the independent review — amendment approved by the
user 2026-11-26
**PRD**: [2026-11-24-REC-001-build-instruction-scanner-prd.md](2026-11-24-REC-001-build-instruction-scanner-prd.md)
**Created**: 2026-11-24

## Overview

recompt is a Python command-line program. A run is a fixed pipeline:

```
resolve source -> detect findings (README read by the LLM) -> build plan
   -> dependency proposal -> (preview: print and stop)
   -> start runner -> resolve system needs to packages (Linux)
   -> plan review (approve, or --yes) -> execute
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

- At design time (2026-11-24): no code, one commit `9b3d117`, no code
  index, no Docker or Podman.
- At the 2026-11-26 amendment: Stories 1 to 8 and most of Story 9 are
  implemented on `main` (last commit `00ed337`, host library check);
  303 unit tests pass — verified via: `pytest -q`, 2026-11-25. Code
  index of 79 files — verified via: `rlm_repl status`, 2026-11-25.
  Rootless Podman works on the development machine — verified via:
  ubuntu, fedora and archlinux containers run, 2026-11-26. The
  amendment changes existing modules; the internal review lists them
  (pipeline, models, planner, deps, pkgmgr, detectors, llm, runners,
  hostlibs, cli, report and their tests).

PRD assumptions resolved here:

| PRD assumption | Resolution |
|---|---|
| FR-1 needs a git client | recompt calls the `git` command; missing git is a missing dependency. |
| FR-2 prose needs an LLM | Pluggable backend below; none available -> documents are skipped, run says so. |
| FR-12 needs a container runtime | Podman, else Docker, found on `PATH`. |
| Built program may not run on host | Image of the host's distribution and release for apt, dnf and pacman distributions; newest image on Arch; Ubuntu LTS elsewhere (Container runner); host library check after the build (Result collector). |
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
   registry; the pipeline calls it separately (see `readme` below).
   - Build files: `node` (package.json; lockfile picks npm/yarn/pnpm),
     `python` (pyproject.toml, setup.py, requirements.txt; `pip install .`
     only with a `[build-system]` table or setup.py, a `[project]` table
     without one installs just its dependencies, and a pyproject.toml with
     only `[tool.*]` settings is not a Python project), `rust`
     (Cargo.toml), `go` (go.mod), `cfamily` (CMakeLists.txt,
     meson.build, configure / configure.ac, Makefile).
   - System needs from build files (`cfamily`). Each becomes a
     `SystemNeed` (kind, name, required, origin); the Linux resolver
     turns it into a package (component 6a). Commands are matched
     without regard to case (`FIND_PATH` = `find_path`). Files read:
     the root `CMakeLists.txt`, folders named by its
     `add_subdirectory()` calls (recursively), the project's
     `CMAKE_MODULE_PATH` folders (`cmake/`, `CMake/`), and the root
     and subproject `meson.build` files. Git submodules and folders
     named `Externals`, `external`, `extern`, `third_party`,
     `thirdparty`, `vendor` and `3rdparty` are skipped, because
     bundled libraries there are built from source (Dolphin has
     hundreds of such finds):
     - `pkg_check_modules(<prefix> [REQUIRED] <module>[>=<ver>] ...)`
       and `pkg_search_module(...)` -> kind `pkgconfig`, one per module.
     - Meson `dependency('<name>', required: ...)` -> kind `pkgconfig`
       (Meson's default lookup method); Meson's built-in names
       (`threads`, `dl`, `m`, `openmp`, `boost`, `python3`) are skipped.
     - `find_package(<Name> [REQUIRED] ...)`:
       - when the project has its own `Find<Name>.cmake`, read its
         `find_path(<var> <file>|NAMES <files> [PATH_SUFFIXES <s>])`
         -> kind `header` (with the suffixes),
         `find_library(<var> <name>|NAMES <names>)` -> kind `library`
         (file `lib<name>.so`), and any `pkg_check_modules` in it;
       - otherwise kind `cmake-config`: the files `<Name>Config.cmake`
         and `<name>-config.cmake` that a config-mode package installs
         (works for Qt6, SDL2 and other projects that ship CMake
         config files). `COMPONENTS <c>...` (and the names after
         `REQUIRED`) add one `cmake-config` need per component,
         `<Name><Comp>Config.cmake`: `find_package(Qt6 COMPONENTS
         Charts)` needs `Qt6ChartsConfig.cmake`, which is how
         Eglantine's `qt6-charts-dev` is found;
       - CMake's built-in Find modules (OpenGL, X11, ZLIB) are not read;
         the resolver makes one `.pc` guess for them and the configure
         loop (6b) covers the rest;
       - a name containing `${…}` (`Qt${QT_VERSION_MAJOR}`) or given
         through `NAMES` alternatives (`find_package(QT NAMES Qt6
         Qt5)`) cannot be read without evaluating CMake; it is listed
         as unresolved and left to the configure loop.
     - `required` is true when the call says `REQUIRED` (Meson:
       `required: true` or no `required:` argument). Only required
       needs are installed; optional ones are listed in the plan
       review as not installed. Calls inside `if()` blocks are read
       as if the condition were true, because files are not
       evaluated. To limit wrong installs, `if()` nesting is tracked:
       a need inside a block whose condition names another platform
       (`WIN32`, `APPLE`, `MSVC`, `ANDROID`, `IOS`, `EMSCRIPTEN`,
       without `NOT`) or tests (`*TEST*`) is demoted to optional, and
       every need inside any `if()` is marked "inside if()" in the
       review. The configure loop only ever reports lookups the build
       actually reached.
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
     - Package-install lines (`apt-get`/`apt install`, `dnf`/`yum
       install`, `pacman -S`, `apk add`, `brew install`,
       `choco`/`winget install`) become one `Requirement` per package,
       tagged with that line's package manager
       (`ci_common.parse_install` returns the manager, not an "is apt"
       flag). Requirements merge on (tool, manager), so the tag
       survives the planner. A package is installed only when its
       manager is the build container's (Linux) or the host's (macOS,
       Windows); packages for any other manager become a `hint` note
       in the plan review and are not translated (PRD FR-6). The
       install line itself is never kept as a plan step; the
       dependency proposal installs the packages.
     - A step's `shell:` (or the platform default: bash on Linux/macOS,
       pwsh on Windows) sets `Step.shell`.
     - GitLab CI: the job named like build/compile, else the first job
       with a `script:`; its `image:` is ignored.
   - `dockerfile`: `RUN` package-install lines become `Requirement`s
     only, tagged by manager as above; no Dockerfile step runs (PRD).
   - `readme` (README*, INSTALL*, BUILDING*, docs/build*.md): called by
     the pipeline on every run that has such a file and an LLM backend
     (PRD FR-2), before `build_plan`; its finding is passed in with the
     others (the planner's `readme_fallback` callable goes away).
     `LLMBackend.extract_plan(sections, distro, manager)` gains the
     two arguments (base, Claude, Ollama and the pipeline's notice
     wrapper). The system prompt changes: install commands go into
     `packages` with their manager, tool and library names without a
     manager go into `requirements`, and setup steps never contain
     package installs; any extracted setup step that parses as an
     install line is dropped and its packages kept.
     Selects build-related sections by heading (build, install,
     dependencies, requirements, compiling) and fenced code blocks,
     then calls the LLM backend. The prompt names the build
     container's distribution and package manager
     (`DetectContext.distro`, `.pkg_manager`) so the model picks the
     matching section of a README that lists packages per
     distribution. Its requirements and packages always join the
     plan; its steps are used only when no other detector produced
     build steps (planner rule). Everything it returns is marked
     `Source.PROSE` and highlighted in the plan review. No LLM -> the
     documents are skipped with a warning.

3. **Planner** (`recompt/planner.py`)
   - Source priority: build files > CI > Dockerfile hints > prose. A
     lower-priority source adds requirements or fills missing steps; on
     conflict the higher source wins and a `PlanNote` records both.
     Prose steps are dropped with a note whenever a higher source has
     build steps; prose requirements, packages and system needs are
     always kept.
   - System needs from every finding are merged by (kind, name) into
     `BuildPlan.system_needs`; a need is required if any source says
     so.
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
     prints it without starting a container; system needs appear there
     by name, unresolved, because resolving them needs the
     distribution's index inside a container (component 6a).
   - macOS and Windows (host): each requirement is checked with
     `shutil.which` plus the tool's version command against its minimum
     version; only missing ones are proposed.

6. **Package-manager adapters** (`recompt/pkgmgr/`)
   - Chosen by the *container image family* on Linux (apt for Ubuntu
     and Debian, dnf for Fedora, pacman for Arch; see Runners for the
     image) and by the host on macOS (brew) and Windows (winget).
   - Each Linux adapter is one set of command templates, not a list of
     packages: `base_setup`, `install(packages)`, `index_update`,
     `search_files(names)`, `search_pkgconfig(modules)`,
     `owner_of(path)`. The `index_update`, `search_*` and `owner_of`
     rows were run in real containers on 2026-11-26 (Ubuntu noble,
     Fedora latest, Arch latest) and found `libudev.pc`, `libudev.h`
     and `lrelease`; the apt `base_setup` and `install` rows are in use
     today; the dnf and pacman `base_setup` and `install` rows are not
     yet run. `pacman -F` prints `repo/pkg version` then the path for a
     package that is not installed, and `<path> is owned by repo/pkg
     version` for one that is; the adapter parses both.

     | Template | apt | dnf | pacman |
     |---|---|---|---|
     | base_setup | `apt-get update && apt-get install -y --no-install-recommends ca-certificates git curl build-essential` | `dnf -y --setopt=install_weak_deps=False install ca-certificates git curl gcc gcc-c++ make` | `pacman -Syu --noconfirm --needed base-devel git curl` (Arch supports no partial upgrades, so this is a full upgrade of the image each run; accepted cost) |
     | install | `apt-get install -y --no-install-recommends <pkgs>` | `dnf -y --setopt=install_weak_deps=False install <pkgs>` | `pacman -S --noconfirm --needed <pkgs>` |
     | index_update (root) | `apt-get install -y apt-file && apt-file update` | `dnf -q makecache` | `pacman -Fy` |
     | search_files | one `apt-file -a <arch> search -x -f <pattern file>` for all needs (about 15 s) | `dnf -q --arch <arch> --arch noarch provides '<path glob>'` per need | `pacman -F -x '<regex>'` per need |
     | search_capability | none | `dnf -q repoquery --arch <arch> --arch noarch --whatprovides 'pkgconfig(<m>)'` or `'cmake(<Name>)'` | none |
     | check_name | `apt-cache show <pkg>` | `dnf -q info <pkg>` | `pacman -Si <pkg>` |
     | owner_of | `dpkg -S <path>` | `rpm -qf <path>` | `pacman -Qo <path>` |

     `<pkgs>` are always joined with `shlex.join` after the safe-name
     check (Security Considerations).

   - Toolchains (the 15 entries in `toolchains.py` today: node,
     python, cmake, meson, ninja, pkg-config and others) still use a
     small per-manager name table, because their names are fixed and
     some need extra packages (Debian splits `python3-venv` from
     `python3`). Today the table has an `apt` column only; `dnf` and
     `pacman` columns are added. This table and the wrapper deny-list
     (6a) are the only package-name lists in recompt (user decisions);
     library and tool needs never use them.
   - When CMake, Meson or Ninja has a minimum version
     (read from `cmake_minimum_required` / `meson_version`), it is
     installed from PyPI into `/opt/recompt/tools` instead, because the
     distribution's package is often older; that folder is first on
     `PATH` in the container. The same holds on the dnf and pacman
     images.
   - Package names from CI, Dockerfile and README lines pass through
     unchanged only when written for the container's manager (see
     Detectors).
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
   - Elevation: apt, dnf and pacman run as root inside the container.
     brew needs none. winget may show its own UAC prompt; recompt never
     elevates itself.
   - After installs on the host, recompt rebuilds `PATH` for its own
     process: known toolchain folders (cargo, Go, Homebrew prefix) plus,
     on Windows, the user and machine `PATH` from the registry.

6a. **System-need resolver** (`recompt/pkgmgr/resolve.py`, Linux only)
   - Runs after `runner.start()` and base setup, before the plan
     review, and only when the plan has system needs. It runs only
     recompt's own commands (index update and searches), never a plan
     step. On macOS and Windows system needs are listed as missing,
     not installed (brew and winget have no file search).
   - Query order per need, most precise first:
     1. capability queries where the manager has them (dnf only):
        `pkgconfig(<module>)` for `pkgconfig` needs, `cmake(<Name>)`
        for `cmake-config` needs;
     2. file search, anchored to the standard place so a bare name
        does not match every package: `pkgconfig` ->
        `/usr/(lib|lib64|share)/(<triplet>/)?pkgconfig/<module>.pc`;
        `header` -> `/usr/include/(<suffix>/)?<file>` (using the
        Find module's `PATH_SUFFIXES`); `library` ->
        `/usr/lib(64)?/(<triplet>/)?lib<name>.so`; `cmake-config` ->
        `.../cmake/<Name>/<Name>Config.cmake` or
        `<name>-config.cmake`; `tool` -> `/usr/bin/<tool>` or
        `/usr/lib*/<anything>/bin/<tool>` (Qt keeps its tools there).
     Names are regex-escaped (`libstdc++`, `SDL.h`) and every hit is
     mapped back to the need it answers.
   - The container's architecture is passed to every search
     (`apt-file -a <arch>`, dnf `--arch <arch> --arch noarch`; pacman
     indexes only its own architecture). `index_update` runs once;
     apt then runs a single `apt-file search -x -f <pattern file>` for
     all needs (about 15 s), dnf and pacman one query per need.
   - Choosing among several packages for one need, in order; the plan
     review shows the pick, the other candidates and the rule that
     decided:
     1. drop packages on the wrapper deny-list (`WRAPPERS` in
        `resolve.py`, user decision): `qtchooser` and the few other
        packages that only redirect to the real tool. Each entry has a
        one-line reason; the list is meant to stay under ten entries;
     2. for `pkgconfig`, `header`, `library` and `cmake-config` needs,
        prefer development packages (`-dev`, `-devel`; pacman does not
        split, so every package counts);
     3. when the need's own name carries a major version (`Qt6`,
        `SDL2`, `gtk+-3.0`), prefer a package whose name carries the
        same number;
     4. prefer a hit at the standard path over one in a versioned
        side folder (`/usr/bin/lrelease` over `/usr/lib/qt5/bin/…`)
        only when rules 1 to 3 left a tie, then the highest number in
        the package name, then the shortest name.
   - Unknown requirement names: a requirement whose tool is neither in
     the toolchain table nor tagged with a package manager (the LLM's
     `lrelease`, `Qt6`) becomes a `SystemNeed(kind="tool")` (or
     `cmake-config` for a name that looks like a CMake package), never
     a package name to install. Pass-through names that are tagged for
     the container's manager are checked once (`apt-cache show`,
     `dnf -q info`, `pacman -Si`); a name the manager does not know is
     listed as "unknown package" and dropped, so one invented name
     cannot fail the whole install.
   - No package found -> the need is listed as unresolved; a required
     one is a warning, not an error, because the configure loop below
     can still find it.
   - Resolved required packages are added to the install proposal for
     the container's manager, each keeping its need's source and
     origin, so the review can mark what came from the LLM.
   - CMake's built-in Find modules (`find_package(ZLIB)` with no
     project Find module and no config file found): one guess search
     for `<name-lower>.pc` and `lib<name-lower>.pc`, marked "guess" in
     the review. The configure loop covers what the guess misses.

6b. **Configure loop** (`recompt/pipeline.py` with
   `recompt/configure_errors.py`, Linux container runs; user decision
   2026-11-26)
   - Applies to the plan's configure step: `cmake -S`/`-B`, `meson
     setup`, `./configure`. When it fails, its full output (captured
     to a file, not only the 40-line tail) is read for missing
     dependencies:
     - CMake: `Could NOT find <Name> (missing: <VARS>)` -> the
       variables' `find_path`/`find_library` names when the project's
       Find module is known, else a `cmake-config` and `.pc` guess for
       `<Name>`; `Could not find a package configuration file provided
       by "<Name>"` -> `cmake-config` `<Name>`; `Package '<m>', required
       by '…', not found` and `No package '<m>' found` (pkg-config) ->
       `pkgconfig` `<m>`;
     - Meson: `Dependency "<m>" not found` -> `pkgconfig` `<m>`;
     - autotools: `No package '<m>' found` -> `pkgconfig`;
       `checking for <header>... no` followed by an error -> `header`.
   - The new needs go through the resolver. If it finds packages that
     are not installed yet, the run pauses for a **second review**
     showing only those packages, their source ("configure output")
     and the choice rule; `--yes` approves it. Approved -> install,
     then run the configure step again. Declined -> the build failure
     stands (exit 1).
   - At most 3 rounds, and a round that finds no new package ends the
     loop; the run then fails with the configure step's error as
     today. Each round is listed in the log and the final report.

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
     - Image: from `/etc/os-release`, checked in this order (`ID`
       first, then each word of `ID_LIKE`), always fully qualified:

       | os-release | Image | Manager |
       |---|---|---|
       | `UBUNTU_CODENAME` set (Ubuntu, Pop!_OS, Mint) | `docker.io/library/ubuntu:<codename>` | apt |
       | `DEBIAN_CODENAME` set, or `ID=debian` + `VERSION_ID` | `docker.io/library/debian:<codename or version>` | apt |
       | `ID=fedora` | `docker.io/library/fedora:<VERSION_ID>` | dnf |
       | `ID=arch` or `ID_LIKE` contains `arch` (Manjaro, EndeavourOS) | `docker.io/library/archlinux:latest`, with a notice that Arch has no releases, so the image can be newer than the host | pacman |
       | anything else | `docker.io/library/ubuntu:latest` | apt |

       Rows also match through `ID_LIKE`: `ubuntu` -> Ubuntu by
       `UBUNTU_CODENAME`; `debian` without a codename (Kali, Devuan)
       -> the last row; `fedora` (Nobara) -> Fedora by `VERSION_ID`
       when that image exists. The last row warns that the program may
       not run on the host.
     - The pipeline picks image, distribution and manager once, at the
       start of the run (`runners.image_for(os-release)`), and passes
       them to detection (`DetectContext`), the dependency proposal,
       the README prompt and `make_runner`; the runner no longer picks
       the image itself.
     - A failed pull falls back only within the same family, so the
       planned package manager still holds: `ubuntu:<codename>` and
       `debian:<codename>` -> that distribution's `latest`;
       `fedora:<VERSION_ID>` -> `fedora:latest`; Arch is already
       `latest`. If the fallback also fails, the run stops with exit 3
       (an environment problem, not a build failure). A fallback to a
       different manager is never made after planning. With
       `--host-build`, `distro` and `pkg_manager` are the host's own.
     - Start: `run -d --rm --init --name recompt-<run id>
       --label recompt=1 --security-opt no-new-privileges
       --security-opt label=disable -v <copy>:/src -w /src <image>
       sleep infinity`. `--init` lets the container stop at once;
       the label lets leftovers be found and removed. `label=disable`
       keeps bind mounts working on SELinux hosts without relabelling
       the user's folder.
     - Base setup (first step, root): the manager's `base_setup`
       (component 6; `DEBIAN_FRONTEND=noninteractive` on apt), create
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
     - `capture(argv, *, root=False, timeout)`: runs one of recompt's
       own commands in the container and returns its full output
       without printing it (`run()` keeps only the last 40 lines).
       `root=True` uses the root user option, needed for the
       resolver's `index_update` (`apt-get install apt-file`,
       `apt-file update`, `pacman -Fy`); searches and the host check
       run as the build user. It goes through `proc.run_process` with
       a time limit (10 minutes for `index_update`, 2 minutes for a
       search), so a stalled mirror ends with `StepTimeoutError` and
       Ctrl-C becomes `CancelledError`, both of which remove the
       container. `index_update` streams its output with a first line
       saying what is downloaded and its rough size (about 410 MB on
       Ubuntu).
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
   - **Host library check** (`recompt/hostlibs.py`, Linux container runs
     only; skipped with `--host-build`, on macOS and Windows, and for
     interpreted projects). A program built in the container can need a
     shared library that only the container has, because the dependency
     proposal installed it there (Eglantine: `libQt6Charts.so.6` from
     `qt6-charts-dev`). It runs after the collector and before
     `runner.stop()`, while the container is still up. Container
     commands go through `ContainerRunner.capture(argv)` as the build
     user (see Runners):
     1. Inside the container, `readelf -d <program>` gives the `NEEDED`
        library names and the `RUNPATH`/`RPATH` folders. `ldd` is not
        run on the host, because it can execute the program's own
        loader, which would run untrusted code outside the container.
        No `readelf` in the container (exit 127) or a non-ELF file ->
        the check is skipped with a warning.
     2. On the host, a library counts as present when `ldconfig -p`
        lists its name, or when it exists in a `RUNPATH`/`RPATH` folder
        (`$ORIGIN` is the program's folder; `/src` maps to the working
        copy).
     3. For each missing library, `ldconfig -p` inside the container
        maps the library name to its full path there, and the
        manager's `owner_of` gives the owning package (`dpkg -S
        <path>`, with the `:<arch>` suffix dropped; `rpm -qf <path>`;
        `pacman -Qo <path>`; `rpm` and `pacman` need a path, not a
        bare name). No path or no owner -> the library is listed by
        name only.
     - Result: `RunResult.missing_host_libraries`. The report prints a
       warning with the libraries and one install line in the host's
       own manager (`sudo apt install`, `sudo dnf install` or
       `sudo pacman -S`), printed only when the host's distribution
       family is the container's (the pipeline knows this from
       `image_for`). When the image is the Ubuntu fallback on another
       distribution, container package names mean nothing on the
       host, so only library names are listed. The exit code stays
       0, because the build itself succeeded. recompt never installs
       them on the host (see Pipeline rules).

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
   - The model gets no tools. Everything it returns is `Source.PROSE`
     and marked in the plan review, which is the prompt-injection
     protection (PRD Risks); no parser is trusted to make the text
     safe.
   - Claude refusals are not retried with server-side fallbacks: that
     option is documented only on the beta client, not with
     `messages.parse`, so a refusal makes document reading unavailable
     for the run. A missing Claude key surfaces from the SDK as a plain
     `TypeError` and is mapped to `LLMUnavailable`.
   - Both SDKs are optional extras (`recompt[claude]`,
     `recompt[ollama]`), imported only when selected.

### Data Models (`recompt/models.py`)

```python
class Source(Enum): BUILD_FILE, CI, DOCKERFILE, PROSE, CONFIGURE

class Requirement(BaseModel):
    tool: str
    min_version: str | None
    source: Source
    origin: str                  # file and line
    manager: str | None          # set for package names from install lines: "apt", "dnf", ...

class SystemNeed(BaseModel):     # a library or tool the build files look for
    kind: Literal["pkgconfig", "header", "library", "cmake-config", "tool"]
    name: str                    # "libudev", "libudev.h", "udev", "Qt6", "lrelease"
    path_suffixes: list[str]     # from find_path PATH_SUFFIXES
    required: bool
    in_if: bool                  # read inside an if() block
    guess: bool                  # built-in Find module guess
    source: Source               # BUILD_FILE, PROSE, or CONFIGURE (configure output)
    origin: str

class ProposedPackage(BaseModel):
    name: str
    source: Source
    origin: str

class ResolvedNeed(BaseModel):
    need: SystemNeed
    package: str | None          # None = unresolved
    candidates: list[str]
    rule: str                    # which choice rule picked the package

class Step(BaseModel):
    kind: Literal["install", "setup", "build", "launch"]
    command: list[str] | str     # list = exec form, str = shell script
    shell: Literal["exec", "sh", "bash", "pwsh", "cmd"]
    cwd: str                     # relative to working copy
    as_root: bool                # True only for kind == "install" in the container
    source: Source
    origin: str

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
    system_needs: list[SystemNeed]
    cmake_options: list[str]     # CI -D options
    cmake_generator: str | None  # CI -G
    cmake_build_dir: str | None  # CI -B

class WorkingCopy(BaseModel):
    path: str
    in_place: bool               # True for a local folder
    url: str | None              # normalized, credentials removed
    ref: str | None

class DetectContext(BaseModel):
    host_os: Literal["linux", "macos", "windows"]
    llm: Any | None              # LLMBackend, only used by the readme detector
    distro: str                  # build distribution: "ubuntu noble", "fedora 45", "arch", "macos", "windows"
    pkg_manager: Literal["apt", "dnf", "pacman", "brew", "winget"]

class StepResult(BaseModel):
    step: Step
    exit_code: int
    output_tail: str             # last lines of combined output
    duration_s: float

class ExtractedPlan(BaseModel):  # LLM output schema
    requirements: list[ExtractedRequirement]   # tool, min_version
    packages: list[ExtractedPackage]           # manager, name: only lines for a named manager
    steps: list[ExtractedStep]                 # kind (setup|build|launch), command, shell, cwd

class BuildPlan(BaseModel):
    project_kind: Literal["compiled", "interpreted"]
    steps: list[Step]
    requirements: list[Requirement]
    targets: list[Target]
    notes: list[PlanNote]        # kind also "hint": packages for another manager
    system_needs: list[SystemNeed]

class InstallProposal(BaseModel):
    manager: Literal["apt", "dnf", "pacman", "brew", "winget", "rustup", "go-archive",
                     "npm", "pip", "report-only"]
    packages: list[ProposedPackage]
    commands: list[Step]

class HostLibrary(BaseModel):
    name: str                    # e.g. "libQt6Charts.so.6"
    package: str | None          # owning package in the container, if any

class RunResult(BaseModel):
    status: Literal["ok", "build_failed", "invalid_input", "deps_missing",
                    "no_runnable_output", "no_plan", "timeout", "cancelled"]
    program_path: str | None
    launch_command: str | None
    completed_steps: list[Step]
    failed_step: Step | None
    error_output: str | None
    missing: list[Requirement]
    missing_host_libraries: list[HostLibrary]
    resolved_needs: list[ResolvedNeed]
    prompts_asked: int           # excludes the plan review
    log_path: str
```

The README detector converts `ExtractedPlan` into a `Finding`, setting
`source=PROSE` and `origin` to the README file; each extracted package
becomes a `Requirement` with its `manager`. The old
`Step.needs_confirm` flag is removed: the plan review covers every
step, and the review marks PROSE items.

### Interfaces

- Options: ref, preview, explicit host build, per-step time limit, LLM
  backend, and `--yes`.
- Plan review (PRD FR-3): every non-preview run shows the whole plan
  and waits for one yes/no answer before any plan step runs. It lists
  steps, requirements, packages to install with their manager,
  resolved system needs (package, other candidates, choice rule),
  unresolved and optional needs, hints for other managers, and notes;
  every PROSE item is marked as read by the LLM. This one answer
  replaces the former install and prose-step confirmations.
- Second review (configure loop, component 6b): same form, listing only
  the packages the configure output led to.
- `--yes` approves both reviews, including PROSE items (accepted risk,
  PRD). Without a terminal and without `--yes`, the run stops with
  exit 5 at its start (`ui.interactive` is checked first in `_run`,
  except in preview), before the LLM call, the container start and the
  index download. When the user answers no to the first review, the
  run stops with exit 5 before any plan step runs.
- UI protocol: `confirm_installs` and `confirm_prose` are replaced by
  `review(plan, proposals, resolved) -> bool` and an `interactive`
  property; the review is built from `Requirement`s and
  `ResolvedNeed`s, so each package shows its source and origin.
  `InstallProposal.packages` becomes `list[ProposedPackage]` (name,
  source, origin) for the same reason.
- Default time limit: 30 minutes per step, install steps included.
- Exit codes:

| Code | Meaning |
|---|---|
| 0 | Runnable result produced |
| 1 | A build step failed |
| 2 | Invalid input |
| 3 | Dependencies not available (no container runtime, or no Podman subordinate ID range) |
| 4 | No runnable program or launch command |
| 5 | No plan that can run, or the plan was not approved |
| 6 | Step time limit exceeded |
| 130 | Cancelled |

### Sequence

```
cli ──> pipeline.run(input, options)
          ├─ not preview, not interactive, no --yes? ────────────  (5)
          ├─ source.resolve(input) ───────────> WorkingCopy       (2)
          ├─ image_for(os-release) ───────────> distro, manager   (Linux)
          ├─ detectors + readme (llm) ────────> [Finding]
          ├─ planner.build(findings) ─────────> BuildPlan         (5 if no steps)
          ├─ several targets? cli.ask_target()
          ├─ deps.propose(plan) ──────────────> [InstallProposal] (no runner needed)
          ├─ preview? report.plan(); exit 0      (needs shown unresolved)
          ├─ try:
          │   ├─ runner.start(); base setup                       (3 if no runtime or pull fails)
          │   ├─ needs? resolve.resolve(needs, runner) ─> [ResolvedNeed] (Linux)
          │   ├─ ui.review(plan, proposals, resolved) or --yes    (5 if not approved)
          │   ├─ for step: runner.run(step)                       (1 / 6 / 130)
          │   │     └─ configure failed? configure_errors -> resolve
          │   │           -> ui.review(new packages) -> install -> rerun (max 3 rounds)
          │   ├─ collect.result(plan) ────────> RunResult         (4)
          │   └─ container? hostlibs.check(programs, runner) ─> [HostLibrary]
          └─ finally: runner.stop(); report.result(); exit code
```

### Pipeline rules

- Install steps come only from the dependency proposal; a plan's own
  `install` steps (CI package lines) are never run directly.
- On Linux the container starts before the plan review, so system
  needs can be resolved for the review. Before approval only recompt's
  own base setup and resolver commands run in it; if the plan is not
  approved, the container is removed and nothing else has run.
- Report-only dependencies are listed as a warning and the run
  continues; a later build failure shows whether they mattered.
- With `--host-build` on Linux, missing tools and system needs are only
  reported; recompt never runs a package manager as root on the host. The same holds for shared
  libraries a container-built program needs on the host: they are
  reported with an install command, never installed.
- Launch steps are never run; v1 returns the launch command.

### Error Handling

- Each stage raises a `RecomptError` subclass carrying its exit code
  and message; `cli` catches it once. No other module calls `sys.exit`.
- `runner.stop()` runs in `finally`; on timeout and Ctrl-C the
  pipeline calls `runner.kill()` first.
- LLM errors (no credentials, rate limit, server down, invalid output)
  turn document reading off for the run with a warning; the run ends
  with exit 5 if nothing else produced a plan.
- Resolver errors (index download fails, search command fails or
  times out) leave the affected needs unresolved with a warning; the
  run continues to the plan review. Ctrl-C during the resolver or a
  review is a cancel (exit 130). The resolver and both reviews run
  inside the same `try/finally` as the steps, so the container is
  always removed.
- A failed image pull, after the same-family fallback, is exit 3
  (`DepsMissingError`), not exit 1: it is an environment problem.
  Other failures to start or prepare the container stay exit 1.
- An install of approved packages that fails is a build failure
  (exit 1) naming the install step, as today. Claude errors are caught
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
  resolution; os-release to image mapping (Ubuntu, Pop!_OS, Mint,
  Debian, Fedora, Arch, Manjaro, an unknown distribution); runtime-mode
  to user-option table; exit-code mapping; system-need extraction
  (fixtures modelled on Dolphin's `FindLIBUDEV.cmake` and
  `pkg_check_modules` calls, uppercase commands, `REQUIRED` and
  optional calls, Meson `dependency()`); the resolver's choice rules
  on recorded search output from all three managers; plan review
  approve / decline / `--yes` / no terminal. Runners, git and LLMs are
  fakes.
- **More unit cases for the amendment**: configure-output parsing
  (CMake "Could NOT find", missing config file, pkg-config, Meson,
  autotools) on recorded logs; second review approve / decline / `--yes`
  and the 3-round limit; safe-name check refusing `x;curl` and similar
  from CI, Dockerfile and LLM sources, and `shlex.join` in every
  install command; same-family image fallback and exit 3 when it
  fails; `capture(root=True)` used for `index_update`, its time limit
  and Ctrl-C; early exit 5 without a terminal and without `--yes`;
  COMPONENTS, `${}` names, vendored folders skipped, platform `if()`
  demotion; deny-list and version-matching choice rules; LLM `lrelease`
  becoming a `tool` need on all three managers.
- **Package-manager smoke tests** (marker `container`): one test per
  manager starts its image and runs `base_setup`, `index_update`, the
  searches for `libudev.pc`, `libudev.h` and `lrelease`, `install`
  of the picked package, and `owner_of`, checking each result.
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
| FR-2: README always read; prose steps only without build steps | `auto-test` | unit | pytest: fake LLM called with build steps present; its packages kept, its steps dropped with a note; no LLM -> warning |
| FR-3: plan with sources; preview runs nothing | `auto-test` | unit | pytest: preview test records zero runner and process calls |
| FR-3: plan review before any step | `auto-test` | unit | pytest: decline and no-terminal -> exit 5 with no plan step run; `--yes` -> runs; PROSE items marked |
| FR-6: system needs from build files resolved by file | `auto-test` | unit | pytest: Dolphin-style fixture -> needs `libudev.h`, `udev` (required); recorded search output -> `libudev-dev` / `systemd-devel` / `systemd-libs` |
| FR-6: package managers in real images | `docker` | integration | pytest -m container: apt, dnf and pacman smoke tests pass |
| FR-6: configure loop and second review | `auto-test` | unit | pytest: recorded "Could NOT find ZLIB" -> need -> package -> second review -> rerun; 3-round limit; decline -> exit 1 |
| FR-6: safe package names | `auto-test` | unit | pytest: unsafe names refused and listed; install commands quoted |
| FR-6: regressions | `manual-run-claude` | integration | Dolphin configures past libudev; m64py finds `lrelease` from its README; Eglantine still builds |
| FR-4: compiled build, program path | `auto-test` | integration | pytest: per-ecosystem builds pass on each OS |
| FR-5: interpreted setup and launch command | `auto-test` | integration | pytest: Node and Python fixtures return a working launch command |
| FR-6: install only after approval | `auto-test` | unit + integration | pytest: review declined -> exit 5, no install step run |
| FR-7: three OSes | `auto-test` | CI matrix | GitHub Actions: three green jobs |
| FR-8: exit codes | `auto-test` | unit | pytest: one test per code |
| FR-9: time limit | `auto-test` | unit + integration | pytest: sleeping step -> exit 6, process tree gone |
| FR-10: Ctrl-C | `manual-run-claude` | integration | interrupted run exits 130, lists completed steps, no container left |
| FR-11: reuse working copy | `auto-test` | integration | pytest: second run fetches into the same folder |
| FR-12: Linux sandbox | `docker` | integration | pytest: mount list, file ownership, canary folder unchanged |
| Host library check (PRD risk: program may not run on the host) | `auto-test` | unit | pytest: fake runner output -> missing library with its package; present, RUNPATH and no-readelf cases |
| Benchmark targets | `manual-run-user` | benchmark | report: Linux ≥ 14/15, macOS ≥ 11/15, Windows ≥ 11/15 |

## Trade-offs

1. **One container per run (chosen) vs one per step**: per-step gives
   clean state but needs an image rebuilt between steps to keep
   installed tools; one container is simpler and faster.
2. **Build-files-first for steps, LLM always for documents (chosen,
   per amended PRD) vs LLM-first vs a text pattern**: steps stay
   deterministic when build files give them; documents are read by
   the LLM every run because packages are often stated only there,
   in forms a pattern cannot follow. The cost is an LLM call per run;
   the injection risk is handled by the plan review, not by parsing.
3. **Plain detector list (chosen) vs entry-point plugins**: plugins
   would let third parties add ecosystems, which nobody needs yet.
4. **Probe-free Linux proposal (chosen) vs probing inside the
   container**: a fresh image has no toolchains, so probing would only
   start a container to learn that; skipping it keeps preview free of
   side effects.
5. Language (Python) and image strategy (host-distro image) are user
   decisions; see Decisions Taken.
6. **Package lookup by file in the distribution's index (chosen) vs a
   name table vs Repology or rosdep**: a table needs constant upkeep
   per distribution (rosdep is exactly such a maintained table);
   Repology maps project names, not files, and is online. File lookup
   uses data each distribution already maintains, at the cost of an
   index download (Performance).
7. **Container before review (chosen) vs review before container**:
   resolving needs requires the index inside the container, so the
   review can show real package names; the cost is a container start
   (and index download) for runs the user then declines.
8. **Required needs only (chosen) vs all needs**: installing optional
   libraries gives more features but more installs and more wrong
   picks; optional needs are shown in the review instead.
9. **Static reading plus a configure loop (chosen) vs static only vs
   configure loop only**: static reading gives preview and the first
   review a full plan; the configure loop catches what static reading
   cannot (CMake's built-in Find modules, `if()` conditions, `${}`
   names), because configure reports only lookups it actually
   reached. The cost is a second review on runs that need it.

## Implementation Constraints

- Python 3.11 or later (`tomllib`).
- Domain modules read only files in the working copy.
- Only `cli` prompts or exits.

## Files to Create

- `pyproject.toml` — metadata, dependencies, extras, `recompt` console
  script, pytest markers
- `recompt/{__init__,__main__,cli,report,pipeline,models,errors,config,proc}.py`
- `recompt/{source,planner,deps,launch,collect,hostlibs,configure_errors}.py`
- `recompt/detectors/{__init__,node,python,rust,go,cfamily,github_actions,gitlab_ci,dockerfile,readme}.py`
- `recompt/runners/{__init__,base,container,host}.py`
- `recompt/pkgmgr/{__init__,apt,dnf,pacman,brew,winget,toolchains,resolve}.py`
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
- LLM output never runs without the plan review, unless the user
  passes `--yes` (accepted risk, PRD); the model has no tools. With
  Claude, selected README sections leave the machine on every run
  that has them, and the run says so first.
- Before approval only recompt's own commands run in the container
  (base setup, index update, searches); no project code runs. The
  working copy stays mounted read-write during this phase (a mount
  cannot change while the container runs); recompt's own commands do
  not write to `/src`.
- Package names from every source (CI, Dockerfile, README via the LLM,
  resolver output) must match `^[A-Za-z0-9][A-Za-z0-9+._:-]*$` (plus
  an optional `=<version>` / `>=<version>` suffix for pip-style names
  where the manager supports it). Others are refused and listed in the
  review as "refused: unsafe name". Every install command is built
  with `shlex.join`, never by joining strings, because install steps
  run as root (`shell="sh"`). Today `apt.py` joins names unquoted and
  `ci_common.parse_install` passes any token without `$` or a leading
  `-`; both change.
- Credentials are stripped from URLs in logs and paths; recompt never
  reads git credentials or API keys itself.

## Performance Considerations

- Shallow fetch of exactly one ref keeps downloads small.
- Toolchain installs in a fresh container dominate run time (minutes
  for Rust or C++). Caching prepared images per distro and ecosystem is
  a later improvement, not v1.
- File index for the resolver, measured 2026-11-26: Ubuntu noble 410 MB
  and 20 s to fetch, about 15 s per `apt-file` search (so all names go
  in one search); Fedora 87 MB, growing to 242 MB on the first file
  search (14 s), while `pkgconfig()` queries need no file lists, so
  they run first; Arch 52 MB and 2 s. The index is fetched only when
  the plan has system needs. Caching it across runs is a later
  improvement.

## Rollback Plan

First code in the repository; rollback is reverting the implementation
commits. On a user's machine recompt leaves its cache folder, committed
images (label `recompt=1`), and any host installs approved in the
plan review.

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
- From the 2026-11-26 PRD amendment (user): apt, dnf and pacman images
  matching the host, Ubuntu LTS elsewhere; packages found by file
  through the distribution's index, no package-name list; README read
  by the LLM every run; plan review every run; `--yes` approves it.
- Following from it (Claude, 2026-11-26): container starts before the
  review so needs resolve to real package names; only required needs
  are installed; CMake built-in Find modules not read (a `.pc` guess
  plus the configure loop instead); a declined or unanswerable review
  exits 5.
- The small toolchain table (15 entries, gaining dnf and pacman
  columns) is kept (user, 2026-11-26).
- From the independent review (2026-11-26):
  - Configure loop with a second review for the new packages, at most
    3 rounds (user).
  - A tiny wrapper deny-list (`qtchooser` and few others) together
    with the choice rules: deny-list, development package, version in
    the need's name, standard path, highest number, shortest name
    (user).
  - Claude, from the review findings: `capture(root=True)` with time
    limits; same-family image fallback only, exit 3 if it fails; image
    and manager picked once by the pipeline; safe-name check and
    `shlex.join` for every install; unknown requirement names become
    `tool` needs and pass-through names are checked; early exit 5
    without a terminal and without `--yes`; `review()` replaces the
    two confirms, with per-package source; manager tags kept through
    merging; `ldconfig -p` path lookup for the host check; README
    prompt with distro and manager and no install steps; COMPONENTS,
    `${}` names, vendored folders skipped, platform `if()` demotion;
    capability queries and architecture flags first; one `apt-file
    -f` search.
  - Not adopted: mounting the working copy read-only during lookups (a
    mount cannot change while the container runs). Index caching
    across runs stays a later improvement.

---

**Next Steps**:
1. Review and approve design
2. Run `/embo:tasks` for task breakdown
