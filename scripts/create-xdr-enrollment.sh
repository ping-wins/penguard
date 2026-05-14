#!/usr/bin/env bash
# Create an xdr_rico enrollment token through the FortiDashboard BFF.
#
# The token is returned only once by xdr_rico. Treat it as a secret and pass it
# to agent_private as AGENT_PRIVATE_ENROLLMENT_TOKEN.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

usage() {
  cat <<'EOF'
Usage:
  scripts/create-xdr-enrollment.sh [options]

Options:
  --api-url URL          FortiDashboard API URL (default: API_HOST/.env or http://localhost:8000)
  --email EMAIL          FortiDashboard login email (or FORTIDASHBOARD_LOGIN_EMAIL)
  --password PASSWORD    FortiDashboard login password (or FORTIDASHBOARD_LOGIN_PASSWORD)
  --display-name NAME    Enrollment display name (default: Agent Private)
  --hostname-hint NAME   Optional endpoint hostname hint
  --raw-token            Print only the enrollment token
  -h, --help             Show this help

Example:
  FORTIDASHBOARD_LOGIN_EMAIL=analyst@example.com \
  FORTIDASHBOARD_LOGIN_PASSWORD='correct-horse-battery-staple' \
    scripts/create-xdr-enrollment.sh --display-name "Windows Server Lab"
EOF
}

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

API_URL="${FORTIDASHBOARD_API_URL:-${API_HOST:-http://localhost:8000}}"
LOGIN_EMAIL="${FORTIDASHBOARD_LOGIN_EMAIL:-}"
LOGIN_PASSWORD="${FORTIDASHBOARD_LOGIN_PASSWORD:-}"
DISPLAY_NAME="Agent Private"
HOSTNAME_HINT=""
RAW_TOKEN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-url)
      API_URL="${2:?missing value for --api-url}"
      shift 2
      ;;
    --email)
      LOGIN_EMAIL="${2:?missing value for --email}"
      shift 2
      ;;
    --password)
      LOGIN_PASSWORD="${2:?missing value for --password}"
      shift 2
      ;;
    --display-name)
      DISPLAY_NAME="${2:?missing value for --display-name}"
      shift 2
      ;;
    --hostname-hint)
      HOSTNAME_HINT="${2:?missing value for --hostname-hint}"
      shift 2
      ;;
    --raw-token)
      RAW_TOKEN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

for tool in curl jq; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "error: ${tool} is required." >&2
    exit 1
  fi
done

if [[ -z "${LOGIN_EMAIL}" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "FortiDashboard email: " LOGIN_EMAIL
  else
    echo "error: set FORTIDASHBOARD_LOGIN_EMAIL or pass --email." >&2
    exit 1
  fi
fi

if [[ -z "${LOGIN_PASSWORD}" ]]; then
  if [[ -t 0 ]]; then
    read -r -s -p "FortiDashboard password: " LOGIN_PASSWORD
    echo
  else
    echo "error: set FORTIDASHBOARD_LOGIN_PASSWORD or pass --password." >&2
    exit 1
  fi
fi

API_URL="${API_URL%/}"
COOKIE_JAR="$(mktemp)"
trap 'rm -f "${COOKIE_JAR}"' EXIT

csrf="$(
  curl -sS -f -c "${COOKIE_JAR}" "${API_URL}/api/auth/csrf" \
    | jq -r '.csrfToken'
)"

if [[ -z "${csrf}" || "${csrf}" == "null" ]]; then
  echo "error: API did not return a CSRF token." >&2
  exit 1
fi

login_payload="$(
  jq -n \
    --arg email "${LOGIN_EMAIL}" \
    --arg password "${LOGIN_PASSWORD}" \
    '{email: $email, password: $password}'
)"

curl -sS -f -b "${COOKIE_JAR}" -c "${COOKIE_JAR}" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: ${csrf}" \
  -d "${login_payload}" \
  "${API_URL}/api/auth/login" >/dev/null

enrollment_payload="$(
  jq -n \
    --arg displayName "${DISPLAY_NAME}" \
    --arg hostnameHint "${HOSTNAME_HINT}" \
    '{
      displayName: $displayName
    } + (if $hostnameHint == "" then {} else {hostnameHint: $hostnameHint} end)'
)"

response="$(
  curl -sS -f -b "${COOKIE_JAR}" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: ${csrf}" \
    -d "${enrollment_payload}" \
    "${API_URL}/api/weapons/enrollments"
)"

token="$(jq -r '.token' <<<"${response}")"
enrollment_id="$(jq -r '.id' <<<"${response}")"

if [[ -z "${token}" || "${token}" == "null" ]]; then
  echo "error: enrollment response did not include token." >&2
  echo "${response}" | jq . >&2
  exit 1
fi

if [[ "${RAW_TOKEN}" -eq 1 ]]; then
  printf '%s\n' "${token}"
  exit 0
fi

cat <<EOF
Enrollment created: ${enrollment_id}

export AGENT_PRIVATE_API_URL="${API_URL}"
export AGENT_PRIVATE_ENDPOINT_ID="${HOSTNAME_HINT:-agent-private-endpoint}"
export AGENT_PRIVATE_ENROLLMENT_TOKEN="${token}"

PowerShell:
\$env:AGENT_PRIVATE_API_URL = "${API_URL}"
\$env:AGENT_PRIVATE_ENDPOINT_ID = "${HOSTNAME_HINT:-agent-private-endpoint}"
\$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "${token}"
EOF
