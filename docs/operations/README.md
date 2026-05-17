# Operations Runbooks

Use these runbooks for real lab/customer setup. Synthetic replay and historical
demo scripts belong outside this directory.

## VMware SOC Lab

Start here:

1. `vmware-soc-lab-blackarch-arch.md` - canonical end-to-end VMware topology.
2. `fortigate-scan-detection.md` - FortiGate/SIEM port-scan validation.
3. `fortiweb-landing-waf-lab.md` - FortiWeb landing reverse-proxy checklist.
4. `fortiweb-dos-lab.md` - controlled FortiWeb DoS/WAF validation.

Current canonical traffic path:

```txt
BlackArch attacker -> FortiGate -> FortiWeb -> Arch victim/origin
```

Current canonical management path:

```txt
Host/FortiDashboard -> FortiGate port1 bridged
Host/FortiDashboard -> FortiWeb port2 bridged
```

FortiDashboard manages FortiGate lab policies directly through the governed
FortiGate API orchestration path. FortiManager is optional/future lab
infrastructure, not a blocker for telemetry, policy validation or containment
tests.
