# 0004: Append-only session log, separate from kagent's store

Status: accepted, 2026-11-15

## Context
Anthropic's "Scaling Managed Agents" design treats the session as an append-only log outside the harness: a crashed harness is replaced, and the new one calls `wake(sessionId)` and rebuilds from the log. kagent already stores sessions in its own Postgres, but rows carry `updated_at` and `sessionRetentionDays` hard-deletes sessions and their events. That cannot serve as an audit record.

## Decision
A separate Postgres (`deploy/60-sessionlog-db.yaml`) holds `session_events(session_id, seq, type, payload, idempotency_key)`. A trigger rejects UPDATE, DELETE and TRUNCATE for every role, and the app role has only SELECT and INSERT. `sessionlog/sessionlog.py` offers `emit_event`, `get_events`, `get_session` and `wake`. Writers lock per session so `seq` has no gaps. An idempotency key makes a replayed write return the first `seq`. `kagent_sync.py` copies kagent sessions in.

## Consequences
- A harness can die mid tool call and a new pod resumes without duplicate events (`scripts/resume-demo.sh`).
- The log survives kagent's retention and keeps every event as written.
- Retrying an interrupted call is safe only for read tools. Write tools need the idempotency key passed through to the tool.
- kagent's own runtime does not yet emit to this log; today it is fed by paddock harnesses and by import.
