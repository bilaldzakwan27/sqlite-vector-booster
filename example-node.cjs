'use strict';
// Copy into an application containing the installed npm package; run on Node 24+.
const { DatabaseSync } = require('node:sqlite');
const booster = require('sqlite-vector-booster');
const db = new DatabaseSync(':memory:', { allowExtension: true });
try {
  booster.load(db);
  db.enableLoadExtension(false);
  const a = Buffer.alloc(8);
  const b = Buffer.alloc(8);
  a.writeFloatLE(1, 0);
  b.writeFloatLE(1, 4);
  const result = db.prepare(
    'SELECT vector_cosine_dist(?, ?) AS cosine, vector_l2_dist(?, ?) AS l2',
  ).get(a, b, a, b);
  if (result.cosine !== 1 || result.l2 !== 2) throw new Error('Unexpected vector distance');
  console.log({ ...result }); // { cosine: 1, l2: 2 }
} finally {
  db.close();
}
