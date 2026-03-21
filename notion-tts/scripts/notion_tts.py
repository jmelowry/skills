#!/usr/bin/env python3
"""
notion_tts.py — Convert a Notion page to TTS audio and attach it back to the page.

Usage:
    python notion_tts.py --page <notion-url-or-id> [options]

Required secrets (resolved in priority order):
    1. 1Password vault "claude":
       - NOTION_API_KEY     ← op://claude/notion-api/credential
       - ELEVENLABS_API_KEY ← op://claude/elevenlabs-api/credential
    2. Environment variables (NOTION_API_KEY, ELEVENLABS_API_KEY)
    3. Error if neither source has the value

    If op is available and authenticated, secrets are pulled from 1Password
    automatically. No env vars need to be set manually.

Options:
    --page              Notion page URL or ID (required)
    --voice             Voice name, vibe keyword, or raw voice_id
                        Examples: "Matilda", "ted talk", "documentary", "calm british male"
                        Run `python voice_selector.py` with no args for full list.
                        Default: "assistant" (Matilda — warm neutral reading voice)
    --model             ElevenLabs model ID (default: eleven_multilingual_v2)
    --output-format     Audio format (default: mp3_44100_128)
    --dry-run           Extract and print text only; skip TTS and upload
    --no-attach         Generate audio but don't attach to Notion page
    --out               Save MP3 to this local path (optional)
    --list-vibes        Print available vibe keywords and exit
"""

import argparse
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import requests

# ─── Constants ───────────────────────────────────────────────────────────────

NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"
ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"

DEFAULT_VIBE = "assistant"  # resolves to Matilda — warm neutral reading voice
DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_FORMAT = "mp3_44100_128"

# Import voice selector (same package)
import sys
sys.path.insert(0, str(Path(__file__).parent))
from voice_selector import resolve_voice, describe_vibe_options

# 1Password secret resolution (optional — falls back to env vars if op unavailable)
try:
    from op_secret import get_secret, check_op_available, OpError
    _OP_AVAILABLE = True
except ImportError:
    _OP_AVAILABLE = False

# 1Password vault + item mapping for this script's secrets
_OP_SECRETS = {
    "ELEVENLABS_API_KEY": ("claude", "elevenlabs-api", "credential"),
    "NOTION_API_KEY":     ("claude", "notion-api",     "credential"),
}


def resolve_secret(env_var: str) -> str:
    """
    Resolve a secret in priority order:
      1. Already set in os.environ → use it
      2. op available + item exists in claude vault → fetch from 1Password
      3. Raise with a clear message pointing to both sources
    """
    # 1. Env var already present
    value = os.environ.get(env_var, "").strip()
    if value:
        return value

    # 2. Try 1Password
    if _OP_AVAILABLE and env_var in _OP_SECRETS:
        ok, msg = check_op_available()
        if ok:
            vault, item, field = _OP_SECRETS[env_var]
            try:
                value = get_secret(vault, item, field)
                if value:
                    print(f"  {env_var}: resolved from op://{vault}/{item}/{field}")
                    return value
            except OpError as e:
                print(f"  Warning: 1Password lookup failed for {env_var}: {e}", file=sys.stderr)
        else:
            print(f"  Note: op unavailable ({msg}) — falling back to env", file=sys.stderr)

    # 3. Nothing worked
    op_ref = ""
    if env_var in _OP_SECRETS:
        v, i, f = _OP_SECRETS[env_var]
        op_ref = f"\n  or store it in 1Password: op item create --vault {v} --category 'API Credential' --title {i} 'credential[password]=<value>'"
    raise SystemExit(
        f"ERROR: {env_var} not found.\n"
        f"  Set it as an env var: export {env_var}=<value>{op_ref}"
    )


MAX_CHUNK_CHARS = 4500
RECURSE_DEPTH = 3

# ─── Helpers ─────────────────────────────────────────────────────────────────

def notion_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def normalize_page_id(raw: str) -> str:
    """Extract and hyphenate a 32-char Notion page ID from a URL or raw string."""
    # Strip URL components
    raw = raw.strip().rstrip("/")
    # Match last 32-char hex segment (with or without hyphens)
    match = re.search(r"([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})", raw, re.I)
    if not match:
        raise ValueError(f"Could not extract a Notion page ID from: {raw!r}")
    raw_id = match.group(1).replace("-", "")
    return f"{raw_id[0:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"


def rich_text_to_plain(rich_text_list: list) -> str:
    return "".join(rt.get("plain_text", "") for rt in rich_text_list)


# ─── Notion: fetch page info ──────────────────────────────────────────────────

def get_page_title(page_id: str, api_key: str) -> str:
    resp = requests.get(f"{NOTION_BASE}/pages/{page_id}", headers=notion_headers(api_key))
    resp.raise_for_status()
    props = resp.json().get("properties", {})
    # Try common title property names
    for key in ("title", "Name", "Title"):
        if key in props:
            title_obj = props[key]
            if title_obj.get("type") == "title":
                return rich_text_to_plain(title_obj.get("title", [])) or "Untitled"
    return "Untitled"


