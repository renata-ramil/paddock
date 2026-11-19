"""Minimal MCP client over streamable HTTP, used to call the gateway directly."""

import json

import httpx

PROTOCOL = "2025-06-18"


def _parse(resp: httpx.Response) -> dict:
    # Reading either a JSON body or the first SSE data line
    if resp.headers.get("content-type", "").startswith("text/event-stream"):
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        return {}
    return resp.json() if resp.content else {}


class MCPSession:
    def __init__(self, url: str, headers: dict[str, str] | list[tuple[str, str]]):
        self.url = url
        self.http = httpx.Client(timeout=30)
        # Keeping headers as a list of pairs so a test can send the same header twice
        self.headers = [
            ("Content-Type", "application/json"),
            ("Accept", "application/json, text/event-stream"),
            ("MCP-Protocol-Version", PROTOCOL),
            *(headers.items() if isinstance(headers, dict) else headers),
        ]
        self.next_id = 1
        init = self._post({
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "paddock-evals", "version": "0.1"}},
        })
        self.headers.append(("Mcp-Session-Id", init.headers["mcp-session-id"]))
        self._post({"method": "notifications/initialized"}, notify=True)

    def _post(self, body: dict, notify: bool = False) -> httpx.Response:
        msg = {"jsonrpc": "2.0", **body}
        if not notify:
            msg["id"] = self.next_id
            self.next_id += 1
        resp = self.http.post(self.url, headers=self.headers, json=msg)
        # Keeping 4xx responses: the gateway answers a denied tool call with an HTTP error
        if resp.status_code >= 500 or body["method"] == "initialize":
            resp.raise_for_status()
        return resp

    def list_tools(self) -> list[str]:
        data = _parse(self._post({"method": "tools/list"}))
        return [t["name"] for t in data.get("result", {}).get("tools", [])]

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        # Returning the HTTP status plus the JSON-RPC message ("result" or "error")
        resp = self._post({"method": "tools/call", "params": {"name": name, "arguments": arguments or {}}})
        try:
            msg = _parse(resp)
        except ValueError:
            msg = {"raw": resp.text}
        return {"http_status": resp.status_code, **msg}
