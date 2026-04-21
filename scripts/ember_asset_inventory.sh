#!/usr/bin/env bash
# Pull a full Ember-product asset inventory from moshq.app.
# Requires cookies exported from moshq.app (Netscape format).
#
# Usage: ember_asset_inventory.sh <path/to/cookies.txt> [output.json]

set -euo pipefail

COOKIES="${1:-/Users/auggieclement/Downloads/moshq.app_cookies (7).txt}"
OUT="${2:-/Users/auggieclement/Downloads/mos_strategy/.local/ember-asset-inventory.json}"

if [[ ! -f "$COOKIES" ]]; then
  echo "cookies file not found: $COOKIES" >&2
  exit 2
fi

mkdir -p "$(dirname "$OUT")"

DBJWT=$(awk '$6=="__clerk_db_jwt" {print $7}' "$COOKIES")
SESSCOOKIE=$(awk '$6=="__session" {print $7}' "$COOKIES")

if [[ -z "$DBJWT" || -z "$SESSCOOKIE" ]]; then
  echo "Missing required cookies (__clerk_db_jwt or __session)" >&2
  exit 2
fi

# Decode the expired __session to recover the session ID
PAYLOAD=$(echo "$SESSCOOKIE" | cut -d. -f2)
PAD=$(( (4 - ${#PAYLOAD} % 4) % 4 ))
PADDED="${PAYLOAD}$(printf '=%.0s' $(seq 1 $PAD))"
SID=$(echo "$PADDED" | tr '_-' '/+' | base64 -d 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['sid'])")

echo "Clerk session id: $SID"

# Mint a fresh backend-template JWT via Clerk's frontend API
CLERK_HOST="https://immune-turtle-79.clerk.accounts.dev"
TOKEN_RESP=$(curl -fsS -X POST \
  "${CLERK_HOST}/v1/client/sessions/${SID}/tokens/backend?_clerk_js_version=5.50.0&__dev_session=${DBJWT}" \
  -H "Origin: https://moshq.app" \
  -H "Referer: https://moshq.app/" \
  -H "Content-Type: application/x-www-form-urlencoded")
JWT=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['jwt'])")
echo "minted JWT (len ${#JWT})"

API=https://api.moshq.app

# 1. Find the Ember client
CLIENTS=$(curl -fsS -H "Authorization: Bearer $JWT" "$API/clients")
EMBER_CLIENT=$(echo "$CLIENTS" | python3 -c "
import sys, json
clients = json.load(sys.stdin)
for c in clients:
    name = (c.get('name') or '').lower()
    cid = c.get('id') or ''
    if 'ember' in name or cid.startswith('070d6cf7'):
        print(json.dumps(c))
        sys.exit(0)
")
if [[ -z "$EMBER_CLIENT" ]]; then
  echo "ERROR: could not find Ember client in list" >&2
  echo "$CLIENTS" | python3 -c "
import sys, json
for c in json.load(sys.stdin):
    print(f\"  - {c.get('name','?')!r} id={c.get('id')}\")
" >&2
  exit 3
fi
EMBER_CLIENT_ID=$(echo "$EMBER_CLIENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Ember clientId: $EMBER_CLIENT_ID"

# 2. Products for Ember
PRODUCTS=$(curl -fsS -H "Authorization: Bearer $JWT" "$API/products?clientId=${EMBER_CLIENT_ID}")
echo "products:"
echo "$PRODUCTS" | python3 -c "
import sys, json
for p in json.load(sys.stdin):
    print(f\"  - {p.get('name','?')!r} id={p.get('id')}\")
"

# 3. All assets for Ember (no assetKind filter so we see everything)
ASSETS=$(curl -fsS -H "Authorization: Bearer $JWT" "$API/assets?clientId=${EMBER_CLIENT_ID}")
ASSET_COUNT=$(echo "$ASSETS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
echo "assets found: $ASSET_COUNT"

# Write combined JSON output
python3 <<PY
import json

with open("/tmp/ember_clients.json","w") as f: f.write("""$CLIENTS""")
with open("/tmp/ember_products.json","w") as f: f.write("""$PRODUCTS""")
with open("/tmp/ember_assets.json","w") as f: f.write("""$ASSETS""")

out = {
    "client": json.loads('''$EMBER_CLIENT'''),
    "products": json.loads('''$PRODUCTS'''),
    "assets": json.loads('''$ASSETS'''),
}
with open("$OUT","w") as f:
    json.dump(out, f, indent=2)
print(f"wrote $OUT ({len(out['assets'])} assets)")
PY
