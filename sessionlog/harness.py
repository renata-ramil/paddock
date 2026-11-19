"""Demo harness with a stubbed brain, to show crash and resume without spending model quota.

The plan is fixed: look up the profile, then the orders, then answer. Tool calls are real
MCP calls through agentgateway as support-agent. Kill the pod at any point: the Job starts
a new pod, which calls wake() and continues from the last event.
"""

import argparse
import json
import logging
import os
import time

from mcp_client import MCPSession
from sessionlog import connect, emit_event, wake

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("harness")

PLAN = ["get_profile", "list_orders"]


def brain(results: dict) -> str:
    # Standing in for the model: composing the answer from tool results
    profile = results.get("get_profile", {})
    orders = results.get("list_orders", [])
    ids = ", ".join(o["order_id"] for o in orders)
    return f"Hi {profile.get('name', 'there')}, you have {len(orders)} orders: {ids}."


def tool_output(resp: dict):
    # Decoding MCP text content back into JSON
    parts = [json.loads(c["text"]) for c in resp["result"]["content"]]
    return parts[0] if len(parts) == 1 and not isinstance(parts[0], list) else parts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=os.environ.get("SESSION_ID"))
    ap.add_argument("--caller", default=os.environ.get("CALLER", "alice"))
    ap.add_argument("--gateway", default=os.environ.get("GATEWAY_URL", "http://127.0.0.1:15001/mcp"))
    ap.add_argument("--step-delay", type=float, default=float(os.environ.get("STEP_DELAY", "15")))
    args = ap.parse_args()

    conn = connect()
    s = wake(conn, args.session)
    pod = os.environ.get("HOSTNAME", "local")
    log.info("wake session=%s last_seq=%s last_type=%s pod=%s", args.session, s.last_seq, s.last_type, pod)
    if s.last_type == "session_completed":
        log.info("session already completed, nothing to do")
        return

    # Rebuilding state from the log instead of from memory
    results = {e.payload["tool"]: e.payload["output"] for e in s.events if e.type == "tool_result"}
    emit_event(conn, args.session, "session_started", {"caller": args.caller, "plan": PLAN}, idempotency_key="start")
    emit_event(conn, args.session, "harness_woke", {"pod": pod, "resumed_after_seq": s.last_seq})

    # Identity comes from the JWT-SVID the identity proxy adds; only the customer travels as a header
    mcp = MCPSession(args.gateway, {"X-Caller": args.caller})
    for i, tool in enumerate(PLAN):
        if tool in results:
            log.info("step %d %s already done, skipping", i, tool)
            continue
        emit_event(conn, args.session, "tool_call", {"step": i, "tool": tool}, idempotency_key=f"call:{i}")
        log.info("step %d calling %s (sleeping %ss first, kill me now to test resume)", i, tool, args.step_delay)
        time.sleep(args.step_delay)
        output = tool_output(mcp.call_tool(tool))
        emit_event(conn, args.session, "tool_result", {"step": i, "tool": tool, "output": output}, idempotency_key=f"result:{i}")
        results[tool] = output

    answer = brain(results)
    emit_event(conn, args.session, "assistant_message", {"text": answer}, idempotency_key="answer")
    emit_event(conn, args.session, "session_completed", {}, idempotency_key="done")
    log.info("done: %s", answer)


if __name__ == "__main__":
    main()