# ─── Notion: block text extraction ───────────────────────────────────────────

TEXT_BLOCK_TYPES = {
    "paragraph", "quote", "callout",
    "heading_1", "heading_2", "heading_3",
    "bulleted_list_item", "numbered_list_item", "to_do",
    "toggle",
}

SKIP_BLOCK_TYPES = {
    "image", "video", "audio", "file", "pdf",
    "child_database", "child_page",
    "table_of_contents", "breadcrumb", "unsupported",
    "embed", "bookmark", "link_preview",
}


def extract_blocks_text(page_id: str, api_key: str, depth: int = 0) -> list[str]:
    """Recursively extract plain text from a page's block tree."""
    if depth > RECURSE_DEPTH:
        return []

    paragraphs = []
    cursor = None

    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        resp = requests.get(
            f"{NOTION_BASE}/blocks/{page_id}/children",
            headers=notion_headers(api_key),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        for block in data.get("results", []):
            btype = block.get("type", "")
            content = block.get(btype, {})

            if btype in SKIP_BLOCK_TYPES:
                continue
            elif btype == "divider":
                paragraphs.append(".")  # natural pause
            elif btype == "code":
                # Skip code blocks in audio — they read terribly
                pass
            elif btype == "column_list":
                # Recurse into columns
                if block.get("has_children"):
                    paragraphs.extend(extract_blocks_text(block["id"], api_key, depth + 1))
            elif btype == "column":
                if block.get("has_children"):
                    paragraphs.extend(extract_blocks_text(block["id"], api_key, depth + 1))
            elif btype in TEXT_BLOCK_TYPES:
                text = rich_text_to_plain(content.get("rich_text", []))
                if text.strip():
                    paragraphs.append(text.strip())
                # Recurse into toggle children
                if btype == "toggle" and block.get("has_children"):
                    paragraphs.extend(extract_blocks_text(block["id"], api_key, depth + 1))
            elif btype == "table":
                # Tables: extract row text row by row
                if block.get("has_children"):
                    paragraphs.extend(extract_blocks_text(block["id"], api_key, depth + 1))
            elif btype == "table_row":
                cells = content.get("cells", [])
                row_text = " | ".join(
                    rich_text_to_plain(cell) for cell in cells
                )
                if row_text.strip():
                    paragraphs.append(row_text.strip())

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return paragraphs


# ─── Text post-processing ─────────────────────────────────────────────────────

def build_tts_text(paragraphs: list[str]) -> str:
    """Join paragraphs with natural spacing for TTS."""
    # Filter empties, join with double-space for a natural pause between sections
    chunks = [p for p in paragraphs if p.strip()]
    text = "\n\n".join(chunks)
    # Collapse 3+ newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at paragraph/sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = []
    current_len = 0

    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if current_len + len(para) + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks


# ─── ElevenLabs TTS ───────────────────────────────────────────────────────────

def tts_chunk(
    text: str,
    voice_id: str,
    model_id: str,
    output_format: str,
    api_key: str,
    previous_text: str = "",
) -> bytes:
    """Convert one text chunk to MP3 bytes."""
    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": text,
        "model_id": model_id,
        "output_format": output_format,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }
    if previous_text:
        body["previous_text"] = previous_text[-500:]  # last 500 chars for continuity

    for attempt in range(3):
        resp = requests.post(url, headers=headers, json=body)
        if resp.status_code == 429:
            wait = 2 ** attempt
            print(f"  Rate limited by ElevenLabs, retrying in {wait}s...", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.content

    raise RuntimeError("ElevenLabs rate limit exhausted after 3 retries")


def generate_audio(
    text: str,
    voice_id: str,
    model_id: str,
    output_format: str,
    api_key: str,
) -> bytes:
    """Generate MP3 bytes for the full text, chunking if necessary."""
    chunks = chunk_text(text)
    print(f"  TTS: {len(chunks)} chunk(s), ~{len(text)} chars total")

    audio_parts = []
    previous_text = ""

    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)} ({len(chunk)} chars)...")
        audio = tts_chunk(chunk, voice_id, model_id, output_format, api_key, previous_text)
        audio_parts.append(audio)
        previous_text = chunk

    return b"".join(audio_parts)


# ─── Notion file upload ───────────────────────────────────────────────────────

