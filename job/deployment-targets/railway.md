# Deployment Target: Railway

**Status: STUB — not yet implemented**

---

## When to use

- Worker needs to stay alive persistently between runs
- Task is a long-lived process (queue consumer, webhook listener, polling loop)
- Agentic Runner that benefits from warm state between invocations

## Not appropriate for

- One-off or scheduled tasks (GHA is simpler)
- Tasks that are truly stateless (Modal or GHA is cheaper)

## Planned integration

When implemented, the job skill will:

1. Generate a `Dockerfile` for the worker
2. Deploy via Railway's GHA action or `railway up`
3. Use Railway's native cron or keep-alive for persistent workers
4. Store secrets via Railway's environment variable UI

## Relationship to GitHub Actions

GHA remains the CI/CD layer:
- GHA builds and deploys the Railway service on merge to main
- Railway runs the service persistently
- GHA can also trigger Railway deploys via webhook

---

*Implement this target when: there is a concrete use case requiring a
persistent, stateful worker process.*
