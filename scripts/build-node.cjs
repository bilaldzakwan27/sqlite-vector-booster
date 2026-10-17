'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const names = {
  linux: 'libsqlite_vector_booster.so',
  darwin: 'libsqlite_vector_booster.dylib',
  win32: 'sqlite_vector_booster.dll',
};
const name = names[process.platform];
if (!name) throw new Error(`Unsupported operating system: ${process.platform}`);

let source = process.env.SQLITE_VECTOR_BOOSTER_LIBRARY;
if (!source) {
  const result = spawnSync('cargo', ['build', '--release', '--locked'], {
    cwd: root,
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
  const target = path.resolve(root, process.env.CARGO_TARGET_DIR || 'target');
  source = path.join(target, process.env.CARGO_BUILD_TARGET || '', 'release', name);
}
const destination = path.join(root, 'npm', 'native');
fs.mkdirSync(destination, { recursive: true });
fs.copyFileSync(path.resolve(source), path.join(destination, name));
