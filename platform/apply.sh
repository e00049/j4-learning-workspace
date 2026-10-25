#!/usr/bin/env bash
# Cluster platform add-ons (vendored manifests). Run after terraform apply, before helm.
set -euo pipefail
cd "$(dirname "$0")"
kubectl create namespace wallettracker --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f custom-metrics-adapter.yaml
kubectl -n custom-metrics rollout status deploy/custom-metrics-stackdriver-adapter --timeout=180s
kubectl get apiservices | grep -E "custom.metrics|external.metrics"
