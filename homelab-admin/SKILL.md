---
name: homelab-admin
description: Homelab sysadmin skill for a k3s cluster at 192.168.0.82. Use for health checks, deploying workloads, troubleshooting pods, managing ArgoCD GitOps workflow, adding applications, inspecting logs, and any cluster operations. The cluster runs at *.internal.catbus.lol with ArgoCD as the GitOps controller. Status page at https://status.internal.catbus.lol/. Manifest repo at /Users/jamie/github.com/k3s-cluster.
---

This skill covers everything needed to operate, debug, and extend the homelab k3s cluster. All persistent changes go through the **GitOps workflow** — commit manifests to the repo, push to Gitea, ArgoCD syncs. Direct `kubectl apply` is reserved for emergencies and bootstrap-only operations.

---

## Cluster Overview

| Property | Value |
|----------|-------|
| Node IP | `192.168.0.82` |
| Distro | k3s (single-node) |
| Domain | `*.internal.catbus.lol` |
| Ingress | Traefik (LoadBalancer IP: `192.168.0.200` via MetalLB) |
| TLS | cert-manager, wildcard cert `wildcard-internal-catbus-lol-tls` (Let's Encrypt DNS-01 via Cloudflare) |
| DNS | Pi-hole (`192.168.0.53`) + external-dns webhook |
| Load balancer | MetalLB (`192.168.0.200`) |
| Storage class | `local-path` (K3s default) |
| Media host paths | `/mnt/kobol/video-nfs/` (read-only), `/mnt/kobol/downloads/` |
| GitOps | ArgoCD (App-of-Apps pattern) |
| Git remote | `https://gitea.internal.catbus.lol/gitea-admin/k3s-cluster` |
| Local repo | `/Users/jamie/github.com/k3s-cluster` |
| Status page | `https://status.internal.catbus.lol/` |
| ArgoCD UI | `https://argocd.internal.catbus.lol` |
| Firewall | UFW — ports 22/80/443 external; K3s API + MetalLB restricted to `192.168.0.0/24` |

---

## Step 1 — Health Check

### Quick cluster health

```bash
# Node status
kubectl get nodes -o wide

# All pods across all namespaces — spot anything not Running/Completed
kubectl get pods -A

# Recent events — surface errors and warnings
kubectl get events -A --sort-by='.lastTimestamp' | tail -30

# Check Gatus status page (uptime of all monitored services)
curl -s https://status.internal.catbus.lol/api/v1/endpoints/statuses | jq '.[].results[-1] | {name: .conditionResults, success}'
```

### ArgoCD application health

```bash
# All apps and their sync/health status
kubectl get applications -n argocd

# Any app out of sync or degraded
kubectl get applications -n argocd -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.sync.status}{"\t"}{.status.health.status}{"\n"}{end}'
```

### Per-app health

```bash
# Pods in a namespace
kubectl get pods -n <namespace>

# Recent logs
kubectl logs -n <namespace> deployment/<name> --tail=50

# Describe a crashlooping or pending pod
kubectl describe pod -n <namespace> <pod-name>
```

---

## Step 2 — GitOps Workflow (ALWAYS use this for persistent changes)

**The rule:** if you want a change to survive a pod restart or cluster reboot, it must go through Git. ArgoCD has `selfHeal: true` — it will revert any manual `kubectl apply` within the next sync cycle.

### Normal workflow

```
1. Edit manifest(s) in /Users/jamie/github.com/k3s-cluster
2. git add + commit + push to main
3. ArgoCD detects the change (webhook instant, or within 3h polling)
4. ArgoCD syncs — applies the diff to the cluster
```

### Force an immediate sync (instead of waiting for polling)

```bash
# Sync a specific app
kubectl -n argocd exec deploy/argocd-server -- argocd app sync <app-name> --auth-token $(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)

# Or trigger via the ArgoCD UI at https://argocd.internal.catbus.lol
```

### Check what ArgoCD would change before pushing

```bash
kubectl get application <app-name> -n argocd -o jsonpath='{.status.sync.comparedTo}'
```

### What ArgoCD manages

ArgoCD's root-app watches `apps/argocd/applications/`. Every `.yaml` in that directory is an ArgoCD Application CRD. The root-app itself is the only thing applied manually (during bootstrap).

Sync policy on all apps:
- `automated.prune: true` — resources removed from Git are deleted from the cluster
- `automated.selfHeal: true` — cluster drift is corrected automatically
- `syncOptions: [CreateNamespace=true]` — namespaces are created if missing

---

## Step 3 — Adding a New Application

### Option A: Raw manifests (standard pattern)

1. Create `apps/<name>/` with these files:

```
apps/<name>/
├── namespace.yaml
├── deployment.yaml
├── service.yaml
├── ingress.yaml
├── pvc.yaml          (if persistent storage needed)
└── secret.yaml       (if credentials needed)
```

**namespace.yaml template:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: <name>
```

**deployment.yaml template:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <name>
  namespace: <name>
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <name>
  template:
    metadata:
      labels:
        app: <name>
    spec:
      containers:
        - name: <name>
          image: <image>:<tag>
          ports:
            - containerPort: <port>
          env: []
          volumeMounts: []
      volumes: []
```

**ingress.yaml template (Traefik + TLS):**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: <name>
  namespace: <name>
  annotations:
    kubernetes.io/ingress.class: traefik
spec:
  rules:
    - host: <name>.internal.catbus.lol
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: <name>
                port:
                  number: <port>
  tls:
    - hosts:
        - <name>.internal.catbus.lol
      secretName: wildcard-internal-catbus-lol-tls
```

**pvc.yaml template:**
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: <name>-data
  namespace: <name>
  annotations:
    argocd.argoproj.io/managed-by: argocd   # prevents ArgoCD from pruning it
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

2. Create the ArgoCD Application at `apps/argocd/applications/<name>.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <name>
  namespace: argocd
spec:
  project: cluster-apps
  source:
    repoURL: https://gitea.internal.catbus.lol/gitea-admin/k3s-cluster
    targetRevision: HEAD
    path: apps/<name>
  destination:
    server: https://kubernetes.default.svc
    namespace: <name>
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

3. Commit and push — ArgoCD's root-app picks up the new Application automatically.

### Option B: Helm chart (use `charts/generic-app/`)

For apps that fit the standard deployment+service+ingress+PVC pattern:

```yaml
# apps/argocd/applications/<name>.yaml
source:
  repoURL: https://gitea.internal.catbus.lol/gitea-admin/k3s-cluster
  targetRevision: HEAD
  path: charts/generic-app
  helm:
    valueFiles:
      - ../../apps/<name>/values.yaml
```

---

## Step 4 — Common Operations

### Restart a deployment

```bash
kubectl rollout restart deployment/<name> -n <namespace>
kubectl rollout status deployment/<name> -n <namespace>
```

### Tail logs

```bash
# Follow logs
kubectl logs -n <namespace> deployment/<name> -f

# Last N lines from all pods in a deployment
kubectl logs -n <namespace> -l app=<name> --tail=100
```

### Shell into a pod

```bash
kubectl exec -it -n <namespace> deployment/<name> -- /bin/sh
```

### Port-forward for local access

```bash
kubectl port-forward -n <namespace> svc/<name> 8080:<service-port>
```

### Scale

```bash
# Scale down (maintenance)
kubectl scale deployment/<name> -n <namespace> --replicas=0

# Scale back up
kubectl scale deployment/<name> -n <namespace> --replicas=1
```

### Check resource usage

```bash
kubectl top nodes
kubectl top pods -A
kubectl top pods -n <namespace>
```

### Inspect a secret

```bash
kubectl get secret <name> -n <namespace> -o jsonpath='{.data}' | jq 'to_entries[] | {key, value: (.value | @base64d)}'
```

---

## Step 5 — Troubleshooting

### CrashLoopBackOff

```bash
# Get logs from the previous (crashed) container
kubectl logs -n <namespace> <pod> --previous

# Check events for the pod
kubectl describe pod -n <namespace> <pod>
```

### OOMKilled

```bash
# Confirm OOM
kubectl describe pod -n <namespace> <pod> | grep -A5 "Last State"

# Fix: increase memory limit in the deployment manifest, commit + push
# In deployment.yaml:
# resources:
#   limits:
#     memory: 512Mi
#   requests:
#     memory: 256Mi
```

### Pending pod (won't schedule)

```bash
# Most common cause: PVC not bound or node resource exhaustion
kubectl describe pod -n <namespace> <pod> | grep -A20 Events

# Check PVC status
kubectl get pvc -n <namespace>

# Check node capacity
kubectl describe node | grep -A10 "Allocated resources"
```

### ArgoCD sync failure

```bash
# See the error
kubectl get application <name> -n argocd -o jsonpath='{.status.conditions}'

# Check what diff ArgoCD sees
kubectl get application <name> -n argocd -o jsonpath='{.status.sync.comparedTo}'
```

### DNS not resolving for a new service

Pi-hole (`192.168.0.53`) is the cluster DNS. CoreDNS routes `internal.catbus.lol` queries to Pi-hole, which resolves `*.internal.catbus.lol` → `192.168.0.200` (Traefik's MetalLB IP). External-dns manages Pi-hole records automatically — adding an Ingress resource with the right hostname is enough, no manual Pi-hole config needed.

```bash
# Confirm external-dns saw the new ingress
kubectl logs -n base deployment/external-dns --tail=30

# Test DNS from the cluster
kubectl run -it --rm dns-test --image=busybox --restart=Never -- nslookup <hostname>

# Test DNS from local machine
nslookup <name>.internal.catbus.lol 192.168.0.53
```

### Certificate not issuing

```bash
# Check Certificate resource
kubectl get certificate -n <namespace>
kubectl describe certificate -n <namespace> <name>

# Check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager --tail=50
```

---

## Step 6 — Deployed Applications Reference

| App | Namespace | URL | Notes |
|-----|-----------|-----|-------|
| ArgoCD | `argocd` | https://argocd.internal.catbus.lol | GitOps controller |
| Gatus | `gatus` | https://status.internal.catbus.lol | Status/uptime page |
| Jellyfin | `jellyfin` | https://jellyfin.internal.catbus.lol | Media server |
| Home Assistant | `home-assistant` | https://home-assistant.internal.catbus.lol | Smart home |
| Grafana | `monitoring` | https://grafana.internal.catbus.lol | Metrics dashboards |
| LibreChat | `librechat` | https://librechat.internal.catbus.lol | LLM interface |
| OpenWebUI | `openwebui` | https://openwebui.internal.catbus.lol | LLM interface |
| Gitea | `gitea` | https://gitea.internal.catbus.lol | Git server |
| Dashy | `dashy` | https://dashy.internal.catbus.lol | Homepage dashboard |
| Calibre-Web | `calibre-web` | https://calibre-web.internal.catbus.lol | E-book library |
| Audiobookshelf | `audiobookshelf` | https://audiobookshelf.internal.catbus.lol | Audiobooks |
| OwnCloud | `owncloud` | https://owncloud.internal.catbus.lol | File sync |
| Media Automation | `media-automation` | — | Sonarr, Radarr, Transmission, NordVPN |
| RomM | `romm` | https://romm.internal.catbus.lol | ROM library (DB migration issue) |
| Kokoro | `kokoro` | https://kokoro.internal.catbus.lol | TTS worker |
| Daily Double | `daily-double` | — | Jeopardy play-along app |
| Gitea Actions | `gitea-actions` | — | CI runner (self-hosted) |

---

## Step 7 — Repo Structure Reference

```
k3s-cluster/
├── apps/
│   ├── argocd/
│   │   ├── applications/       # ArgoCD Application CRDs (one per app)
│   │   │   └── root-app.yaml   # App-of-Apps root — watches this dir
│   │   ├── ingress.yaml
│   │   ├── kustomization.yaml
│   │   └── GITOPS-SETUP.md
│   ├── monitoring/
│   │   └── exporters/          # smartctl, omada, speedtest, blackbox, home-assistant-metrics
│   └── <app-name>/             # One dir per application
│       ├── namespace.yaml
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── ingress.yaml
│       ├── pvc.yaml
│       └── secret.yaml
├── base/                       # Core cluster services
│   ├── ingress/                # Traefik config
│   ├── metallb/                # MetalLB (192.168.0.200)
│   ├── coredns-custom.yaml     # Routes internal.catbus.lol → Pi-hole
│   ├── monitoring/             # Prometheus + kube-prometheus-stack
│   └── k8s-dashboard/
├── bootstrap/                  # One-time cluster setup (apply manually)
│   ├── namespaces.yaml
│   ├── cert-manager/           # Let's Encrypt + Cloudflare DNS-01
│   ├── gitea/
│   ├── pihole/
│   └── security/setup-firewall.sh
├── storage/                    # Storage namespace
├── charts/
│   └── generic-app/            # Reusable Helm chart for new apps
├── container-images/           # Custom images (gitea-actions-runner, comfyui)
│   └── build.sh                # Kaniko build → Harbor push
├── monitoring/                 # Grafana dashboard JSON definitions
└── .gitea/workflows/           # Gitea Actions CI (builds container images)
```

---

## Output Checklist

Before finishing any task, confirm:
- [ ] Persistent changes are committed to `/Users/jamie/github.com/k3s-cluster` and pushed to Gitea — not applied directly with kubectl
- [ ] New app follows the namespace/deployment/service/ingress pattern
- [ ] New app has an ArgoCD Application in `apps/argocd/applications/`
- [ ] PVCs have `argocd.argoproj.io/managed-by: argocd` annotation to prevent pruning
- [ ] Ingress uses `wildcard-internal-catbus-lol-tls` TLS secret
- [ ] Ingress hostname follows `<name>.internal.catbus.lol` pattern
- [ ] Secrets use `stringData` (not `data`) for readability in the repo
- [ ] After pushing, verify ArgoCD syncs cleanly: `kubectl get applications -n argocd`
