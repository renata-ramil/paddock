#!/usr/bin/env bash
# Opening local ports for the eval runner:
#   8080   gateway, no workload identity
#   15001  support-agent's identity sidecar (127.0.0.1 in the pod), so calls carry its JWT-SVID
#   18080  support-agent A2A
set -euo pipefail
POD=$(kubectl get pods -n kagent -l paddock.dev/agent=support-agent -o jsonpath='{.items[0].metadata.name}')
kubectl port-forward -n agentgateway-system svc/agentgateway-proxy 8080:80 >/dev/null 2>&1 &
kubectl port-forward -n kagent "pod/$POD" 15001:15001 >/dev/null 2>&1 &
kubectl port-forward -n kagent svc/support-agent 18080:8080 >/dev/null 2>&1 &
sleep 3
echo "gateway: http://localhost:8080/mcp  agent identity: http://localhost:15001/mcp  support-agent A2A: http://localhost:18080/"
echo "stop with: pkill -f 'kubectl port-forward'"
