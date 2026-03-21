#!/usr/bin/env python3
"""
para_index.py — Fetch and print a live index of the Notion PARA workspace.

Fetches the children of all four PARA root pages via the Notion API and prints
a compact tree. Useful for quickly seeing the current structure before filing.

Usage:
    python scripts/para_index.py             # print full index
    python scripts/para_index.py --json      # output as JSON
    python scripts/para_index.py --pillar areas   # single pillar only

Secret resolution (in priority order):
    1. NOTION_API_KEY env var
    2. op CLI: op://claude/notion-api/credential
"""

import sys
import os
import json
import argparse
import subprocess
import urllib.request
import urllib.error

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

PARA_ROOTS = {
    "projects": {
        "id": "f09305c7-1857-4d97-83ef-cc240b03e2e2",
        "label": "☑️  1. Projects",
    },
    "areas": {
        "id": "8d27c2d1-93ae-4d42-ab48-27b067a343e2",
        "label": "⚙️  2. Areas",
    },
    "resources": {
        "id": "d49ac77b-8397-43b3-a0df-7b61b17d7c21",
        "label": "📚 3. Resources",
    },
    "archive": {
        "id": "ff86dbac-6f45-4225-be8d-79514346de9f",
        "label": "🗄️  4. Archive",
    },
}


def resolve_token() -> str:
    token = os.environ.get("NOTION_API_KEY", "")
    if token:
        return token
    try:
        result = subprocess.run(
            ["op", "read", "op://claude/notion-api/credential"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("ERROR: NOTION_API_KEY not set and op CLI unavailable.", file=sys.stderr)
    print("  Set it: export NOTION_API_KEY=secret_...", file=sys.stderr)
    print("  Or store in 1Password: op://claude/notion-api/credential", file=sys.stderr)
    sys.exit(1)


def notion_get(path: str, token: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR {e.code} fetching {path}: {body}", file=sys.stderr)
        sys.exit(1)


def get_children(page_id: str, token: str) -> list[dict]:
    """Fetch all direct children of a page (handles pagination)."""
    children = []
    cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = notion_get(path, token)
        for block in data.get("results", []):
            btype = block.get("type")
            # child_page and child_database are the interesting ones
            if btype == "child_page":
                title = block["child_page"].get("title", "(untitled)")
                children.append({
                    "type": "page",
                    "id": block["id"],
                    "title": title,
                    "url": f"https://www.notion.so/{block['id'].replace('-', '')}",
                })
            elif btype == "child_database":
                title = block["child_database"].get("title", "(untitled)")
                children.append({
                    "type": "database",
                    "id": block["id"],
                    "title": title,
                    "url": f"https://www.notion.so/{block['id'].replace('-', '')}",
                })
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return children


def build_index(pillars: list[str], token: str) -> dict:
    index = {}
    for key in pillars:
        root = PARA_ROOTS[key]
        children = get_children(root["id"], token)
        index[key] = {
            "label": root["label"],
            "id": root["id"],
            "children": children,
        }
    return index


def print_index(index: dict) -> None:
    for key, pillar in index.items():
        print(f"\n{pillar['label']}")
        print(f"  ID: {pillar['id']}")
        children = pillar["children"]
        if not children:
            print("  (empty)")
            continue
        for i, child in enumerate(children):
            connector = "└─" if i == len(children) - 1 else "├─"
            tag = "[db]" if child["type"] == "database" else "    "
            print(f"  {connector} {tag} {child['title']}")
            print(f"       {child['id']}")


def main():
    parser = argparse.ArgumentParser(description="Print live PARA workspace index")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--pillar",
        choices=list(PARA_ROOTS.keys()),
        help="Only fetch one pillar",
    )
    args = parser.parse_args()

    token = resolve_token()
    pillars = [args.pillar] if args.pillar else list(PARA_ROOTS.keys())
    index = build_index(pillars, token)

    if args.json:
        print(json.dumps(index, indent=2))
    else:
        print_index(index)


if __name__ == "__main__":
    main()
