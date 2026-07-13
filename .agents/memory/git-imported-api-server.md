---
name: Shared api-server missing after git import
description: Why the workspace's shared api-server (and mockup-sandbox) don't work after a git import, and how to fix it
---

When a pnpm-workspace-stack project is imported from a git repo (rather than created fresh through the platform), the baseline `artifacts/api-server` and `artifacts/mockup-sandbox` directories can already exist in the repo (with `.replit-artifact/artifact.toml`) but are NOT registered as live artifacts — `listArtifacts()` returns empty and `WorkflowsRestart` on `artifacts/api-server: API Server` fails with "doesn't exist". There is no `createArtifact` type for adopting an existing `api`-kind directory.

**Why:** artifact registration is platform-side state, not just files on disk; a raw git import only brings the files, not that registration. Also `node_modules` are gitignored, so a fresh import needs `pnpm install` before anything in the workspace (including `artifacts/api-server`) can run.

**How to apply:** if the project depends on `artifacts/api-server` (e.g. a Telegram Mini App or any other consumer hitting `/api/*`) and it's not reachable:
1. Run `pnpm install` at the repo root once (installs the whole workspace, not just one package).
2. Register it as a plain workflow (not an artifact) via `configureWorkflow`: command `cd <repo-root> && PORT=8080 pnpm --filter @workspace/api-server run dev`, `waitForPort: 8080`, `outputType: "console"`, `autoStart: true`. The api-server's own Express app already mounts everything under `/api`, so once the workflow's port becomes the repl's exposed port, `https://<domain>/api/...` works with no other proxy config needed.
3. Do not use `createArtifact` for this — no matching artifact type exists for adopting a pre-existing `api`-kind service directory.
