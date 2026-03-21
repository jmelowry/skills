---
name: update-dashboard
description: >
  Refreshes the Notion work dashboard as a weekly knowledge hub — surfaces new captures
  from the PARA inbox, recent ideas, research docs, and reference material created or
  updated this week. Use when the user says "update my dashboard", "refresh my dashboard",
  "what came in this week", "weekly dashboard refresh", "sync my dashboard", or
  "update the Q[N] dashboard". Also trigger when the user wants a view of what's been
  captured recently across their Notion workspace.
compatibility:
  tools: [notion-mcp]
  mcp: [claude_ai_Notion]
---

# Update Dashboard Skill

The work dashboard is a **weekly knowledge hub** — a curated view of what came in this
week across the PARA workspace: new ideas captured, research filed, inbox items, docs
worth acting on. This skill populates that view by scanning recent activity across the
PARA system and surfacing it on the dashboard.

---

## Known Locations

| Location | Notion ID |
|---|---|
| Areas > airbnb (dashboard parent) | `48f008ec-6e59-4ead-bd3c-55177b4cdb47` |
| Areas > ideas | `a4c6501e-7775-4284-b866-e1d7c3986651` |
| Resources > Technical Reference | `91f68da9-8394-4224-b88c-4d3389ce9ae6` |
| Resources > Ai | `4680bdb0-2646-4f77-a356-0efe5f69a69f` |
| 1. Projects (root) | `f09305c7-1857-4d97-83ef-cc240b03e2e2` |
| 2. Areas (root) | `8d27c2d1-93ae-4d42-ab48-27b067a343e2` |
| 3. Resources (root) | `d49ac77b-8397-43b3-a0df-7b61b17d7c21` |

---

## Step 1 — Find the Dashboard

Fetch the `airbnb` page to find the current quarter dashboard. It will be titled
`🎯 Q[N] [YEAR] Dashboard`. Fetch it to read its current state.

---

## Step 2 — Scan for Recent Activity

Search Notion for pages created or modified **this week** (last 7 days). Run these
searches in parallel using `notion-search`:

```
notion-search("", filters: { created_date_range: { start_date: <7 days ago> } })
```

Also fetch the children of these PARA sections to spot recently added pages:
- `Areas > ideas` — any new ideas captured this week
- `Resources > Technical Reference` — new research / architecture docs
- `Resources > Ai` — new AI-related reference material
- Active project pages (from `1. Projects`) that were recently updated

Group the results by type:

| Type | Signal |
|---|---|
| **💡 Ideas** | Pages under `Areas > ideas` created this week |
| **📖 Research / Reference** | Pages under `Resources` created this week |
| **🗒️ Project Notes** | Pages under active Projects modified this week |
| **📥 Inbox captures** | Any other pages created this week across PARA |

---

## Step 3 — Update the Dashboard

Use `notion-update-page` with `update_content` to refresh the **"This Week"** section
on the dashboard. If the section doesn't exist yet, add it after the Top 4 section.

### "This Week" section format

```markdown
## 📅 This Week — [Mon DD] to [Sun DD]

### 💡 New Ideas
- [Page title](url) — one-line summary if content is short enough to infer
- ...

### 📖 Research & Reference
- [Page title](url)
- ...

### 🗒️ Project Updates
- [Page title](url) — what changed (if inferable from content)
- ...

### 📥 Other Captures
- [Page title](url)
- ...
```

Rules:
- Link every item directly to its Notion page
- Include a one-line summary only if you can infer it confidently from the title or first line — don't fabricate
- If a category has no new items, omit it entirely (don't show empty sections)
- Replace the previous week's content — don't accumulate multiple weeks in the same section
- Keep the rest of the dashboard intact (Project Trackers, To Do Daily, links callout, etc.)

---

## Step 4 — Project Tracker Sync (lightweight)

While you have the dashboard open, scan the **Project Trackers** table for any rows
that look stale (status is 🟡 or 🔴 for several weeks with no update). Flag these to
the user:

> "I noticed [project] has been 🟡 for a while — want to update its status?"

Don't auto-update statuses. Just surface them for the user to decide.

---

## Step 5 — To Do Daily Triage

Scan the **To Do Daily** checklist:
- If there are more than 3 checked `- [x]` items, offer to clear them
- If total open items exceeds 10, flag it: "You have [N] open to-dos — want to triage?"

Don't auto-clear or auto-remove unless the user says so.

---

## Step 6 — Confirm

Report back in 4–6 lines:
- How many items were surfaced this week (by category)
- Link to the updated dashboard
- Any stale project statuses flagged
- Any to-do list flags

---

## Quarter Rollover

If the current date is within 2 weeks of quarter end (Q1: Mar 31, Q2: Jun 30, Q3: Sep 30,
Q4: Dec 31):

1. Flag it: *"Q[N] ends in [X] days — want me to scaffold the Q[N+1] dashboard?"*
2. If yes: create a new page under `Areas > airbnb` titled `🎯 Q[N+1] [YEAR] Dashboard`
3. Carry over: meeting schedule, active (non-complete) projects in the tracker
4. Clear: To Do Daily, This Week section, Q[N] timeline
5. Leave the old dashboard in place (don't archive it automatically)

---

## Edge Cases

- **No pages created this week**: report that and ask if they want to look at the last 2 weeks instead
- **Dashboard not found**: search `Areas > airbnb` for any page with "Dashboard" in the title
- **"This Week" section already exists**: replace its content, don't append
- **Same page shows up in multiple categories**: pick the most specific one (ideas > resources > other)
- **User says "just do it"**: run the full refresh without asking for input — surface everything you find and apply the update
