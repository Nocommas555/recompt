from types import SimpleNamespace

from recompt.hostlibs import check, parse_ldconfig
from recompt.models import HostLibrary

READELF = """
Dynamic section at offset 0x2d1b8 contains 30 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [libQt6Charts.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libQt6Core.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x000000000000000c (INIT)               0x6000
"""

LDCONFIG = """3 libs found in cache `/etc/ld.so.cache'
\tlibQt6Core.so.6 (libc6,x86-64) => /lib/x86_64-linux-gnu/libQt6Core.so.6
\tlibc.so.6 (libc6,x86-64, OS ABI: Linux 3.2.0) => /lib/x86_64-linux-gnu/libc.so.6
\tlibz.so.1 (libc6,x86-64) => /lib/x86_64-linux-gnu/libz.so.1
"""


def result(code=0, out="", err=""):
    return SimpleNamespace(returncode=code, stdout=out, stderr=err)


def fake_capture(responses):
    calls = []

    def capture(argv):
        calls.append(argv)
        for prefix, value in responses.items():
            if tuple(argv[: len(prefix)]) == prefix:
                return value
        return result(1)

    capture.calls = calls
    return capture


def test_ldconfig_listing_gives_library_names():
    assert parse_ldconfig(LDCONFIG) == {"libQt6Core.so.6", "libc.so.6", "libz.so.1"}


def test_missing_library_is_reported_with_its_container_package(tmp_path):
    program = tmp_path / "build/release/bin/eglantine"
    capture = fake_capture({
        ("readelf", "-d"): result(out=READELF),
        ("dpkg", "-S"): result(out="libqt6charts6:amd64: /usr/lib/x86_64-linux-gnu/libQt6Charts.so.6\n"),
    })
    missing, warnings = check([str(program)], tmp_path, capture, parse_ldconfig(LDCONFIG))
    assert missing == [HostLibrary(name="libQt6Charts.so.6", package="libqt6charts6")]
    assert warnings == []
    assert capture.calls[0] == ["readelf", "-d", "/src/build/release/bin/eglantine"]
    assert capture.calls[1] == ["dpkg", "-S", "*/libQt6Charts.so.6"]


def test_all_libraries_present_on_host_reports_nothing(tmp_path):
    capture = fake_capture({("readelf", "-d"): result(out=READELF)})
    host = parse_ldconfig(LDCONFIG) | {"libQt6Charts.so.6"}
    assert check([str(tmp_path / "app")], tmp_path, capture, host) == ([], [])


def test_library_in_origin_runpath_inside_the_working_copy_counts_as_present(tmp_path):
    (tmp_path / "out/lib").mkdir(parents=True)
    (tmp_path / "out/lib/libown.so.1").write_bytes(b"")
    readelf = (" 0x0000000000000001 (NEEDED)             Shared library: [libown.so.1]\n"
               " 0x000000000000001d (RUNPATH)            Library runpath: [$ORIGIN/../lib:/opt/recompt/x]\n")
    capture = fake_capture({("readelf", "-d"): result(out=readelf)})
    assert check([str(tmp_path / "out/bin/app")], tmp_path, capture, set()) == ([], [])


def test_missing_library_without_owning_package_is_listed_by_name(tmp_path):
    readelf = " 0x0000000000000001 (NEEDED)             Shared library: [libgone.so.2]\n"
    capture = fake_capture({("readelf", "-d"): result(out=readelf), ("dpkg", "-S"): result(1, err="no path found")})
    missing, _ = check([str(tmp_path / "app")], tmp_path, capture, set())
    assert missing == [HostLibrary(name="libgone.so.2", package=None)]


def test_no_readelf_in_container_skips_the_check_with_a_warning(tmp_path):
    capture = fake_capture({("readelf", "-d"): result(127, err="executable file not found")})
    missing, warnings = check([str(tmp_path / "app")], tmp_path, capture, set())
    assert missing == []
    assert len(warnings) == 1 and "readelf" in warnings[0]


def test_non_elf_program_is_skipped_silently(tmp_path):
    capture = fake_capture({("readelf", "-d"): result(1, err="readelf: Error: Not an ELF file")})
    assert check([str(tmp_path / "run.sh")], tmp_path, capture, set()) == ([], [])
