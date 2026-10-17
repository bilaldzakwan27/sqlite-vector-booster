# Contributing

Use the source prerequisites in README: Git, the pinned Rust nightly with fmt/clippy,
a native linker, Python 3.9+ in a virtual environment, and Node 24+ for full integration tests.
Python 3.12 and Node 24 are the release CI versions. Building/releasing Python
artifacts additionally needs setuptools>=68 and wheel>=0.41 (pip installs these automatically).

## Local checks

From the repository root, after activating your Python environment:

```sh
cargo fmt --all --check
cargo clippy --locked --all-targets -- -D warnings
cargo build --release --locked
cargo test --release --locked
python -m pip install . -r requirements-qa.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python example.py
```

Set SQLITE_VECTOR_BOOSTER_LIBRARY to the absolute release library path as shown in
README Verification, then run:

```sh
python tests/integration.py
# Linux, with the sqlite3 CLI installed:
python tests/cli.py
python tests/python_package.py
python qa_suite.py -q -o junit_family=legacy --junitxml=qa-results/results.xml
node scripts/build-node.cjs
npm install --no-save --package-lock=false better-sqlite3
npm test
```

Node 18 runs wrapper argument tests and explains why DatabaseSync integration is
skipped. Use Node 24+ for that integration. The optional better-sqlite3 test skips
locally if its dependency is absent; release CI installs it. Driver tests run in
separate processes because the drivers may embed independent SQLite engines.
Skipped driver tests are not evidence that integration passed.

The 15 ms mean latency limit in qa_suite.py is a strict, machine-specific gate.
Investigate failures with the recorded environment and timings; do not quietly
relax the gate to make a slower machine pass.

## Regression reports

Open an issue with: version/commit, OS and process architecture, runtime and SQLite
versions, exact command, expected and actual output, and a minimal synthetic input.
For an installation failure, include whether you used a wheel, source checkout,
or npm archive. For crashes include sanitized exit status and reproducer. Do not
include credentials, personal records, or proprietary embeddings.

For contributions, use a branch and pull request. Explain the user-visible behavior
and the checks run. Add a focused regression test when fixing a functional failure.

## Release acceptance

1. Keep Cargo.toml, Cargo.lock, pyproject.toml, package.json, and Python __version__ in sync.
2. Build from the exact candidate commit; require every native CI target to pass.
3. Inspect each wheel with `python verify_wheel.py <wheel-file>`. On macOS this checks
   the filename, internal Tag, binary architecture, and native minimum deployment version.
4. Install the generated wheel and npm archive in clean application environments;
   run both scalar functions and the runnable examples. Verify CLI loading separately.
5. Test on the minimum OS being claimed. A successful macOS 15 runner and a correct
   Mach-O header do not replace a macOS 11 runtime test. Record anything untested.
6. Create a new version tag only after acceptance. Preserve previous release tags.
7. After publication, download the actual assets, verify their checksums, repeat the
   smoke tests, and check anonymous access if the repository is public.

Source fixes do not rewrite existing v0.1.0 release assets. Publish 0.1.1 through
the tag workflow after checks pass. The tested macOS support baseline is 15+;
macOS 11–14 must remain explicitly unverified until runtime acceptance is available.
