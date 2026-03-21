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
