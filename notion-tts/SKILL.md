---
name: notion-tts
description: >
  Convert any referenced Notion page into a spoken-word audio file using the ElevenLabs TTS API,
  then attach the resulting MP3 directly to that Notion page as a file block. Use this skill
  whenever the user says things like "read this page aloud", "turn this Notion page into audio",
  "generate a TTS for this page", "make a podcast version of this", "attach audio to this Notion
  page", or any phrasing that combines Notion content with speech/audio generation. Also trigger
  when the user provides a Notion URL or page ID and asks for any kind of audio output.
compatibility:
  tools: [bash]
  env:
    - ELEVENLABS_API_KEY     # ElevenLabs API key
    - NOTION_API_KEY         # Notion integration token (needs read + file upload + block append)
  python_deps: [requests]    # stdlib only otherwise
---

# Notion → TTS Skill

Converts a Notion page's text content into a high-quality MP3 via ElevenLabs, then uploads and
attaches it to that same page using Notion's File Upload API.

---

## Workflow

```
Notion page  ──fetch──▶  extract text  ──chunk──▶  ElevenLabs TTS
                                                          │
                                                      MP3 bytes
                                                          │
                                          Notion File Upload (3-step)
                                                          │
                                          append Audio block to page ✓
```

### Step 1 — Resolve the page

Accept any of:
- Full URL: `https://www.notion.so/workspace/Page-Title-<id>` → extract the last 32-char hex
- Short URL: `https://notion.so/<id>`
- Raw page ID (with or without hyphens)

Normalize to hyphenated UUID format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### Step 2 — Fetch and extract page text

Use `GET https://api.notion.com/v1/blocks/{page_id}/children?page_size=100` with
`Authorization: Bearer $NOTION_API_KEY` and `Notion-Version: 2022-06-28`.

Recursively follow `has_children: true` blocks (up to 3 levels deep is sufficient for most pages).

**Text extraction per block type:**

