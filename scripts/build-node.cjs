'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
function fail(message) {
  console.error(`sqlite-vector-booster: ${message}`);
  process.exit(1);
}
const names = {
  linux: 'libsqlite_vector_booster.so',
  darwin: 'libsqlite_vector_booster.dylib',
  win32: 'sqlite_vector_booster.dll',
};
const name = names[process.platform];
if (!name) fail(`Unsupported operating system: ${process.platform}`);

let source = process.env.SQLITE_VECTOR_BOOSTER_LIBRARY;
if (!source) {
  const result = spawnSync('cargo', ['build', '--release', '--locked'], {
    cwd: root,
    stdio: 'inherit',
  });
  if (result.error) {
    if (result.error.code === 'ENOENT') {
      fail('Cargo was not found in PATH. Install Rustup from https://rustup.rs and ' +
        'the toolchain in rust-toolchain.toml, reopen your terminal, and retry npm install.');
    }
    fail(`Could not start Cargo: ${result.error.message}`);
  }
  if (result.status !== 0) fail('Rust build failed. Check the compiler output above and README.md linker/toolchain prerequisites.');
  const target = path.resolve(root, process.env.CARGO_TARGET_DIR || 'target');
  source = path.join(target, process.env.CARGO_BUILD_TARGET || '', 'release', name);
}
if (!fs.existsSync(path.resolve(source))) fail(`Native extension does not exist: ${source}. Build it first or correct SQLITE_VECTOR_BOOSTER_LIBRARY.`);
const destination = path.join(root, 'npm', 'native');
fs.mkdirSync(destination, { recursive: true });
fs.copyFileSync(path.resolve(source), path.join(destination, name));
