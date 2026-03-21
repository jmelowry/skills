---
name: job
description: >
  Deploy an unsupervised background job without tying it to your local machine.
  Given a task description, classifies it as a Script Worker or Agentic Runner,
  checks for existing workflows, estimates cost if agentic, generates a GitHub
  Actions workflow (and supporting script if needed), commits everything to
  jmelowry/skills via gh api, and updates the workflow inventory.
  Use when the user wants to run something autonomously, on a schedule, on a
  trigger, or as a one-off — without babysitting it.
---

# Job Skill

Deploy unsupervised background jobs to GitHub Actions from a task description.
No local clone required. Everything commits directly to jmelowry/skills via the
GitHub API.

---

## Repo Constants

```
REPO: jmelowry/skills
WORKFLOWS_DIR: .github/workflows
SCRIPTS_DIR: scripts
INVENTORY_PATH: workflows/INVENTORY.md
```

---

## Step 1 — Read the Inventory

Before generating anything, fetch the current inventory to check for duplicates.

```bash
gh api repos/jmelowry/skills/contents/workflows/INVENTORY.md \
  --jq '.content' | base64 -d
```

Parse the markdown table. For each existing row, assess semantic similarity to
the requested task.

**If a close match is found**, stop and present it:

```
Found existing workflow: <filename>
Description: <description>
Archetype: <Script|Agentic>
Trigger: <trigger>

Options:
  [1] Run the existing workflow
  [2] Update it with new behavior
  [3] Create a new one anyway
```

Wait for the user to choose before proceeding.

**If no match**, proceed to Step 2.

---

## Step 2 — Classify the Task

Reason about the task description across these axes. Do not ask the user
clarifying questions — infer from what was provided.

### Archetype

| Signals → Script Worker | Signals → Agentic Runner |
|---|---|
| fetch, sync, transform, notify, deploy, convert, upload, check, ping | analyze, research, write, summarize, review, decide, explore, audit |
| operates on known data with known steps | requires reasoning, iteration, or unknown branching |
| output is a file, API call, or side effect | output is text, a report, or a code change |
| runtime is bounded and predictable | runtime depends on what Claude discovers |
| mentions specific tools/APIs by name | mentions "use my skills", "figure out", "however you see fit" |

When ambiguous, prefer **Script Worker** — it's cheaper and more predictable.

### Trigger Type

| Signals | Trigger |
|---|---|
| "every X hours/days", "daily", "weekly", "nightly", "on a schedule" | `schedule` (cron) |
| "when PR", "on push", "on merge", "when a file changes" | repository event |
| "run once", "now", "one-off", "manually", "on demand", no timing mentioned | `workflow_dispatch` |
| "when X happens" referencing an external system | `workflow_dispatch` + external webhook caller |

### Infer a workflow filename

Derive a short, lowercase, hyphenated name from the task.
Example: "summarize my GitHub notifications daily" → `summarize-github-notifications.yml`

Check INVENTORY.md to ensure uniqueness. Append `-2`, `-3` etc. if needed.

---

## Step 3 — Cost Estimate (Agentic Only)

If archetype is **Agentic Runner**, estimate before doing anything else.

Produce a pre-flight estimate:

```
─────────────────────────────────────
  Agentic Job Pre-flight Estimate
─────────────────────────────────────
  Task:         <one-line description>
  Model:        claude-sonnet-4-6
  Est. turns:   <N>
  Est. tokens:  ~<N> input / ~<N> output
  Est. cost:    ~$<N>
  Timeout:      <N> minutes
  Hard limits:  --max-turns <N>, token budget wrapper
─────────────────────────────────────
  Proceed? (yes / adjust / cancel)
```

Use these rough heuristics for estimation:

| Task type | Est. turns | Est. tokens |
|---|---|---|
| Simple research/summarize | 5–10 | 20k–50k |
| Code review or audit | 10–20 | 50k–100k |
| Multi-file refactor or write | 20–40 | 100k–200k |
| Open-ended exploration | 20–50 | 100k–300k |

**Do not proceed until the user confirms.** If they say "adjust", ask what budget
or turn limit they want. If they say "cancel", stop.

---

## Step 4 — Generate Workflow YAML

Use the appropriate archetype template below. Fill in all `<placeholders>`.

### Archetype A — Script Worker

