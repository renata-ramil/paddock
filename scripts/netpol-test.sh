#!/usr/bin/env bash
# Proving the paddock NetworkPolicies with two throwaway curl pods:
#   outsider  default/np-outsider, no labels: must not reach the tools or the gateway
#   agent     kagent/np-agent, labeled paddock.dev/agent: gateway, controller and public 443 only
set -uo pipefail
IMG=curlimages/curl:8.17.0
fail=0

kubectl run np-outsider -n default --image=$IMG --restart=Never --command -- sleep 600 >/dev/null
kubectl run np-agent -n kagent --image=$IMG --labels=paddock.dev/agent=np-test --restart=Never --command -- sleep 600 >/dev/null
kubectl wait -n default pod/np-outsider --for=condition=Ready --timeout=120s >/dev/null
kubectl wait -n kagent pod/np-agent --for=condition=Ready --timeout=120s >/dev/null

check() { # namespace pod url expect(open|blocked)
  code=$(kubectl exec -n "$1" "$2" -- curl -s -o /dev/null -m 5 -w '%{http_code}' "$3" 2>/dev/null)
  got=$([ "$code" = "000" ] || [ -z "$code" ] && echo blocked || echo open)
  mark=$([ "$got" = "$4" ] && echo PASS || { fail=1; echo FAIL; })
  printf '%-5s %-12s %-55s expect %-7s got %s (%s)\n' "$mark" "$2" "$3" "$4" "$got" "${code:-none}"
}

check default np-outsider http://paddock-tools.paddock:8000/healthz blocked
check default np-outsider http://agentgateway-proxy.agentgateway-system/mcp blocked
check kagent np-agent http://agentgateway-proxy.agentgateway-system/mcp open
check kagent np-agent http://kagent-controller.kagent:8083/health open
check kagent np-agent https://generativelanguage.googleapis.com/ open
check kagent np-agent http://paddock-tools.paddock:8000/healthz blocked
check kagent np-agent https://kubernetes.default.svc/healthz blocked
check kagent np-agent http://kagent-tools.kagent:8084/mcp blocked
check kagent np-agent http://example.com/ blocked

kubectl delete pod np-outsider -n default --wait=false >/dev/null
kubectl delete pod np-agent -n kagent --wait=false >/dev/null
exit $fail
