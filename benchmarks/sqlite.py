import argparse
import json
import os
import platform
import random
import sqlite3
import statistics
import struct
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--rows", type=int, default=10000)
parser.add_argument("--dimensions", type=int, default=768)
parser.add_argument("--repetitions", type=int, default=7)
parser.add_argument("--library", type=Path, help="Native library path (overrides SQLITE_VECTOR_BOOSTER_LIBRARY)")
args = parser.parse_args()
if min(args.rows, args.dimensions, args.repetitions) <= 0:
    parser.error("all counts must be positive")
if args.dimensions > 1_048_576:
    parser.error("dimensions must not exceed 1048576")

configured = args.library or os.environ.get("SQLITE_VECTOR_BOOSTER_LIBRARY")
root = Path(__file__).resolve().parents[1]
library_name = {"Linux": "libsqlite_vector_booster.so", "Darwin": "libsqlite_vector_booster.dylib",
                "Windows": "sqlite_vector_booster.dll"}.get(platform.system())
if library_name is None:
    parser.error(f"unsupported operating system: {platform.system()}")
target_dir = Path(os.environ.get("CARGO_TARGET_DIR", "target"))
if not target_dir.is_absolute():
    target_dir = root / target_dir
triple = os.environ.get("CARGO_BUILD_TARGET", "")
candidates = [Path(configured).expanduser()] if configured else [
    target_dir / triple / "release" / library_name,
    target_dir / "release" / library_name,
]
library = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
if library is None:
    parser.error("Compiled extension not found. Run cargo build --release --locked, "
                 "then pass --library /absolute/path/to/the/library or set SQLITE_VECTOR_BOOSTER_LIBRARY.")

rng = random.Random(42)
pack = struct.Struct(f"<{args.dimensions}f")
query = pack.pack(*(rng.uniform(-1, 1) for _ in range(args.dimensions)))
db = sqlite3.connect(":memory:")
db.enable_load_extension(True)
db.load_extension(str(library))
db.enable_load_extension(False)
db.execute("CREATE TABLE embeddings(id INTEGER PRIMARY KEY, vec BLOB NOT NULL)")
db.executemany(
    "INSERT INTO embeddings(vec) VALUES (?)",
    ((pack.pack(*(rng.uniform(-1, 1) for _ in range(args.dimensions))),) for _ in range(args.rows)),
)
db.commit()
sql = "SELECT id FROM embeddings ORDER BY vector_cosine_dist(vec, ?1), id LIMIT 10"
db.execute(sql, {"1": query}).fetchall()
samples = []
for _ in range(args.repetitions):
    start = time.perf_counter_ns()
    db.execute(sql, {"1": query}).fetchall()
    samples.append((time.perf_counter_ns() - start) / 1e6)

try:
    rustc = subprocess.check_output(["rustc", "--version"], text=True).strip()
except (OSError, subprocess.SubprocessError):
    rustc = "unavailable"

print(json.dumps({
    "platform": platform.platform(),
    "cpu": platform.processor(),
    "python": platform.python_version(),
    "sqlite": sqlite3.sqlite_version,
    "rustc": rustc,
    "rows": args.rows,
    "dimensions": args.dimensions,
    "repetitions": args.repetitions,
    "median_query_ms": statistics.median(samples),
    "min_query_ms": min(samples),
    "max_query_ms": max(samples),
    "samples_ms": samples,
    "cache": "warm, in-memory database",
    "query": sql,
}, indent=2))
db.close()
