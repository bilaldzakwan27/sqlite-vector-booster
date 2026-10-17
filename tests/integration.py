import concurrent.futures
import math
import os
import random
import sqlite3
import struct
import unittest
from pathlib import Path

LIBRARY = Path(os.environ["SQLITE_VECTOR_BOOSTER_LIBRARY"]).resolve(strict=True)


def vector(values):
    return struct.pack(f"<{len(values)}f", *values)


def connect():
    db = sqlite3.connect(":memory:")
    db.enable_load_extension(True)
    db.load_extension(str(LIBRARY))
    db.enable_load_extension(False)
    return db


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()

    def tearDown(self):
        self.db.close()

    def distance(self, name, a, b):
        return self.db.execute(f"SELECT {name}(?, ?)", (a, b)).fetchone()[0]

    def test_known_values_and_nulls(self):
        a, b = vector([1, 0]), vector([0, 1])
        self.assertEqual(self.distance("vector_l2_dist", a, b), 2.0)
        self.assertEqual(self.distance("vector_cosine_dist", a, b), 1.0)
        for name in ("vector_cosine_dist", "vector_l2_dist"):
            self.assertIsNone(self.distance(name, None, a))
            self.assertIsNone(self.distance(name, a, None))
            self.assertIsNone(self.distance(name, None, "invalid"))
        self.assertEqual(self.distance("vector_l2_dist", vector([0]), vector([0])), 0.0)
        self.assertEqual(self.distance("vector_cosine_dist", a, vector([-1, 0])), 2.0)

    def test_invalid_inputs(self):
        for name in ("vector_cosine_dist", "vector_l2_dist"):
            for a, b in [
                (b"", b""), (b"123", b"123"), (vector([1]), vector([1, 2])),
                ("text", "text"), (1, 2), (1.0, 2.0),
                (vector([math.nan]), vector([1])),
                (vector([math.inf]), vector([1])),
                (vector([-math.inf]), vector([1])),
            ]:
                with self.subTest(name=name, a=a):
                    with self.assertRaises(sqlite3.DatabaseError):
                        self.distance(name, a, b)
            with self.assertRaisesRegex(sqlite3.DatabaseError, "1048576"):
                self.db.execute(f"SELECT {name}(zeroblob(4194308), zeroblob(4194308))").fetchone()
            with self.assertRaises(sqlite3.DatabaseError):
                self.db.execute(f"SELECT {name}(?)", (vector([1]),))
        with self.assertRaisesRegex(sqlite3.DatabaseError, "zero-norm"):
            self.distance("vector_cosine_dist", vector([0, -0.0]), vector([1, 2]))

    def test_random_dimensions_and_tails(self):
        rng = random.Random(2025)
        for dim in list(range(1, 66)) + [127, 128, 129, 384, 768, 1536, 4097]:
            a = vector([rng.uniform(-10, 10) for _ in range(dim)])
            b = vector([rng.uniform(-10, 10) for _ in range(dim)])
            x, y = struct.unpack(f"<{dim}f", a), struct.unpack(f"<{dim}f", b)
            l2 = math.fsum((i - j) ** 2 for i, j in zip(x, y))
            dot = math.fsum(i * j for i, j in zip(x, y))
            cosine = 1 - dot / math.sqrt(math.fsum(i*i for i in x) * math.fsum(j*j for j in y))
            self.assertTrue(math.isclose(self.distance("vector_l2_dist", a, b), l2, rel_tol=1e-12))
            self.assertAlmostEqual(self.distance("vector_cosine_dist", a, b), cosine, places=12)

    def test_extremes(self):
        for value in [struct.unpack('<f', bytes.fromhex('ffff7f7f'))[0], 2**-149, 2**-126]:
            a, b = vector([value] * 33), vector([-value] * 33)
            self.assertAlmostEqual(self.distance("vector_cosine_dist", a, b), 2.0, places=12)
            self.assertTrue(math.isfinite(self.distance("vector_l2_dist", a, b)))

    def test_knn_and_metadata_index(self):
        self.db.execute("CREATE TABLE docs(id INTEGER PRIMARY KEY, tenant INTEGER, vec BLOB)")
        self.db.execute("CREATE INDEX tenant_index ON docs(tenant)")
        self.db.executemany("INSERT INTO docs VALUES (?, ?, ?)", [
            (1, 1, vector([1, 0])), (2, 1, vector([0, 1])),
            (3, 1, vector([-1, 0])), (4, 2, vector([1, 0])),
        ])
        rows = self.db.execute(
            "SELECT id FROM docs WHERE tenant = ?2 ORDER BY vector_cosine_dist(vec, ?1), id LIMIT 10",
            {"1": vector([1, 0]), "2": 1},
        ).fetchall()
        self.assertEqual(rows, [(1,), (2,), (3,)])
        plan = self.db.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM docs WHERE tenant = 1 ORDER BY vector_cosine_dist(vec, ?)",
            (vector([1, 0]),),
        ).fetchall()
        self.assertTrue(any("tenant_index" in row[3] for row in plan))

    def test_deterministic_and_innocuous(self):
        self.db.execute("PRAGMA trusted_schema = OFF")
        self.db.execute("CREATE TABLE vectors(v BLOB)")
        self.db.execute("CREATE INDEX distance_index ON vectors(vector_l2_dist(v, X'0000803F'))")
        self.db.execute("INSERT INTO vectors VALUES (?)", (vector([2]),))
        self.assertEqual(self.db.execute("SELECT vector_l2_dist(v, X'0000803F') FROM vectors").fetchone()[0], 1.0)
        rows = self.db.execute("PRAGMA function_list").fetchall()
        functions = {row[0]: row for row in rows if row[0].startswith("vector_")}
        for name in ["vector_cosine_dist", "vector_l2_dist"]:
            self.assertEqual(functions[name][4], 2)
            self.assertEqual(functions[name][5] & 0x200800, 0x200800)

    def test_reload(self):
        self.db.enable_load_extension(True)
        self.db.load_extension(str(LIBRARY))
        self.db.enable_load_extension(False)
        self.assertEqual(self.distance("vector_l2_dist", vector([1]), vector([2])), 1.0)

    def test_concurrent_connections(self):
        def worker(seed):
            db = connect()
            try:
                for _ in range(50):
                    result = db.execute("SELECT vector_l2_dist(?, ?)", (vector([seed, 1]), vector([seed, 2]))).fetchone()[0]
                    if result != 1.0:
                        raise AssertionError(result)
            finally:
                db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(worker, range(32)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
