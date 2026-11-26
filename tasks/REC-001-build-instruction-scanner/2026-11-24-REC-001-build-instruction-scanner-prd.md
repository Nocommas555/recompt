# REC-001: Build Instruction Scanner - PRD

**Status**: Approved (2026-11-24)
**Created**: 2026-11-24
**Ticket**: none (local ID REC-001)
**Author**: Claude (via dev workflow analysis)

---

## Wider Context / Higher Goal

recompt is a universal "point it at a repo, get a working program"
tool: the user gives it a git remote URL or a local folder, and ends up
with an app they can run on their own machine. The scanner is the first
step that makes this possible across projects with very different
languages and tech stacks.

## Context

To work, recompt has to know how to build and launch a large number of
apps whose codebases, languages, and build systems differ widely. Each
project describes this in its own way: in build files, in CI or
container configuration, or in prose in its README. The scanner finds
those instructions, turns them into one ordered plan, and carries out
the build (or, for interpreted languages, the setup and the launch
command).

### Current State (observed)

- The repository contains only an empty README and a `.gitignore`;
  there is no source code yet — verified via: `git log --oneline -10`
  (one commit, `9b3d117`) and `git diff --stat HEAD` (no changes),
  2026-11-24
- No code index exists for this repo — verified via: `rlm_repl status`
  (exit 2, no state file), 2026-11-24
- The development machine runs Linux — verified via: session
  environment (platform `linux`), 2026-11-24

### Past Similar Features (from claude-mem)

None. Memory holds only this session's repository setup.

## Problem Statement

**Who**: A person who wants to use an open-source program that is
distributed as source code, not as a ready-made binary.
**What**: Each project builds differently; working out the right
commands, toolchains, and dependencies takes reading and trial and
error.
**Why**: This effort stops people from using software that is otherwise
freely available, and it has to be repeated for every project.
**When**: Whenever the user has a link to a repository or a folder of
source code and wants to run the program in it.

## Goals

### Primary Goal

Given a git remote URL or a local folder, recompt produces a runnable
result on the user's machine without the user reading the project's
build documentation.

**Runnable result** means one of:
- **Compiled project**: every build step exits successfully and the
  program file the plan expects exists at the reported location.
- **Interpreted project**: every setup step exits successfully and a
  launch command is returned.

v1 does **not** start the app itself; it hands the user the program
location or the launch command.

### Secondary Goals

- Show what it found and what it is about to do before doing it.
- When a build cannot be completed, explain why and what is missing,
  instead of failing silently.

## User Stories

### Epic

As a user with a link to a project's source code, I want recompt to
find and follow that project's build instructions, so that I get a
runnable result without working out the build myself.

### User Stories

1. **As a** user
   **I want** to give recompt a git remote URL or a local folder
   **So that** I can start from whatever form of the source I have

   **Acceptance Criteria**:
   - [ ] A git remote URL (any git server, including GitHub) is fetched
         to a local working copy
   - [ ] Without a ref, the remote's default branch is used; a branch,
         tag, or commit can be given to use that instead
   - [ ] A GitHub link to a page inside a repository (a tree or file
         view) is resolved to that repository and the ref in the link
   - [ ] Private repositories work only through the user's existing git
         credentials; recompt does not ask for or store credentials
   - [ ] A local folder is used in place without being copied; the user
         is told that build output will be written into that folder
   - [ ] An unreachable URL, unknown ref, or missing folder stops the
         run with a message naming the input that failed

2. **As a** user
   **I want** recompt to find the project's build instructions
   **So that** projects are handled no matter how they document their
   build

   **Acceptance Criteria**:
   - [ ] Build files of each supported ecosystem (see Support Matrix)
         are detected
   - [ ] Build steps are read from supported CI and container files;
         container files are only read for hints, never run
   - [ ] Build steps are taken from README/INSTALL prose only when no
         build file or CI file yields them; requirements and packages
         are read from those documents on every run (FR-2)
   - [ ] For each fixture README in the test set, the plan drawn from
         prose matches that fixture's expected plan
   - [ ] When sources disagree, the plan states which source it used
         and why

