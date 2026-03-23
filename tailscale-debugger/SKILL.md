---
name: tailscale-debugger
description: Diagnose and fix Tailscale networking issues in the catbus homelab. Covers asymmetric routing (the most common failure), subnet route conflicts, DNS/MagicDNS problems, device connectivity, and access to local-network services (192.168.0.x / MetalLB 192.168.0.200) from the tailnet. Use when services are unreachable via local IP but work via Tailscale IP, or when Tailscale routing is suspected to be causing network weirdness.
---

> Skills repo: `/Users/jamie/github.com/skills` — create/edit skill files there, then run `./install.sh` to apply.

---

## Tailnet Overview

| Device | Tailscale IP | Role | Notes |
|--------|-------------|------|-------|
| m4-mba | 100.106.153.58 | Primary workstation | This machine |
| jamies-imac | 100.104.68.77 | Desktop | |
| vm1 (k3s node) | 100.67.1.39 | k3s control plane | Also advertises 192.168.0.0/24 — **accept-routes=false** |
| pve | 100.83.170.65 | Proxmox hypervisor | **Subnet router** for 192.168.0.0/24 |
| pihole | 100.76.249.86 | DNS server | |
| catbus-cloud | 100.66.27.19 | Cloud VPS | |
| iphone | 100.113.4.105 | Mobile | |

**Subnet routing:** `pve` advertises `192.168.0.0/24` → all tailnet devices can reach local network through pve. vm1 also advertises `192.168.0.0/24` but with `--accept-routes=false` so it doesn't route via Tailscale for local traffic (it's directly on the LAN).

**DNS:** Tailscale MagicDNS is active (`100.100.100.100`). Split DNS for `internal.catbus.lol` is configured to forward to Pi-hole (`192.168.0.53`) so `*.internal.catbus.lol` resolves to `192.168.0.200` (MetalLB) on all tailnet devices. `--accept-dns=false` is set on vm1 to avoid DNS conflicts with k3s CoreDNS.

---

## The Most Common Problem: Asymmetric Routing

**Symptom:** A node on the local network (192.168.0.x) is unreachable from other local devices AND from `pve`, but accessible via its Tailscale IP. `pve` also cannot ping the node directly.

**What's happening:** A device that is physically on `192.168.0.0/24` (via ethernet) has also *accepted* the Tailscale subnet route for `192.168.0.0/24` from `pve`. Tailscale adds that route to a high-priority routing table (table 52), which beats the main table. When the device tries to reply to local-network traffic, it routes the reply through the Tailscale tunnel — the sender never sees the reply.

**Diagnosis:**
```bash
# SSH to the affected device (use its Tailscale IP if local is broken)
ssh ubuntu@<tailscale-ip>

# Check routing tables
ip rule show
ip route show table 52

# If you see:
#   192.168.0.0/24 dev tailscale0
# in table 52, AND the device is directly on that subnet → this is the bug

# Confirm Tailscale has accepted routes from peers
tailscale debug prefs | grep -i accept
# "AcceptRoutes": true  ← problem if device is also on that subnet
```

**Fix (persistent):**
```bash
# Get current non-default settings first to preserve them
tailscale debug prefs

# Apply with accept-routes=false, keeping everything else the same
# Example for vm1:
sudo tailscale up --accept-routes=false --accept-dns=false --advertise-routes=192.168.0.0/24

# Verify the bad route is gone
ip route show table 52 | grep 192.168  # should be empty

# Test local connectivity
curl -k --connect-timeout 5 https://192.168.0.200
```

**Why `--accept-dns=false` on vm1:** k3s has its own CoreDNS that handles cluster DNS. If Tailscale overwrites `/etc/resolv.conf`, CoreDNS breaks. Always keep `--accept-dns=false` on the k3s node.

---

## Diagnosing Connectivity

### Can't reach a local IP from this Mac

```bash
# Check if we're using the subnet route
ip route show table 52 | grep 192.168  # should show pve's route
# Or on macOS:
/Applications/Tailscale.app/Contents/MacOS/Tailscale status --json | python3 -c \
  "import json,sys; d=json.load(sys.stdin); [print(p.get('HostName'), p.get('PrimaryRoutes','')) for p in d.get('Peer',{}).values() if p.get('PrimaryRoutes')]"

# Test DNS
nslookup sonarr.internal.catbus.lol       # uses MagicDNS (should return 192.168.0.200)
nslookup sonarr.internal.catbus.lol 192.168.0.53  # test Pi-hole directly

# Test connectivity
nc -zv 192.168.0.200 443     # MetalLB/Traefik
nc -zv 192.168.0.82 22       # k3s node SSH
ping 192.168.0.111           # pve (ping is blocked by pve's firewall — expect no reply)
```

