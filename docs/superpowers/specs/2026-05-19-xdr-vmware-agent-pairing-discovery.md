# XDR Agent VMware Pairing And Discovery Spec

## Goal

Windows Server lab operators should not pass FortiDashboard host URLs,
endpoint IDs or environment variables during normal setup. The cockpit shows
only the one-time enrollment token. The Windows agent discovers the dashboard
host on the VMware management network, pairs with that token and saves local
daemon configuration.

## Lab Network Contract

Use a VMware host-only or NAT management network shared by:

- the machine hosting FortiDashboard Docker Compose;
- the Windows Server 2022 Desktop Experience VM running `agent_private`.

Keep this management network separate from the FortiGate/FortiWeb/victim traffic
path when the lab needs multiple NICs.

## Operator Flow

1. Analyst opens Endpoints and creates a Windows agent enrollment.
2. Cockpit displays only the enrollment token returned once by `xdr_rico`.
3. Operator runs `agent-private pair "<token>"` from the Windows checkout.
4. Agent sends a UDP discovery request on the VMware management network.
5. FortiDashboard API replies with product metadata and API port.
6. Agent builds the API URL from the UDP response source IP.
7. If UDP discovery fails, agent probes likely VMware host addresses for the VM
   subnet, such as `.1` and `.2`, via `/health`.
8. Agent posts the token and host metadata to `/api/weapons/agent/pair`.
9. BFF forwards to `xdr_rico` `/enrollments/pair`.
10. `xdr_rico` validates the token hash and returns the endpoint ID.
11. Agent saves API URL, endpoint ID and token to local config.
12. Operator installs/starts the Windows Service.

## Discovery Protocol

Request:

```json
{
  "type": "fortidashboard.agent_discovery.v1",
  "nonce": "random",
  "service": "agent_private"
}
```

Response:

```json
{
  "type": "fortidashboard.agent_discovery.response.v1",
  "product": "FortiDashboard",
  "apiScheme": "http",
  "apiPort": 8000,
  "apiBasePath": "/api",
  "nonce": "same random"
}
```

The response does not include secrets. The agent uses the UDP packet source IP
plus `apiScheme` and `apiPort` to create the API URL. Gateway probing is a
fallback for VMware/Docker/firewall combinations where broadcast packets do not
reach the API container.

## Security Boundaries

- Discovery does not authenticate or enroll hosts.
- The enrollment token remains the only bootstrap secret and is still shown once.
- Pairing responses do not echo the token.
- Pairing is audited without token values.
- The dashboard does not connect inbound to the Windows host.
- Remote XDR actions remain typed pull actions; no arbitrary PowerShell.

## VMware Notes

Open these paths on the host firewall for the VMware management adapter:

- `8000/tcp` for the BFF API.
- `8764/udp` for discovery.

If UDP broadcast is blocked, `agent-private pair --api-url
http://<host-ip>:8000 "<token>"` exists only as an advanced diagnostic fallback,
not the normal lab path.