3. **As a** user
   **I want** to see the plan before anything runs
   **So that** I know what will happen on my machine

   **Acceptance Criteria**:
   - [ ] A preview mode prints the full plan, each step's source, and
         the missing dependencies, and runs nothing
   - [ ] In a normal run, recompt pauses after planning and runs
         nothing until the user approves the whole plan; items the LLM
         read from documents are marked (FR-3)
   - [ ] `--yes` approves the plan without the pause

4. **As a** user
   **I want** recompt to build compiled projects
   **So that** I get a runnable program

   **Acceptance Criteria**:
   - [ ] Plan steps run in order; each step's output is shown and
         logged
   - [ ] On success, the program file's location is reported
   - [ ] On failure, the failing step and its error output are reported
   - [ ] If the project builds but produces no runnable program (for
         example it is a library), the run reports that and ends
   - [ ] If the project contains several apps, the run lists them and
         asks which to build

5. **As a** user of an interpreted-language project
   **I want** recompt to prepare the project and tell me how to launch
   it
   **So that** I can run projects that have no compile step

   **Acceptance Criteria**:
   - [ ] Setup the launch needs (for example installing the project's
         dependencies) is run, with its commands shown
   - [ ] The launch command is returned after setup succeeds

6. **As a** user
   **I want** recompt to ask before installing missing toolchains or
   system packages
   **So that** nothing is installed on my machine without my consent

   **Acceptance Criteria**:
   - [ ] Missing compilers, runtimes, and system packages are listed,
         with required versions where the project states them, before
         anything is installed
   - [ ] Installation, including any administrator elevation, happens
         only after the user confirms
   - [ ] If the user declines the plan review, the run stops before
         anything runs and reports what would have been installed
   - [ ] On a system without a supported package manager, recompt lists
         what is missing and installs nothing
   - [ ] On Linux, dependencies are installed inside the build container
         (Story 7); they are approved with the plan review (FR-3) like
         every other item, with no separate install prompt
   - [ ] System packages are found even when the project has no CI
         file: from what the LLM reads in its README or other build
         documents, and from the libraries and tools its build files
         look for (see FR-6)

7. **As a** Linux user
   **I want** builds to run inside a container
   **So that** a project's build scripts cannot change my system

   **Acceptance Criteria**:
   - [ ] On Linux, every plan step runs inside a container; only the
         working copy is shared with it
   - [ ] For a compiled project, the program file is copied out of the
         container and its host location is reported
   - [ ] For an interpreted project, the returned launch command starts
         the app inside the same container image
   - [ ] If no supported container runtime is installed, the run stops
         and says what to install; it builds directly on the host only
         when the user explicitly asks for that
   - [ ] After a sandboxed run, nothing outside the working copy and
         the container runtime's own storage has changed

## Support Matrix (v1)

| | Linux | macOS | Windows |
|---|---|---|---|
| Ecosystems | Node/JS, Python, Rust, Go, C/C++ | same | same |
| Build isolation | container sandbox | none (runs on host) | none (runs on host) |
| Install missing deps via | the host distribution's package manager, inside a container of the same distribution (see below) | Homebrew | winget |
| CI / container files read | GitHub Actions, GitLab CI, Dockerfile | same | same |

Linux distributions in v1:

| Host distribution | Build container image | Package manager |
|---|---|---|
| Ubuntu, Debian and their derivatives (Mint, Pop!_OS) | same distribution and release | apt |
| Fedora | same release | dnf |
| Arch and its derivatives (Manjaro, EndeavourOS) | newest Arch image (Arch has no releases, so the image can be newer than the host) | pacman |
| any other | latest Ubuntu LTS, with a warning that the program may not run on the host | apt |

C/C++ covers Make, CMake, Meson, and autotools projects. Native Windows
C/C++ toolchains are harder to detect and install than the others; see
Risks.

## Requirements

### Functional Requirements

1. **FR-1**: Accept a git remote URL (with an optional ref) or a local
   folder, as described in Story 1.
   - **Priority**: High
   - **Dependencies**: a git client on the host
     [assumption, verify in tech-design]