### Can't reach a tailnet device

```bash
# Check device is online
/Applications/Tailscale.app/Contents/MacOS/Tailscale status | grep <device-name>

# Ping via Tailscale IP
ping 100.67.1.39   # vm1

# Test a port
nc -zv 100.67.1.39 22
nc -zv 100.67.1.39 443

# Check if your device is actually connected to Tailscale
/Applications/Tailscale.app/Contents/MacOS/Tailscale status
```

### DNS not resolving internal hostnames

```bash
# Check what DNS server is being used
nslookup sonarr.internal.catbus.lol
# Server should be 100.100.100.100 (Tailscale MagicDNS) or 192.168.0.53 (Pi-hole)
# NOT 8.8.8.8 — if it is, fix your system DNS settings

# Test split DNS is working
nslookup internal.catbus.lol 100.100.100.100

# If MagicDNS isn't working, check Tailscale is connected:
/Applications/Tailscale.app/Contents/MacOS/Tailscale status
```

---

## Checking the Subnet Router (pve)

`pve` is the gateway for all local network access from the tailnet. If it goes down, remote devices lose access to `192.168.0.x`.

```bash
# SSH to pve via Tailscale IP
ssh root@100.83.170.65

# Check Tailscale status on pve
tailscale status

# Check IP forwarding (must be 1)
cat /proc/sys/net/ipv4/ip_forward

# Check what subnet routes pve is advertising
tailscale debug prefs | grep -i route

# Check if pve can reach the local network
ping -c 2 192.168.0.82   # k3s node
ping -c 2 192.168.0.200  # MetalLB VIP
ping -c 2 192.168.0.53   # Pi-hole
```

**Note:** `pve` blocks ICMP from external hosts (Proxmox default firewall behavior). Pinging pve from your Mac will time out — that's expected. But pve can ping others on the LAN.

---

## Checking vm1 (k3s node) Tailscale Config

vm1's Tailscale config is intentionally different from other devices:

```bash
ssh ubuntu@100.67.1.39

# Current prefs — key settings to verify:
tailscale debug prefs
# Expected:
#   "AcceptRoutes": false  ← must be false (prevents asymmetric routing)
#   "AcceptDNS": false     ← must be false (k3s CoreDNS owns DNS)
#   "AdvertiseRoutes": ["192.168.0.0/24"]  ← vm1 also serves as subnet router

# Check routing table 52 is clean (no 192.168 routes)
ip route show table 52

# Check tailscale0 interface
ip addr show tailscale0
```

**If AcceptRoutes is true on vm1:** run the fix from the Asymmetric Routing section above.

---

## Re-enabling Tailscale After Config Change

If you run `tailscale up` with new flags, always include ALL non-default settings or use `--reset` carefully:

```bash
# Safe pattern: check current prefs first
tailscale debug prefs

# Then reconstruct the full command with your change + existing non-defaults
# For vm1:
sudo tailscale up --accept-routes=false --accept-dns=false --advertise-routes=192.168.0.0/24

# For pve (subnet router, full routing):
tailscale up --advertise-routes=192.168.0.0/24 --accept-routes=true
```

---

## Tailscale Admin Console

The Tailscale admin console is where subnet routes get approved. Without approval, advertised routes don't propagate to peers.

- Route approvals: approve new `--advertise-routes` here after running `tailscale up`
- Split DNS: `internal.catbus.lol` → `192.168.0.53` (Pi-hole)
- Access controls: if a device can't reach another, check ACLs here

---

## Checking iptables Interference

k3s and Docker both modify iptables heavily. Tailscale also adds `ts-input` and `ts-forward` chains. On vm1, check for unexpected drops:

```bash
# FORWARD chain — default policy is DROP, packets need explicit ACCEPT
sudo iptables -L FORWARD -n -v | head -15

# ts-forward — should only mark/accept Tailscale-interface traffic
sudo iptables -L ts-forward -n -v

# ts-input — should ACCEPT from tailscale0, RETURN for local IPs, DROP for spoofed CGNAT
sudo iptables -L ts-input -n -v

# Check for asymmetric routing symptoms in iptables counters
# If ts-forward has high DROP counts, something is being blocked
sudo iptables -L ts-forward -n -v -x
```
