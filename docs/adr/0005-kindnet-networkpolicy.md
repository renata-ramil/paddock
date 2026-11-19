# 0005: Use kindnet's NetworkPolicy support instead of installing Calico or Cilium

Status: accepted, 2026-11-15

## Context
Isolation needs a CNI that enforces NetworkPolicy. Older kind releases did not, and the docs do not say clearly that kindnet now does.

## Decision
Test first. `scripts/netpol-test.sh` showed kindnet (kind v0.33.0) enforces ingress and egress rules, so paddock adds no CNI.

## Consequences
- Fewer moving parts and less memory on a laptop cluster.
- NetworkPolicy has no domain rules, so agent egress to the model API is "any public address on 443". Routing model traffic through agentgateway would close this.
- On a real cluster, the same manifests work with any enforcing CNI.
