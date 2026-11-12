"""Local persistent job leases for bounded workers. Assets, not geographic tiles, own recipes."""

import contextlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

from .artifacts import digest, file_hash


class JobQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, payload TEXT NOT NULL, dependencies TEXT NOT NULL, status TEXT NOT NULL, priority INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, lease TEXT, expires REAL, artifact TEXT, error TEXT, artifact_sha256 TEXT)"
            )
            if "artifact_sha256" not in {
                r[1] for r in db.execute("PRAGMA table_info(jobs)")
            }:
                db.execute("ALTER TABLE jobs ADD COLUMN artifact_sha256 TEXT")

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, payload, dependencies=(), priority=0):
        key = digest({"payload": payload, "dependencies": sorted(dependencies)})
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO jobs(key,payload,dependencies,status,priority) VALUES(?,?,?,?,?)",
                (
                    key,
                    json.dumps(payload),
                    json.dumps(list(dependencies)),
                    "pending",
                    priority,
                ),
            )
        return key

    def get(self, key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result["status"] == "complete" and (
            not result["artifact"]
            or not Path(result["artifact"]).is_file()
            or file_hash(result["artifact"]) != result["artifact_sha256"]
        ):
            raise ValueError("JOB_ARTIFACT_HASH_MISMATCH")
        return result

    def claim(self, seconds=300):
        if seconds <= 0:
            raise ValueError("Positive lease required")
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Expired leases require explicit reconciliation: no automatic replay of a paid request.
            db.execute(
                "UPDATE jobs SET status='uncertain', error='lease-expired-reconcile-provider-and-artifacts' WHERE status='running' AND expires<?",
                (now,),
            )
            rows = db.execute(
                "SELECT * FROM jobs WHERE status='pending' ORDER BY priority DESC, key"
            ).fetchall()
            for row in rows:
                deps = json.loads(row["dependencies"])
                if any(
                    (
                        r := db.execute(
                            "SELECT status FROM jobs WHERE key=?", (k,)
                        ).fetchone()
                    )
                    is None
                    or r["status"] != "complete"
                    for k in deps
                ):
                    continue
                token = uuid.uuid4().hex
                db.execute(
                    "UPDATE jobs SET status='running', lease=?, expires=?, attempts=attempts+1 WHERE key=?",
                    (token, now + seconds, row["key"]),
                )
                return {
                    "key": row["key"],
                    "lease": token,
                    "payload": json.loads(row["payload"]),
                }
        return None

    def heartbeat(self, key, lease, seconds=300):
        with self.connect() as db:
            n = db.execute(
                "UPDATE jobs SET expires=? WHERE key=? AND lease=? AND status='running' AND expires>?",
                (time.time() + seconds, key, lease, time.time()),
            ).rowcount
            if n != 1:
                raise ValueError("LEASE_LOST")

    def finish(self, key, lease, artifact):
        artifact = Path(artifact).resolve()
        if not artifact.is_file():
            raise ValueError("OUTPUT_ARTIFACT_MISSING")
        with self.connect() as db:
            n = db.execute(
                "UPDATE jobs SET status='complete',artifact=?,artifact_sha256=? WHERE key=? AND lease=? AND status='running' AND expires>?",
                (str(artifact), file_hash(artifact), key, lease, time.time()),
            ).rowcount
            if n != 1:
                raise ValueError("LEASE_LOST")

    def fail(self, key, lease, reason):
        with self.connect() as db:
            n = db.execute(
                "UPDATE jobs SET status='blocked',error=? WHERE key=? AND lease=? AND status='running' AND expires>?",
                (reason, key, lease, time.time()),
            ).rowcount
            if n != 1:
                raise ValueError("LEASE_LOST")

    def requeue_preflight_budget(self, key):
        """Reopen only a request rejected before transport because its local budget was spent."""
        with self.connect() as db:
            n = db.execute(
                "UPDATE jobs SET status='pending',error=NULL,lease=NULL,expires=NULL WHERE key=? AND status='blocked' AND error LIKE ?",
                (key, "BudgetExceeded: MODEL_BUDGET_EXHAUSTED%"),
            ).rowcount
        if n != 1:
            raise ValueError("JOB_NOT_SAFE_TO_REQUEUE")
