"""
op_secret.py — Python helper for reading 1Password secrets via the op CLI.

Designed to be imported by other scripts (like notion_tts.py) that need
secrets without requiring the caller to manage op invocations directly.

Usage:
    from op_secret import get_secret, inject_secrets, check_op_available

    # Get a single secret value
    api_key = get_secret("claude", "elevenlabs-api", "credential")

    # Get using a raw op:// reference
    api_key = get_secret_ref("op://claude/elevenlabs-api/credential")

    # Inject multiple secrets into os.environ for the current process
    inject_secrets({
        "ELEVENLABS_API_KEY": "op://claude/elevenlabs-api/credential",
        "NOTION_API_KEY":      "op://claude/notion-api/credential",
    })

    # Check whether op is available and authenticated before using it
    ok, msg = check_op_available()
"""

import os
import shutil
import subprocess
from typing import Optional


class OpError(RuntimeError):
    """Raised when the op CLI returns an error."""


def check_op_available() -> tuple[bool, str]:
    """
    Returns (True, "") if op is installed and authenticated,
    or (False, "<error message>") otherwise.
    """
    if not shutil.which("op"):
        return False, (
            "`op` CLI not found. Install from https://1password.com/downloads/command-line/ "
            "and ensure it's on your PATH."
        )
    try:
        result = subprocess.run(
            ["op", "whoami"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            msg = result.stderr.strip() or "op whoami failed"
            return False, (
                f"1Password CLI not authenticated: {msg}\n"
                "Run `op signin` or open the 1Password desktop app."
            )
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "op CLI timed out — is the 1Password desktop app running?"
    except Exception as e:
        return False, f"op CLI error: {e}"


def get_secret_ref(ref: str) -> str:
    """
    Read a secret using a full op:// reference URI.

    Args:
        ref: e.g. "op://claude/elevenlabs-api/credential"

    Returns:
        The plaintext secret value.

    Raises:
        OpError on failure.
    """
    result = subprocess.run(
        ["op", "read", ref],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise OpError(
            f"Failed to read secret {ref!r}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def get_secret(vault: str, item: str, field: str = "credential") -> str:
    """
    Read a single field from a 1Password item.

    Args:
        vault:  Vault name (e.g. "claude")
        item:   Item name (e.g. "elevenlabs-api")
        field:  Field label (default: "credential"; use "password" for Login items)

    Returns:
        The plaintext secret value.

    Raises:
        OpError on failure.
    """
    ref = f"op://{vault}/{item}/{field}"
    return get_secret_ref(ref)


def inject_secrets(
    mapping: dict[str, str],
    overwrite: bool = False,
) -> dict[str, str]:
    """
    Resolve op:// references and inject them into os.environ.

    Args:
        mapping:   Dict of ENV_VAR_NAME -> "op://vault/item/field"
                   Values that don't start with "op://" are passed through as-is.
        overwrite: If False (default), skip vars that are already set in the environment.

    Returns:
        Dict of env var names that were actually set (for logging).

    Raises:
        OpError if any secret fails to resolve.
    """
    injected = {}
    for env_var, ref_or_value in mapping.items():
        if not overwrite and os.environ.get(env_var):
            continue  # already set, respect existing value
        if ref_or_value.startswith("op://"):
            value = get_secret_ref(ref_or_value)
        else:
            value = ref_or_value
        os.environ[env_var] = value
        injected[env_var] = ref_or_value  # log ref, not plaintext
    return injected


def list_vault_items(vault: str = "claude") -> list[dict]:
    """
    List all items in a vault.

    Returns:
        List of dicts with keys: id, title, category, updated_at
    """
    import json
    result = subprocess.run(
        ["op", "item", "list", "--vault", vault, "--format", "json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise OpError(f"Failed to list vault {vault!r}: {result.stderr.strip()}")
    items = json.loads(result.stdout)
    return [
        {
            "id":         i.get("id", ""),
            "title":      i.get("title", ""),
            "category":   i.get("category", ""),
            "updated_at": i.get("updated_at", ""),
        }
        for i in items
    ]


def create_secret(
    title: str,
    value: str,
    vault: str = "claude",
    field: str = "credential",
    category: str = "API Credential",
) -> str:
    """
    Create a new secret item in a vault.

    Args:
        title:    Item name
        value:    The secret value
        vault:    Vault name (default: "claude")
        field:    Field label (default: "credential")
        category: Item category (default: "API Credential")

    Returns:
        The new item's ID.

    Raises:
        OpError on failure.
    """
    import json
    result = subprocess.run(
        [
            "op", "item", "create",
            "--vault", vault,
            "--category", category,
            "--title", title,
            f"{field}[password]={value}",
            "--format", "json",
        ],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise OpError(f"Failed to create item {title!r}: {result.stderr.strip()}")
    item = json.loads(result.stdout)
    return item["id"]


def update_secret(
    item: str,
    value: str,
    vault: str = "claude",
    field: str = "credential",
) -> None:
    """
    Update a field on an existing item.

    Args:
        item:   Item name or ID
        value:  New secret value
        vault:  Vault name (default: "claude")
        field:  Field label to update (default: "credential")

    Raises:
        OpError on failure.
    """
    result = subprocess.run(
        [
            "op", "item", "edit", item,
            "--vault", vault,
            f"{field}[password]={value}",
        ],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise OpError(f"Failed to update item {item!r}: {result.stderr.strip()}")


# ── CLI usage ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Read or write secrets in a 1Password vault"
    )
    sub = parser.add_subparsers(dest="cmd")

    # get
    p_get = sub.add_parser("get", help="Read a secret")
    p_get.add_argument("--vault", default="claude")
    p_get.add_argument("--item", required=True)
    p_get.add_argument("--field", default="credential")

    # set
    p_set = sub.add_parser("set", help="Create or update a secret")
    p_set.add_argument("--vault", default="claude")
    p_set.add_argument("--item", required=True)
    p_set.add_argument("--field", default="credential")
    p_set.add_argument("--value", required=True)
    p_set.add_argument("--create", action="store_true", help="Create new item (vs update)")

    # list
    p_list = sub.add_parser("list", help="List items in a vault")
    p_list.add_argument("--vault", default="claude")

    # check
    sub.add_parser("check", help="Check op availability and auth")

    args = parser.parse_args()

    if args.cmd == "check":
        ok, msg = check_op_available()
        if ok:
            print("op is available and authenticated.")
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "get":
        ok, msg = check_op_available()
        if not ok:
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)
        try:
            val = get_secret(args.vault, args.item, args.field)
            print(val)
        except OpError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "set":
        ok, msg = check_op_available()
        if not ok:
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)
        try:
            if args.create:
                item_id = create_secret(args.item, args.value, args.vault, args.field)
                print(f"Created item '{args.item}' (id: {item_id})")
            else:
                update_secret(args.item, args.value, args.vault, args.field)
                print(f"Updated item '{args.item}' field '{args.field}'")
        except OpError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "list":
        ok, msg = check_op_available()
        if not ok:
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)
        try:
            items = list_vault_items(args.vault)
            print(f"{'Title':<40} {'Category':<20} ID")
            print("-" * 90)
            for i in items:
                print(f"{i['title']:<40} {i['category']:<20} {i['id']}")
        except OpError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
