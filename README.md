# skills

Reusable Claude skills for development workflows.

Skills are consumed by [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and [Claude.ai](https://claude.ai). Each skill is a `SKILL.md` file that instructs Claude how to handle a specific category of task.

---

## Installation

```bash
# Clone the repo
git clone https://github.com/jmelowry/skills ~/skills

# Symlink individual skills into Claude's skills directory (auto-updates on pull)
ln -s ~/skills/project-scaffold ~/.claude/skills/project-scaffold
```

Or copy if you prefer explicit control:

```bash
cp -r ~/skills/project-scaffold ~/.claude/skills/project-scaffold
```

Verify Claude can see it:

```bash
claude
/skills   # should list installed skills
```

---

## Usage

Invoke a skill at the start of a Claude Code or Claude.ai session:

```
use the project-scaffold skill to set up this project
```

Claude reads the skill file and follows its instructions.

---

## Skills

### `para-inbox`

PARA method inbox for Notion. Classifies and files any kind of input into the correct location in the PARA workspace — ideas, tasks, resources, project notes, links.

- Fetches a **live index** of the workspace structure at invocation time (no stale hardcoded maps)
- Decision tree + signal words classify input to the right pillar and sub-page automatically
- Ships with `scripts/para_index.py` — a standalone CLI for printing the full PARA tree

**Invoke with:** `"I have an idea..."`, `"remember this"`, `"file this under..."`, `"inbox this"`

---

### `project-scaffold`

Scaffolds a new project with the full two-surface development workflow:

- `CLAUDE.md` — authoritative context file Claude Code reads at session start
- `STATUS.md` — feature tracker by layer with phase exit checklist
- `DECISIONS.md` — architecture decision log (ADR format)
- `~/.claude.json` MCP config snippet (Notion, Neon, etc.)
- Notion workspace structure (Roadmap, Product Spec, Architecture, Design System)
- `MEMORY.md` pointer for Claude Code memory (optional)

**Invoke with:** `use the project-scaffold skill to set up this project`

The skill asks for project context before generating anything — no placeholders.

---

### `notion-tts`

Converts a Notion page into a spoken-word MP3 via ElevenLabs and attaches it directly to that page as an audio block. Full voice library with vibe-based selection (`"ted talk"`, `"documentary"`, `"calm"`), chunking for long pages, and a browser-based voice preview server.

**Invoke with:** `"read this page aloud"`, `"turn this Notion page into audio"`, `"make a podcast version of this"`

---

### `homelab-admin`

Full sysadmin skill for a k3s homelab cluster. Covers health checks, GitOps deployments via ArgoCD, pod troubleshooting, adding new applications, log inspection, and deprecation workflows. Knows the full cluster topology, ingress patterns, TLS setup, and the Gitea → ArgoCD push flow.

**Invoke with:** any cluster operation — `"deploy X"`, `"why is Y crashing"`, `"add a new app"`, `"check cluster health"`

---

### `job`

Deploys an unsupervised background job to GitHub Actions without tying it to your local machine. Classifies the task as a Script Worker or Agentic Runner, generates the workflow YAML (and supporting scripts), commits to the repo via `gh api`, and tracks it in the workflow inventory.

**Invoke with:** `"run this on a schedule"`, `"deploy this as a background job"`, `"run this autonomously"`

---

### `dia-tts`

Generates realistic multi-speaker dialogue audio using Dia2-1B (Nari Labs) deployed on a RunPod serverless endpoint. Supports `[S1]`/`[S2]` speaker tags, nonverbal cues `(laughs)`, `(sighs)`, etc., seeded generation for reproducibility, and voice cloning via reference WAVs. Also acts as a **TTS primitive** for other skills — call `scripts/generate.py` directly to get audio without reimplementing the RunPod API.

The `dia-tts/` directory contains both the skill definition and the full RunPod worker (Dockerfile, handler, CI/CD). See `dia-tts/README.md` for deployment instructions.

**Invoke with:** `"generate audio of this script"`, `"synthesize this dialogue"`, `"TTS this"`, `"make this into audio"`

---

### `runpod-worker`

Builds, containerizes, and deploys a RunPod serverless worker end-to-end. Covers handler scaffolding, model loading, streaming responses, network volume patterns, Dockerfile layer optimization, GitHub Actions CI/CD to GHCR, and RunPod template management via GraphQL API. Supports image generation (SDXL/FLUX/RealVisXL), TTS, and text generation workers.

**Invoke with:** `"build a RunPod worker for..."`, `"deploy this model to RunPod"`

---

### `op-vault`

Reads, creates, and manages secrets in the 1Password `claude` vault using the `op` CLI. Used directly or as a dependency by other skills that need secrets resolved at runtime.

**Invoke with:** `"get the API key from 1Password"`, `"store this in the claude vault"`, `"what's in my claude vault"`

---

### `learn-by-doing`

After completing a task, extracts what was learned and revises the relevant skill file, then re-installs. Keeps skills up to date with real-world lessons without a separate documentation step. Also triggers proactively when a task surfaces a non-obvious fix that belongs in a skill.

**Invoke with:** `"learn from that"`, `"update the skill"`, `"remember that for next time"`

---

### `update-dashboard`

Refreshes the Notion work dashboard as a weekly knowledge hub — surfaces new captures from the PARA inbox, recent ideas, research docs, and reference material created or updated this week.

**Invoke with:** `"update my dashboard"`, `"refresh my dashboard"`, `"what came in this week"`, `"weekly dashboard refresh"`

---

### `tailscale-debugger`

Diagnoses and fixes Tailscale networking issues in the catbus homelab. Covers the most common failure (asymmetric routing via `pve`'s subnet advertisement), subnet route conflicts, DNS/MagicDNS problems, and access to local-network services from the tailnet.

**Invoke with:** any Tailscale connectivity issue — services unreachable via local IP but reachable via Tailscale IP, routing weirdness, `192.168.0.x` / MetalLB `192.168.0.200` access problems

---

### `omada-debugger`

Diagnoses and fixes TP-Link Omada WiFi issues in the shaffer home network. Covers WiFi drops, sticky clients (RSSI thresholds), AP health metrics, channel interference, and range extender management. Knows the full network topology, all 3 APs, and how to use the Omada API via the `tplink-omada-client` Python library. Reads credentials from 1Password automatically.

**Invoke with:** `"wifi is dropping"`, `"clients have weak signal"`, `"disable extender"`, `"enable extender"`, `"check AP health"`, `"audit wifi clients"`

---

### `media-automation-debugger`

Debugger and ops skill for the media-automation stack on the catbus k3s cluster. Covers Sonarr, Radarr, Prowlarr, SABnzbd, NordVPN/Jackett, and the Jellyfin family-sync cron. Knows the NordVPN sidecar pattern, VPN connectivity checks, download client issues, and indexer problems. Extends `homelab-admin`.

**Invoke with:** any media stack issue — `"why isn't SABnzbd downloading"`, `"Sonarr can't find releases"`, `"Jackett indexers failing"`, `"jellyfin sync didn't run"`

---

## The Workflow Pattern

These skills are built around a two-surface AI development workflow:

| Surface | Use for |
|---|---|
| **Claude Code** (terminal) | All implementation — reads repo docs as context |
| **Claude.ai** (chat) | Architecture decisions, spec work, Notion sync |

The three repo files (`CLAUDE.md`, `STATUS.md`, `DECISIONS.md`) are the shared context that makes both surfaces consistent. Claude has no memory between sessions — these files are the memory.

For heavier projects, [Superpowers](https://github.com/obra/superpowers) extends Claude Code with structured planning via `~/.claude/plans/`. The `project-scaffold` skill assesses whether it's warranted and calls it out explicitly. Completed plans are historical artifacts — reference them in `MEMORY.md` so future sessions have context without re-executing them.

Full workflow documentation: [How I Work With Claude](https://www.notion.so/32aae77531ef8130b00ff41526fab821) (Notion)

---

## Adding a New Skill

1. Create a directory: `mkdir my-skill-name`
2. Add a `SKILL.md` with frontmatter and instructions:

```markdown
---
name: my-skill-name
description: One sentence — when should Claude use this skill? Be specific about triggers.
---

Instructions for Claude go here.
```

3. The `description` field is what Claude uses to decide when to load the skill — make it specific and action-oriented.
