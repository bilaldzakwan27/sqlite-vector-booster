'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
let DatabaseSync;
try {
  ({ DatabaseSync } = require('node:sqlite'));
} catch (error) {
  if (error.code !== 'ERR_UNKNOWN_BUILTIN_MODULE') throw error;
}
const { load } = require('../npm/index.cjs');

function vector(values) {
  const buffer = Buffer.alloc(values.length * 4);
  values.forEach((value, index) => buffer.writeFloatLE(value, index * 4));
  return buffer;
}

test('loader rejects invalid connection arguments on supported Node versions', () => {
  for (const value of [null, undefined, {}, 42]) {
    assert.throws(() => load(value), /synchronous loadExtension/);
  }
});

test('Node loads the packaged extension and executes both distances', {
  skip: !DatabaseSync && 'DatabaseSync integration requires Node 24+; wrapper tests still run on Node 18+',
}, () => {
  const db = new DatabaseSync(':memory:', { allowExtension: true });
  try {
    load(db);
    db.enableLoadExtension(false);
    const a = vector([1, 0, 0]);
    const b = vector([0, 1, 0]);
    const result = db.prepare(
      'SELECT vector_cosine_dist(?, ?) AS cosine, vector_l2_dist(?, ?) AS l2',
    ).get(a, b, a, b);
    assert.equal(result.cosine, 1);
    assert.equal(result.l2, 2);
    assert.throws(() => db.prepare("SELECT vector_l2_dist('text', 'text')").get(), /BLOB/);
  } finally {
    db.close();
  }
});
