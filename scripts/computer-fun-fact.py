#!/usr/bin/env python3
"""Generate a fun fact about computers using the Claude API."""

import os
import sys
import argparse
import anthropic
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Skip API call, print placeholder")
    args = parser.parse_args()

    topic_hint = os.environ.get("TOPIC_HINT", "").strip()
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    if args.dry_run:
        fact = "[DRY RUN] Did you know? The first computer bug was an actual bug — a moth found in a relay of the Harvard Mark II in 1947."
        print(fact)
        (output_dir / "summary.txt").write_text(fact + "
")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    topic_clause = f" Focus on something related to: {topic_hint}." if topic_hint else ""

    prompt = (
        f"Give me one genuinely surprising and delightful fun fact about computers, "
        f"programming history, or technology.{topic_clause} "
        f"Keep it to 2–3 sentences. Start directly with the fact — no preamble like 'Here's a fun fact'."
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    fact = message.content[0].text.strip()

    print(fact)
    (output_dir / "summary.txt").write_text(fact + "
")

if __name__ == "__main__":
    main()
