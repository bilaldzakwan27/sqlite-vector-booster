import sqlite3
import struct

import sqlite_vector_booster

connection = sqlite3.connect(":memory:")
try:
    sqlite_vector_booster.load(connection)
    result = connection.execute(
        "SELECT vector_l2_dist(?, ?), vector_cosine_dist(?, ?)",
        (
            struct.pack("<f", 1), struct.pack("<f", 2),
            struct.pack("<2f", 1, 0), struct.pack("<2f", 0, 1),
        ),
    ).fetchone()
    assert result == (1.0, 1.0), result
    print("Installed Python wheel: both scalar functions passed")
finally:
    connection.close()
