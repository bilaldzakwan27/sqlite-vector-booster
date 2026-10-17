from __future__ import annotations

import argparse
import ctypes
import faulthandler
import gc
import json
import math
import os
import platform
import random
import shutil
import sqlite3
import struct
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest


VECTOR_DIMENSIONS = 128
DATASET_ROWS = 10_000
BENCHMARK_ITERATIONS = 100
BENCHMARK_WARMUP_ITERATIONS = 10
MAX_AVERAGE_QUERY_NS = 15_000_000
RANDOM_SEED = 0x51A17E

STRESS_COMPUTATIONS = 50_000
STRESS_WARMUP_COMPUTATIONS = 5_000
STRESS_SAMPLE_INTERVAL = 5_000
MAX_RETAINED_RSS_GROWTH = 4 * 1024 * 1024
MAX_PEAK_RSS_GROWTH = 8 * 1024 * 1024
MAX_PYTHON_ALLOCATION_GROWTH = 512 * 1024
MAX_RSS_GROWTH_BYTES_PER_CALL = 64.0

DISTANCE_FUNCTIONS = ("vector_cosine_dist", "vector_l2_dist")
DISTANCE_SQL = {
    name: f"SELECT {name}(?1, ?2)" for name in DISTANCE_FUNCTIONS
}
KNN_SQL = (
    "SELECT id FROM vectors "
    "ORDER BY vector_cosine_dist(embedding, :query) LIMIT 10"
)
KNOWN_A = struct.pack("<4f", 1.0, 2.0, 3.0, 4.0)
KNOWN_B = struct.pack("<4f", 4.0, 3.0, 2.0, 1.0)
VECTOR_STRUCT = struct.Struct(f"<{VECTOR_DIMENSIONS}f")


