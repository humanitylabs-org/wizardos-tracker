"""Shrink the inline app bundle in runtipi/docker-compose.yml with zlib.

`wam package-inline` ships every file as one base64 argument; past 128 KiB
Linux refuses to start the container ("argument list too long"). Run this
after every `wam package-inline .`.
"""
import base64
import pathlib
import re
import zlib

import yaml

path = pathlib.Path(__file__).resolve().parent.parent / "runtipi" / "docker-compose.yml"
raw = path.read_text()
if "zlib.decompress(base64.b64decode(" in raw:
    print("already compressed")
else:
    m = re.search(r"base64\.b64decode\('([A-Za-z0-9+/=]+)'\)", raw)
    payload = m.group(1)
    packed = base64.b64encode(zlib.compress(base64.b64decode(payload), 9)).decode()
    raw = raw.replace("import base64,json,pathlib,runpy\\n", "import base64,json,pathlib,runpy,zlib\\n", 1)
    raw = raw.replace(f"base64.b64decode('{payload}')", f"zlib.decompress(base64.b64decode('{packed}'))", 1)
    path.write_text(raw)
cmd = yaml.safe_load(path.read_text())["services"]["board"]["command"]
longest = max(len(a) for a in cmd)
compile(cmd[-1], "start", "exec")
assert longest < 120_000, longest
print("longest start argument:", longest)
