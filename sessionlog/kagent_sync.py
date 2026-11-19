"""Copy a kagent session into the append-only log.

kagent keeps sessions in its own Postgres, where rows carry updated_at and can be hard-deleted
by sessionRetentionDays. This keeps an immutable copy. Re-running is safe: each kagent event id
is the idempotency key, so nothing is written twice.
"""

import argparse
import json
import os

import httpx

from sessionlog import connect, emit_event, get_session


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_id")
    ap.add_argument("--kagent-url", default=os.environ.get("KAGENT_URL", "http://localhost:8083"))
    ap.add_argument("--user-id", default="admin@kagent.dev")
    args = ap.parse_args()

    resp = httpx.get(f"{args.kagent_url}/api/sessions/{args.session_id}", params={"user_id": args.user_id}, timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]
    conn = connect()
    sid = f"kagent:{args.session_id}"
    before = get_session(conn, sid).last_seq
    emit_event(conn, sid, "kagent_session", data["session"], idempotency_key="kagent_session")
    # Ordering by creation time, the order kagent recorded them
    for ev in sorted(data["events"], key=lambda e: e["created_at"]):
        body = json.loads(ev["data"]) if isinstance(ev.get("data"), str) else ev.get("data")
        emit_event(conn, sid, "kagent_event", {"kagent_event_id": ev["id"], "created_at": ev["created_at"], "data": body}, idempotency_key=ev["id"])
    after = get_session(conn, sid).last_seq
    print(f"{sid}: {after - before} new events, {after} total")


if __name__ == "__main__":
    main()
