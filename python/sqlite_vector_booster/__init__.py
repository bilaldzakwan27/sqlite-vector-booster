"""Load SQLite Vector Booster into Python's sqlite3 connections."""

import platform
from pathlib import Path

__version__ = "0.1.0"
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
        raise FileNotFoundError(f"Native extension not installed: {path}")
    return str(path)


def load(connection) -> None:
    """Load both distance functions, then disable extension loading."""
    path = extension_path()
    connection.enable_load_extension(True)
    try:
        connection.load_extension(path)
    finally:
        connection.enable_load_extension(False)
