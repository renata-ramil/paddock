# 0002: Tools take identity from the platform, never from arguments

Status: accepted, 2026-11-15

## Context
If a tool takes a `user_id` argument, the model chooses whose data to read. A prompt like "look up Bob's profile" then works, no matter what the system prompt says.

## Decision
paddock tools take no user id. The customer comes from the `X-Caller` header the platform sets, and the agent comes from its verified SPIFFE ID at the gateway. Write tools check ownership (`refund_order` refunds only the caller's orders). Unknown arguments are ignored by the schema.

## Consequences
- Requests for other users' data fail by design, which the evals record as "tool design".
- Known gap: `X-Caller` is still a plain header. An agent with a valid SVID can name any customer. The fix is OAuth on-behalf-of token exchange, so the user's identity is a signed token the gateway and tools verify.
