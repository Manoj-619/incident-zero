"""SQLite event journal, capability ownership, retention, and atomic approval."""

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Journal:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL,
                    status TEXT NOT NULL, request TEXT NOT NULL, result TEXT, error TEXT,
                    approved REAL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    created REAL NOT NULL, role TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS event_run ON events(run_id, sequence);
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, token: str, request: dict) -> str:
        identifier = secrets.token_urlsafe(18)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM runs WHERE created < ? AND status != 'running'", (time.time() - 86400,)
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM runs WHERE created > ?", (time.time() - 3600,)
            ).fetchone()[0]
            if count >= 12:
                raise Conflict(
                    "Demo quota reached: 12 mission starts per hour across this instance."
                )
            connection.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    self.digest(token),
                    time.time(),
                    "running",
                    json.dumps(request),
                    None,
                    None,
                    None,
                ),
            )
        return identifier

    def get(self, identifier: str, token: str) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id=? AND owner=? AND created>?",
                (identifier, self.digest(token), time.time() - 86400),
            ).fetchone()
        if row is None:
            raise NotFound()
        result = dict(row)
        for key in ("request", "result"):
            result[key] = None if result[key] is None else json.loads(result[key])
        result.pop("owner")
        return result

    def event(self, identifier: str, role: str, kind: str, payload: dict):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO events(run_id,created,role,kind,payload) VALUES(?,?,?,?,?)",
                (identifier, time.time(), role, kind, json.dumps(payload, allow_nan=False)),
            )

    def events(self, identifier: str, after: int = 0) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 500",
                (identifier, after),
            ).fetchall()
        return [
            {
                "sequence": row["sequence"],
                "created": row["created"],
                "role": row["role"],
                "kind": row["kind"],
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def finish(self, identifier: str, result: dict | None = None, error: str | None = None):
        status = "failed" if error else result["decision"]
        with self.connect() as connection:
            connection.execute(
                "UPDATE runs SET status=?,result=?,error=? WHERE id=?",
                (
                    status,
                    None if result is None else json.dumps(result, allow_nan=False),
                    error,
                    identifier,
                ),
            )

    def approve(self, identifier: str, token: str) -> dict:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM runs WHERE id=? AND owner=? AND created>?",
                (identifier, self.digest(token), time.time() - 86400),
            ).fetchone()
            if row is None:
                raise NotFound()
            if row["status"] == "approved":
                return {"status": "approved", "simulation_only": True, "already_approved": True}
            result = None if row["result"] is None else json.loads(row["result"])
            if (
                row["status"] != "approval_pending"
                or not result
                or not result["verification"]["passed"]
            ):
                raise Conflict("Only a verified maneuver awaiting approval can be approved.")
            connection.execute(
                "UPDATE runs SET status='approved',approved=? WHERE id=?", (time.time(), identifier)
            )
            connection.execute(
                "INSERT INTO events(run_id,created,role,kind,payload) VALUES(?,?,?,?,?)",
                (
                    identifier,
                    time.time(),
                    "human",
                    "approval",
                    json.dumps({"simulation_only": True, "action": "accept simulated maneuver"}),
                ),
            )
        return {"status": "approved", "simulation_only": True, "already_approved": False}

    def recover(self):
        with self.connect() as connection:
            connection.execute(
                "UPDATE runs SET status='failed',error='Worker restarted before mission completed.' WHERE status='running'"
            )
