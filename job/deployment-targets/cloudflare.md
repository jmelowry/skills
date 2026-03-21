# Deployment Target: Cloudflare Workers

**Status: STUB — not yet implemented**

---

## When to use

- Script Worker archetype
- Task needs an HTTP trigger (vs. cron or manual dispatch)
- Latency matters — Workers run at the edge, not in a datacenter
- Task is lightweight: < 30s CPU time, < 128MB memory
- Output needs to be a response to an HTTP request

## Not appropriate for

- Agentic Runner archetype (Workers timeout too aggressively for multi-turn Claude)
- Tasks needing > 128MB memory
- Tasks that shell out or need arbitrary binaries
- Anything requiring a filesystem (use R2 for storage instead)

## Planned integration

When implemented, the job skill will:

1. Generate a `workers/<name>/index.ts` instead of `scripts/<name>.py`
2. Generate a `wrangler.toml` with the appropriate trigger (HTTP or cron)
3. Deploy via `wrangler deploy` instead of `gh api`
4. Store output in R2 instead of GitHub Actions artifacts

## Relationship to GitHub Actions

Even when deploying to CF Workers, GHA remains the **dispatcher**:
- GHA workflow calls `wrangler deploy` to push the Worker
- CF cron triggers or HTTP triggers then run the Worker independently
- GHA can also invoke the Worker via `curl` for on-demand runs

## R2 for artifact storage

CF R2 is a natural complement to both GHA and Workers:
- Workers write output to R2 instead of returning it in the response
- GHA workflows can also write artifacts to R2 for persistence beyond 14 days
- Access via `wrangler r2 object get` or the R2 HTTP API

## Secrets mapping

| Current (GHA) | CF Workers equivalent |
|---|---|
| `secrets.ANTHROPIC_API_KEY` | `wrangler secret put ANTHROPIC_API_KEY` |
| GitHub Environments approval gate | Not available — use a webhook + Slack confirmation pattern |

---

*Implement this target when: the skill has validated the GHA path and there is
a concrete use case requiring HTTP triggers or edge latency.*