2. **FR-2**: Detect build instructions for the ecosystems and CI/
   container formats in the Support Matrix; use documentation prose only
   as a fallback for build steps. The README and other build documents
   are always read with the LLM for requirements and system packages,
   because projects often state them only there, in free text, tables
   or per-distribution sections. When build files already give steps,
   the LLM may add requirements and packages only, never steps. With no
   LLM available, the documents are skipped with a warning.
   - **Priority**: High
   - **Dependencies**: reading prose reliably likely needs an LLM
     [assumption, verify in tech-design]

3. **FR-3**: Combine detected instructions into one ordered plan that
   records each step's source; offer a preview mode that prints the plan
   and runs nothing.
   - **Priority**: High
   - Every run pauses at the end of planning and shows the whole plan:
     steps, requirements, packages to install, and where each came
     from (marking what the LLM read from documents). Nothing runs
     until the user approves. This one review replaces the separate
     install and prose-step confirmations.
   - When the configure step reports missing libraries (FR-6), the
     run pauses a second time and shows only the newly found packages;
     nothing more is installed until the user approves them.
   - `--yes` approves both reviews without pausing, including what the
     LLM read from documents. Without a terminal and without `--yes`,
     the run stops at its start, before anything runs; the exit code is
     set in the tech design.
   - Preview starts no container and runs no plan step, but still
     reads documents with the LLM, because the plan depends on them.

4. **FR-4**: Run the plan for compiled projects and report the program
   file's location, or report that no runnable program was produced.
   - **Priority**: High

5. **FR-5**: For interpreted projects, run setup and return the launch
   command.
   - **Priority**: High

