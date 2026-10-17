"""Build-time checks; the installed Python package has no build dependencies."""

import os
import platform
import shutil
import struct
from pathlib import Path


def require_cargo():
    if shutil.which("cargo") is None:
        raise ValueError(
            "Cargo was not found in PATH. Source installation requires Rustup "
            "and the toolchain in rust-toolchain.toml. Install Rustup from "
            "https://rustup.rs, reopen your terminal, and retry. "
            "Python users can instead install a matching prebuilt release wheel."
        )


def macos_target():
    value = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "11.0")
    try:
        parts = tuple(int(x) for x in value.split("."))
        if not 1 <= len(parts) <= 3 or min(parts) < 0:
            raise ValueError
        version = (parts + (0, 0))[:3]
        if version < (11, 0, 0):
            raise ValueError
    except ValueError:
        raise ValueError("MACOSX_DEPLOYMENT_TARGET must be a version >= 11.0") from None
    return version


def macos_wheel_platform():
    major, minor, patch = macos_target()
    if patch:
        raise ValueError("Use a major.minor MACOSX_DEPLOYMENT_TARGET for wheel builds")
    arch = platform.machine().lower()
    if arch not in {"arm64", "x86_64"}:
        raise ValueError(f"Unsupported macOS process architecture: {arch}")
    return f"macosx_{major}_{minor}_{arch}"


def validate_macos_binary(path):
    """Refuse to advertise an older OS or different architecture than Mach-O allows."""
    data = Path(path).read_bytes()
    if len(data) < 32 or data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("Expected a thin little-endian 64-bit macOS dylib")
    cpu, _, _, count, size = struct.unpack_from("<5I", data, 4)
    expected = {"x86_64": 0x01000007, "arm64": 0x0100000C}.get(platform.machine().lower())
    if cpu != expected:
        raise ValueError("Native dylib architecture does not match this Python process")
    end = 32 + size
    if end > len(data):
        raise ValueError("Truncated Mach-O load commands")
    offset = 32
    versions = []
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError("Truncated Mach-O load command")
        command, length = struct.unpack_from("<2I", data, offset)
        if length < 8 or offset + length > end:
            raise ValueError("Invalid Mach-O load command length")
        if command == 0x32 and length >= 24:  # LC_BUILD_VERSION
            os_platform, encoded = struct.unpack_from("<2I", data, offset + 8)
            if os_platform != 1:
                raise ValueError("Native dylib must target macOS, not another Apple platform")
            versions.append((encoded >> 16, (encoded >> 8) & 255, encoded & 255))
        elif command == 0x24 and length >= 16:  # LC_VERSION_MIN_MACOSX
            encoded = struct.unpack_from("<I", data, offset + 8)[0]
            versions.append((encoded >> 16, (encoded >> 8) & 255, encoded & 255))
        offset += length
    if not versions:
        raise ValueError("Native dylib does not declare a macOS minimum version")
    if max(versions) > macos_target():
        actual = ".".join(map(str, max(versions)))
        raise ValueError(
            f"Native dylib requires macOS {actual}, newer than MACOSX_DEPLOYMENT_TARGET. "
            "Rebuild it for the declared minimum; do not simply rename the wheel."
        )
