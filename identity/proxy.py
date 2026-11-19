"""paddock identity proxy: a sidecar in each agent pod.

Listens on 127.0.0.1 only. Forwards MCP traffic to agentgateway and adds the pod's JWT-SVID
as a bearer token, fetched from the SPIRE Workload API (SPIFFE CSI volume). The agent never
handles the credential, and nothing outside the pod can reach this port except through
kubectl port-forward, which needs pod RBAC.

Refresh is decided by the token's own wall-clock expiry, checked on every request. A timer
would stall while a laptop sleeps and then hand out an expired token.
"""

import asyncio
import base64
import json
import logging
import os
import time

import httpx
import uvicorn
from spiffe import WorkloadApiClient
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

UPSTREAM = os.environ.get("UPSTREAM_URL", "http://agentgateway-proxy.agentgateway-system.svc.cluster.local")
SOCKET = os.environ.get("SPIFFE_ENDPOINT_SOCKET", "unix:///spiffe-workload-api/spire-agent.sock")
AUDIENCE = os.environ.get("JWT_AUDIENCE", "paddock-gateway")
# Fetching a new token once less than this many seconds remain
REFRESH_MARGIN = int(os.environ.get("REFRESH_MARGIN_SECONDS", "600"))
# Dropping hop-by-hop headers and anything that could carry a second identity
DROP_REQUEST = {"host", "authorization", "x-agent-id", "content-length", "connection", "transfer-encoding"}
DROP_RESPONSE = {"content-length", "connection", "transfer-encoding", "content-encoding"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("identity-proxy")
logging.getLogger("httpx").setLevel(logging.WARNING)
client = httpx.AsyncClient(base_url=UPSTREAM, timeout=httpx.Timeout(30, read=None), limits=httpx.Limits(max_keepalive_connections=0))
_cache: dict = {"token": "", "exp": 0.0, "sub": ""}
_lock = asyncio.Lock()


def _claims(token: str) -> dict:
    # Reading exp and sub from the payload; the gateway does the signature check
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _fetch() -> str:
    wl = WorkloadApiClient(socket_path=SOCKET)
    try:
        return wl.fetch_jwt_svid(audience={AUDIENCE}).token
    finally:
        wl.close()


async def token() -> str:
    async with _lock:
        if _cache["exp"] - time.time() < REFRESH_MARGIN:
            tok = await asyncio.to_thread(_fetch)
            c = _claims(tok)
            _cache.update(token=tok, exp=float(c["exp"]), sub=c.get("sub", ""))
            log.info("fetched JWT-SVID for %s, expires in %ds", _cache["sub"], int(_cache["exp"] - time.time()))
        return _cache["token"]


async def forward(request: Request) -> Response:
    try:
        bearer = await token()
    except Exception as exc:
        log.warning("no JWT-SVID: %s", exc)
        return JSONResponse({"error": "no JWT-SVID"}, status_code=503)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP_REQUEST}
    headers["authorization"] = f"Bearer {bearer}"
    upstream = client.build_request(request.method, request.url.path, params=request.query_params, headers=headers, content=await request.body())
    resp = await client.send(upstream, stream=True)
    # Streaming the body through, so MCP server-sent events pass unchanged
    return StreamingResponse(
        resp.aiter_raw(),
        status_code=resp.status_code,
        headers={k: v for k, v in resp.headers.items() if k.lower() not in DROP_RESPONSE},
        background=BackgroundTask(resp.aclose),
    )


async def healthz(_: Request) -> Response:
    try:
        await token()
        return JSONResponse({"ok": True, "sub": _cache["sub"], "expires_in": int(_cache["exp"] - time.time())})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)


app = Starlette(routes=[
    Route("/healthz", healthz),
    Route("/{path:path}", forward, methods=["GET", "POST", "DELETE"]),
])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "15001")), log_level="warning")
