'use strict';

const fs = require('node:fs');
const path = require('node:path');

function extensionPath() {
  const names = {
    linux: 'libsqlite_vector_booster.so',
    darwin: 'libsqlite_vector_booster.dylib',
    win32: 'sqlite_vector_booster.dll',
  };
  const name = names[process.platform];
  if (!name) throw new Error(`Unsupported operating system: ${process.platform}`);
  const file = path.join(__dirname, 'native', name);
  if (!fs.existsSync(file)) throw new Error(`Native extension not installed: ${file}`);
  return file;
}

function load(database) {
  if (!database || typeof database.loadExtension !== 'function') {
    throw new TypeError('A database with a synchronous loadExtension method is required');
  }
  database.loadExtension(extensionPath());
}

module.exports = { extensionPath, load };
