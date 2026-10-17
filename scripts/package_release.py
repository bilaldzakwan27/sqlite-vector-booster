import argparse
import hashlib
import json
import shutil
import tomllib
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--target", required=True)
parser.add_argument("--tag")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "Cargo.toml").read_text())["package"]["version"]
python_version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
node_version = json.loads((root / "package.json").read_text())["version"]
if version != python_version or version != node_version:
    parser.error("package versions do not match")
if args.tag and args.tag != f"v{version}":
    parser.error(f"tag must equal v{version}")

names = {
    "x86_64-unknown-linux-gnu": "libsqlite_vector_booster.so",
    "x86_64-apple-darwin": "libsqlite_vector_booster.dylib",
    "aarch64-apple-darwin": "libsqlite_vector_booster.dylib",
    "x86_64-pc-windows-msvc": "sqlite_vector_booster.dll",
}
if args.target not in names:
    parser.error("unsupported release target")
source = root / "target" / args.target / "release" / names[args.target]
output = root / "dist"
output.mkdir(exist_ok=True)
asset = output / f"sqlite-vector-booster-{version}-{args.target}{source.suffix}"
shutil.copy2(source, asset)
digest = hashlib.sha256(asset.read_bytes()).hexdigest()
asset.with_name(asset.name + ".sha256").write_text(f"{digest}  {asset.name}\n", encoding="ascii")
print(asset)
