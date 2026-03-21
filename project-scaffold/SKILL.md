---
name: project-scaffold
description: Scaffold a new software project with the Claude.ai + Claude Code + Notion workflow. Use when starting a new project and wanting to establish the three-file repo context system (CLAUDE.md, STATUS.md, DECISIONS.md), Notion workspace structure, and Claude Code MCP configuration. Produces all files ready to commit and a Notion workspace ready to use.
---

This skill scaffolds a new project using the two-surface development workflow:
- **Claude.ai** — architecture, decisions, spec work, Notion sync
- **Claude Code** — implementation, with repo docs as authoritative context

The user provides project context: name, stack, current phase, team structure. Claude produces the full scaffold.

This is an entrypoint skill — it establishes the context that downstream skills depend on. For heavier projects, it will recommend and configure [Superpowers](https://github.com/obra/superpowers), whose skills (planning, implementation, testing, etc.) pick up where this one leaves off. The scaffold is what makes those skills effective.

---

## Step 1 — Gather Context

Before generating anything, collect:

1. **Project name and one-line description**
2. **Stack** — language, framework, hosting, DB, key third-party services
3. **Monorepo structure** — top-level directories and what lives in each
4. **Current phase** — what's being built right now, what's done, what's next
5. **Team structure** — solo, coder + PM, full team? Who implements vs. who directs?
6. **Key constraints** — decisions already made that should never be re-litigated

If any of these are missing, ask before proceeding. Do not generate placeholder content — every field should reflect the actual project.

Based on the answers, assess whether the project warrants the [Superpowers](https://github.com/obra/superpowers) Claude Code plugin. Use it for:
- Apps or services with meaningful coupling between components
- Work that requires architecture planning, tests, or multi-step implementation
- Anything where getting it wrong is costly to unwind

Skip it for quick scripts, patches, or standalone utilities where the overhead isn't worth it. Call this out explicitly in the scaffold so the user knows what was decided and why.

---

## Step 2 — Generate Repo Files

Produce three files at repo root. These are the authoritative context for all Claude Code sessions.

### CLAUDE.md

The entry point Claude Code reads at session start. Include:

```
# <Project Name> — Claude Code Context

> Authoritative context file. Read STATUS.md and DECISIONS.md before writing any code.
> Do not contradict decisions in DECISIONS.md without explicitly flagging the conflict.

## What This Is
<one paragraph: what the product is, who it's for, what makes it different>

## Stack (non-negotiable)
| Layer | Tech |
...

## Monorepo Structure
<directory tree with one-line descriptions>

## Current Phase: <Phase Name>
**Goal:** <what this phase validates or delivers>
**Exit criteria:**
- <measurable criterion>
...
**Do not start <Next Phase> work until exit criteria are met.**

## Architecture Notes
<key technical decisions that affect day-to-day coding — model choices, queue patterns, API design, etc.>

## Key Constraints
<bullet list of hard constraints — things that are decided and should not be re-litigated>

## Context Maintenance Protocol

| Surface | Tools | Use for |
|---|---|---|
| Claude Code (terminal) | Filesystem, shell, [MCP servers] | All implementation |
| Claude.ai (chat) | Notion, web search, [MCP servers] | Architecture, decisions, doc updates |

**Rules:**
- CLAUDE.md, STATUS.md, DECISIONS.md are canonical.
- If Claude Code proposes something that contradicts DECISIONS.md, stop and resolve in Claude.ai first.
- When work ships, update STATUS.md. When an architectural decision is made, append to DECISIONS.md.
- Do this before closing the session.
```

### STATUS.md

Feature tracker. Organized by layer (backend, workers, frontend, infra). Include:

```
# <Project Name> — Feature Status
> Update when work ships, not after.
Last updated: <date>

## Status Key
✅ Shipped | 🔧 In progress | 📋 Planned | 🔜 Deferred | ❓ Unclear

## <Layer>
| Feature | Status | Notes |
...

## Open Questions
- <unresolved items that block work>

## Phase <N> Exit Checklist
- [ ] <criterion>
...

## Cleanup Tasks
| Task | Priority | Notes |
...
```

### DECISIONS.md

Architecture decision log. Seed with any decisions already made. Template for each entry:

```
### <NNN> — <Short title>
**Date:** YYYY-MM-DD
**Status:** Active | Superseded by #NNN
**Context:** What forced the decision.
**Decision:** What was decided.
**Rationale:** Why.
**Consequences:** What this forecloses or opens up.
```

Seed with at minimum:
- Stack choices (why this framework, why this DB, why this hosting)
- Any approaches that were evaluated and ruled out
- Any constraints that came from external factors (licensing, API availability, etc.)

---

## Step 3 — Configure Claude Code MCP

Produce a `~/.claude.json` snippet (not a file to commit — reference only) for any MCP servers the project needs.

Standard servers to consider:
- **Notion** — always include if Notion is the project hub
- **Neon** — include if using Neon Postgres (enables live schema inspection in Claude Code)
- **GitHub** — include if Claude Code should be able to read/create issues or PRs

```json
{
  "mcpServers": {
    "notion": {
      "type": "url",
      "url": "https://mcp.notion.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_NOTION_INTEGRATION_TOKEN"
      }
    },
    "neon": {
      "type": "url",
      "url": "https://mcp.neon.tech/sse",
      "headers": {
        "Authorization": "Bearer YOUR_NEON_API_KEY"
      }
    }
  }
}
```

Note: `~/.claude.json` stores tokens in plaintext. Confirm it's in `.gitignore` before proceeding.

Verify with:
```bash
claude
/mcp   # should list connected servers
```

---

## Step 4 — Create Notion Workspace

Create the following pages under a root project page in Notion. Use the Notion MCP if available; otherwise provide the content for manual creation.

### Root page
Title: `<Project Name>`
Icon: appropriate emoji for the project type

### Child pages to create:

**🗺️ Roadmap**
Phases ordered by dependency. Each phase has:
- Goal callout block
- Checklist of items ([ ] not started, [x] done)
- Exit criteria
- Status indicator in the title (⚠️ IN PROGRESS, ✅ SHIPPED, 🔒 SCOPED, etc.)

**📋 Product Spec**
User stories organized by epic. Format:
```
## Epic N — <Name>
**Goal:** <what this epic delivers to the user>
US-NNN — As a <user>, I want to <action> so that <outcome>.
  - Acceptance criteria
```

**🏗️ Architecture**
- Stack overview table
- Key architectural diagrams or descriptions
- Integration map (what talks to what)
- Pointer to DECISIONS.md in repo for the full ADR log

**🎨 Design System** (if applicable)
- Color tokens
- Typography
- Component inventory
- Interaction patterns

---

## Step 5 — MEMORY.md for Claude Code (optional)

If the project uses Claude Code's memory system (`~/.claude/projects/.../memory/`), create a `MEMORY.md` that is a **pointer only** — not a parallel source of truth:

```markdown
# <Project Name> — Claude Code Memory

> Repo docs are canonical. This file is a pointer.
> Read CLAUDE.md, STATUS.md, and DECISIONS.md at the start of every session.

## Repo location
<path to repo>

## Key page IDs (Notion)
- Root: <page_id>
- Roadmap: <page_id>
- Product Spec: <page_id>

## Superpowers plans (historical)
<!-- Superpowers (https://github.com/obra/superpowers) stores plans in ~/.claude/plans/.
     List completed plans here as historical artifacts — so future sessions have context
     without re-executing them. -->
<list any ~/.claude/plans/ files and what they implemented — for reference only>
```

---

## Step 6 — Session Kickoff Template

Produce a standard session opener the user can paste into Claude Code at the start of any new session:

```
Read CLAUDE.md, STATUS.md, and DECISIONS.md before we start.
Today's goal: <fill in>
```

And for Claude.ai sessions that need Notion sync:

```
Check STATUS.md and the Notion Roadmap — are they in sync?
Flag any drift and update both if needed.
```

---

## Output Checklist

Before finishing, confirm:
- [ ] CLAUDE.md has real stack, real phase, real constraints — no placeholders
- [ ] STATUS.md has at least one row per shipped feature and one exit checklist
- [ ] DECISIONS.md has at least 3 seeded decisions
- [ ] MCP config snippet produced with correct server URLs
- [ ] Notion workspace created or content produced for manual creation
- [ ] MEMORY.md produced if Claude Code memory is in use
- [ ] User reminded to add `~/.claude.json` to `.gitignore`
