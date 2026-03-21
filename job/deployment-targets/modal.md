# Deployment Target: Modal

**Status: STUB — not yet implemented**

---

## When to use

- Python-heavy Script Worker or Agentic Runner
- Task needs GPU (local model inference, embeddings, image gen)
- Per-second billing is preferable to always-on compute
- Team is Python-first and wants decorator-based DX

## Not appropriate for

- Non-Python workloads
- Tasks that need to stay alive persistently between runs (use Railway)
- Very short tasks where Modal cold start overhead is significant

## Planned integration

When implemented, the job skill will:

1. Generate a `modal_jobs/<n>.py` with `@app.function()` decorator pattern
2. Deploy via `modal deploy modal_jobs/<n>.py`
3. Schedule via `@app.function(schedule=modal.Cron("0 9 * * *"))` for cron tasks
4. Use `modal.Secret.from_name("anthropic")` for secrets

## Relationship to GitHub Actions

GHA remains the dispatcher:
- GHA workflow calls `modal run modal_jobs/<n>.py` for on-demand
- Modal's own scheduler handles cron independently once deployed
- GHA can pass inputs via CLI args or environment variables

---

*Implement this target when: there is a concrete use case requiring GPU or
Python-native ML workloads that benefit from Modal's serverless model.*
