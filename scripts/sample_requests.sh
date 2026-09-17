#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TENANT="${TENANT:-acme}"

echo "== Health =="
curl -sS "$BASE_URL/health" | python3 -m json.tool

echo
echo "== Create document =="
CREATE_RESP=$(curl -sS -X POST "$BASE_URL/documents" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT" \
  -d '{"title":"Kubernetes networking","content":"Services, ingress controllers, and CNI plugins enable cluster networking.","metadata":{"topic":"k8s"}}')
echo "$CREATE_RESP" | python3 -m json.tool
DOC_ID=$(echo "$CREATE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo
echo "== Search (assessment contract: ?tenant=) =="
curl -sS "$BASE_URL/search?q=kubernetes&tenant=$TENANT" | python3 -m json.tool

echo
echo "== Search (header tenant) =="
curl -sS "$BASE_URL/search?q=kubernetes" \
  -H "X-Tenant-ID: $TENANT" | python3 -m json.tool

echo
echo "== Get document =="
curl -sS "$BASE_URL/documents/$DOC_ID" \
  -H "X-Tenant-ID: $TENANT" | python3 -m json.tool

echo
echo "== Cross-tenant should 404 =="
curl -sS -o /tmp/cross_tenant.json -w "HTTP %{http_code}\n" \
  "$BASE_URL/documents/$DOC_ID" \
  -H "X-Tenant-ID: other-tenant" || true
python3 -m json.tool < /tmp/cross_tenant.json || cat /tmp/cross_tenant.json

echo
echo "== Delete document =="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" \
  -X DELETE "$BASE_URL/documents/$DOC_ID" \
  -H "X-Tenant-ID: $TENANT"

echo "Done."
