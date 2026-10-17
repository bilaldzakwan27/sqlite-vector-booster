# SQLite Vector Booster

[![Build and test](https://github.com/bilaldzakwan27/sqlite-vector-booster/actions/workflows/release.yml/badge.svg)](https://github.com/bilaldzakwan27/sqlite-vector-booster/actions/workflows/release.yml)
[MIT license](LICENSE) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Security](SECURITY.md)

Exact vector distance functions for SQLite, implemented in Rust with portable SIMD.
No third-party Rust dependencies or separately linked SQLite runtime: the extension
uses the loading connection's SQLite extension API.

| Function | Result |
| --- | --- |
| `vector_cosine_dist(a, b)` | `1 − dot(a,b) / (norm(a) × norm(b))`, clamped to `[0, 2]` |
| `vector_l2_dist(a, b)` | **Squared** Euclidean distance, `sum((a[i] − b[i])²)` |

Lower distances mean closer vectors. Both functions are deterministic and innocuous.
`vector_l2_dist` does **not** take a square root. These are scalar functions for
exhaustive exact search, not an ANN index or virtual table.

## Quickstart: Python wheel, no Rust required

1. Download a wheel from [GitHub Releases](https://github.com/bilaldzakwan27/sqlite-vector-booster/releases/latest).
2. Match the wheel to your **Python process architecture** using the table below.
3. Install it in a virtual environment and run your first query:

```sh
# Linux/macOS; on Ubuntu/Zorin install python3-venv first (see Prerequisites).
python3 -m venv .venv
source .venv/bin/activate
python -m pip install /absolute/path/to/the-downloaded.whl
python -c "import sqlite3, sqlite_vector_booster as v; c=sqlite3.connect(':memory:'); v.load(c); print(c.execute('SELECT vector_l2_dist(?, ?)', (bytes.fromhex('0000803F'), bytes.fromhex('00000040'))).fetchone()); c.close()"
```

Expected output: `(1.0,)`. Replace the wheel path with the exact downloaded filename.
For Windows PowerShell create the environment with `py -3 -m venv .venv`, activate
with `.venv\Scripts\Activate.ps1`, then run the two `python` commands above.
If activation is blocked, use `.venv\Scripts\python.exe` directly; activation is optional.

| Process / system | Wheel suffix | Prebuilt environment |
| --- | --- | --- |
| Linux x86-64 | `py3-none-linux_x86_64.whl` | glibc 2.35+ (Ubuntu 22.04+ baseline); not Alpine/musl |
| Windows x86-64 | `py3-none-win_amd64.whl` | 64-bit Windows Python |
| macOS Apple Silicon | `py3-none-macosx_11_0_arm64.whl` | macOS 15+ tested; binary deployment target 11 |
| macOS Intel / Rosetta Python | `py3-none-macosx_11_0_x86_64.whl` | macOS 15+ tested; binary deployment target 11 |

**Release status:** version **0.1.1** includes the compatibility and onboarding fixes. Existing **v0.1.0**
macOS wheels are tagged `macosx_15_0` and need macOS 15+ for pip installation.
macOS **15+** is the tested support baseline for both architectures. macOS 11–14
remain unverified: the binary deployment target and wheel tag are 11, but that is
not a runtime support guarantee. Do not rename old wheels to bypass compatibility checks.
Linux arm64, Windows arm64, and musl are not prebuilt release targets.
PyPI/npm registry publication is not configured; use the explicit local package or release asset instructions.

## Prerequisites

| Route | Required tools |
| --- | --- |
| Python wheel | Python 3.9+, pip, SQLite 3.31+ with extension loading; no Rust/linker |
| Python/npm source | Rustup, pinned nightly Rust, native linker; Python 3.9+ or Node 18+ |
| Built-in Node SQLite example / full contributor tests | Node 24+ |
| better-sqlite3 application | A driver version compatible with your Node release; Node 24 recommended |
| SQLite CLI | SQLite 3.31+ CLI with loadable extensions and a built/downloaded native library |

Ubuntu/Zorin/Debian source and CLI prerequisites:

```sh
sudo apt update
sudo apt install git build-essential python3 python3-venv python3-pip sqlite3
```

Install Rustup from [rustup.rs](https://rustup.rs), reopen your terminal, and check
`rustup --version` and `cargo --version`. On macOS install Xcode Command Line Tools
with `xcode-select --install`; on Windows install Visual Studio Build Tools with
**Desktop development with C++**. Prebuilt Python wheels avoid compiler prerequisites.
Use a Python SQLite build that exposes `sqlite3.Connection.enable_load_extension`.

## Get the source

```sh
git clone https://github.com/bilaldzakwan27/sqlite-vector-booster.git
cd sqlite-vector-booster
```

Or download **Source code (zip)** from the desired release, extract it, and open a
terminal inside the extracted directory. Access is required while the repository is private.
All source commands below run from the repository root unless stated otherwise.

## Build the native extension

```sh
rustup toolchain install nightly-2026-10-17 --profile minimal --component rustfmt --component clippy
cargo build --release --locked
```

`std::simd` requires nightly; `rust-toolchain.toml` pins the compiler.

| Platform | Local output |
| --- | --- |
| Linux | `target/release/libsqlite_vector_booster.so` |
| macOS | `target/release/libsqlite_vector_booster.dylib` |
| Windows | `target/release/sqlite_vector_booster.dll` |

Release builds use opt-level 3, full LTO, and one codegen unit. Runtime dispatch
selects AVX2 on supported x86-64 CPUs. The baseline uses portable SIMD (SSE2 on
x86-64 and NEON on arm64); distributed binaries do not require AVX2 or target-cpu=native.
Matching process architecture is required.

## Python source installation

After the source prerequisites above:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

On Windows use `py -3 -m venv .venv` and `.venv\Scripts\Activate.ps1` instead of the
first two commands. The installer compiles and packages the extension in a platform wheel.

```python
import sqlite3
import struct
import sqlite_vector_booster

connection = sqlite3.connect(":memory:")
sqlite_vector_booster.load(connection)
a = struct.pack("<3f", 1.0, 0.0, 0.0)
b = struct.pack("<3f", 0.0, 1.0, 0.0)
print(connection.execute(
    "SELECT vector_cosine_dist(?1, ?2), vector_l2_dist(?1, ?2)",
    {"1": a, "2": b},
).fetchone())  # (1.0, 2.0)
connection.close()
```

The loader disables extension loading after initialization, including a failed load.
Run `python example.py` for an executable **insert → commit → close → reopen →
tenant-filtered nearest-neighbor search**. Expected output:

```text
[(1, 'closest', 0.0), (2, 'orthogonal', 1.0)]
```

## npm source installation

From the repository root, with Rust available:

```sh
npm pack
mkdir vector-example
cd vector-example
npm init -y
npm install ../sqlite-vector-booster-0.1.1.tgz
```

The install script compiles Rust locally; it does not download executable code.
On Node 24+, run a complete example using the built-in SQLite driver:

```sh
# Inside vector-example; PowerShell can use Copy-Item instead of cp.
cp ../example-node.cjs .
node example-node.cjs
```

Expected output: `{ cosine: 1, l2: 2 }`.
For the alternative `better-sqlite3` driver, install a version compatible with Node:

```sh
npm install better-sqlite3
```

```javascript
const Database = require('better-sqlite3');
const booster = require('sqlite-vector-booster');
const db = new Database(':memory:');
booster.load(db);
const a = Buffer.alloc(8);
const b = Buffer.alloc(8);
a.writeFloatLE(1, 0);
b.writeFloatLE(1, 4);
console.log(db.prepare(
  'SELECT vector_cosine_dist(?, ?) AS cosine, vector_l2_dist(?, ?) AS l2'
).get(a, b, a, b)); // { cosine: 1, l2: 2 }
db.close();
```

`booster.extensionPath()` returns the library path. `booster.load()` accepts a
synchronous `loadExtension()` driver. For Node DatabaseSync use `{ allowExtension: true }`
and call `db.enableLoadExtension(false)` after initialization, as in example-node.cjs.
The wrapper supports Node 18+; built-in SQLite examples and full CI use Node 24+.
Different drivers may embed different SQLite engines: use one driver per process
when loading this extension. Multiple connections to the same engine are supported.

## SQLite CLI

After building, run `sqlite3 :memory:` from the repo root and enter:

```sql
.load ./target/release/libsqlite_vector_booster
SELECT vector_cosine_dist(X'0000803F00000000', X'000000000000803F');
SELECT vector_l2_dist(X'0000803F00000000', X'000000000000803F');
```

Expected outputs: `1.0` and `2.0`. On Windows use
`.load ./target/release/sqlite_vector_booster`. For downloaded architecture-qualified
assets, load the exact absolute path. SQLite finds the exported sqlite3_extension_init entry point.

## Storage and nearest neighbors


Store raw **little-endian IEEE-754 f32** values, with no dimension header. All four
release architectures use this byte order. Alignment is unrestricted: BLOBs are
read as bytes and are never reinterpreted as aligned Rust float slices.

```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    vec BLOB NOT NULL CHECK(typeof(vec) = 'blob' AND length(vec) = 3072)
);
CREATE INDEX documents_tenant ON documents(tenant_id);

SELECT id, body, vector_cosine_dist(vec, ?1) AS distance
FROM documents
ORDER BY vector_cosine_dist(vec, ?1), id
LIMIT 10;

SELECT id, body, vector_l2_dist(vec, ?1) AS distance
FROM documents
WHERE tenant_id = ?2
ORDER BY distance, id
LIMIT 10;
```

Bind `?1` to a 768-dimensional BLOB and `?2` to a tenant ID. The tenant B-tree
reduces candidates before distance evaluation. For a minimal K-NN query:

```sql
SELECT id FROM documents ORDER BY vector_cosine_dist(vec, ?1) LIMIT 10;
```

These are exhaustive, exact searches over the selected candidates, with `O(N × d)`
distance work. The extension provides scalar functions, not an ANN index or virtual
table. An ordinary index on `vec` does not accelerate a changing query vector.
Deterministic expression indexes can serve a **fixed** query vector only, for example:

```sql
CREATE TABLE points(id INTEGER PRIMARY KEY, vec BLOB NOT NULL CHECK(length(vec) = 8));
CREATE INDEX points_fixed_origin ON points(vector_l2_dist(vec, X'0000000000000000'));
SELECT id FROM points ORDER BY vector_l2_dist(vec, X'0000000000000000') LIMIT 10;
```

## Input contract


| Input | Behavior |
| --- | --- |
| Either argument is SQL `NULL` | Returns SQL `NULL` without validating the other argument |
| Non-BLOB argument | SQL error; no text or numeric coercion |
| Empty BLOB or byte length not divisible by four | SQL error |
| Unequal dimensions | SQL error |
| More than 1,048,576 components per vector | SQL error |
| NaN or positive/negative infinity | SQL error |
| Zero norm in cosine distance | SQL error |
| Zero vector in squared L2 distance | Accepted |

Float components are promoted to f64 **before** arithmetic, preventing overflow
when squaring finite f32 values and preserving f32 subnormal inputs on the supported
targets. SIMD reduction order can differ from scalar accumulation in the last few
bits. Small cosine rounding excursions are clamped. Successful evaluations allocate
no heap memory and contain no mutable shared numerical state. SQLite's own
connection-threading rules still apply. Multiple connections to the same SQLite
engine may invoke the functions concurrently; loading one extension instance into
multiple independent SQLite engines in a single process is rejected.

Validate vectors at ingestion: require nonempty finite f32 arrays, one fixed
dimension per collection, and nonzero norm for cosine datasets. A schema byte-length
check cannot detect NaN or zero norm. A bad stored vector aborts the search with a
SQL error, so correct it before querying rather than silently dropping results.

## Verification

Activate the Python environment first. Full contributor tests need Node 24+;
see [CONTRIBUTING.md](CONTRIBUTING.md) for driver installation and Node 18 behavior.

```sh
cargo fmt --all --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --release --locked
cargo build --release --locked
python -m unittest discover -s tests -p 'test_*.py' -v
```

Linux CI additionally runs the actual SQLite CLI smoke test (`python tests/cli.py`),
including `.load`, both metrics, nearest-neighbor ordering, and malformed-input errors.
It requires the `sqlite3` executable and SQLITE_VECTOR_BOOSTER_LIBRARY.

For the SQLite integration suite:

```sh
export SQLITE_VECTOR_BOOSTER_LIBRARY="$PWD/target/release/libsqlite_vector_booster.so"
python tests/integration.py
```

On macOS change .so to .dylib. In Windows PowerShell:

```powershell
$env:SQLITE_VECTOR_BOOSTER_LIBRARY = (Resolve-Path target/release/sqlite_vector_booster.dll).Path
python tests/integration.py
```

Tests cover scalar agreement, SIMD tails, unaligned buffers, malformed BLOBs,
non-finite inputs, extremes, NULL semantics, expression indexes, K-NN ordering,
reload, concurrency, and SQLite ABI slot offsets. Rust unwinding is contained at C entry points.

```sh
python -m pip install -r requirements-qa.txt
python qa_suite.py -q -o junit_family=legacy --junitxml=qa-results/results.xml
```

The QA suite checks known 4D results, isolates malformed-input checks, and times
100 top-10 queries over 10,000 seeded 128D vectors after warm-up. Mean latency must
be strictly below 15 ms on the machine running the suite. P50/P95/P99 and all
100 latency samples are recorded. A separate process performs 50,000 alternating
metric calls and samples memory every 5,000 calls: limits are 4 MiB retained RSS,
8 MiB peak sampled RSS, 512 KiB retained Python allocations, and 64 bytes/call fitted
RSS growth. These are workload-specific bounded-growth checks, not a universal
no-leak guarantee. CI retains the JUnit report for each of four release targets.

## Benchmarks

After a release build, run on the actual deployment hardware:

```sh
cargo bench --locked --bench distance > benchmark-kernels.csv
python benchmarks/sqlite.py --rows 10000 --dimensions 768 --repetitions 7 > benchmark-sqlite.json
```

The SQL benchmark discovers the local build automatically, including CARGO_TARGET_DIR
and CARGO_BUILD_TARGET. Use `--library /absolute/path/to/library` for a downloaded binary.
Precedence: `--library`, then SQLITE_VECTOR_BOOSTER_LIBRARY, then build discovery.
Run `python benchmarks/sqlite.py --help` for options. Counts must be positive;
dimensions must not exceed 1,048,576.

The Rust harness reports median latency from seven samples of 100,000 pairs per
metric and dimension, including warm-up and optimization barriers. It compares
checked SIMD entry points with a scalar f64 reference over the same f32 BLOBs.
Reported GB/s is logical input volume for repeatedly reused buffers, not measured
DRAM bandwidth. The SQL benchmark measures warm, in-memory top-10 queries, including
SQLite function dispatch and ordering.

Measured on 2026-10-17: AMD Ryzen 7 4700U, Linux x86-64, SQLite 3.45.1,
Rust 1.101.0-nightly (`5d8fec066`), AVX2 runtime dispatch. This is one local run;
CPU frequency scaling and shared-host load were not controlled.

| Metric, 768 dimensions | SIMD | Scalar reference | Speedup |
| --- | ---: | ---: | ---: |
| Cosine, median ns/pair | 280.241 | 968.367 | 3.46× |
| Squared L2, median ns/pair | 163.781 | 680.142 | 4.15× |
| Cosine throughput, million pairs/s | 3.568 | 1.033 | — |
| Squared L2 throughput, million pairs/s | 6.106 | 1.470 | — |

```text
Exact top-10 cosine search: 10,000 rows × 768 dimensions
Median query latency:      6.931 ms
Observed range:            6.788–7.025 ms (7 runs)
Storage/cache:             warm, in-memory SQLite database
```

Raw measurements and environment details are checked in as
[`local-kernels.csv`](benchmarks/local-kernels.csv),
[`local-sqlite.json`](benchmarks/local-sqlite.json), and
[`local-environment.txt`](benchmarks/local-environment.txt).
These measurements are not a guarantee for other hardware or workloads. The release
workflow records fresh measurements on its Linux runner and attaches them to the release.

## Releases

The workflow builds and tests Linux x86-64, macOS x86-64, macOS arm64, and Windows
x86-64 on native runners. PRs and pushes to main run the same checks. After all
acceptance checks pass for 0.1.1:

```sh
git tag v0.1.1
git push origin v0.1.1
```

A v* tag must match the Rust, Python, and npm package versions. Publication waits
for all build jobs, attaches native libraries with SHA-256 checksums, Python wheels,
an npm source archive, and Linux benchmarks. It uses a scoped GITHUB_TOKEN, not a
stored PAT. PyPI/npm registry publication remains a separate operation.

Wheel creation verifies the native macOS binary's declared minimum OS and architecture.
CI checks the actual wheel filename, internal Tag, and bundled Mach-O header before
installation. Official macOS support is limited to the tested 15+ baseline. The 11 deployment
target is retained for compatibility engineering, without claiming verified 11–14 runtime support. Preserve old tags
and publish fixes under a new version. See [CONTRIBUTING.md](CONTRIBUTING.md) for the release checklist.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| python: command not found before activation | Use python3 -m venv .venv on Linux/macOS, or py -3 -m venv .venv on Windows |
| ensurepip is not available | On Ubuntu/Zorin install python3-venv; use the matching venv package for a separately installed Python |
| Cargo or pinned nightly missing | Install Rustup, reopen the terminal, and run the Build toolchain command; Python users may use a wheel |
| Native linker missing | Install build-essential, Xcode Command Line Tools, or Windows C++ Build Tools |
| Unsupported wheel | Check Python process architecture and OS tag; v0.1.0 macOS wheels require macOS 15+ |
| Python lacks extension loading | Use an extension-enabled Python build; Homebrew Python is one macOS option. Check with python -c "import sqlite3; print(hasattr(sqlite3.Connection, 'enable_load_extension'))" |
| not authorized when loading | Set allowExtension: true for DatabaseSync; ensure the runtime permits SQLite extensions |
| Native extension not installed | Reinstall the correct wheel or rebuild npm with scripts enabled and Rust available |
| vector arguments must be BLOBs | Pack little-endian f32; do not bind JSON arrays, TEXT, or raw float64 arrays |
| vector dimensions must match | Check byte lengths and ensure both vectors use the same embedding dimension |
| zero-norm / non-finite | Fix stored vectors at ingestion; cosine rejects zeros and both metrics reject NaN/infinity |
| Node 18 skips DatabaseSync test | Wrapper validation still runs; use Node 24+ for built-in SQLite integration |
| Benchmark library not found | Build first or pass --library; run --help for options |

When reporting a bug include package version, OS/process architecture, Python/Node
and SQLite versions, install route, exact command/error, and a minimal synthetic
vector example. Remove credentials and private vector data.

## License

MIT. SQLite ABI declarations follow SQLite's public-domain extension interface.
