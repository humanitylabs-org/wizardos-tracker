"""Shrink the inline app bundle in runtipi/docker-compose.yml with zlib, split across arguments.

`wam package-inline` ships every file as one base64 argument; past 128 KiB per argument Linux refuses to start the
container ("argument list too long"). This compresses the bundle and passes it as base64 parts after the start script
(`python -c <script> <part> <part> ...`, each part under 100000 characters); the script joins sys.argv[1:].
Run this after every `wam package-inline .`.
"""
import base64
import json
import pathlib
import re
import zlib

import yaml

PART = 100_000
path = pathlib.Path(__file__).resolve().parent.parent / "runtipi" / "docker-compose.yml"
raw = path.read_text()
if "sys.argv[1:]" in raw:
    print("already compressed")
else:
    m = re.search(r"base64\.b64decode\('([A-Za-z0-9+/=]+)'\)", raw)
    payload = m.group(1)
    packed = base64.b64encode(zlib.compress(base64.b64decode(payload), 9)).decode()
    parts = [packed[i:i + PART] for i in range(0, len(packed), PART)]
    raw = raw.replace("import base64,json,pathlib,runpy\\n", "import base64,json,pathlib,runpy,sys,zlib\\n", 1)
    raw = raw.replace(f"base64.b64decode('{payload}')", "zlib.decompress(base64.b64decode(''.join(sys.argv[1:])))", 1)
    # the script is the command's last item: add the parts right after it (before the x-runtipi block)
    i = raw.index("\n    x-runtipi:", raw.index("    command:\n"))
    raw = raw[:i] + "".join(f"\n    - {p}" for p in parts) + raw[i:]
    path.write_text(raw)
cmd = next(iter(yaml.safe_load(path.read_text())["services"].values()))["command"]
longest = max(len(a) for a in cmd)
compile(cmd[2], "start", "exec")
files = json.loads(zlib.decompress(base64.b64decode("".join(cmd[3:]))))
assert "app/server.py" in files, sorted(files)
assert longest < 120_000, longest
print("arguments:", len(cmd), "longest:", longest, "files:", len(files))
