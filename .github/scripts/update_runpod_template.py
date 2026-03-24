"""
update_runpod_template.py — Update a RunPod serverless template's image via GraphQL API.

Fetches the current template (preserving all fields), upserts any env vars from
INJECT_ENV, then updates only the imageName — so CI/CD is the source of truth,
not the RunPod UI.

Required env vars:
    RUNPOD_API_KEY       RunPod API key
    RUNPOD_TEMPLATE_ID   Template ID to update
    IMAGE_TAG            Full image reference (e.g. ghcr.io/jmelowry/dia-tts:sha-abc1234)

Optional env vars:
    INJECT_ENV           JSON object of env vars to upsert, e.g. '{"HF_TOKEN":"abc"}'
"""
import json
import os
import sys
import urllib.request

API = "https://api.runpod.io/graphql"
API_KEY = os.environ["RUNPOD_API_KEY"]
TEMPLATE_ID = os.environ["RUNPOD_TEMPLATE_ID"]
IMAGE_TAG = os.environ["IMAGE_TAG"]
INJECT_ENV = json.loads(os.environ.get("INJECT_ENV", "{}"))


def graphql(query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
            "User-Agent": "curl/7.88.1",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
        sys.exit(1)
    return data


def upsert_env(env_list: list[dict], updates: dict) -> list[dict]:
    env = {e["key"]: e["value"] for e in env_list}
    env.update(updates)
    return [{"key": k, "value": v} for k, v in env.items()]


# 1. Fetch current template (podTemplates has no id filter — fetch all, match by id)
fetch_q = """
{
  myself {
    podTemplates {
      id
      name
      imageName
      dockerArgs
      containerDiskInGb
      volumeInGb
      volumeMountPath
      ports
      env { key value }
      startJupyter
      startSsh
    }
  }
}
"""
result = graphql(fetch_q)
all_templates = result["data"]["myself"]["podTemplates"]
templates = [t for t in all_templates if t["id"] == TEMPLATE_ID]
if not templates:
    print(f"Template {TEMPLATE_ID} not found", file=sys.stderr)
    sys.exit(1)

tmpl = templates[0]
print(f"Updating template: {tmpl['name']} ({TEMPLATE_ID})")
print(f"  {tmpl['imageName']}  →  {IMAGE_TAG}")

updated_env = upsert_env(tmpl.get("env") or [], INJECT_ENV)

# 2. Mutate — preserve all fields, update only imageName (and env)
save_q = """
mutation SaveTemplate($input: SaveTemplateInput!) {
  saveTemplate(input: $input) {
    id
    imageName
  }
}
"""
save_result = graphql(save_q, {
    "input": {
        "id": TEMPLATE_ID,
        "name": tmpl["name"],
        "imageName": IMAGE_TAG,
        "dockerArgs": tmpl.get("dockerArgs", ""),
        "containerDiskInGb": tmpl["containerDiskInGb"],
        "volumeInGb": tmpl.get("volumeInGb", 0),
        "volumeMountPath": tmpl.get("volumeMountPath", "/workspace"),
        "ports": tmpl.get("ports", ""),
        "env": updated_env,
        "startJupyter": tmpl.get("startJupyter", False),
        "startSsh": tmpl.get("startSsh", False),
    }
})

updated = save_result["data"]["saveTemplate"]
print(f"Done. Template {updated['id']} now uses: {updated['imageName']}")
