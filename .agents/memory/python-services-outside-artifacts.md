---
name: Python services outside the artifact system
description: How to run a non-web Python process (e.g. a polling Telegram bot) in a pnpm-artifact-based project when no artifact type matches.
---

The `artifacts` skill only covers `expo`, `openscad`, `react-vite`, `slides`,
`video-js` — there is no artifact type for a plain background service like a
polling Telegram bot (no HTTP port, no preview path).

**How to apply:** for this kind of process, don't force it into the artifact
system. Instead:
1. Install Python via `installProgrammingLanguage` and add packages with
   `installLanguagePackages({ language: "python", packages: [...] })` — this
   creates a root-level `pyproject.toml`/`uv.lock` managed by `uv`.
2. Put the code in its own top-level directory (e.g. `telegram-bot/`), not
   under `artifacts/` or `lib/`.
3. Register it with a plain `configureWorkflow({ name, command, outputType: "console", autoStart: true })` — no `waitForPort` needed for a polling process.

**Why:** `createArtifact` requires one of the fixed artifact types and always
sets up preview routing; a headless polling service has neither a port nor a
preview path, so it doesn't fit that model.
