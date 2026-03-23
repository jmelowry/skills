---
name: media-automation-debugger
description: Debugger and ops skill for the media-automation stack on the catbus k3s cluster. Use for troubleshooting Sonarr, Radarr, Prowlarr, SABnzbd, NordVPN, and the Jellyfin family-sync cron. Covers pod health, VPN connectivity, download client issues, indexer problems, and the NordVPN sidecar pattern. Extension of the homelab-admin skill.
---

> **Extends homelab-admin.** All GitOps, kubectl access, and cluster context from that skill applies here.
> Skills repo: `/Users/jamie/github.com/skills` — create/edit skill files there, then run `./install.sh` to apply.

---

## Stack Overview

All resources live in the **`media-automation`** namespace.

| App | Containers | Port | URL |
|-----|-----------|------|-----|
| Sonarr | `sonarr` + `exportarr` | 8989 | https://sonarr.internal.catbus.lol |
| Radarr | `radarr` + `exportarr` | 7878 | https://radarr.internal.catbus.lol |
| Prowlarr | `prowlarr` | 9696 | https://prowlarr.internal.catbus.lol |
| SABnzbd | `sabnzbd` + `sabnzbd-exporter` | 8080 | https://sabnzbd.internal.catbus.lol |
| NordVPN + Jackett | `vpn` + `jackett` | 9117 (Jackett), 9091, 51413 | https://jackett.internal.catbus.lol |

**Sidecar pattern:** `sonarr` and `radarr` each have an `exportarr` sidecar for Prometheus metrics. `sabnzbd` has a `sabnzbd-exporter` sidecar. `nordvpn` pod runs `jackett` as a sidecar sharing the VPN network namespace — Jackett traffic routes through the VPN.

**CronJob:** `jellyfin-family-sync` — runs daily at 04:00, syncs Jellyfin libraries. Completed jobs are normal; Failed jobs need investigation.

---

## Step 1 — Quick Health Check

```bash
# All pods in namespace — anything not Running/Completed is a problem
kubectl get pods -n media-automation

# Check a specific app
kubectl get pods -n media-automation -l app=sonarr
kubectl get pods -n media-automation -l app=radarr
kubectl get pods -n media-automation -l app=nordvpn

# Recent events for the namespace
kubectl get events -n media-automation --sort-by='.lastTimestamp' | tail -20

# Ingress — confirm all routes have ADDRESS 192.168.0.200
kubectl get ingress -n media-automation
```

---

## Step 2 — Service Reachability

```bash
# Test the URL end-to-end (DNS + TLS + ingress + service)
curl -so /dev/null -w "%{http_code}" https://sonarr.internal.catbus.lol
curl -so /dev/null -w "%{http_code}" https://radarr.internal.catbus.lol

# Confirm MetalLB VIP is up
curl -k --connect-timeout 5 https://192.168.0.200

# If URL resolves but VIP times out → Tailscale asymmetric routing (see Step 6)
# If VIP responds but URL fails → Traefik routing or TLS issue
```

---

## Step 3 — Pod Logs

```bash
# Sonarr
kubectl logs -n media-automation deployment/sonarr -c sonarr --tail=50
kubectl logs -n media-automation deployment/sonarr -c sonarr --previous  # if crash

# Radarr
kubectl logs -n media-automation deployment/radarr -c radarr --tail=50

# Prowlarr
kubectl logs -n media-automation deployment/prowlarr --tail=50

# SABnzbd
kubectl logs -n media-automation deployment/sabnzbd -c sabnzbd --tail=50

# NordVPN (VPN container) — look for connection status, IP leaks
kubectl logs -n media-automation deployment/nordvpn -c vpn --tail=50

# Jackett (sidecar in nordvpn pod) — indexer issues
kubectl logs -n media-automation deployment/nordvpn -c jackett --tail=50

# Jellyfin family-sync cron — check last run
kubectl logs -n media-automation -l job-name --tail=50
# Or target the most recent completed job:
kubectl get jobs -n media-automation --sort-by=.status.completionTime | tail -5
kubectl logs -n media-automation job/<job-name>
```

---

## Step 4 — VPN Connectivity

Jackett runs inside the `nordvpn` pod's network namespace — all its traffic goes through the VPN. If indexers are failing, check VPN health first.

