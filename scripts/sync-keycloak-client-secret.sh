#!/usr/bin/env bash
# Align the Keycloak `penguard-bff` client secret with the value in .env
# after the first `docker compose up`. The realm import file ships with the
# literal `dev-client-secret`; this script overwrites it via the Keycloak
# admin REST API so the BFF and Keycloak agree on the same value.
#
# Usage:
#   ./scripts/sync-keycloak-client-secret.sh
#
# Requires `curl` and `jq`. Reads .env from the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "error: ${ENV_FILE} not found. Run scripts/bootstrap-secrets.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

for required in PENGUARD_KEYCLOAK_BASE_URL \
                PENGUARD_KEYCLOAK_REALM \
                PENGUARD_KEYCLOAK_CLIENT_ID \
                PENGUARD_KEYCLOAK_CLIENT_SECRET \
                KC_BOOTSTRAP_ADMIN_USERNAME \
                KC_BOOTSTRAP_ADMIN_PASSWORD; do
  if [[ -z "${!required:-}" ]]; then
    echo "error: ${required} is not set in ${ENV_FILE}" >&2
    exit 1
  fi
done

for tool in curl jq; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "error: ${tool} is required." >&2
    exit 1
  fi
done

KC_BASE="${PENGUARD_KEYCLOAK_BASE_URL%/}"
REALM="${PENGUARD_KEYCLOAK_REALM}"
CLIENT_ID="${PENGUARD_KEYCLOAK_CLIENT_ID}"

echo "Authenticating against ${KC_BASE} as ${KC_BOOTSTRAP_ADMIN_USERNAME}…"
token="$(
  curl -s -f --data-urlencode "username=${KC_BOOTSTRAP_ADMIN_USERNAME}" \
       --data-urlencode "password=${KC_BOOTSTRAP_ADMIN_PASSWORD}" \
       --data "grant_type=password" \
       --data "client_id=admin-cli" \
       "${KC_BASE}/realms/master/protocol/openid-connect/token" \
    | jq -r .access_token
)"

if [[ -z "${token}" || "${token}" == "null" ]]; then
  echo "error: admin token request failed." >&2
  exit 1
fi

echo "Looking up client ${CLIENT_ID} in realm ${REALM}…"
client_uuid="$(
  curl -s -f -H "Authorization: Bearer ${token}" \
       "${KC_BASE}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" \
    | jq -r '.[0].id'
)"

if [[ -z "${client_uuid}" || "${client_uuid}" == "null" ]]; then
  echo "error: client ${CLIENT_ID} not found in realm ${REALM}." >&2
  exit 1
fi

echo "Pushing the new secret for client ${CLIENT_ID} (uuid ${client_uuid})…"
curl -s -f -X PUT \
     -H "Authorization: Bearer ${token}" \
     -H "Content-Type: application/json" \
     --data "{\"secret\": \"${PENGUARD_KEYCLOAK_CLIENT_SECRET}\"}" \
     "${KC_BASE}/admin/realms/${REALM}/clients/${client_uuid}" \
  > /dev/null

echo "Done. The Keycloak client secret now matches PENGUARD_KEYCLOAK_CLIENT_SECRET in .env."

# Disable Kerberos storage provider when running without a real AD/KDC.
# The placeholder keytab signals a local-dev or lab setup where no Windows
# Server is running. Leaving Kerberos enabled causes "Cannot locate KDC"
# errors that block user creation and login.
KEYTAB_PATH="${PENGUARD_KEYTAB_PATH:-}"
if echo "${KEYTAB_PATH}" | grep -qE 'empty-keytab|placeholder'; then
  echo "Empty keytab detected — disabling Kerberos storage provider in realm ${REALM}…"
  component_id="$(
    curl -s -f -H "Authorization: Bearer ${token}" \
         "${KC_BASE}/admin/realms/${REALM}/components?name=kerberos-penguard" \
      | jq -r '.[0].id // empty'
  )"
  if [[ -n "${component_id}" && "${component_id}" != "null" ]]; then
    component_json="$(
      curl -s -f -H "Authorization: Bearer ${token}" \
           "${KC_BASE}/admin/realms/${REALM}/components/${component_id}"
    )"
    is_enabled="$(echo "${component_json}" | jq -r '.config.enabled[0] // "false"')"
    if [[ "${is_enabled}" == "true" ]]; then
      updated="$(echo "${component_json}" | jq '.config.enabled = ["false"]')"
      curl -s -f -X PUT \
           -H "Authorization: Bearer ${token}" \
           -H "Content-Type: application/json" \
           --data "${updated}" \
           "${KC_BASE}/admin/realms/${REALM}/components/${component_id}" > /dev/null \
        && echo "Kerberos provider disabled. Enable it manually when a real AD/KDC is available." \
        || echo "Warning: could not disable Kerberos provider (non-fatal)."
    else
      echo "Kerberos provider already disabled."
    fi
  fi
fi
