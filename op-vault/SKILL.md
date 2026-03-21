---
name: op-vault
description: >
  Read, create, and manage secrets in 1Password using the op CLI. Use this skill whenever
  the user wants to get a secret, API key, or credential from 1Password; store a new secret;
  update an existing item; list what's in a vault; or wire a 1Password secret into another
  script or workflow. Trigger on phrases like "get the API key from 1password", "store this
  in the claude vault", "read from op", "inject secrets from 1password", "what's in my
  claude vault", or any mention of 1Password alongside a secret retrieval or storage task.
  Also use this skill when another skill or script needs secrets resolved from 1Password
  before running.
---

# 1Password Vault Skill (`op-vault`)

Interact with 1Password via the `op` CLI. Covers reading secrets, creating/editing items,
listing vault contents, and injecting secrets as environment variables into subprocesses.

The default vault for this user is **`claude`**. Use it unless another vault is specified.

---

## Prerequisites

`op` must be installed and authenticated:
```bash
op --version          # confirm installed
op whoami             # confirm session is active
```

If `op whoami` returns an error, the user needs to sign in:
```bash
op signin
```
Authentication state is managed by the 1Password desktop app + CLI integration. If the
desktop app is running with CLI integration enabled (Settings → Developer → CLI), `op`
commands work without an explicit `op signin` call.

---

## Core Operations

### Read a single field

```bash
op read "op://claude/<item>/<field>"
```

The field for an API key is almost always `credential` or `password`. Check with:
```bash
op item get "<item>" --vault claude --format json | jq '.fields[] | {label:.label, value:.value}'
```

**Common field names:**
| Item type       | Typical field label |
|---|---|
| API Key         | `credential`        |
| Login           | `password`          |
| Secure Note     | `notesPlain`        |
| Custom field    | whatever you named it |

**Examples:**
```bash
# Read the ElevenLabs API key
op read "op://claude/elevenlabs-api/credential"

# Read a login password
op read "op://claude/my-service/password"

# Read a custom field named "token"
op read "op://claude/github/token"
```

### Resolve field label uncertainty

If you're unsure what field name an item uses:
```bash
op item get "<item>" --vault claude --format json \
  | python3 -c "import sys,json; [print(f['label'], '->', f.get('value','')) for f in json.load(sys.stdin)['fields'] if f.get('value')]"
```

### Inject secrets into a subprocess (preferred for scripts)

Instead of reading secrets into shell variables (which can leak to `ps`, history, etc.),
use `op run` to inject them as env vars:

```bash
op run \
  --env-file=<(echo "ELEVENLABS_API_KEY=op://claude/elevenlabs-api/credential") \
  -- python3 my_script.py
```

Or inline without a file:
```bash
ELEVENLABS_API_KEY="op://claude/elevenlabs-api/credential" \
  op run -- python3 my_script.py
```

`op run` substitutes the `op://` references with real values before exec-ing the subprocess.
The plaintext value is never in shell history or visible to `ps aux`.

### Read into a shell variable (when you need the value directly)

```bash
API_KEY=$(op read "op://claude/elevenlabs-api/credential")
```

Use with care — value is in memory but not logged if assigned this way.

---

## Create a new secret

### API key / generic credential

```bash
op item create \
  --vault claude \
  --category "API Credential" \
  --title "<item-name>" \
  "credential[password]=<value>"
```

### Login item

```bash
op item create \
  --vault claude \
  --category Login \
  --title "<item-name>" \
  --url "https://example.com" \
  "username[text]=<user>" \
  "password[password]=<pass>"
```

### Secure note

```bash
op item create \
  --vault claude \
  --category "Secure Note" \
  --title "<item-name>" \
  "notesPlain[notes]=<content>"
```

---

## Edit / update a secret

```bash
# Update a field on an existing item
op item edit "<item-name>" --vault claude "credential[password]=<new-value>"

# Add a new custom field
op item edit "<item-name>" --vault claude "my-field[text]=<value>"
```

---

## List items in the claude vault

```bash
# All items
op item list --vault claude --format json \
  | python3 -c "import sys,json; [print(i['title'], '-', i['id']) for i in json.load(sys.stdin)]"

# Just names
op item list --vault claude --format json | jq -r '.[].title'
```

---

## Delete an item

```bash
op item delete "<item-name>" --vault claude
# or archive (recoverable for 30 days):
op item delete "<item-name>" --vault claude --archive
```

---

## Secret reference URI format

```
op://<vault>/<item>/<field>
op://<vault>/<item>/<section>/<field>   # if field is in a named section
```

- Vault, item, and field names are **case-insensitive**
- Spaces in names: quote the whole URI or use the item's ID instead
- If a name is ambiguous, use the item ID (from `op item list`)

---

## `scripts/op_secret.py` — Python helper

Use this when another Python script needs to resolve a 1Password secret at runtime
without shelling out manually. See the script for usage.

```python
from op_secret import get_secret, run_with_secrets

# Get a single value
api_key = get_secret("claude", "elevenlabs-api", "credential")

# Run a function with secrets injected as env vars
run_with_secrets(
    {"ELEVENLABS_API_KEY": "op://claude/elevenlabs-api/credential"},
    my_function
)
```

---

## Error reference

| Error | Likely cause |
|---|---|
| `session expired` / `auth required` | Run `op signin` or ensure desktop app is open |
| `"X" isn't a vault` | Vault name casing or typo — run `op vault list` |
| `"X" isn't an item` | Item name mismatch — run `op item list --vault claude` |
| `no field named "X"` | Use `op item get <item> --format json` to see actual field labels |
| `op: command not found` | 1Password CLI not installed or not on PATH |
