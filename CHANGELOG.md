# Changelog

## 0.1.1 — Unreleased

- Generate macOS wheel tags from the declared deployment target instead of the
  build-host Python version; verify native Mach-O minimum OS and architecture.
- Add wheel-content validation and UAT regression checks to release CI.
- Explain missing Cargo, unsupported Python extension loading, and missing native libraries.
- Let the SQL benchmark discover local build output or accept --library; reject invalid counts early.
- Run Node 18 wrapper checks while clearly skipping unsupported built-in SQLite integration.
- Exercise better-sqlite3 separately in CI, add runnable Python/Node examples, and
  document installation routes, troubleshooting, contribution, and release acceptance.
- Clarify that existing v0.1.0 macOS wheels are tagged for macOS 15; source changes
  do not retroactively modify published release assets.

## 0.1.0

- Initial exact cosine and squared-L2 SQLite functions, portable SIMD kernels,
  strict BLOB validation, Python/npm loaders, and cross-platform native releases.
