import sqlite3
import time
from contextlib import contextmanager
from app.models import InvestigationState


class Store:
    def __init__(self, path):
        self.path = path
        with self.connection() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS investigations(id TEXT PRIMARY KEY, owner TEXT, expires REAL, payload TEXT); CREATE TABLE IF NOT EXISTS quotas(bucket TEXT PRIMARY KEY, count INTEGER, expires REAL);"
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def allow(self, bucket, cap, ttl):
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM quotas WHERE expires<=?", (now,))
            row = db.execute(
                "SELECT count FROM quotas WHERE bucket=?", (bucket,)
            ).fetchone()
            if cap <= 0 or (row and row[0] >= cap):
                return False
            db.execute(
                "INSERT INTO quotas VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1",
                (bucket, now + ttl),
            )
            return True

    def save(self, state, owner):
        with self.connection() as db:
            db.execute("DELETE FROM investigations WHERE expires<=?", (time.time(),))
            db.execute(
                "INSERT OR REPLACE INTO investigations VALUES(?,?,?,?)",
                (
                    state.investigation_id,
                    owner,
                    time.time() + 86400,
                    state.model_dump_json(),
                ),
            )

    def get(self, identifier, owner):
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM investigations WHERE id=? AND owner=? AND expires>?",
                (identifier, owner, time.time()),
            ).fetchone()
        return InvestigationState.model_validate_json(row[0]) if row else None

    def approve(self, identifier, owner, approved):
        from app.sandbox.runner import simulate

        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM investigations WHERE id=? AND owner=? AND expires>?",
                (identifier, owner, time.time()),
            ).fetchone()
            if not row:
                return None
            state = InvestigationState.model_validate_json(row[0])
            if state.phase.value != "complete" or not state.remediation:
                raise ValueError("No completed remediation proposal")
            plan = state.remediation
            if approved and not plan.executed:
                if not plan.intervention_id:
                    raise ValueError("No validated simulation intervention")
                plan.recovery = simulate(plan.intervention_id)
                plan.approved = plan.executed = True
                state.events.append(
                    {
                        "phase": "remediation",
                        "message": "Approved simulation applied; recovery values are simulated.",
                    }
                )
                db.execute(
                    "UPDATE investigations SET payload=? WHERE id=?",
                    (state.model_dump_json(), identifier),
                )
            return state
