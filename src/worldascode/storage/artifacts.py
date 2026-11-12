import contextlib
import hashlib
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temp = Path(stream.name)
        stream.write(text)
    try:
        if exclusive:
            try:
                os.link(temp, path)
            except FileExistsError:
                pass
        else:
            for attempt in range(10):
                try:
                    os.replace(temp, path)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(min(0.01 * 2**attempt, 0.2))
    finally:
        temp.unlink(missing_ok=True)


@contextlib.contextmanager
def database(path):
    db = sqlite3.connect(path, timeout=30)
    try:
        with db:
            yield db
    finally:
        db.close()


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,ts REAL,node TEXT,status TEXT,payload TEXT)"
            )

    def connect(self):
        return database(self.path)

    def event(self, node, status, **payload):
        with self.connect() as db:
            db.execute(
                "INSERT INTO events(ts,node,status,payload) VALUES(?,?,?,?)",
                (time.time(), node, status, canonical(payload)),
            )

    def events(self):
        with self.connect() as db:
            return [
                {
                    "id": r[0],
                    "ts": r[1],
                    "node": r[2],
                    "status": r[3],
                    **json.loads(r[4]),
                }
                for r in db.execute("SELECT * FROM events ORDER BY id")
            ]


class AssetStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, payload, dependencies=()):
        key = digest({"payload": payload, "dependencies": list(dependencies)})
        target = self.root / (key + ".json")
        if not target.exists():
            write_json(
                target,
                {"key": key, "payload": payload, "dependencies": list(dependencies)},
                exclusive=True,
            )
        self.get(key)
        return key

    def get(self, key):
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("INVALID_ASSET_KEY")
        item = json.loads((self.root / (key + ".json")).read_text(encoding="utf-8"))
        if (
            digest({"payload": item["payload"], "dependencies": item["dependencies"]})
            != key
        ):
            raise ValueError("ASSET_HASH_MISMATCH")
        return item["payload"]


@contextlib.contextmanager
def run_lock(run):
    path = Path(run) / ".run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    stream.seek(0)
    if not path.stat().st_size:
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise RuntimeError("RUN_ALREADY_ACTIVE") from None
    try:
        yield
    finally:
        stream.seek(0)
        if os.name == "nt":
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()
