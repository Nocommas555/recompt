import re

from recompt.detectors.common import min_version, req, root, step
from recompt.models import DetectContext, Finding, PlanNote, WorkingCopy

VERSION_PATTERNS = {
    "cmake": ("CMakeLists.txt", re.compile(r"cmake_minimum_required\s*\(\s*VERSION\s+([\d.]+?)(?:\.\.\.|\s|\))", re.I)),
    "meson": ("meson.build", re.compile(r"meson_version\s*:\s*'([^']*)'")),
}


def _tool_version(base, tool: str) -> str | None:
    if tool not in VERSION_PATTERNS:
        return None
    filename, pattern = VERSION_PATTERNS[tool]
    path = base / filename
    match = pattern.search(path.read_text(errors="ignore")) if path.exists() else None
    return min_version(match.group(1)) if match else None

SYSTEMS = [
    (
        "CMakeLists.txt",
        ["cmake", "c-compiler"],
        [
            ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"],
            ["cmake", "--build", "build", "--config", "Release"],
        ],
    ),
    (
        "meson.build",
        ["meson", "ninja", "c-compiler"],
        [["meson", "setup", "build"], ["meson", "compile", "-C", "build"]],
    ),
    ("configure", ["make", "c-compiler"], ["./configure", "make"]),
    ("configure.ac", ["autoconf", "automake", "make", "c-compiler"], ["autoreconf -fi", "./configure", "make"]),
    ("Makefile", ["make", "c-compiler"], ["make"]),
]


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    base = root(copy)
    present = [s for s in SYSTEMS if (base / s[0]).exists()]
    if not present:
        return []
    origin, tools, commands = present[0]
    others = [s[0] for s in present[1:]]
    if origin == "configure" and "configure.ac" in others:
        others.remove("configure.ac")

    steps = [
        step("build", cmd, origin, shell="exec" if isinstance(cmd, list) else "sh")
        for cmd in commands
    ]
    notes = [PlanNote(kind="skipped", message=f"Also found {o}; using {origin}", sources=[o]) for o in others]
    return [
        Finding(
            detector="cfamily",
            ecosystem="cfamily",
            requirements=[req(t, origin, _tool_version(base, t)) for t in tools],
            steps=steps,
            notes=notes,
        )
    ]
