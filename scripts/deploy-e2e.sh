#!/usr/bin/env bash
set -euo pipefail

: "${API_BASE:=https://moshq.app/api}"
: "${INSTANCE_NAME:=ubuntu-4gb-nbg1-2}"
: "${WORKLOAD_NAME:=honest-herbalist}"
: "${MOS_TOKEN:?MOS_TOKEN is required (Clerk backend JWT token)}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd curl
require_cmd jq
require_cmd mktemp

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

PLAN_FILE="${TMP_DIR}/plan.json"
cat >"${PLAN_FILE}" <<'JSON'
{
  "operations": [],
  "new_spec": {
    "provider": "hetzner",
    "region": "fsn1",
    "networks": [
      {
        "name": "default",
        "cidr": "10.0.0.0/16"
      }
    ],
    "instances": [
      {
        "name": "ubuntu-4gb-nbg1-2",
        "size": "cx23",
        "network": "default",
        "region": "nbg1",
        "labels": {},
        "workloads": [
          {
            "name": "honest-herbalist",
            "repo_url": "https://github.com/auggie-clement/temp-landing",
            "branch": "main",
            "runtime": "nodejs",
            "build_config": {
              "install_command": "npm install",
              "build_command": "npm run build",
              "system_packages": []
            },
            "service_config": {
              "command": "npm run start",
              "environment": {},
              "ports": [
                3000
              ]
            },
            "destination_path": "/opt/apps"
          }
        ],
        "maintenance": null
      }
    ],
    "load_balancers": [],
    "firewalls": [],
    "dns_records": [],
    "containers": []
  }
}
JSON

request_post() {
  local url="$1"
  local data="$2"
  curl --fail-with-body --silent --show-error \
    --request POST "${url}" \
    --header "Authorization: Bearer eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDIyMkFBQSIsImtpZCI6Imluc18zNmlRenNVb25UN2VXS3RSNXZJNkthelkxU0EiLCJ0eXAiOiJKV1QifQ.eyJhenAiOiJodHRwczovL21vc2hxLmFwcCIsImV4cCI6MTc3MDg0MTQyNywiaWF0IjoxNzcwODQxMzY3LCJpc3MiOiJodHRwczovL2ltbXVuZS10dXJ0bGUtNzkuY2xlcmsuYWNjb3VudHMuZGV2IiwianRpIjoiN2EzMzUxYmYwMjI5MDA4NzZlNTMiLCJuYmYiOjE3NzA4NDEzNjIsIm9yZ19pZCI6Im9yZ18zNmliN1JxNU5pc2JHR1FDcDU0cmJRQTRCaEsiLCJzdWIiOiJ1c2VyXzM2aVRNdENsbmtTZGNSQkRGdXF2Y0Q3MkR3dCJ9.nTChifsrsrTWC3W27f2BmDuPyixbyjkLAXRPQu7sLok9POS2C5KK2nUBG2uXgiWekFuyfGdiYTlCeNzoXx3byPDtWkIboZD5NdoRFMmq9J2pZXMnIMajxRWIkFoTR4mQNpwEC2yQ80KNrzcKViX03xdP7WaFd7iPGggUzvHiZYOUBte74F2AI1_CXpYtD4-G3zYXOIz8l1Yav4VT2gtUL9BtOI-eeCKyEnrIMAdN5Tgq4KDCFr9Z80jT8hlM2kerM95kuaP4w_xxgamjmzf6LLXh9iognlKdJot88UFS7V3UNpfoHTDVuGwaAOK2yPSva7SdLH12JV1iHTvzUnH_nQ" \
    --header "Content-Type: application/json" \
    --data "${data}"
}

echo "==> Step 1/4: create plan via API"
CREATE_PAYLOAD="$(jq -n --rawfile content "${PLAN_FILE}" '{content:$content}')"
CREATE_RESP="$(request_post "${API_BASE}/deploy/plans" "${CREATE_PAYLOAD}")"
echo "${CREATE_RESP}" | jq .

PLAN_PATH="$(echo "${CREATE_RESP}" | jq -r '.path // empty')"
if [ -z "${PLAN_PATH}" ]; then
  echo "Create plan response did not include .path" >&2
  exit 1
fi

echo "==> Step 2/4: apply created plan"
APPLY_1_PAYLOAD="$(jq -n --arg plan_path "${PLAN_PATH}" '{plan_path:$plan_path}')"
APPLY_1_RESP="$(request_post "${API_BASE}/deploy/plans/apply" "${APPLY_1_PAYLOAD}")"
echo "${APPLY_1_RESP}" | jq '{returncode, plan_path, server_ips, live_url}'

APPLY_1_RC="$(echo "${APPLY_1_RESP}" | jq -r '.returncode // 1')"
if [ "${APPLY_1_RC}" != "0" ]; then
  echo "First apply failed. Full response:" >&2
  echo "${APPLY_1_RESP}" | jq . >&2
  exit 1
fi

echo "==> Step 3/4: modify workload in plan"
PATCH_BODY="$(jq -n \
  --arg name "${WORKLOAD_NAME}" \
  '{name:$name, service_config:{environment:{DEPLOY_TEST_REVISION:"2"}}}')"
PLAN_PATH_Q="$(jq -rn --arg v "${PLAN_PATH}" '$v|@uri')"
PATCH_URL="${API_BASE}/deploy/plans/workloads?plan_path=${PLAN_PATH_Q}&instance_name=${INSTANCE_NAME}&create_if_missing=false&in_place=false"
PATCH_RESP="$(request_post "${PATCH_URL}" "${PATCH_BODY}")"
echo "${PATCH_RESP}" | jq .

UPDATED_PLAN_PATH="$(echo "${PATCH_RESP}" | jq -r '.updated_plan_path // empty')"
if [ -z "${UPDATED_PLAN_PATH}" ]; then
  echo "Patch response did not include .updated_plan_path" >&2
  exit 1
fi

echo "==> Step 4/4: apply modified plan"
APPLY_2_PAYLOAD="$(jq -n --arg plan_path "${UPDATED_PLAN_PATH}" '{plan_path:$plan_path}')"
APPLY_2_RESP="$(request_post "${API_BASE}/deploy/plans/apply" "${APPLY_2_PAYLOAD}")"
echo "${APPLY_2_RESP}" | jq '{returncode, plan_path, server_ips, live_url}'

APPLY_2_RC="$(echo "${APPLY_2_RESP}" | jq -r '.returncode // 1')"
if [ "${APPLY_2_RC}" != "0" ]; then
  echo "Second apply failed. Full response:" >&2
  echo "${APPLY_2_RESP}" | jq . >&2
  exit 1
fi

echo "Deploy E2E sequence passed: create -> apply -> modify -> apply"
