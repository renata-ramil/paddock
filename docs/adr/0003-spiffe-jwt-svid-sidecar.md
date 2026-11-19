# 0003: Agent identity with SPIFFE JWT-SVIDs, attached by a sidecar

Status: accepted, 2026-11-15

## Context
The first version named the agent with an `X-Agent-Id` header, which any caller can set. The gateway needs an identity it can verify. Options checked:
- mTLS with X.509-SVIDs: kagent's RemoteMCPServer TLS takes only a CA, no client certificate. agentgateway lists `source.spiffeId` in CEL but does not document when it is set.
- JWT-SVID in a static header: kagent `headersFrom` is static, and JWT-SVIDs expire after an hour.
- HTTP proxy env vars: kagent's MCP client builds a bare `http.Transport`, which ignores them.

## Decision
SPIRE issues each agent pod `spiffe://paddock.local/ns/<namespace>/sa/<serviceaccount>`. One sidecar, `identity/proxy.py` on 127.0.0.1:15001, fetches a JWT-SVID (audience `paddock-gateway`) from the SPIRE Workload API over the SPIFFE CSI socket and adds it as a bearer token to every MCP call. It refreshes when less than 10 minutes remain, judged by the token's own `exp` on each request.

A first version used spiffe-helper to write the token to a file. Its refresh is a timer, and on a laptop the timer stalls while the Docker VM is paused by sleep, so after a sleep it kept serving an expired token and the gateway returned 401. Checking expiry against the wall clock on every request removes that failure and one container. The agent's RemoteMCPServer points at the sidecar. agentgateway validates the token against SPIRE's JWKS (`deploy/80-gateway-identity.yaml`) and the allowlist matches `jwt.sub`.

## Consequences
- No header, label or forged token gets tools. A real SVID for the wrong identity gets none (`scripts/identity-test.sh`).
- The agent process never handles the credential, and rotation is automatic, including after sleep.
- The kagent controller cannot discover tools at a pod-local URL, so the RemoteMCPServer shows ACCEPTED False. The agent itself works.
- Anyone allowed to port-forward to an agent pod can borrow its identity. That is Kubernetes RBAC on pods, the same trust as exec.
- If kagent adds native SPIFFE or token exchange for MCP, the sidecars go away and the gateway side stays as it is.
