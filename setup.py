import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel
from setuptools.errors import SetupError

ROOT = Path(__file__).resolve().parent
# PEP 517 executes setup.py without guaranteeing the source root is on sys.path.
sys.path.insert(0, str(ROOT))
from build_support import macos_target, macos_wheel_platform, require_cargo, validate_macos_binary


def library_name():
    return {
        "Linux": "libsqlite_vector_booster.so",
        "Darwin": "libsqlite_vector_booster.dylib",
        "Windows": "sqlite_vector_booster.dll",
    }[platform.system()]


class BuildExtension(build_py):
    def run(self):
        supplied = os.environ.get("SQLITE_VECTOR_BOOSTER_LIBRARY")
        if not supplied:
            try:
                require_cargo()
            except ValueError as error:
                raise SetupError(str(error)) from None
        super().run()
        if supplied:
            source = Path(supplied).expanduser().resolve()
            if not source.is_file():
                raise SetupError(f"SQLITE_VECTOR_BOOSTER_LIBRARY does not exist: {source}")
        else:
            build_env = os.environ.copy()
            if platform.system() == "Darwin":
                try:
                    macos_target()
                except ValueError as error:
                    raise SetupError(str(error)) from None
                build_env.setdefault("MACOSX_DEPLOYMENT_TARGET", "11.0")
            try:
                subprocess.run(["cargo", "build", "--release", "--locked"], cwd=ROOT,
                               env=build_env, check=True)
            except subprocess.CalledProcessError:
                raise SetupError("Rust build failed. Check the compiler output above and the "
                                 "Rust toolchain/linker prerequisites in README.md.") from None
            target = Path(os.environ.get("CARGO_TARGET_DIR", ROOT / "target"))
            if not target.is_absolute():
                target = ROOT / target
            target_triple = os.environ.get("CARGO_BUILD_TARGET")
            if target_triple:
                target /= target_triple
            source = target / "release" / library_name()
        if platform.system() == "Darwin":
            try:
                validate_macos_binary(source)
            except ValueError as error:
                raise SetupError(str(error)) from None
        destination = Path(self.build_lib) / "sqlite_vector_booster" / "native"
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / library_name())


class PlatformWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, _, platform_tag = super().get_tag()
        if platform.system() == "Darwin":
            try:
                platform_tag = macos_wheel_platform()
            except ValueError as error:
                raise SetupError(str(error)) from None
        return "py3", "none", platform_tag


setup(cmdclass={"build_py": BuildExtension, "bdist_wheel": PlatformWheel})
