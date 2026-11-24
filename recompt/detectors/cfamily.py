from recompt.detectors.common import req, root, step
from recompt.models import DetectContext, Finding, PlanNote, WorkingCopy

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
            requirements=[req(t, origin) for t in tools],
            steps=steps,
            notes=notes,
        )
    ]
