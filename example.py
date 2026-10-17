"""Run after installing the Python package: python example.py."""
import sqlite3
import struct
import tempfile
from pathlib import Path

import sqlite_vector_booster


def vector(*values):
    return struct.pack(f"<{len(values)}f", *values)


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "documents.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE documents(id INTEGER PRIMARY KEY, tenant INTEGER NOT NULL, body TEXT, vec BLOB NOT NULL CHECK(typeof(vec)='blob' AND length(vec)=12))")
    connection.executemany("INSERT INTO documents VALUES(?,?,?,?)", [
        (1, 15, "closest", vector(1, 0, 0)),
        (2, 15, "orthogonal", vector(0, 1, 0)),
        (3, 99, "another tenant", vector(1, 0, 0)),
    ])
    connection.commit()
    connection.close()

    connection = sqlite3.connect(path)
    sqlite_vector_booster.load(connection)
    rows = connection.execute(
        "SELECT id,body,vector_cosine_dist(vec,?1) AS distance FROM documents "
        "WHERE tenant=?2 ORDER BY distance,id LIMIT 10",
        {"1": vector(1, 0, 0), "2": 15},
    ).fetchall()
    connection.close()
    assert rows == [(1, "closest", 0.0), (2, "orthogonal", 1.0)], rows
    print(rows)