def upload_to_notion(
    mp3_bytes: bytes,
    filename: str,
    page_id: str,
    api_key: str,
) -> str:
    """Upload MP3 bytes to Notion and attach as an audio block. Returns file_upload ID."""
    headers = notion_headers(api_key)

    # Step 1: Create the file upload object
    print("  Notion: creating file upload object...")
    resp = requests.post(
        f"{NOTION_BASE}/file_uploads",
        headers=headers,
        json={"filename": filename, "content_type": "audio/mpeg"},
    )
    resp.raise_for_status()
    upload = resp.json()
    file_upload_id = upload["id"]
    upload_url = upload["upload_url"]
    print(f"  File upload ID: {file_upload_id}")

    # Step 2: Send the file
    print("  Notion: uploading MP3 bytes...")
    upload_headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
    }
    resp = requests.post(
        upload_url,
        headers=upload_headers,
        files={"file": (filename, mp3_bytes, "audio/mpeg")},
    )
    resp.raise_for_status()
    status = resp.json().get("status")
    if status != "uploaded":
        raise RuntimeError(f"Unexpected file upload status: {status!r}")
    print(f"  Upload status: {status}")

    # Step 3: Attach as audio block
    print("  Notion: appending audio block to page...")
    resp = requests.patch(
        f"{NOTION_BASE}/blocks/{page_id}/children",
        headers=headers,
        json={
            "children": [
                {
                    "object": "block",
                    "type": "audio",
                    "audio": {
                        "type": "file_upload",
                        "file_upload": {"id": file_upload_id},
                    },
                }
            ]
        },
    )
    resp.raise_for_status()
    print("  Audio block attached.")
    return file_upload_id


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Convert Notion page to TTS and attach audio.")
    parser.add_argument("--page", help="Notion page URL or ID")
    parser.add_argument("--voice", default=DEFAULT_VIBE,
                        help="Voice name, vibe keyword, or raw voice_id (default: 'assistant')")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="ElevenLabs model ID")
    parser.add_argument("--output-format", default=DEFAULT_FORMAT, help="Audio output format")
    parser.add_argument("--dry-run", action="store_true", help="Extract text only; skip TTS/upload")
    parser.add_argument("--no-attach", action="store_true", help="Generate audio but skip Notion upload")
    parser.add_argument("--out", help="Save MP3 to this local path")
    parser.add_argument("--list-vibes", action="store_true", help="Print available vibe keywords and exit")
    args = parser.parse_args()

    if args.list_vibes:
        print(describe_vibe_options())
        sys.exit(0)

    if not args.page:
        parser.error("--page is required")

    # Resolve secrets (1Password → env var fallback)
    print("Resolving secrets...")
    notion_key = resolve_secret("NOTION_API_KEY")
    elevenlabs_key = resolve_secret("ELEVENLABS_API_KEY") if not args.dry_run else ""

    # Resolve page ID
    page_id = normalize_page_id(args.page)
    print(f"Page ID: {page_id}")

    # Resolve voice from vibe/name/id
    resolved = resolve_voice(args.voice)
    print(f"Voice: {resolved.name} ({resolved.voice_id})")
    print(f"  └─ {resolved.reason}")

    # Fetch page title
    print("Fetching page title...")
    title = get_page_title(page_id, notion_key)
    print(f"Title: {title!r}")

    # Extract text
    print("Extracting page text...")
    paragraphs = extract_blocks_text(page_id, notion_key)
    text = build_tts_text(paragraphs)

    word_count = len(text.split())
    est_minutes = round(word_count / 150, 1)  # ~150 wpm average
    print(f"Extracted {word_count} words (~{est_minutes} min read time)")

    if not text:
        print("WARNING: No readable text found on this page.")
        sys.exit(0)

    if args.dry_run:
        print("\n─── Extracted Text ───────────────────────────────────────")
        print(text)
        print("──────────────────────────────────────────────────────────")
        sys.exit(0)

    # Generate TTS
    print(f"\nGenerating TTS with voice={resolved.name}, model={args.model}...")
    mp3_bytes = generate_audio(text, resolved.voice_id, args.model, args.output_format, elevenlabs_key)
    mp3_size_kb = len(mp3_bytes) / 1024
    print(f"Generated {mp3_size_kb:.1f} KB of audio")

    # Save locally if requested
    safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
    filename = f"{safe_title}.mp3" if safe_title else "notion_tts.mp3"

    if args.out:
        out_path = Path(args.out)
        out_path.write_bytes(mp3_bytes)
        print(f"Saved to: {out_path}")

    # Upload to Notion
    if not args.no_attach:
        print(f"\nUploading to Notion as {filename!r}...")
        file_upload_id = upload_to_notion(mp3_bytes, filename, page_id, notion_key)

        print(f"\n✓ Done.")
        print(f"  Page:            {title}")
        print(f"  Words:           {word_count} (~{est_minutes} min)")
        print(f"  Voice:           {resolved.name} ({resolved.voice_id})")
        print(f"  Model:           {args.model}")
        print(f"  MP3 size:        {mp3_size_kb:.1f} KB")
        print(f"  File upload ID:  {file_upload_id}")
        print(f"  Audio block appended to page ✓")
    else:
        print(f"\n✓ Audio generated ({mp3_size_kb:.1f} KB). Skipped Notion upload (--no-attach).")


if __name__ == "__main__":
    main()