```yaml
name: <Workflow Display Name>

on:
  # TRIGGER — fill in the appropriate block:

  # Option: scheduled
  schedule:
    - cron: '<cron expression>'

  # Option: manual
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Dry run (no side effects)'
        type: boolean
        default: false

  # Option: repository event
  # push:
  #   branches: [main]

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: false   # set true if runs are idempotent

jobs:
  run:
    name: <Short job description>
    runs-on: ubuntu-latest
    timeout-minutes: <N>      # keep tight — script workers should be fast

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      # RUNTIME SETUP — pick one:

      # Python
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r scripts/requirements.txt   # if needed

      # Node
      # - name: Set up Node
      #   uses: actions/setup-node@v4
      #   with:
      #     node-version: '20'

      - name: Run script
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          # Add other secrets here
        run: |
          python scripts/<script-name>.py \
            ${{ github.event.inputs.dry_run == 'true' && '--dry-run' || '' }}

      - name: Upload output
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: output-${{ github.run_id }}
          path: output/
          retention-days: 7

      - name: Job summary
        if: always()
        run: |
          echo "## Job Summary" >> $GITHUB_STEP_SUMMARY
          echo "- **Workflow:** ${{ github.workflow }}" >> $GITHUB_STEP_SUMMARY
          echo "- **Run ID:** ${{ github.run_id }}" >> $GITHUB_STEP_SUMMARY
          echo "- **Status:** ${{ job.status }}" >> $GITHUB_STEP_SUMMARY
          if [ -f output/summary.txt ]; then
            echo "### Output" >> $GITHUB_STEP_SUMMARY
            cat output/summary.txt >> $GITHUB_STEP_SUMMARY
          fi
```

---

### Archetype B — Agentic Runner

This archetype uses two jobs: a **preflight** job that posts a cost estimate and
pauses for approval, and an **agent** job that does the actual work.

```yaml
name: <Workflow Display Name>

on:
  workflow_dispatch:
    inputs:
      task_override:
        description: 'Override the default task prompt (optional)'
        type: string
        required: false
      skip_approval:
        description: 'Skip approval gate (use for low-cost tasks only)'
        type: boolean
        default: false

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: false   # never cancel a running agent mid-task

env:
  DEFAULT_TASK: |
    <default task prompt — be specific>
  MAX_TURNS: <N>
  TOKEN_BUDGET: <N>            # hard stop in tokens
  TIMEOUT_MINUTES: <N>

jobs:
  # ── Job 1: Preflight ──────────────────────────────────────────────────────
  preflight:
    name: Cost estimate & approval gate
    runs-on: ubuntu-latest
    timeout-minutes: 5
    # Skip approval gate if explicitly bypassed
    if: ${{ github.event.inputs.skip_approval != 'true' }}
    environment: agentic-approval   # requires a reviewer in repo settings

    steps:
      - name: Post pre-flight estimate
        run: |
          TASK="${{ github.event.inputs.task_override || env.DEFAULT_TASK }}"
          echo "## ⚡ Agentic Job Pre-flight" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "**Task:**" >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
          echo "$TASK" >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "| Parameter | Value |" >> $GITHUB_STEP_SUMMARY
          echo "|---|---|" >> $GITHUB_STEP_SUMMARY
          echo "| Model | claude-sonnet-4-6 |" >> $GITHUB_STEP_SUMMARY
          echo "| Max turns | ${{ env.MAX_TURNS }} |" >> $GITHUB_STEP_SUMMARY
          echo "| Token budget | ${{ env.TOKEN_BUDGET }} |" >> $GITHUB_STEP_SUMMARY
          echo "| Timeout | ${{ env.TIMEOUT_MINUTES }} min |" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "> Approve this run in the GitHub Actions UI to proceed." >> $GITHUB_STEP_SUMMARY

  # ── Job 2: Agent ──────────────────────────────────────────────────────────
  agent:
    name: Run agent
    runs-on: ubuntu-latest
    needs: [preflight]
    if: always() && (needs.preflight.result == 'success' || needs.preflight.result == 'skipped')
    timeout-minutes: ${{ fromJSON(env.TIMEOUT_MINUTES) }}

    steps:
      - name: Checkout skills repo
        uses: actions/checkout@v4
        with:
          repository: jmelowry/skills

      - name: Set up Node (for Claude Code CLI)
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install Claude Code
        run: npm install -g @anthropic-ai/claude-code

      - name: Run agent with guardrails
        id: agent_run
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          TASK: ${{ github.event.inputs.task_override || env.DEFAULT_TASK }}
        run: |
          mkdir -p output

          # Run claude with hard limits, capture output and usage
          claude -p "$TASK" \
            --max-turns ${{ env.MAX_TURNS }} \
            --output-format json \
            --no-interactive \
            2>&1 | tee output/raw.json

          # Extract token usage from output
          TOKENS_USED=$(cat output/raw.json | \
            python3 -c "
          import json, sys
          data = [json.loads(l) for l in sys.stdin if l.strip()]
          usage = next((d.get('usage', {}) for d in reversed(data) if 'usage' in d), {})
          total = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
          print(total)
          " 2>/dev/null || echo "unknown")

          echo "tokens_used=$TOKENS_USED" >> $GITHUB_OUTPUT

          # Enforce token budget
          if [ "$TOKENS_USED" != "unknown" ] && \
             [ "$TOKENS_USED" -gt "${{ env.TOKEN_BUDGET }}" ]; then
            echo "::error::Token budget exceeded: $TOKENS_USED > ${{ env.TOKEN_BUDGET }}"
            exit 1
          fi

          # Extract final text output
          cat output/raw.json | \
            python3 -c "
          import json, sys
          data = [json.loads(l) for l in sys.stdin if l.strip()]
          for d in reversed(data):
            if d.get('type') == 'result':
              print(d.get('result', ''))
              break
          " > output/result.txt 2>/dev/null || true

      - name: Upload output
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: agent-output-${{ github.run_id }}
          path: output/
          retention-days: 14

      - name: Job summary
        if: always()
        run: |
          echo "## 🤖 Agentic Job Summary" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "| Metric | Value |" >> $GITHUB_STEP_SUMMARY
          echo "|---|---|" >> $GITHUB_STEP_SUMMARY
          echo "| Status | ${{ job.status }} |" >> $GITHUB_STEP_SUMMARY
          echo "| Tokens used | ${{ steps.agent_run.outputs.tokens_used }} |" >> $GITHUB_STEP_SUMMARY
          echo "| Token budget | ${{ env.TOKEN_BUDGET }} |" >> $GITHUB_STEP_SUMMARY
          echo "| Run ID | ${{ github.run_id }} |" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          if [ -f output/result.txt ] && [ -s output/result.txt ]; then
            echo "### Result" >> $GITHUB_STEP_SUMMARY
            cat output/result.txt >> $GITHUB_STEP_SUMMARY
          fi
```