def _find_extension() -> Path:
    configured = os.environ.get("SQLITE_VECTOR_BOOSTER_LIBRARY")
    if configured is not None:
        candidate = Path(configured).expanduser().resolve()
        if not candidate.is_file():
            pytest.fail(
                f"Extension library does not exist: {candidate}", pytrace=False
            )
        return candidate

    machine = platform.machine().lower()
    if machine in {"amd64", "x64"}:
        machine = "x86_64"
    elif machine == "arm64":
        machine = "aarch64"

    if sys.platform == "win32":
        filename = "sqlite_vector_booster.dll"
        target = f"{machine}-pc-windows-msvc"
    elif sys.platform == "darwin":
        filename = "libsqlite_vector_booster.dylib"
        target = f"{machine}-apple-darwin"
    elif sys.platform.startswith("linux"):
        filename = "libsqlite_vector_booster.so"
        target = f"{machine}-unknown-linux-gnu"
    else:
        pytest.fail(f"Unsupported platform: {sys.platform}", pytrace=False)

    roots = dict.fromkeys((Path(__file__).resolve().parent, Path.cwd().resolve()))
    candidates = [
        candidate
        for root in roots
        for candidate in (
            root / "target" / "release" / filename,
            root / "target" / target / "release" / filename,
            root / "native" / filename,
            root / filename,
        )
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    searched = "\n".join(str(candidate) for candidate in candidates)
    pytest.fail(
        "Compiled extension not found. Set SQLITE_VECTOR_BOOSTER_LIBRARY "
        f"to its absolute path.\nSearched:\n{searched}",
        pytrace=False,
    )


def _open_database(extension: Path) -> sqlite3.Connection:
    database = sqlite3.connect(":memory:")
    try:
        if not hasattr(database, "enable_load_extension"):
            raise RuntimeError(
                "This Python sqlite3 build does not support extension loading."
            )
        database.enable_load_extension(True)
        try:
            database.load_extension(str(extension))
        finally:
            database.enable_load_extension(False)
        return database
    except BaseException:
        database.close()
        raise


@pytest.fixture(scope="session")
def extension_path() -> Path:
    return _find_extension()


@pytest.fixture
def database(extension_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(_open_database(extension_path)) as connection:
        yield connection


def _assert_connection_healthy(cursor: sqlite3.Cursor) -> None:
    row = cursor.execute(
        DISTANCE_SQL["vector_l2_dist"], (KNOWN_A, KNOWN_B)
    ).fetchone()
    if row != (20.0,):
        raise AssertionError(
            f"Connection or extension became unusable after an error: {row!r}"
        )


def _expect_sql_error(
    cursor: sqlite3.Cursor,
    sql: str,
    arguments: tuple[bytes, bytes],
    message: str,
) -> None:
    try:
        cursor.execute(sql, arguments).fetchone()
    except sqlite3.DatabaseError as error:
        if getattr(error, "sqlite_errorcode", None) == 0:
            raise AssertionError("SQLite reported an error with SQLITE_OK.") from error
        if message not in str(error):
            raise AssertionError(
                f"Expected validation error containing {message!r}, got {error!r}"
            ) from error
    else:
        raise AssertionError(
            "Invalid vector input was accepted: "
            f"argument lengths={tuple(map(len, arguments))}"
        )
    _assert_connection_healthy(cursor)


def _boundary_worker(
    extension: Path, category: str, function: str
) -> dict[str, Any]:
    if function not in DISTANCE_SQL:
        raise ValueError(f"Unsupported distance function: {function}")

    sql = DISTANCE_SQL[function]
    valid = VECTOR_STRUCT.pack(*([1.0] * VECTOR_DIMENSIONS))
    zero = VECTOR_STRUCT.pack(*([0.0] * VECTOR_DIMENSIONS))
    cases = 0

    with closing(_open_database(extension)) as connection:
        with closing(connection.cursor()) as cursor:
            if category == "dimensions":
                shorter = struct.pack("<64f", *([1.0] * 64))
                for arguments in ((valid, shorter), (shorter, valid)):
                    _expect_sql_error(cursor, sql, arguments, "dimensions must match")
                    cases += 1
            elif category == "empty_zero":
                for arguments in ((b"", valid), (valid, b""), (b"", b"")):
                    _expect_sql_error(cursor, sql, arguments, "at least one f32")
                    cases += 1

                zero_cases = ((zero, valid), (valid, zero), (zero, zero))
                if function == "vector_cosine_dist":
                    for arguments in zero_cases:
                        _expect_sql_error(cursor, sql, arguments, "zero-norm")
                        cases += 1
                else:
                    for arguments, expected in zip(
                        zero_cases,
                        (float(VECTOR_DIMENSIONS), float(VECTOR_DIMENSIONS), 0.0),
                    ):
                        row = cursor.execute(sql, arguments).fetchone()
                        if row != (expected,):
                            raise AssertionError(
                                "Incorrect squared L2 distance for zero input: "
                                f"{row!r}"
                            )
                        cases += 1
            elif category == "blob_size":
                for length in (1, 2, 3, 5, 7, 511, 513):
                    malformed = (
                        struct.pack("<f", 1.0) * ((length + 3) // 4)
                    )[:length]
                    for arguments in (
                        (malformed, valid),
                        (valid, malformed),
                        (malformed, malformed),
                    ):
                        _expect_sql_error(cursor, sql, arguments, "multiple of four")
                        cases += 1
            else:
                raise ValueError(f"Unsupported boundary category: {category}")

    return {"category": category, "function": function, "cases": cases}


def _resident_memory_reader() -> Callable[[], int]:
    if sys.platform.startswith("linux"):
        statm = Path("/proc/self/statm")
        if statm.is_file():
            page_size = int(os.sysconf("SC_PAGE_SIZE"))

            def read_linux_rss() -> int:
                fields = statm.read_text(encoding="ascii").split()
                return int(fields[1]) * page_size

            return read_linux_rss

    if os.name == "nt":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = wintypes.HANDLE
        get_memory_info = psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_memory_info.restype = wintypes.BOOL
        process = get_current_process()

        def read_windows_rss() -> int:
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not get_memory_info(process, ctypes.byref(counters), counters.cb):
                raise ctypes.WinError(ctypes.get_last_error())
            return int(counters.WorkingSetSize)

        return read_windows_rss

    ps = shutil.which("ps")
    if os.name == "posix" and ps:
        command = [ps, "-o", "rss=", "-p", str(os.getpid())]
        environment = dict(os.environ, LC_ALL="C")

        def read_posix_rss() -> int:
            output = subprocess.check_output(
                command, text=True, encoding="ascii", env=environment, timeout=5
            )
            return int(output.strip()) * 1024

        return read_posix_rss

    raise RuntimeError("Current resident-memory measurement is unavailable.")


def _distance_loop(
    cursor: sqlite3.Cursor,
    arguments: tuple[bytes, bytes],
    count: int,
    offset: int = 0,
) -> None:
    statements = tuple(DISTANCE_SQL.values())
    for index in range(offset, offset + count):
        row = cursor.execute(statements[index & 1], arguments).fetchone()
        if row is None or not isinstance(row[0], (int, float)):
            raise AssertionError(f"Distance computation returned an invalid value: {row!r}")
        if not math.isfinite(row[0]):
            raise AssertionError(f"Distance computation returned a non-finite value: {row!r}")


def _memory_slope(samples: list[dict[str, int]]) -> float:
    count = len(samples)
    sum_x = sum(sample["calls"] for sample in samples)
    sum_y = sum(sample["rss_bytes"] for sample in samples)
    sum_xy = sum(sample["calls"] * sample["rss_bytes"] for sample in samples)
    sum_x_squared = sum(sample["calls"] ** 2 for sample in samples)
    denominator = count * sum_x_squared - sum_x**2
    return (count * sum_xy - sum_x * sum_y) / denominator


def _memory_worker(extension: Path) -> dict[str, Any]:
    read_rss = _resident_memory_reader()
    arguments = (
        VECTOR_STRUCT.pack(
            *(float(index % 11 + 1) for index in range(VECTOR_DIMENSIONS))
        ),
        VECTOR_STRUCT.pack(
            *(float(index % 7 - 3) for index in range(VECTOR_DIMENSIONS))
        ),
    )

    with closing(_open_database(extension)) as connection:
        with closing(connection.cursor()) as cursor:
            _distance_loop(cursor, arguments, STRESS_WARMUP_COMPUTATIONS)
            tracemalloc.start(1)
            try:
                for _ in range(3):
                    read_rss()
                    tracemalloc.get_traced_memory()
                    gc.collect()

                baseline_rss = read_rss()
                baseline_python, _ = tracemalloc.get_traced_memory()
                tracemalloc.reset_peak()
                samples = [{
                    "calls": 0,
                    "rss_bytes": baseline_rss,
                    "python_bytes": baseline_python,
                }]

                completed = 0
                while completed < STRESS_COMPUTATIONS:
                    batch_size = min(
                        STRESS_SAMPLE_INTERVAL, STRESS_COMPUTATIONS - completed
                    )
                    _distance_loop(cursor, arguments, batch_size, completed)
                    completed += batch_size
                    gc.collect()
                    rss = read_rss()
                    python_current, _ = tracemalloc.get_traced_memory()
                    samples.append({
                        "calls": completed,
                        "rss_bytes": rss,
                        "python_bytes": python_current,
                    })

                _, python_peak = tracemalloc.get_traced_memory()
                return {
                    "category": "memory",
                    "computations": completed,
                    "baseline_rss_bytes": baseline_rss,
                    "final_rss_bytes": samples[-1]["rss_bytes"],
                    "retained_rss_growth_bytes": max(
                        0, samples[-1]["rss_bytes"] - baseline_rss
                    ),
                    "peak_rss_growth_bytes": max(
                        0, max(sample["rss_bytes"] for sample in samples) - baseline_rss
                    ),
                    "python_allocation_growth_bytes": max(
                        0, samples[-1]["python_bytes"] - baseline_python
                    ),
                    "python_peak_growth_bytes": max(0, python_peak - baseline_python),
                    "rss_growth_bytes_per_call": _memory_slope(samples),
                    "samples": samples,
                }
            finally:
                tracemalloc.stop()


def _run_isolated(
    extension: Path, category: str, function: str | None = None
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--_qa-worker",
        category,
        str(extension),
    ]
    if function is not None:
        command.extend(("--function", function))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120 if category == "memory" else 30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"Isolated {category} test timed out.", pytrace=False)

    if completed.returncode != 0:
        pytest.fail(
            f"Isolated {category} test failed or crashed "
            f"(exit status {completed.returncode}).\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            pytrace=False,
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        pytest.fail(
            f"Invalid {category} worker report: {error}\n{completed.stdout}",
            pytrace=False,
        )
    if not isinstance(report, dict) or report.get("category") != category:
        pytest.fail(f"Unexpected worker report: {report!r}", pytrace=False)
    return report


def _percentile(values: list[int], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def test_correctness_and_six_decimal_accuracy(database: sqlite3.Connection) -> None:
    expected_cosine = 1.0 - 20.0 / math.sqrt(30.0 * 30.0)
    expected_l2_squared = 9.0 + 1.0 + 1.0 + 9.0
    for first, second in ((KNOWN_A, KNOWN_B), (KNOWN_B, KNOWN_A)):
        row = database.execute(
            "SELECT vector_cosine_dist(:a, :b), vector_l2_dist(:a, :b)",
            {"a": first, "b": second},
        ).fetchone()
        assert row is not None
        cosine, l2_squared = row
        assert isinstance(cosine, float) and math.isfinite(cosine)
        assert isinstance(l2_squared, float) and math.isfinite(l2_squared)
        assert cosine == pytest.approx(expected_cosine, rel=0, abs=0.0000005)
        assert l2_squared == pytest.approx(expected_l2_squared, rel=0, abs=0.0000005)


@pytest.mark.parametrize("function", DISTANCE_FUNCTIONS)
def test_dimension_mismatch_does_not_crash(extension_path: Path, function: str) -> None:
    report = _run_isolated(extension_path, "dimensions", function)
    assert report["function"] == function
    assert report["cases"] == 2


@pytest.mark.parametrize("function", DISTANCE_FUNCTIONS)
def test_empty_and_zero_vectors_do_not_crash(
    extension_path: Path, function: str
) -> None:
    report = _run_isolated(extension_path, "empty_zero", function)
    assert report["function"] == function
    assert report["cases"] == 6


@pytest.mark.parametrize("function", DISTANCE_FUNCTIONS)
def test_invalid_blob_sizes_do_not_crash(extension_path: Path, function: str) -> None:
    report = _run_isolated(extension_path, "blob_size", function)
    assert report["function"] == function
    assert report["cases"] == 21


def test_knn_average_latency_under_15_milliseconds(
    database: sqlite3.Connection,
    capsys: pytest.CaptureFixture[str],
    record_property: Callable[[str, object], None],
) -> None:
    generator = random.Random(RANDOM_SEED)
    database.execute("PRAGMA temp_store = MEMORY")
    database.execute(
        "CREATE TEMP TABLE vectors ("
        "id INTEGER PRIMARY KEY, "
        "embedding BLOB NOT NULL CHECK(length(embedding) = 512))"
    )

    def rows() -> Iterator[tuple[int, bytes]]:
        for identifier in range(1, DATASET_ROWS + 1):
            yield identifier, VECTOR_STRUCT.pack(
                *(generator.uniform(-1.0, 1.0) for _ in range(VECTOR_DIMENSIONS))
            )

    with database:
        database.executemany(
            "INSERT INTO vectors(id, embedding) VALUES (?, ?)", rows()
        )

    query = VECTOR_STRUCT.pack(
        *(generator.uniform(-1.0, 1.0) for _ in range(VECTOR_DIMENSIONS))
    )
    parameters = {"query": query}
    durations_ns: list[int] = []
    with closing(database.cursor()) as cursor:
        baseline = None
        for _ in range(BENCHMARK_WARMUP_ITERATIONS):
            result = cursor.execute(KNN_SQL, parameters).fetchall()
            if baseline is None:
                baseline = result
            assert result == baseline

        assert baseline is not None
        assert len(baseline) == 10
        assert len({row[0] for row in baseline}) == 10
        assert all(1 <= row[0] <= DATASET_ROWS for row in baseline)
        for _ in range(BENCHMARK_ITERATIONS):
            started_ns = time.perf_counter_ns()
            result = cursor.execute(KNN_SQL, parameters).fetchall()
            elapsed_ns = time.perf_counter_ns() - started_ns
            durations_ns.append(elapsed_ns)
            assert result == baseline

    mean_ns = math.fsum(durations_ns) / len(durations_ns)
    metrics_ms = {
        "mean_ms": mean_ns / 1_000_000,
        "p50_ms": _percentile(durations_ns, 0.50) / 1_000_000,
        "p95_ms": _percentile(durations_ns, 0.95) / 1_000_000,
        "p99_ms": _percentile(durations_ns, 0.99) / 1_000_000,
    }
    record_property("knn_rows", DATASET_ROWS)
    record_property("knn_dimensions", VECTOR_DIMENSIONS)
    record_property("knn_iterations", BENCHMARK_ITERATIONS)
    record_property("knn_seed", RANDOM_SEED)
    record_property("knn_sqlite_version", sqlite3.sqlite_version)
    record_property("knn_samples_ns", json.dumps(durations_ns))
    for name, value in metrics_ms.items():
        record_property(f"knn_{name}", value)
    with capsys.disabled():
        print(
            f"\nKNN: rows={DATASET_ROWS}, dimensions={VECTOR_DIMENSIONS}, "
            f"iterations={BENCHMARK_ITERATIONS}, percentile_method=linear, "
            + ", ".join(f"{name}={value:.6f}" for name, value in metrics_ms.items()),
            flush=True,
        )
    assert mean_ns < MAX_AVERAGE_QUERY_NS, (
        f"Average KNN latency was {metrics_ms['mean_ms']:.6f} ms; "
        "required average is strictly below 15.000000 ms."
    )


def test_memory_stability_across_50000_ffi_computations(
    extension_path: Path,
    capsys: pytest.CaptureFixture[str],
    record_property: Callable[[str, object], None],
) -> None:
    report = _run_isolated(extension_path, "memory")
    assert report["computations"] == STRESS_COMPUTATIONS
    metrics = {
        "retained_rss_growth_bytes": report["retained_rss_growth_bytes"],
        "peak_rss_growth_bytes": report["peak_rss_growth_bytes"],
        "python_allocation_growth_bytes": report["python_allocation_growth_bytes"],
        "rss_growth_bytes_per_call": report["rss_growth_bytes_per_call"],
    }
    record_property("memory_computations", STRESS_COMPUTATIONS)
    record_property("memory_samples", json.dumps(report["samples"]))
    for name, value in metrics.items():
        record_property(f"memory_{name}", value)
    with capsys.disabled():
        print(
            f"\nMemory: computations={STRESS_COMPUTATIONS}, "
            + ", ".join(f"{name}={value}" for name, value in metrics.items()),
            flush=True,
        )
    details = json.dumps(report, sort_keys=True)
    assert report["retained_rss_growth_bytes"] <= MAX_RETAINED_RSS_GROWTH, details
    assert report["peak_rss_growth_bytes"] <= MAX_PEAK_RSS_GROWTH, details
    assert (
        report["python_allocation_growth_bytes"] <= MAX_PYTHON_ALLOCATION_GROWTH
    ), details
    assert (
        report["rss_growth_bytes_per_call"] <= MAX_RSS_GROWTH_BYTES_PER_CALL
    ), details


def _main(arguments: list[str]) -> int:
    if arguments[:1] == ["--_qa-worker"]:
        faulthandler.enable()
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "category", choices=("dimensions", "empty_zero", "blob_size", "memory")
        )
        parser.add_argument("extension", type=Path)
        parser.add_argument("--function", choices=DISTANCE_FUNCTIONS)
        options = parser.parse_args(arguments[1:])
        if options.category == "memory":
            report = _memory_worker(options.extension)
        else:
            if options.function is None:
                parser.error("--function is required for boundary tests")
            report = _boundary_worker(
                options.extension, options.category, options.function
            )
        print(json.dumps(report, allow_nan=False, sort_keys=True), flush=True)
        return 0
    return int(pytest.main([str(Path(__file__).resolve()), *arguments]))


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
