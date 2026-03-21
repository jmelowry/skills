---
name: para-inbox
description: >
  PARA method inbox for Notion. Classifies and files any kind of input — ideas, tasks, resources,
  project notes — into the correct location in the PARA workspace. Use when the user says "I have
  an idea", "remember this", "I want to save this resource", "file this under", "log this task",
  "add a note about", "don't let me forget", or any phrasing that implies capturing something for
  later use. Also trigger when the user says "inbox this", "PARA this", or "file this".
compatibility:
  tools: [notion-mcp]
  mcp: [claude_ai_Notion]
---

# PARA Inbox Skill

Files user input into the correct location in the Notion PARA workspace. Always fetches a live
index of the workspace structure before deciding where to file — never rely on cached or hardcoded
sub-page lists (they change).

---

## PARA Root Pages (stable anchors)

These four page IDs are fixed. Fetch their children live at the start of every invocation.

| PARA Pillar | Notion Page ID | Emoji |
|---|---|---|
| Projects | `f09305c7-1857-4d97-83ef-cc240b03e2e2` | ☑️ |
| Areas | `8d27c2d1-93ae-4d42-ab48-27b067a343e2` | ⚙️ |
| Resources | `d49ac77b-8397-43b3-a0df-7b61b17d7c21` | 📚 |
| Archive | `ff86dbac-6f45-4225-be8d-79514346de9f` | 🗄️ |

---

## Step 1 — Build a Live Index

Before filing anything, fetch the children of the relevant PARA root(s) using `notion-fetch`.
For ambiguous inputs, fetch all four. For clear inputs (e.g., "I have an idea" → Areas only),
fetch just the relevant root to stay fast.

```
notion-fetch("f09305c7-1857-4d97-83ef-cc240b03e2e2")  → live list of Projects sub-pages
notion-fetch("8d27c2d1-93ae-4d42-ab48-27b067a343e2")  → live list of Areas sub-pages
notion-fetch("d49ac77b-8397-43b3-a0df-7b61b17d7c21")  → live list of Resources sub-pages
notion-fetch("ff86dbac-6f45-4225-be8d-79514346de9f")  → live list of Archive sub-pages
```

The response lists all child pages with their titles and URLs. Use these to find the best
destination. Never assume a sub-page exists — always verify from the live fetch.

For an even faster full index (useful when destination is ambiguous), run the index script:

```bash
python scripts/para_index.py
```

This prints a compact PARA tree to stdout in ~2 seconds using the Notion API directly.

---

## Step 2 — Classify the Input

Use the following rules to choose the PARA pillar and sub-page:

### PARA Pillar Decision Tree

```
Is this something with a defined outcome you're actively working toward?
  → Projects

Is this an ongoing responsibility, interest, or habit with no end date?
  → Areas
    Is it a fleeting idea, half-formed thought, or creative spark?
      → Areas > ideas
    Is it a task or to-do that fits an existing Area?
      → Areas > Personal Tasks (database) or the most relevant Area sub-page
    Does it fit an existing area topic (health, homelab, kids, investing, etc.)?
      → Areas > [matching sub-page]

Is this reference material — something you'd look up later, not act on now?
  → Resources
    Technical (code, systems, tools, docs)?  → Resources > Technical Reference
    Career/professional?                     → Resources > Career
    AI-related?                              → Resources > Ai
    Links/bookmarks?                         → Resources > My links or Links (db)
    Other?                                   → Resources > [closest match]

Is this complete, inactive, or something you want to preserve but no longer act on?
  → Archive
```

### Signal Words