---

## Step 5 — Generate Supporting Script (Archetype A only)

If archetype is Script Worker, write the actual script the workflow runs.

The script must:
- Accept `--dry-run` flag that skips all side effects and prints what it would do
- Write any meaningful output to `output/` directory
- Write a `output/summary.txt` with 3–10 lines summarizing what happened
- Exit non-zero on failure with a descriptive message
- Be self-contained — no assumptions about the environment beyond what the
  workflow installs

Use Python unless the task is clearly shell-native (simple curl chains, file ops).

Place at: `scripts/<workflow-name-without-yml>.py`

If the script needs dependencies beyond stdlib, also generate
`scripts/requirements.txt` (or append to it if it exists — fetch current
contents via `gh api` first).

---

## Step 6 — Commit to jmelowry/skills via gh api

Commit all generated files without cloning the repo. Use `gh api` with the
contents endpoint. For each file:

**IMPORTANT — safe base64 encoding for Python scripts:**

Never use a bash heredoc or `echo` to base64-encode Python script content directly.
Shell heredocs interpret escape sequences (e.g. `\n` becomes a real newline inside a
string literal, causing `SyntaxError: unterminated string literal`).

Instead, use Python to generate the base64:

```bash
python3 -c "
import base64
script = '''<script content here>'''
print(base64.b64encode(script.encode()).decode())
" > /tmp/script_b64.txt
CONTENT=$(cat /tmp/script_b64.txt)
```

For YAML and Markdown files, heredoc + `base64 -w 0` is fine since they have no
escape-sequence ambiguity.

```bash
# Get current SHA if file exists (needed for updates)
CURRENT=$(gh api repos/jmelowry/skills/contents/<path> --jq '.sha' 2>/dev/null || echo "")

# Base64-encode the content
CONTENT=$(echo '<file content>' | base64 -w 0)

# Create or update
if [ -z "$CURRENT" ]; then
  # Create
  gh api repos/jmelowry/skills/contents/<path> \
    --method PUT \
    --field message="job: add <workflow-name>" \
    --field content="$CONTENT"
else
  # Update
  gh api repos/jmelowry/skills/contents/<path> \
    --method PUT \
    --field message="job: update <workflow-name>" \
    --field content="$CONTENT" \
    --field sha="$CURRENT"
fi
```