| Block type | Extraction |
|---|---|
| `paragraph`, `quote`, `callout` | `.rich_text[*].plain_text` joined |
| `heading_1/2/3` | `.rich_text[*].plain_text` joined |
| `bulleted_list_item`, `numbered_list_item`, `to_do` | `.rich_text[*].plain_text` joined |
| `code` | Skip (or include with "Code block:" prefix if user wants it) |
| `divider` | Emit a short pause via ". " |
| `child_page`, `child_database` | Skip (don't recurse into sub-pages) |
| `image`, `file`, `video`, `audio` | Skip |
| `toggle` | Extract the toggle text; recurse into children |

Strip markdown-style formatting artifacts. Collapse multiple blank lines. Result should read
naturally when spoken.

> **Long pages:** If extracted text exceeds ~4500 characters (~1500 tokens, ~3 min audio),
> consider chunking — see "Chunking" section below.

### Step 3 — Resolve voice

**Never hardcode a voice ID.** Always resolve via `voice_selector.py`.

The `--voice` argument accepts any of:
- A **vibe keyword**: `"ted talk"`, `"documentary"`, `"calm"`, `"podcast"`, etc.
- A **voice name**: `"Matilda"`, `"Daniel"`, `"Bella"`, etc.
- A **raw voice_id** (20-25 char alphanumeric) — used as-is

Resolution order in `voice_selector.py`:
1. Raw voice_id → pass through
2. Exact name match in `voices.json` cache (live IDs)
3. Exact name match in hardcoded fallbacks
4. Longest matching vibe alias keyword
5. Label/description scoring against cache (fuzzy match)
6. Fallback to default (Matilda)

**Default voice:** `Matilda` — warm, approachable, neutral American female.
Good for reading documentation, notes, or reference content.

**Common vibe → voice mappings:**

| Vibe keyword(s) | Voice | Character |
|---|---|---|
| `assistant`, `neutral`, `default` | Matilda | Warm neutral assistant |
| `ted talk`, `presentation`, `keynote` | Bella | Confident, forward-leaning |
| `documentary`, `narration` | Daniel | Deep authoritative British male |
| `audiobook`, `book` | George | Warm British male, long-form |
| `podcast`, `conversational` | Liam / Josh | Bright and casual |
| `storytelling`, `irish` | Fin | Natural Irish cadence |
| `authoritative`, `news` | Arnold | Commanding American male |
| `calm`, `gentle` | Charlotte / Dorothy | Soft, measured delivery |
| `warm`, `friendly` | Freya | Inviting American female |
| `british` | George | Friendly British male |
| `deep` | Adam | Resonant American male |

Run `python scripts/voice_selector.py` with no args to see the full list.

**Keeping voice IDs current:**
```bash
# Refresh the local cache of all ElevenLabs voices
python scripts/list_voices.py --refresh

# Search voices by keyword
python scripts/list_voices.py --search british

# See vibe → voice matches for the current catalog
python scripts/list_voices.py --vibes

# Test vibe resolution
python scripts/voice_selector.py "calm documentary"
```

The `voices.json` cache auto-expires after 24 hours. If a voice name or ID
returns a 400 from ElevenLabs, run `list_voices.py --refresh` to get current IDs.

### Step 4 — Generate TTS via ElevenLabs

**Endpoint:** `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`

**Headers:**
```
xi-api-key: $ELEVENLABS_API_KEY
Content-Type: application/json
Accept: audio/mpeg
```

**Body:**
```json
{
  "text": "<extracted text>",
  "model_id": "eleven_multilingual_v2",
  "output_format": "mp3_44100_128",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75
  }
}
```

**Default voice:** `21m00Tcm4TlvDq8ikWAM` (Rachel) — a neutral, clear reading voice.
If the user specifies a different voice by name or ID, use that instead. To list available
voices: `GET https://api.elevenlabs.io/v1/voices`.

Response body is raw MP3 bytes — write directly to a temp file.

### Step 4 — Upload to Notion (3-step)

#### 4a. Create the upload object
```
POST https://api.notion.com/v1/file_uploads
{
  "filename": "<page-title>.mp3",
  "content_type": "audio/mpeg"
}
```
Response contains `id` (the file_upload ID) and `upload_url`.

#### 4b. Send the file bytes
```
POST <upload_url>
Content-Type: multipart/form-data
  file: <mp3 bytes>
```
Response `status` should become `"uploaded"`.

#### 4c. Attach as audio block on the page
```
POST https://api.notion.com/v1/blocks/{page_id}/children
{
  "children": [
    {
      "object": "block",
      "type": "audio",
      "audio": {
        "type": "file_upload",
        "file_upload": { "id": "<file_upload_id>" }
      }
    }
  ]
}
```

The file becomes a permanent part of the workspace once attached.

---

## Chunking (long pages)

ElevenLabs has a practical ~5000 char per request limit for quality output. For longer pages:

1. Split text at paragraph/sentence boundaries into chunks of ≤ 4500 chars
2. TTS each chunk sequentially, passing `previous_text` for continuity
3. Concatenate raw MP3 bytes (they're valid to concatenate for same-encoding outputs)
4. Upload the single combined MP3

---

## Secret Resolution

Secrets are resolved in this priority order — **no manual export needed** if 1Password is configured:

```
1. os.environ already set  →  use it
2. op CLI available + authenticated  →  fetch from 1Password vault "claude"
3. Neither  →  fail with a clear message showing both options
```

**1Password item mapping:**

| Secret          | op reference                              |
|---|---|
| `ELEVENLABS_API_KEY` | `op://claude/elevenlabs-api/credential` |
| `NOTION_API_KEY`     | `op://claude/notion-api/credential`     |

If the `claude` vault items exist and `op whoami` succeeds, the script pulls secrets
automatically. The `op_secret.py` module handles this; it's imported at startup with a
graceful fallback if the `op` CLI isn't available.

**Store a secret in 1Password (one-time setup):**
```bash
# ElevenLabs
op item create --vault claude --category "API Credential" \
  --title "elevenlabs-api" "credential[password]=<your-key>"

# Notion
op item create --vault claude --category "API Credential" \
  --title "notion-api" "credential[password]=<your-integration-token>"
```

Or use the `op-vault` skill for guided secret management.

## Voice Library Preview Server

When the user says anything like:
- "show me the voice library"
- "open the voice browser"
- "preview voices"
- "what voices are available"
- "let me hear some voices"

Launch the preview server:

```bash
python scripts/voice_preview_server.py [--port 7123] [--no-browser]
```

This spins up a Flask server and opens `http://localhost:7123` in the default browser. The UI shows a filterable table of all ElevenLabs premade voices with:

- **Filter chips** — quick-filter by common categories (assistant, narration, british, female, etc.)
- **Search** — live filter by name, label, use case, or description
- **Labels** — gender, age, accent, use_case shown as tags
- **Vibe aliases** — which `--voice` keywords map to each voice (clickable to filter)
- **Play button** — streams preview audio directly in the page (proxied through the server, no CORS issues, no key exposed to browser)
- **Copy ID** — click the truncated voice ID to copy the full ID to clipboard
- **Refresh button** — re-fetches from ElevenLabs API and updates the cache

The server stays alive until the user presses Ctrl+C or says "stop the server" / "shut it down". If the user spots a voice they like and wants to use it, they can copy the ID from the UI and pass it as `--voice` to `notion_tts.py`, or just use the voice name.

**Port conflict:** If 7123 is taken, try `--port 7124` (or any open port).

**Dependencies:** Requires `flask` — install with `pip install flask` if missing.

## Scripts

### `scripts/op_secret.py` — 1Password secret resolver (shared with op-vault skill)
Imported automatically by `notion_tts.py`. Falls back gracefully if `op` is unavailable.
Can also be used standalone:
```bash
python scripts/op_secret.py check              # verify op auth
python scripts/op_secret.py get --item elevenlabs-api
python scripts/op_secret.py list               # list claude vault
```

### `scripts/voice_preview_server.py` — Browser-based voice preview UI
```bash
python scripts/voice_preview_server.py          # opens http://localhost:7123
python scripts/voice_preview_server.py --port 7124   # alternate port
python scripts/voice_preview_server.py --no-browser  # don't auto-open tab
```
Requires `flask` (`pip install flask`). Opens automatically in the browser.
Streams voice preview audio via `/api/preview/<voice_id>` proxy endpoint.

### `scripts/notion_tts.py` — Main pipeline
```bash
python scripts/notion_tts.py \
  --page "https://www.notion.so/..." \
  [--voice "ted talk"]          # vibe keyword, name, or raw voice_id
  [--model eleven_multilingual_v2]
  [--output-format mp3_44100_128]
  [--dry-run]                   # extract and show text only
  [--no-attach]                 # generate audio but skip Notion upload
  [--out output.mp3]            # also save locally
  [--list-vibes]                # print available vibe keywords and exit
```

### `scripts/list_voices.py` — Voice discovery and cache management
```bash
python scripts/list_voices.py              # load/refresh cache, print table
python scripts/list_voices.py --refresh   # force re-fetch from API
python scripts/list_voices.py --search british  # filter by keyword
python scripts/list_voices.py --vibes     # print vibe→voice match table
```
Run this when voices seem stale, you get 400 errors, or you want to find
new voices to add to the vibe alias map.

### `scripts/voice_selector.py` — Voice resolution utility
```bash
python scripts/voice_selector.py "documentary"         # resolve a vibe
python scripts/voice_selector.py "calm british female" # fuzzy match
python scripts/voice_selector.py                       # list all vibes
```

---

## Output confirmation

After a successful run, report back:
- Page title
- Word count / estimated reading time
- ElevenLabs voice used + model
- MP3 size
- Notion file_upload ID
- Confirmation that the audio block was appended

---

## Error handling

| Error | Action |
|---|---|
| Notion 401 | Check `NOTION_API_KEY`; integration may not be added to the page |
| Notion 404 on page | Page not found or not shared with integration |
| ElevenLabs 401 | Check `ELEVENLABS_API_KEY` |
| ElevenLabs 429 | Rate limit — retry with backoff |
| File upload `status != uploaded` | Log and abort cleanly |
| Text extraction yields empty string | Warn user; page may be empty or contain only unsupported blocks |

---

## Edge cases

- **Already has audio block:** Append another; don't replace (Notion has no block-update-in-place for audio)
- **Page with sub-pages:** Don't recurse into child pages unless the user explicitly asks
- **Private/locked pages:** Will 403 — user needs to share the page with the integration
- **Title extraction:** Get the page title from `GET /v1/pages/{page_id}` → `.properties.title` or `.properties.Name` → use as filename base
