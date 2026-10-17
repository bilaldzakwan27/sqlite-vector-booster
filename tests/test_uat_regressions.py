"""Regression checks for installation and DX failures found during UAT."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_support

spec = importlib.util.spec_from_file_location("source_booster", ROOT / "python/sqlite_vector_booster/__init__.py")
booster = importlib.util.module_from_spec(spec)
spec.loader.exec_module(booster)


def macho(version, cpu=0x0100000C, legacy=False):
    encoded = version[0] << 16 | version[1] << 8
    command = (struct.pack("<4I", 0x24, 16, encoded, encoded) if legacy else
               struct.pack("<6I", 0x32, 24, 1, encoded, encoded, 0))
    return struct.pack("<8I", 0xFEEDFACF, cpu, 0, 6, 1, len(command), 0, 0) + command


class BuildChecks(unittest.TestCase):
    def test_missing_cargo_explains_remediation(self):
        with patch("build_support.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "Install Rustup.*prebuilt"):
                build_support.require_cargo()

    def test_wheel_tag_uses_declared_target_not_build_host(self):
        with patch.dict(os.environ, {"MACOSX_DEPLOYMENT_TARGET": "11.0"}):
            for arch in ["arm64", "x86_64"]:
                with patch("build_support.platform.machine", return_value=arch):
                    self.assertEqual(build_support.macos_wheel_platform(), f"macosx_11_0_{arch}")

    def test_macho_minimum_and_architecture_must_match_wheel(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "library.dylib"
            with patch.dict(os.environ, {"MACOSX_DEPLOYMENT_TARGET": "11.0"}), patch("build_support.platform.machine", return_value="arm64"):
                binary.write_bytes(macho((11, 0)))
                build_support.validate_macos_binary(binary)
                binary.write_bytes(macho((15, 0)))
                with self.assertRaisesRegex(ValueError, "newer than"):
                    build_support.validate_macos_binary(binary)
                binary.write_bytes(macho((11, 0), cpu=0x01000007))
                with self.assertRaisesRegex(ValueError, "architecture"):
                    build_support.validate_macos_binary(binary)
                binary.write_bytes(b"bad")
                with self.assertRaisesRegex(ValueError, "64-bit"):
                    build_support.validate_macos_binary(binary)

    def test_legacy_macho_minimum_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "library.dylib"
            binary.write_bytes(macho((11, 0), cpu=0x01000007, legacy=True))
            with patch.dict(os.environ, {"MACOSX_DEPLOYMENT_TARGET": "11.0"}), patch("build_support.platform.machine", return_value="x86_64"):
                build_support.validate_macos_binary(binary)

    def test_invalid_deployment_target_is_explained(self):
        for target in ["bad", "10.15", "11.-1", "11.0.0.1"]:
            with patch.dict(os.environ, {"MACOSX_DEPLOYMENT_TARGET": target}):
                with self.assertRaisesRegex(ValueError, ">= 11.0"):
                    build_support.macos_target()

    def test_node_install_without_cargo_has_actionable_error(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is not installed")
        env = os.environ.copy()
        env.pop("SQLITE_VECTOR_BOOSTER_LIBRARY", None)
        with tempfile.TemporaryDirectory() as empty_path:
            env["PATH"] = empty_path
            result = subprocess.run([node, str(ROOT / "scripts/build-node.cjs")], env=env,
                                    text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cargo was not found", result.stderr)
        self.assertIn("retry npm install", result.stderr)
        self.assertNotIn("spawnSync cargo ENOENT", result.stderr)


class PythonLoaderChecks(unittest.TestCase):
    def test_invalid_connection_has_type_error(self):
        with self.assertRaisesRegex(TypeError, "sqlite3 connection"):
            booster.load(None)

    def test_python_without_extension_capability_has_remediation(self):
        class NoExtensionSupport:
            def load_extension(self, path):
                pass
        with self.assertRaisesRegex(RuntimeError, "extension-enabled Python"):
            booster.load(NoExtensionSupport())

    def test_failed_load_still_disables_extension_loading(self):
        class FailingConnection:
            def __init__(self):
                self.states = []
            def enable_load_extension(self, state):
                self.states.append(state)
            def load_extension(self, path):
                raise RuntimeError("simulated incompatible library")
        connection = FailingConnection()
        with patch.object(booster, "extension_path", return_value="test-library"):
            with self.assertRaisesRegex(RuntimeError, "incompatible"):
                booster.load(connection)
        self.assertEqual(connection.states, [True, False])


class BenchmarkChecks(unittest.TestCase):
    def run_benchmark(self, *arguments):
        env = os.environ.copy()
        env.pop("SQLITE_VECTOR_BOOSTER_LIBRARY", None)
        return subprocess.run([sys.executable, str(ROOT / "benchmarks/sqlite.py"), *arguments],
                              env=env, capture_output=True, text=True)

    def test_missing_library_has_cli_remediation(self):
        result = self.run_benchmark("--library", "/does-not-exist/library", "--rows", "2")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--library", result.stderr)
        self.assertIn("cargo build", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_bad_counts_do_not_allocate_vectors(self):
        for arguments in [("--rows", "0"), ("--dimensions", "1048577"), ("--repetitions", "no")]:
            result = self.run_benchmark(*arguments)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)

    def test_default_build_output_is_found_without_environment(self):
        filename = {"linux": "libsqlite_vector_booster.so", "darwin": "libsqlite_vector_booster.dylib", "win32": "sqlite_vector_booster.dll"}.get(sys.platform)
        base = Path(os.environ.get("CARGO_TARGET_DIR", ROOT / "target"))
        if not base.is_absolute():
            base = ROOT / base
        library = base / os.environ.get("CARGO_BUILD_TARGET", "") / "release" / str(filename)
        if not library.is_file():
            self.skipTest("Build the native extension first")
        result = self.run_benchmark("--rows", "2", "--dimensions", "2", "--repetitions", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["rows"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
