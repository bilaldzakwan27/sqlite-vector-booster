import os
import platform
import shutil
import subprocess
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel

ROOT = Path(__file__).resolve().parent


def library_name():
    return {
        "Linux": "libsqlite_vector_booster.so",
        "Darwin": "libsqlite_vector_booster.dylib",
        "Windows": "sqlite_vector_booster.dll",
    }[platform.system()]


class BuildExtension(build_py):
    def run(self):
        super().run()
        supplied = os.environ.get("SQLITE_VECTOR_BOOSTER_LIBRARY")
        if supplied:
            source = Path(supplied).resolve(strict=True)
        else:
            subprocess.run(["cargo", "build", "--release", "--locked"], cwd=ROOT, check=True)
            target = Path(os.environ.get("CARGO_TARGET_DIR", ROOT / "target"))
            if not target.is_absolute():
                target = ROOT / target
            target_triple = os.environ.get("CARGO_BUILD_TARGET")
            if target_triple:
                target /= target_triple
            source = target / "release" / library_name()
        destination = Path(self.build_lib) / "sqlite_vector_booster" / "native"
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / library_name())


class PlatformWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, _, platform_tag = super().get_tag()
        return "py3", "none", platform_tag


setup(cmdclass={"build_py": BuildExtension, "bdist_wheel": PlatformWheel})
