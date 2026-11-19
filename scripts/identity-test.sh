#!/usr/bin/env bash
# Proving the gateway allowlist keys on the SPIFFE ID, not on labels or headers.
# Runs a Job in kagent with the agent label and a real JWT-SVID, under service account "default":
# spiffe://paddock.local/ns/kagent/sa/default. It claims X-Agent-Id: support-agent. It must see no tools.
set -euo pipefail
kubectl delete job identity-test -n kagent --ignore-not-found >/dev/null
python3 - <<'PY' | kubectl apply -f - >/dev/null
import yaml
docs = list(yaml.safe_load_all(open("deploy/70-harness-demo.yaml")))
job = next(d for d in docs if d["kind"] == "Job")
job["metadata"]["name"] = "identity-test"
spec = job["spec"]["template"]["spec"]
spec["serviceAccountName"] = "default"
job["spec"]["backoffLimit"] = 0
c = spec["containers"][0]
c["name"] = "probe"
c["env"] = []
c["command"] = ["python", "-c", (
    "from mcp_client import MCPSession\n"
    "s = MCPSession('http://127.0.0.1:15001/mcp', {'X-Caller': 'alice', 'X-Agent-Id': 'support-agent'})\n"
    "print('TOOLS', s.list_tools())\n"
    "r = s.call_tool('get_profile')\n"
    "print('GET_PROFILE', r.get('http_status'), r.get('error', {}).get('message'))\n"
)]
print(yaml.safe_dump(job))
PY
kubectl wait job/identity-test -n kagent --for=condition=complete --timeout=180s >/dev/null
out=$(kubectl logs -n kagent job/identity-test -c probe)
echo "$out"
kubectl delete job identity-test -n kagent --wait=false >/dev/null
if echo "$out" | grep -q "TOOLS \[\]" && echo "$out" | grep -q "GET_PROFILE 400 unknown resource"; then
  echo "PASS: a valid SVID for the wrong identity gets no tools"
else
  echo "FAIL"; exit 1
fi