```bash
# Check what IP the VPN pod is using (should NOT be your home IP)
kubectl exec -n media-automation deployment/nordvpn -c vpn -- curl -s https://api.ipify.org

# Check VPN container status and recent logs
kubectl logs -n media-automation deployment/nordvpn -c vpn --tail=30

# Shell into the nordvpn pod (uses vpn container's network)
kubectl exec -it -n media-automation deployment/nordvpn -c vpn -- /bin/sh

# If VPN is disconnected, restart the deployment
kubectl rollout restart deployment/nordvpn -n media-automation
kubectl rollout status deployment/nordvpn -n media-automation
```

---

## Step 5 — Download Client (SABnzbd)

```bash
# Check sabnzbd is responding
kubectl port-forward -n media-automation svc/sabnzbd 8080:8080
# then: open http://localhost:8080

# Logs
kubectl logs -n media-automation deployment/sabnzbd -c sabnzbd --tail=50

# Shell in
kubectl exec -it -n media-automation deployment/sabnzbd -c sabnzbd -- /bin/sh

# Check disk space (downloads go to /mnt/kobol/downloads/ on the node)
kubectl exec -n media-automation deployment/sabnzbd -c sabnzbd -- df -h /downloads
```

---

## Step 6 — Tailscale Asymmetric Routing (Known Footgun)

**Symptom:** Services unreachable from local network and from `pve`, but reachable via vm1's Tailscale IP (`100.67.1.39`).

**Root cause:** `pve` advertises `192.168.0.0/24` as a Tailscale subnet route. If vm1 accepts that route, Tailscale adds `192.168.0.0/24 → tailscale0` to routing table 52 (higher priority than main table). All replies to local-network traffic then route through the Tailscale tunnel instead of `ens18`, breaking connectivity from the LAN.

**Diagnosis:**
```bash
# SSH to vm1 (via Tailscale IP if local network is broken)
ssh ubuntu@100.67.1.39

# Check if the bad route is present
ip route show table 52 | grep 192.168
# If you see: 192.168.0.0/24 dev tailscale0 → this is the problem

# Confirm pve can't reach vm1 even though they're on same LAN
# (pve can't ping 192.168.0.82 — asymmetric routing breaks replies)
```

**Fix (persistent across reboots):**
```bash
# On vm1 — disable acceptance of subnet routes from other Tailscale peers
# vm1 is directly on 192.168.0.0/24 via ens18 and doesn't need Tailscale routing for it
# Preserve other settings (dns, advertise-routes) from current prefs:
sudo tailscale debug prefs  # check current non-default settings first
sudo tailscale up --accept-routes=false --accept-dns=false --advertise-routes=192.168.0.0/24
```

**Verify fix:**
```bash
ip route show table 52 | grep 192.168  # should return nothing
curl -k --connect-timeout 5 https://192.168.0.200  # should connect
```

---

## Step 7 — Jellyfin Family Sync CronJob

```bash
# Check cron schedule and last run
kubectl get cronjob jellyfin-family-sync -n media-automation

# List recent jobs (Completed = good, Failed = investigate)
kubectl get jobs -n media-automation --sort-by=.metadata.creationTimestamp | tail -10

# Logs from the most recent job
LATEST=$(kubectl get jobs -n media-automation --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')
kubectl logs -n media-automation job/$LATEST

# Manually trigger a sync
kubectl create job --from=cronjob/jellyfin-family-sync manual-sync-$(date +%s) -n media-automation
```

---

## Step 8 — Restart / Recovery

```bash
# Restart a specific app
kubectl rollout restart deployment/<name> -n media-automation
kubectl rollout status deployment/<name> -n media-automation

# Scale down for maintenance, scale back up
kubectl scale deployment/<name> -n media-automation --replicas=0
kubectl scale deployment/<name> -n media-automation --replicas=1

# Force delete a stuck pod (k8s will recreate it)
kubectl delete pod -n media-automation <pod-name>
```

---

## Step 9 — Storage

Media files live on the node host path (not PVCs):
- **Media (read-only):** `/mnt/kobol/video-nfs/` → mounted into pods as `/media` or `/movies`, `/tv`
- **Downloads:** `/mnt/kobol/downloads/` → mounted into sabnzbd and *arr apps

```bash
# Check if host paths are accessible from a pod
kubectl exec -n media-automation deployment/sonarr -c sonarr -- ls /tv
kubectl exec -n media-automation deployment/radarr -c radarr -- ls /movies
kubectl exec -n media-automation deployment/sabnzbd -c sabnzbd -- ls /downloads
```

If these fail with "no such file or directory", the NFS mount on the node is down:
```bash
# On vm1:
df -h | grep kobol
mount | grep kobol
# Remount if needed:
sudo mount -a
```
