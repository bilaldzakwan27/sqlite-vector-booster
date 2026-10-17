"""Exercise the real sqlite3 shell, including dot-load and failure exit status."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

executable = shutil.which("sqlite3")
if executable is None:
    sys.exit("SQLite CLI is missing. Install sqlite3, then rerun python tests/cli.py.")
configured = os.environ.get("SQLITE_VECTOR_BOOSTER_LIBRARY")
if not configured or not Path(configured).is_file():
    sys.exit("Set SQLITE_VECTOR_BOOSTER_LIBRARY to the built native library's absolute path.")
library = Path(configured).resolve()
load = f".load {json.dumps(str(library))}\n"
sql = """SELECT vector_cosine_dist(X'0000803F00000000',X'000000000000803F');
SELECT vector_l2_dist(X'0000803F00000000',X'000000000000803F');
CREATE TABLE points(id INTEGER PRIMARY KEY,vec BLOB);
INSERT INTO points VALUES(1,X'0000803F00000000'),(2,X'000000000000803F');
SELECT id FROM points ORDER BY vector_cosine_dist(vec,X'0000803F00000000'),id;
"""
result = subprocess.run([executable, "-batch", "-bail", ":memory:"],
                        input=load+sql, text=True, capture_output=True, timeout=30)
if result.returncode or result.stdout.splitlines() != ["1.0", "2.0", "1", "2"]:
    sys.exit(f"SQLite CLI functional smoke test failed: {result!r}")
invalid = subprocess.run([executable, "-batch", "-bail", ":memory:"],
                         input=load+"SELECT vector_l2_dist(X'01',X'01');\n",
                         text=True, capture_output=True, timeout=30)
if invalid.returncode != 1 or "multiple of four" not in invalid.stderr:
    sys.exit(f"SQLite CLI did not reject malformed input correctly: {invalid!r}")
version = subprocess.check_output([executable, "--version"], text=True).strip()
print(json.dumps({"status":"PASS","sqlite_cli":version,"library":str(library),
                  "outputs":result.stdout.splitlines(),"invalid_input_exit":invalid.returncode,
                  "invalid_input_error":invalid.stderr.strip()}, indent=2))