**Commit order:**
1. `scripts/<name>.py` (if Archetype A)
2. `scripts/requirements.txt` (if Archetype A and dependencies needed)
3. `.github/workflows/<name>.yml`
4. `workflows/INVENTORY.md` (always last)

All files in a single logical batch with consistent commit messages prefixed
`job:`.

---

## Step 7 — Update INVENTORY.md

Fetch the current inventory, append a new row, and commit it.

Inventory format:

```markdown
# Workflow Inventory

| Workflow | Archetype | Trigger | Description | Est. Cost | Created |
|---|---|---|---|---|---|
| [name.yml](.github/workflows/name.yml) | Script | schedule `0 9 * * 1` | Brief description | — | YYYY-MM-DD |
| [name.yml](.github/workflows/name.yml) | Agentic | workflow_dispatch | Brief description | ~$0.05/run | YYYY-MM-DD |
```

Rules:
- Description: one line, plain English, what it does not how
- Est. Cost: `—` for Script workers (negligible), `~$X/run` for Agentic
- Never delete rows — mark removed workflows as `~~strikethrough~~` in the
  Workflow column

---

## Step 8 — Offer Immediate Dispatch

After committing, if the trigger is `workflow_dispatch`:

```
✓ Workflow committed: .github/workflows/<name>.yml
✓ Inventory updated

Run it now?
  [1] Yes — gh workflow run <name>.yml
  [2] No — I'll trigger it manually
```

If yes:
```bash
gh workflow run <name>.yml --repo jmelowry/skills
```

For Agentic workflows, remind:
```
Note: This will hit the approval gate first. Check the Actions tab
in jmelowry/skills to approve the run.
```

---

## Guardrail Reference

Default limits by task complexity. Override at Step 3 if user adjusts:

| Complexity | Max Turns | Token Budget | Timeout |
|---|---|---|---|
| Simple (research, summarize) | 10 | 50,000 | 15 min |
| Medium (audit, review, write) | 20 | 100,000 | 30 min |
| Complex (multi-file, explore) | 40 | 200,000 | 60 min |
| Uncapped (explicitly requested) | 80 | 400,000 | 120 min |

Always set `timeout-minutes` on the job as the hard backstop regardless of
token tracking.

---

## Deployment Target Stubs

The following targets are not yet implemented. When a user asks to deploy to
one of these, explain it's on the roadmap and fall back to GitHub Actions.

See `deployment-targets/` for stub files.

### Cloudflare Workers

Appropriate for: lightweight script workers that need HTTP triggers, sub-100ms
latency, or global edge distribution. Deployed via `wrangler deploy`.

Status: **stub** — see `deployment-targets/cloudflare.md`

### Modal

Appropriate for: Python-heavy agents, tasks needing GPU, or workflows that
benefit from Modal's per-second billing and Python decorator DX.

Status: **stub** — see `deployment-targets/modal.md`

### Railway

Appropriate for: persistent workers that need to stay alive between runs,
or agents that need a long-lived process model.

Status: **stub** — see `deployment-targets/railway.md`

---

## Output Checklist

Before finishing, confirm:
- [ ] Inventory checked — no duplicate workflow exists (or user chose to proceed)
- [ ] Archetype classified and stated to user
- [ ] Trigger type inferred and stated to user
- [ ] If Agentic: cost estimate shown and confirmed before any generation
- [ ] Workflow YAML generated from correct archetype template
- [ ] If Script: supporting script generated with `--dry-run` support
- [ ] All files committed via `gh api` to `jmelowry/skills`
- [ ] INVENTORY.md updated as last commit
- [ ] If `workflow_dispatch`: offered immediate dispatch
- [ ] Secrets checklist shown to user (what needs to be added to repo settings)

---

## Secrets Checklist Template

Always show this after committing:

```
Secrets required in jmelowry/skills → Settings → Secrets and variables → Actions:

  ANTHROPIC_API_KEY     — always required for Agentic workflows
  <OTHER_SECRET>        — required for <step>

GitHub Environment required (Agentic only):
  agentic-approval      — create at Settings → Environments
                          Add yourself as a required reviewer
```