| Signal | Filing Destination |
|---|---|
| "idea", "what if", "I was thinking", "concept" | Areas > ideas |
| "task", "to-do", "I need to", "remind me to" | Areas > Personal Tasks |
| "note on", "log this", "keep track of" | Most relevant Area sub-page |
| "resource", "link", "article", "bookmark", "reference" | Resources > closest match |
| "project", "I'm building", "I want to start" | Projects > Active or Ideation |
| "archive", "done with", "wrap up", "no longer" | Archive |
| "learn", "study", "practice" | Areas > Personal Learning |
| "write", "essay", "draft" | Areas > Writing |
| "health", "fitness", "workout" | Areas > Health & Fitness |
| "homelab", "cluster", "k3s" | Areas > Homelab |

---

## Step 3 — Create the Page

Once the destination is identified, create a new page using `notion-create-pages`.

### Page Creation Rules

- **Parent**: the destination sub-page (or PARA root if no sub-page fits)
- **Title**: extract a clean, concise title from the user's input (4–8 words)
- **Body**: the user's full input, lightly formatted — preserve their words, don't paraphrase
- **Date**: add today's date as a callout block or `Created: YYYY-MM-DD` line if relevant
- **No extra structure**: don't add headers, tags, or metadata the user didn't ask for

### For database destinations (Personal Tasks, My links, Links):

Use `notion-create-pages` with the database as parent. Match the database schema:
- **Personal Tasks**: set the `Name` property; optionally set due date if user specified one
- **Links / My links**: set `Name` + `URL` properties from the user's input

### Confirm before creating (only if ambiguous):

If the classification is genuinely unclear, show the user the proposed destination and ask:
> "I'd file this under **[Pillar > Sub-page]** — does that work, or somewhere else?"

For unambiguous inputs (e.g., "I have an idea about X"), create immediately without asking.

---

## Step 4 — Confirm to User

After creating, report back:
- Where it was filed: `Areas > ideas`
- The page title
- A direct Notion link to the new page

Keep it to 2–3 lines. Don't summarize the content back to the user.

---

## Known Sub-Page IDs (current — verify via live fetch if uncertain)

These are provided as a speed reference. Always prefer the live index over these.

| Sub-page | Page ID |
|---|---|
| Areas > ideas | `a4c6501e-7775-4284-b866-e1d7c3986651` |
| Areas > Personal Tasks (db) | `c69bf023-0068-4ded-9bb6-d6adf5140f97` |
| Areas > Personal Learning | `179ae775-31ef-803d-bf71-c4e0195268b2` |
| Areas > Writing | `fa64717e-9ad3-47e6-9d07-c85416249ef0` |
| Areas > Health & Fitness | `59cab64e-7262-4097-aab0-f15b6e72f17a` |
| Areas > Homelab | `11dae775-31ef-804f-a409-e539f453d0fa` |
| Areas > investing | `71fbbd6d-267e-40e5-a6ea-0a18c23aa5c5` |
| Areas > AI | `191ae775-31ef-80a8-972f-d9d4cdc67d1a` |
| Areas > Job Search | `248ae775-31ef-802d-b0f1-cb495c371ba6` |
| Areas > Kids | `1cfae775-31ef-8071-a019-ddb6183337f7` |
| Areas > Marriage | `1cfae775-31ef-80d0-b31c-e34126870444` |
| Resources > Technical Reference | `91f68da9-8394-4224-b88c-4d3389ce9ae6` |
| Resources > Career | `3f36f5dd-3765-4dd9-b5ed-23452c262e48` |
| Resources > Ai | `4680bdb0-2646-4f77-a356-0efe5f69a69f` |
| Resources > Goals | `5e33e5b1-1351-4328-9599-ff54575a767e` |
| Projects root | `f09305c7-1857-4d97-83ef-cc240b03e2e2` |

---

## Edge Cases

- **"Add to [specific page]"**: The user names a destination explicitly — skip classification, use it
- **Multiple items in one message**: File each separately, confirm all destinations at once
- **New topic with no matching sub-page**: Create the page under the PARA root directly (don't invent sub-pages)
- **Already exists check**: Don't search for duplicates unless the user says "if it doesn't already exist"
- **Private pages**: If a `notion-create-pages` call fails with 403, tell the user the page needs to be shared with the integration
