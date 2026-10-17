"""Load SQLite Vector Booster into Python's sqlite3 connections."""

import platform
from pathlib import Path

__version__ = "0.1.1"
__all__ = ["extension_path", "load"]


def extension_path() -> str:
    """Return the absolute path of the installed native extension."""
    names = {
        "Linux": "libsqlite_vector_booster.so",
        "Darwin": "libsqlite_vector_booster.dylib",
        "Windows": "sqlite_vector_booster.dll",
    }
    system = platform.system()
    if system not in names:
        raise RuntimeError(f"Unsupported operating system: {system}")
    path = Path(__file__).resolve().parent / "native" / names[system]
    if not path.is_file():
        raise FileNotFoundError(
            f"Native extension not installed: {path}. Reinstall a matching release "
            "wheel, or install from source with the Rust toolchain in README.md."
        )
    return str(path)


def load(connection) -> None:
    """Load both distance functions, then disable extension loading."""
    if not callable(getattr(connection, "load_extension", None)):
        raise TypeError("Expected a sqlite3 connection with a load_extension method")
    if not callable(getattr(connection, "enable_load_extension", None)):
        raise RuntimeError(
            "This Python SQLite build does not support extension loading. "
            "Use an extension-enabled Python build; see README.md Troubleshooting."
        )
    path = extension_path()
    try:
        connection.enable_load_extension(True)
    except NotImplementedError as error:
        raise RuntimeError(
            "This Python SQLite build does not support extension loading. "
            "Use an extension-enabled Python build; see README.md Troubleshooting."
        ) from error
    try:
        connection.load_extension(path)
    finally:
        connection.enable_load_extension(False)