6. **FR-6**: Detect missing toolchains, runtimes, and system packages;
   list them; install them through the Support Matrix package managers
   only after the user confirms, elevating only then.
   - **Priority**: High
   - System packages come from every source the project offers, not
     only CI:
     - install lines in CI files and the Dockerfile;
     - requirements and install commands the LLM finds in the README
       and other build documents (FR-2);
     - the libraries and tools the build files look for (CMake
       `pkg_check_modules`, `find_package` with the project's own Find
       modules, Meson `dependency()`), read before the build;
     - the libraries the configure step reports missing when it runs
       (for example CMake's "Could NOT find ZLIB"), which also covers
       CMake's built-in Find modules and checks inside `if()` blocks
       that reading the files cannot evaluate. recompt looks these up
       the same way, asks for approval (FR-3), installs them and runs
       configure again, for a few rounds at most.
   - Libraries and tools are turned into package names by asking the
     package manager which package contains the needed file or
     pkg-config module, using the distribution's own package index.
     recompt keeps no list of package names per distribution.
   - Install lines written for a different package manager than the
     build container's (an `apt install` line on Fedora) are not
     translated; they are shown as hints, and the build-file lookup
     above supplies the packages.
   - When a lookup finds several packages for one file, recompt picks
     one by fixed rules set in the tech design, and the plan shows
     which one was picked, the alternatives, and why. A tiny,
     documented list of wrapper packages (for example `qtchooser`,
     which only redirects to the real Qt tools) is never picked; it is
     the one package-name list besides the toolchain names.
   - Package names from any source are checked against a safe-name
     pattern and quoted before use; others are refused and shown in
     the review.

7. **FR-7**: Run on Linux, macOS, and Windows hosts per the Support
   Matrix.
   - **Priority**: High

8. **FR-8**: Command-line interface with defined exit codes: success,
   build failure, plan not approved, missing container runtime,
   invalid input, cancelled.
   The exact codes are set in tech-design.
   - **Priority**: High

9. **FR-9**: Every step has a time limit; a step that exceeds it fails
   the run with a timeout message. The default limit is set in
   tech-design.
   - **Priority**: Medium

10. **FR-10**: The user can cancel a run at any time (Ctrl-C); recompt
    stops the current step and reports which steps finished.
    - **Priority**: Medium

11. **FR-11**: Remote sources are fetched into a recompt-managed working
    folder; running again on the same source and ref reuses that copy
    and updates it.
    - **Priority**: Medium

12. **FR-12**: On Linux, run every plan step inside a container that
    shares only the working copy, as described in Story 7.
    - **Priority**: High
    - **Dependencies**: a container runtime on the host, such as Docker
      or Podman [assumption, verify in tech-design]

### Non-Functional Requirements

1. **NFR-1**: Transparency - every command recompt runs is shown to the
   user and written to a log file.
2. **NFR-2**: Failure reporting - every failed run ends with the failing
   step, its error output, and, when known, what is missing.
3. **NFR-3**: Host changes - on Linux, a sandboxed run changes nothing
   outside the working copy and the container runtime's storage. On
   macOS and Windows, a run changes only what confirmed installs and
   the ecosystems' own dependency caches change outside the working
   copy.
4. **NFR-4**: Platform testing - the test suite runs on Linux, macOS,
   and Windows.

### Technical Constraints

- No existing code to integrate with; implementation language and
  structure are chosen in tech-design.
- Must run on Linux, macOS, and Windows hosts (FR-7).

## Out of Scope

- **Sandboxing on macOS and Windows.** Builds there run directly on
  the host. The user decided to come back to this later.
- Starting the built app (v1 returns the location or launch command).
- Running a project's own Dockerfile; container files in the project
  are read for hints only (the Linux sandbox uses recompt's own
  container image).
- Managing git credentials.
- Producing binaries for a different OS or CPU than the host
  (cross-compiling).
- Installing through package managers not in the Support Matrix.
- Build containers for Linux distributions other than Ubuntu, Debian,
  Fedora and Arch and their derivatives, for example openSUSE (zypper
  cannot search the files of packages that are not installed), Rocky
  Linux, AlmaLinux, RHEL and Alpine (apk has no local file search, and
  its musl-based programs do not run on glibc hosts). These hosts use
  the Ubuntu LTS image with a warning.
- Updating or uninstalling apps after they are built.

## Risks

- **Running untrusted code on the host (macOS and Windows).** A
  project's build scripts run with the user's permissions and can
  change or damage the system. Accepted for v1; to be revisited.
- **Container limits (Linux).** A container lowers the risk but is not
  a complete security boundary; a build with network access can still
  download and run anything inside it.
- **Built program may not run on the host (Linux).** A program
  compiled inside the container can depend on system libraries the
  host does not have, or has in other versions. Mitigated by a
  container image of the host's distribution and release (newest image
  on Arch; Ubuntu LTS on unsupported distributions), and by a check
  after the build that lists the libraries missing on the host with
  the command to install them in the host's own package manager (tech
  design, result collector).
- **Package index size.** Finding packages by file needs the
  distribution's file index in the container. Measured on 2026-11-26:
  Ubuntu noble about 410 MB and 20 s to fetch, then about 15 s per
  search; Fedora 87 MB, growing to 242 MB on the first file search;
  Arch 52 MB and 2 s. The index is fetched only when a lookup is
  needed, once per run.
- **Wrong package from a lookup.** One file can be in several packages
  (Qt 5 and Qt 6 both ship `lrelease`; Fedora lists 32- and 64-bit
  builds). A wrong pick fails the build; the plan shows each pick so
  the user can see it.
- **Wrong commands or packages from prose.** Plans drawn from README
  text by an LLM can contain wrong or invented commands and packages.
  Mitigated by taking steps from prose only when build files give none,
  and by the plan review every run, which marks what came from the LLM
  (FR-3).
- **Prompt injection.** README text is written by the project's
  authors and can contain instructions aimed at the LLM, including
  packages an attacker wants installed. The plan review is the
  protection; no parser can make this text safe. With `--yes` there is
  no review, so a hostile README gets through: accepted by the user
  for unattended runs (2026-11-26). On Linux the result is still
  confined to the build container.
- **LLM on every run.** Documents are read with the LLM on every run
  that has them, not only as a fallback. With Claude, repository text
  leaves the machine and costs money each run; with no LLM, the
  documents are skipped and packages stated only there are missed.
