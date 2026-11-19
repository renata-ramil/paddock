# 0001: Scope tools at the gateway, not in the agent

Status: accepted, 2026-11-15

## Context
An agent's tool list is the most direct control over what it can do. kagent lets an Agent name `toolNames`, but that list lives in the agent's own config and is enforced by the agent runtime. A prompt injection, a bug in the runtime, or anyone who can reach the tool server directly bypasses it.

## Decision
All MCP traffic goes through agentgateway. An AgentgatewayPolicy (`deploy/40-tool-policy.yaml`) decides which identity may see and call which tool. Denied tools are filtered out of `tools/list` and rejected on `tools/call`. Default deny: an identity with no rule gets no tools. NetworkPolicy makes the gateway the only path to the tool server.

## Consequences
- One place to read, review and audit every agent's tool permissions.
- The model never learns that `refund_order` or `delete_account` exist, so it cannot be talked into calling them.
- The eval suite can attack the gateway directly, without the model, and prove the policy holds.
- The gateway is now a critical dependency on every tool call. Its denials return HTTP 400 with "unknown resource", the same as a missing tool.
