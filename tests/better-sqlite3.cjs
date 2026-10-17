'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { load } = require('../npm/index.cjs');
let Database;
try {
  Database = require('better-sqlite3');
} catch (error) {
  if (error.code !== 'MODULE_NOT_FOUND') throw error;
}
test('better-sqlite3 loads both vector functions', {
  skip: !Database && 'Install better-sqlite3 to test this optional driver; release CI installs it',
}, () => {
  const db = new Database(':memory:');
  try {
    load(db);
    const a = Buffer.alloc(8);
    const b = Buffer.alloc(8);
    a.writeFloatLE(1, 0);
    b.writeFloatLE(1, 4);
    const result = db.prepare(
      'SELECT vector_cosine_dist(?, ?) AS cosine, vector_l2_dist(?, ?) AS l2',
    ).get(a, b, a, b);
    assert.deepEqual(result, { cosine: 1, l2: 2 });
  } finally {
    db.close();
  }
});