- **Sending repository content to an LLM.** If the LLM is an external
  service, repository text leaves the machine, costs money per run,
  and needs a network connection
  [assumption, verify in tech-design].
- **Partial host changes.** A failed build can leave installed packages
  and partial build output behind; v1 does not undo them.
- **Three operating systems at once.** Toolchain names, package
  managers, and build behavior differ per OS; native Windows C/C++
  toolchains are the hardest case.

## Success Metrics

1. **Benchmark build success**: a fixed list of 15 named repositories
   per OS, spread across the supported ecosystems, chosen in
   tech-design.
   - Linux: at least 90% (14 of 15) end in a runnable result.
   - macOS: at least 70% (11 of 15).
   - Windows: at least 70% (11 of 15).
2. **Prompts per run**: on successful benchmark runs, the average
   number of prompts other than the plan reviews (FR-3) is zero.

## References

### From Codebase (RLM)

- None. The repository has no code yet.

### From History (Claude-Mem)

- None. No earlier PRDs exist for this project.

## Decisions Taken

- Input: git remote URL with optional ref, or local folder (user,
  2026-11-24).
- Instruction sources: build files, CI configs, README/docs prose
  (user, 2026-11-24); prose as fallback only for build steps (review,
  2026-11-24; narrowed 2026-11-26, see below).
- Interpreted languages: run setup and return the launch command
  (user, 2026-11-24).
- OS scope: Linux, macOS, and Windows in v1 (user, 2026-11-24).
- Sandboxing: container sandbox on Linux only; none on macOS and
  Windows for now (user, 2026-11-24).
- Linux in-container installs need no confirmation; no container
  runtime means the run stops unless the user explicitly asks for a
  host build (Claude, 2026-11-24, follows from the sandbox decision).
- Missing dependencies: install after asking (user, 2026-11-24).
- Ecosystems: Node/JS, Python, Rust, Go, C/C++ (user, 2026-11-24).
- Package managers: apt, Homebrew, winget (user, 2026-11-24); on
  Linux, apt, dnf and pacman inside a container of the host's
  distribution; other distributions use Ubuntu LTS (user, 2026-11-26).
- System packages come from CI, the Dockerfile, documented install
  commands and the build files' library lookups, not from CI alone;
  taking them only from CI was a planning mistake (user, 2026-11-26).
- No list of package names kept by recompt; packages are found by file
  or pkg-config module through the distribution's own index (user,
  2026-11-26). Exceptions, also by user decision: the small toolchain
  table and the tiny wrapper deny-list.
- The README and other build documents are always read with the LLM
  for requirements and packages; a fixed text pattern would miss most
  of them and would not stop an attacker (user, 2026-11-26). Steps
  still come from prose only when build files give none (Claude,
  2026-11-26).
- Every run pauses after planning for a review of the whole plan
  (user, 2026-11-26); the review is the single approval and replaces
  the install and prose-step confirmations (Claude, 2026-11-26,
  follows from it). This supersedes "Linux in-container installs need
  no confirmation" above.
- `--yes` approves the whole plan, including what the LLM read from
  documents (user, 2026-11-26, risk accepted).
- The 2026-11-26 amendment as a whole, including the items marked
  Claude, was confirmed by the user on 2026-11-26.
- After the independent review (2026-11-26): run configure once and
  look up what it reports missing, with a second review for those
  packages (user); a tiny deny-list of wrapper packages together with
  the choice rules (user); safe-name check and quoting of package
  names; early stop without a terminal and without `--yes` (Claude,
  from the review findings). Confirmed by the user on 2026-11-26.
- CI/container files: GitHub Actions, GitLab CI, Dockerfile (user,
  2026-11-24).
- Benchmark target: 90% Linux, 70% macOS and Windows (user,
  2026-11-24); 15 repos per OS (Claude, 2026-11-24, user did not set a
  size).

---

**Next Steps**:
1. Review and refine this PRD
2. Run `/embo:tech-design` to create technical design
3. Run `/embo:tasks` to break down into tasks
