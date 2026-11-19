#!/usr/bin/env bash
# Resume demo: start a harness on a new session, kill its pod mid tool call, watch a new pod resume.
# Uses a stub brain, so it spends no model quota. Tool calls are real, through agentgateway.
set -euo pipefail
SID="demo-$(date +%s)"
PSQL=(kubectl exec -n paddock sessionlog-db-0 -- psql -U postgres -d sessionlog -tA)

kubectl delete job harness-demo -n kagent --ignore-not-found >/dev/null
sed -e "s/SESSION_ID_PLACEHOLDER/$SID/" -e "s/SERVICE_ACCOUNT_PLACEHOLDER/paddock-harness/" deploy/70-harness-demo.yaml | kubectl apply -f - >/dev/null
echo "started session $SID"

# Waiting for the first tool_call, then killing the pod while the tool call is in flight
until [ "$("${PSQL[@]}" -c "select count(*) from session_events where session_id='$SID' and type='tool_call'")" -ge 1 ]; do sleep 1; done
POD=$(kubectl get pods -n kagent -l job-name=harness-demo -o jsonpath='{.items[0].metadata.name}')
echo "killing $POD during step 0"
kubectl delete pod "$POD" -n kagent --grace-period=0 --force >/dev/null 2>&1

kubectl wait job/harness-demo -n kagent --for=condition=complete --timeout=300s >/dev/null
echo "job complete. event log for $SID:"
"${PSQL[@]}" -F ' | ' -c "select seq, type, left(payload::text, 100) from session_events where session_id='$SID' order by seq"

# Checking the resume: two wakes, each tool result exactly once, one completion
r=$("${PSQL[@]}" -c "select count(*) filter (where type='harness_woke'), count(*) filter (where type='tool_result'), count(distinct payload->>'tool') filter (where type='tool_result'), count(*) filter (where type='session_completed') from session_events where session_id='$SID'")
echo "harness_woke | tool_result | distinct tools | completed = $r"
[ "$r" = "2|2|2|1" ] && echo "PASS: resumed from the log after the pod was killed" || { echo "FAIL"; exit 1; }
