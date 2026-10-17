"""Validate the actual wheel tag and packaged macOS binary before distribution."""
import argparse
from pathlib import Path
import platform
import tempfile
import zipfile

from build_support import macos_wheel_platform, validate_macos_binary

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("wheel", type=Path)
args = parser.parse_args()
with zipfile.ZipFile(args.wheel) as archive:
    metadata = next(name for name in archive.namelist() if name.endswith(".dist-info/WHEEL"))
    if platform.system() == "Darwin":
        expected = f"py3-none-{macos_wheel_platform()}"
        if not args.wheel.name.endswith(f"-{expected}.whl"):
            parser.error(f"Wheel filename must end with -{expected}.whl")
        if f"Tag: {expected}" not in archive.read(metadata).decode():
            parser.error("Wheel internal Tag disagrees with the deployment target")
        binary = next((name for name in archive.namelist()
                       if name.endswith("sqlite_vector_booster/native/libsqlite_vector_booster.dylib")), None)
        if binary is None:
            parser.error("Wheel does not contain the macOS native extension")
        with tempfile.TemporaryDirectory() as folder:
            native = Path(folder) / "extension.dylib"
            native.write_bytes(archive.read(binary))
            try:
                validate_macos_binary(native)
            except ValueError as error:
                parser.error(str(error))
    else:
        suffix = ".dll" if platform.system() == "Windows" else ".so"
        if not any("sqlite_vector_booster/native/" in name and name.endswith(suffix)
                   for name in archive.namelist()):
            parser.error("Wheel does not contain the platform native extension")
print(f"Verified wheel contents and platform: {args.wheel.name}")
