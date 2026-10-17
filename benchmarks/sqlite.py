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
args = parser.parse_args()
if min(args.rows, args.dimensions, args.repetitions) <= 0:
    parser.error("all counts must be positive")

rng = random.Random(42)
pack = struct.Struct(f"<{args.dimensions}f")
query = pack.pack(*(rng.uniform(-1, 1) for _ in range(args.dimensions)))
db = sqlite3.connect(":memory:")
db.enable_load_extension(True)
db.load_extension(str(Path(os.environ["SQLITE_VECTOR_BOOSTER_LIBRARY"]).resolve(strict=True)))
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
