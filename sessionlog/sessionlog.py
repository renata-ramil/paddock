"""Append-only session event log, after Anthropic's "Scaling Managed Agents" design.

The session is the durable record of everything that happened. Harnesses hold no state
that must survive a crash: a new harness calls wake(session_id) and rebuilds from the log.

Interfaces:
  emit_event(session_id, type, payload, idempotency_key) -> seq
  get_events(session_id, after_seq=0, limit=None)        -> list[Event]
  get_session(session_id)                                -> Session summary
  wake(session_id)                                       -> Session summary plus every event
"""

import os
from dataclasses import dataclass, field
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb


@dataclass
class Event:
    session_id: str
    seq: int
    type: str
    payload: dict
    idempotency_key: str | None
    created_at: datetime


@dataclass
class Session:
    session_id: str
    last_seq: int
    last_type: str | None
    events: list[Event] = field(default_factory=list)


def connect(dsn: str | None = None) -> psycopg.Connection:
    # Reading the DSN from the environment so passwords stay in the Secret
    return psycopg.connect(dsn or os.environ["SESSIONLOG_DSN"], autocommit=False)


def emit_event(conn: psycopg.Connection, session_id: str, type: str, payload: dict | None = None, idempotency_key: str | None = None) -> int:
    """Append one event and return its seq. Replaying the same idempotency_key returns the first seq."""
    with conn.transaction():
        # Serializing writers per session so seq has no gaps and no races
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (session_id,))
        if idempotency_key is not None:
            row = conn.execute(
                "SELECT seq FROM session_events WHERE session_id = %s AND idempotency_key = %s",
                (session_id, idempotency_key),
            ).fetchone()
            if row:
                return row[0]
        row = conn.execute(
            """INSERT INTO session_events (session_id, seq, type, payload, idempotency_key)
               SELECT %s, COALESCE(MAX(seq), 0) + 1, %s, %s, %s FROM session_events WHERE session_id = %s
               RETURNING seq""",
            (session_id, type, Jsonb(payload or {}), idempotency_key, session_id),
        ).fetchone()
        return row[0]


def get_events(conn: psycopg.Connection, session_id: str, after_seq: int = 0, limit: int | None = None) -> list[Event]:
    """Read a positional slice of the log: events with seq greater than after_seq, in order."""
    rows = conn.execute(
        """SELECT session_id, seq, type, payload, idempotency_key, created_at FROM session_events
           WHERE session_id = %s AND seq > %s ORDER BY seq LIMIT %s""",
        (session_id, after_seq, limit),
    ).fetchall()
    conn.commit()
    return [Event(*r) for r in rows]


def get_session(conn: psycopg.Connection, session_id: str) -> Session:
    row = conn.execute(
        "SELECT seq, type FROM session_events WHERE session_id = %s ORDER BY seq DESC LIMIT 1", (session_id,)
    ).fetchone()
    conn.commit()
    return Session(session_id, row[0] if row else 0, row[1] if row else None)


def wake(conn: psycopg.Connection, session_id: str) -> Session:
    """Start or restart a harness on a session: return where it stands and the full history."""
    s = get_session(conn, session_id)
    s.events = get_events(conn, session_id)
    return s
