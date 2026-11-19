# paddock: one command to bring up the stack on kind.
#   make up     build and deploy everything (idempotent; reuses an existing cluster)
#   make test   prove isolation, identity and resume (no model calls)
#   make eval   run the attack suite (agent cases spend Gemini quota)
#   make down   delete the kind cluster (asks first)
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
CLUSTER ?= paddock
CTX := kind-$(CLUSTER)
K := kubectl --context $(CTX)
H := helm --kube-context $(CTX)

GWAPI_VERSION := v1.6.3
AGENTGATEWAY_VERSION := v1.7.0
KAGENT_VERSION := 0.10.4
SPIRE_VERSION := 0.30.4
SPIRE_CRDS_VERSION := 0.6.1
SPIRE_REPO := https://spiffe.github.io/helm-charts-hardened/
IMAGES := paddock-tools:0.1.0 paddock-sessionlog:0.1.0 paddock-identity-proxy:0.1.0
PY := uv run --quiet --with httpx==0.28.1 --with pyyaml==6.0.3 python

.PHONY: up check cluster kagent gateway spire images paddock wait test eval down

up: check cluster kagent gateway spire images paddock wait
	@echo "paddock is up on $(CTX). Next: make test, then make eval."

check:
	@for t in docker kind kubectl helm uv openssl; do command -v $$t >/dev/null || { echo "missing: $$t"; exit 1; }; done
	@docker info >/dev/null 2>&1 || { echo "Docker is not running"; exit 1; }
	@[ -n "$${GOOGLE_API_KEY:-}" ] || { echo "GOOGLE_API_KEY is not set"; exit 1; }

# Creating the cluster if needed and pointing kubectl at it
cluster:
	@kind get clusters 2>/dev/null | grep -qx $(CLUSTER) || kind create cluster --name $(CLUSTER)
	@kubectl config use-context $(CTX) >/dev/null

# Installing kagent only on a cluster without it; an existing install is left as it is
kagent:
	@if $(H) status kagent -n kagent >/dev/null 2>&1; then echo "kagent already installed, leaving it as is"; else \
	  $(H) upgrade --install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds --version $(KAGENT_VERSION) -n kagent --create-namespace && \
	  $(H) upgrade --install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent --version $(KAGENT_VERSION) -n kagent \
	    -f deploy/kagent/values.yaml -f <(printf 'providers:\n  gemini:\n    apiKey: "%s"\n' "$$GOOGLE_API_KEY") --wait --timeout 10m; fi

gateway:
	$(K) apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/gateway-api/releases/download/$(GWAPI_VERSION)/standard-install.yaml >/dev/null
	$(H) upgrade --install agentgateway-crds oci://cr.agentgateway.dev/charts/agentgateway-crds --version $(AGENTGATEWAY_VERSION) -n agentgateway-system --create-namespace
	$(H) upgrade --install agentgateway oci://cr.agentgateway.dev/charts/agentgateway --version $(AGENTGATEWAY_VERSION) -n agentgateway-system --wait

spire:
	$(H) upgrade --install spire-crds spire-crds --repo $(SPIRE_REPO) --version $(SPIRE_CRDS_VERSION) -n spire --create-namespace
	$(H) upgrade --install spire spire --repo $(SPIRE_REPO) --version $(SPIRE_VERSION) -n spire -f deploy/spire/values.yaml --wait --timeout 10m

images:
	docker build -q -t paddock-tools:0.1.0 tools/
	docker build -q -f sessionlog/Dockerfile -t paddock-sessionlog:0.1.0 .
	docker build -q -t paddock-identity-proxy:0.1.0 identity/
	@for i in $(IMAGES); do kind load docker-image $$i --name $(CLUSTER) >/dev/null; done

paddock:
	$(K) apply -f deploy/00-namespace.yaml -f deploy/10-tools.yaml
	scripts/sessionlog-secret.sh
	$(K) apply -f deploy/60-sessionlog-db.yaml -f deploy/20-gateway.yaml -f deploy/30-mcp-route.yaml -f deploy/40-tool-policy.yaml
	$(K) apply -f deploy/80-gateway-identity.yaml -f deploy/50-netpol.yaml
	$(K) apply -f agents/paddock-model-config.yaml -f agents/support-agent.yaml

wait:
	$(K) rollout status deploy/paddock-tools -n paddock --timeout=180s
	$(K) rollout status sts/sessionlog-db -n paddock --timeout=180s
	$(K) wait gateway/agentgateway-proxy -n agentgateway-system --for=condition=Programmed --timeout=180s
	@until $(K) get deploy support-agent -n kagent >/dev/null 2>&1; do sleep 2; done
	$(K) rollout status deploy/support-agent -n kagent --timeout=300s

# Scripts use the current kubectl context, which `make up` sets to this cluster
test:
	scripts/netpol-test.sh
	scripts/identity-test.sh
	scripts/resume-demo.sh

# Agent cases spend Gemini quota; the runner stops on HTTP 429 and resumes on the next run
eval:
	@pkill -f 'kubectl port-forward' || true
	scripts/port-forward.sh
	$(PY) evals/run_evals.py --resume

down:
	@read -r -p "Delete kind cluster $(CLUSTER) and everything in it? [y/N] " a; if [ "$$a" = y ]; then kind delete cluster --name $(CLUSTER); else echo "kept"; fi
