---
name: learn-by-doing
description: >
  After completing a task, extract what was learned and revise the relevant skill file
  in /Users/jamie/github.com/skills, then re-run install.sh to apply the update.
  Use when the user says "learn from that", "update the skill", "remember that for next time",
  "learn by doing", or any phrasing that implies capturing a lesson from just-completed work
  and baking it back into a skill. Also trigger proactively when a task surfaces a non-obvious
  fix or workaround that belongs in a skill (e.g. a bug was hit and fixed mid-skill).
---

# Learn-by-Doing Skill

After a task completes, extract the lesson and revise the relevant skill so future runs
don't repeat the same mistake or rediscover the same non-obvious technique.

---

## When to Use

Trigger on explicit requests:
- "learn by doing", "learn from that", "update the skill with that"
- "remember this for next time", "bake that into the skill"
- "if you learned anything, update the skill"

Trigger proactively (without being asked) when:
- A task hit a bug mid-execution that required a fix to the skill's own instructions
- A workaround was discovered that the skill should have known about
- A step in a skill produced wrong output and had to be redone

Do NOT trigger for:
- Lessons that are already documented in the skill
- Project-specific one-offs that don't generalize
- Preferences or feedback that belong in memory (use memory system instead)

---

## Step 1 — Identify the Skill to Update

Review what just happened and identify which skill file is responsible.

Skills live at: `/Users/jamie/github.com/skills/<skill-name>/SKILL.md`

List available skills:
```bash
ls /Users/jamie/github.com/skills/
```

If the lesson spans multiple skills, update each one separately.

If the lesson is about general Claude Code behavior (not a specific skill), save it
as a feedback memory instead and stop.

---

## Step 2 — Extract the Lesson

Before editing, clearly articulate:

1. **What went wrong or what was non-obvious** — the specific failure or gap
2. **What the fix or correct approach is** — the new knowledge
3. **Where it belongs in the skill** — which section or step should carry this

Good lessons to capture:
- A shell/scripting pitfall that caused a failure (e.g. heredoc escape handling)
- An API behavior that wasn't obvious (e.g. field name, required header)
- A required ordering of steps that the skill didn't make clear
- A prerequisite check that should happen before proceeding

Not worth capturing:
- "It worked fine" — no lesson
- One-time environmental issues (network blips, auth expiry)
- Things already covered in the skill

---

## Step 3 — Read the Current Skill

```bash
cat /Users/jamie/github.com/skills/<skill-name>/SKILL.md
```

Identify the right section to insert or amend. Prefer:
- Adding a clearly-labeled warning or note near the affected step
- Updating an example to show the correct approach
- Adding a new subsection if the lesson is substantial

Keep edits **minimal and surgical** — don't rewrite sections that didn't need changing.

---

## Step 4 — Edit the Skill File

Use the Edit tool to make the targeted change.

**Formatting conventions:**
- Use `**IMPORTANT —` prefix for critical gotchas that prevent failures
- Use `> Note:` blockquotes for tips and non-critical improvements
- Keep new content in the same style and voice as the surrounding text
- Don't add a "Changelog" section — edits speak for themselves

**Example of a good addition:**

```markdown
**IMPORTANT — safe base64 encoding for Python scripts:**

Never use a bash heredoc to base64-encode Python script content.
Shell heredocs interpret `\n` as a real newline inside string literals,
causing `SyntaxError: unterminated string literal`.

Instead, use Python to generate the base64:
\`\`\`bash
python3 -c "import base64; ..." > /tmp/b64.txt
\`\`\`
```

---

## Step 5 — Reinstall

After editing, run install.sh to apply the change:

```bash
bash /Users/jamie/github.com/skills/install.sh
```

Confirm the skill name appears in the output.

---

## Step 6 — Commit and Push

Commit the updated skill directly to main and push. No PR needed for skill updates.

```bash
cd /Users/jamie/github.com/skills
git add <skill-name>/SKILL.md
git commit -m "learn: <one-line description of what was learned>"
git push
```

Commit message format: `learn: <skill-name> — <what was added in plain English>`

Example: `learn: job — warn against bash heredoc for base64-encoding Python scripts`

---

## Step 7 — Report to User

Tell the user:
- Which skill was updated
- What was added (one sentence)
- Confirm the skill was reinstalled and pushed

Keep it brief. No need to quote the full diff.

Example:
```
Updated job/SKILL.md: added warning about using Python (not bash heredoc)
to base64-encode Python scripts. Reinstalled and pushed to main.
```

---

## Guardrails

- Never delete existing content from a skill — only add or amend
- Never add speculative lessons ("this might also be useful someday")
- If unsure whether something belongs in the skill vs. memory, prefer memory
- If the skill's SKILL.md frontmatter `description` field no longer accurately
  covers the skill's scope after the edit, update it too
