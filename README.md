# SQLite Vector Booster

Exact vector distance functions for SQLite, implemented in Rust with portable SIMD.
The extension has no third-party Rust dependencies and no separately linked SQLite
runtime. It uses the loading connection's SQLite extension API.

| Function | Result |
| --- | --- |
| `vector_cosine_dist(a, b)` | `1 − dot(a,b) / (norm(a) × norm(b))`, clamped to `[0, 2]` |
| `vector_l2_dist(a, b)` | Squared Euclidean distance, `sum((a[i] − b[i])²)` |

Both functions are deterministic and innocuous. Lower distances mean closer vectors.
`vector_l2_dist` does **not** take a square root.

## Requirements

- SQLite 3.31.0 or newer, built with loadable extension support.
- Rustup and the pinned `nightly-2026-10-17` toolchain for source installations.
  `std::simd` requires nightly Rust; `rust-toolchain.toml` pins the compiler.
- A native linker: GCC/Clang on Linux, Xcode Command Line Tools on macOS, or
  Visual Studio Build Tools with Desktop development with C++ on Windows.
- Python 3.9+ for the Python wrapper; Node.js 18+ for the npm wrapper.

Release builds target Linux x86-64, macOS x86-64, macOS arm64, and Windows x86-64 MSVC.
Linux artifacts are built on Ubuntu 22.04 and require a compatible glibc environment;
macOS artifacts target macOS 11+. Matching process architecture is required.

## Build

From the repository root:

```sh
rustup toolchain install nightly-2026-10-17 --profile minimal --component rustfmt --component clippy
cargo build --release --locked
```

| Platform | Local output |
| --- | --- |
| Linux | `target/release/libsqlite_vector_booster.so` |
| macOS | `target/release/libsqlite_vector_booster.dylib` |
| Windows | `target/release/sqlite_vector_booster.dll` |

Release optimization uses `opt-level = 3`, full LTO, and one codegen unit.
Runtime detection selects AVX2 on supported x86-64 CPUs; the baseline uses
portable SIMD, including SSE2 on x86-64 and NEON on arm64. Distributed binaries
do not require AVX2. There is no `target-cpu=native` requirement.

## Python installation

Install directly from this checkout. These commands do not depend on a package
having been published to PyPI:

```sh
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS or
`.venv\Scripts\Activate.ps1` in Windows PowerShell, then:

```sh
python -m pip install --upgrade pip
python -m pip install .
```

The installer compiles the extension and packages it inside a platform-specific
wheel. To install a downloaded release wheel, run `python -m pip install` followed
by its filename. Rust is unnecessary when installing a prebuilt wheel.

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

The loader disables extension loading after initialization. Python distributions
whose SQLite module omits extension loading need an extension-enabled Python build.

## npm installation

From this repository's root, build a source package and install it in an application:

```sh
npm pack
mkdir vector-example
cd vector-example
npm init -y
npm install ../sqlite-vector-booster-0.1.0.tgz better-sqlite3
```

The installation script compiles the Rust extension. The npm package is source-based;
it does not download executable code or claim registry publication.

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

`booster.extensionPath()` returns the library path for other extension-capable
SQLite drivers. `booster.load()` supports synchronous `loadExtension()` drivers,
including `better-sqlite3` and Node's `DatabaseSync` configured with
`{ allowExtension: true }`. Node's built-in SQLite API requires a newer Node version
than the wrapper's minimum; CI exercises it on Node 24.

## SQLite CLI

```sql
.load ./target/release/libsqlite_vector_booster
SELECT vector_cosine_dist(X'0000803F00000000', X'000000000000803F');
SELECT vector_l2_dist(X'0000803F00000000', X'000000000000803F');
```

The outputs are `1.0` and `2.0`. On Windows, use
`.load ./target/release/sqlite_vector_booster`. SQLite discovers the exported
`sqlite3_extension_init` entry point. Downloaded release assets may retain their
architecture-qualified names; load their exact absolute path.

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

## Verification

```sh
cargo fmt --all --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --release --locked
cargo build --release --locked
```

Set the library path before the SQL integration suite:

```sh
export SQLITE_VECTOR_BOOSTER_LIBRARY="$PWD/target/release/libsqlite_vector_booster.so"
python tests/integration.py
```

On macOS change `.so` to `.dylib`. In Windows PowerShell:

```powershell
$env:SQLITE_VECTOR_BOOSTER_LIBRARY = (Resolve-Path target/release/sqlite_vector_booster.dll).Path
python tests/integration.py
```

Tests cover scalar reference agreement, SIMD tails, unaligned buffers, malformed
BLOBs, non-finite inputs, numerical extremes, SQL NULL behavior, expression indexes,
K-NN ordering, repeated loading, and concurrent independent connections. Rust tests
also verify SQLite ABI slot offsets. Rust unwinding is contained at C entry points.

## Benchmarks

Run benchmarks on the actual deployment hardware:

```sh
cargo bench --locked --bench distance > benchmark-kernels.csv
python benchmarks/sqlite.py --rows 10000 --dimensions 768 --repetitions 7 > benchmark-sqlite.json
```

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

`.github/workflows/release.yml` builds and tests each target on a matching native
runner. Pull requests and pushes to `main` run the same checks. To release version
0.1.0 after all checks pass:

```sh
git tag v0.1.0
git push origin v0.1.0
```

A `v*` tag triggers all four builds. Publication requires every job to pass and the
tag to match the Rust, Python, and npm package versions. The workflow attaches
architecture-qualified `.so`, `.dylib`, and `.dll` files with SHA-256 checksums,
Python wheels, an npm source archive, and Linux benchmark outputs. Authentication
uses the workflow's scoped `GITHUB_TOKEN`; no PAT is stored in the repository.
PyPI and npm registry publication are separate operations and are not configured.

## License

MIT. SQLite ABI declarations follow SQLite's public-domain extension interface.
