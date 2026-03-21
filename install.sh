#!/usr/bin/env bash
# install.sh — sync all skills from this repo into ~/.claude/skills/
#
# Usage:
#   ./install.sh          # install/update all skills
#   ./install.sh --pull   # git pull first, then install
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"

if [[ "${1:-}" == "--pull" ]]; then
  echo "Pulling latest from origin..."
  git -C "$REPO_DIR" pull
fi

mkdir -p "$SKILLS_DIR"

# Each subdirectory that contains a SKILL.md is a skill
for skill_dir in "$REPO_DIR"/*/; do
  skill="$(basename "$skill_dir")"
  if [[ -f "$skill_dir/SKILL.md" ]]; then
    rm -rf "${SKILLS_DIR:?}/$skill"
    cp -r "$skill_dir" "$SKILLS_DIR/$skill"
    echo "installed: $skill"
  fi
done

echo "Done. Skills installed to $SKILLS_DIR"
