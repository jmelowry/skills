#!/usr/bin/env python3
"""
list_voices.py — Fetch and cache ElevenLabs voices to a local JSON file.

Usage:
    python list_voices.py [--out voices.json] [--refresh] [--search <term>]

Required env:
    ELEVENLABS_API_KEY

Options:
    --out       Where to write the cache (default: voices.json in script dir)
    --refresh   Force re-fetch even if cache is recent
    --search    Filter by name, description, or label values
    --vibes     Print vibe → voice recommendation table (useful for prompt design)

The cache file is what notion_tts.py reads for voice selection. Run this whenever
voices seem stale or you want to add new community voices to your selection pool.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
CACHE_TTL_HOURS = 24
DEFAULT_CACHE_PATH = Path(__file__).parent / "voices.json"


def el_headers(api_key: str) -> dict:
    return {"xi-api-key": api_key, "Content-Type": "application/json"}


def fetch_all_voices(api_key: str) -> list[dict]:
    """Paginate through all available voices (premade + any added to account)."""
    voices = []
    page_token = None

    while True:
        params = {
            "page_size": 100,
            "category": "premade",  # premade = ElevenLabs default voices
            "sort": "name",
            "sort_direction": "asc",
        }
        if page_token:
            params["next_page_token"] = page_token

        resp = requests.get(
            f"{ELEVENLABS_BASE}/voices/search",
            headers=el_headers(api_key),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        voices.extend(data.get("voices", []))

        if not data.get("has_more"):
            break
        page_token = data.get("next_page_token")

    return voices


def normalize_voice(v: dict) -> dict:
    """Flatten a voice object to what we care about."""
    labels = v.get("labels") or {}
    return {
        "voice_id": v["voice_id"],
        "name": v["name"],
        "description": v.get("description") or "",
        "category": v.get("category", ""),
        "labels": {
            "gender": labels.get("gender", ""),
            "accent": labels.get("accent", ""),
            "age": labels.get("age", ""),
            "use_case": labels.get("use_case", ""),
            "descriptive": labels.get("descriptive", ""),
        },
        "preview_url": v.get("preview_url", ""),
    }


def load_cache(path: Path) -> dict | None:
    """Load cache if it exists and isn't stale."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        age_hours = (time.time() - data.get("fetched_at", 0)) / 3600
        if age_hours > CACHE_TTL_HOURS:
            return None
        return data
    except (json.JSONDecodeError, KeyError):
        return None


def save_cache(voices: list[dict], path: Path) -> None:
    payload = {
        "fetched_at": time.time(),
        "fetched_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(voices),
        "voices": voices,
    }
    path.write_text(json.dumps(payload, indent=2))


def search_voices(voices: list[dict], term: str) -> list[dict]:
    term = term.lower()
    results = []
    for v in voices:
        searchable = " ".join([
            v["name"],
            v["description"],
            *v["labels"].values(),
        ]).lower()
        if term in searchable:
            results.append(v)
    return results


def print_voice_table(voices: list[dict]) -> None:
    print(f"\n{'Name':<20} {'Gender':<8} {'Age':<12} {'Accent':<16} {'Use Case':<18} {'ID'}")
    print("-" * 105)
    for v in voices:
        l = v["labels"]
        print(
            f"{v['name']:<20} {l['gender']:<8} {l['age']:<12} {l['accent']:<16} {l['use_case']:<18} {v['voice_id']}"
        )


def print_vibe_table(voices: list[dict]) -> None:
    """Show a vibe→voice mapping for common use cases."""
    vibe_map = {
        "assistant / neutral": lambda v: "assistant" in v["labels"].get("use_case", "").lower(),
        "narration / documentary": lambda v: "narration" in v["labels"].get("use_case", "").lower(),
        "news / authoritative": lambda v: "news" in v["labels"].get("use_case", "").lower(),
        "conversational": lambda v: "conversational" in v["labels"].get("use_case", "").lower(),
        "young female": lambda v: v["labels"].get("gender") == "female" and v["labels"].get("age") == "young",
        "middle-aged male": lambda v: v["labels"].get("gender") == "male" and v["labels"].get("age") == "middle aged",
        "british accent": lambda v: "british" in v["labels"].get("accent", "").lower(),
        "american accent": lambda v: "american" in v["labels"].get("accent", "").lower(),
    }

    print("\n─── Vibe → Voice Matches ─────────────────────────────────────────")
    for vibe, predicate in vibe_map.items():
        matches = [v for v in voices if predicate(v)]
        if matches:
            names = ", ".join(f"{v['name']} ({v['voice_id'][:8]}...)" for v in matches[:3])
            print(f"  {vibe:<30} → {names}")
        else:
            print(f"  {vibe:<30} → (no matches)")


def main():
    parser = argparse.ArgumentParser(description="Fetch and cache ElevenLabs voices.")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch")
    parser.add_argument("--search", help="Filter voices by keyword")
    parser.add_argument("--vibes", action="store_true", help="Print vibe→voice table")
    args = parser.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Try cache first
    cache = None if args.refresh else load_cache(args.out)

    if cache:
        print(f"Loaded {cache['count']} voices from cache ({args.out})")
        print(f"  Cached at: {cache['fetched_at_iso']}")
        voices = cache["voices"]
    else:
        print("Fetching voices from ElevenLabs API...")
        raw = fetch_all_voices(api_key)
        voices = [normalize_voice(v) for v in raw]
        save_cache(voices, args.out)
        print(f"Fetched and cached {len(voices)} voices → {args.out}")

    if args.search:
        voices = search_voices(voices, args.search)
        print(f"\nSearch results for {args.search!r}: {len(voices)} match(es)")

    print_voice_table(voices)

    if args.vibes:
        print_vibe_table(voices)

    print(f"\nTotal: {len(voices)} voices")
    print(f"Cache: {args.out}")


if __name__ == "__main__":
    main()
