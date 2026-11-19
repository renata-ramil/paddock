#!/usr/bin/env bash
# Creating random session log DB passwords in-cluster. Values are never printed or written to disk.
# paddock/paddock-sessionlog-db holds both passwords. kagent/paddock-sessionlog-app gets only the app password,
# for harness pods that run next to the agents.
set -euo pipefail
if ! kubectl get secret paddock-sessionlog-db -n paddock >/dev/null 2>&1; then
  kubectl create secret generic paddock-sessionlog-db -n paddock \
    --from-literal=admin-password="$(openssl rand -hex 24)" \
    --from-literal=app-password="$(openssl rand -hex 24)" >/dev/null
  echo "created paddock/paddock-sessionlog-db"
fi
if ! kubectl get secret paddock-sessionlog-app -n kagent >/dev/null 2>&1; then
  kubectl create secret generic paddock-sessionlog-app -n kagent \
    --from-literal=app-password="$(kubectl get secret paddock-sessionlog-db -n paddock -o jsonpath='{.data.app-password}' | base64 -d)" >/dev/null
  echo "created kagent/paddock-sessionlog-app"
fi
