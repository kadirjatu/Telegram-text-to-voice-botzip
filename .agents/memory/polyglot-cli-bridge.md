---
name: Reusing Python logic from a Node service
description: How to let a Node/Express service call into existing Python business logic without duplicating it in JS.
---

When a monorepo has both a Node service (e.g. an artifact's api-server) and a
Python service (e.g. a Telegram bot) that both need the same non-trivial
logic (voice synthesis, ML inference, a data pipeline, etc.), don't
reimplement it in the second language.

**How to apply:** add a thin CLI entrypoint to the Python package
(`python -m pkg.cli <command>`, JSON in via stdin, one JSON line out via
stdout). From Node, `spawn()` that CLI with `cwd` set to the Python
package's directory, resolving the Python interpreter path deterministically
(e.g. `<repoRoot>/.pythonlibs/bin/python3`) rather than relying on `PATH`.
Resolve `<repoRoot>` from `import.meta.url` (stable after bundling) instead
of `process.cwd()`, which differs between dev and production run commands.

**Why:** keeps one source of truth for the logic (cache, error handling,
domain rules all live in one place), avoids silent behavior drift between
two implementations, and is far less work than porting a library (e.g.
edge-tts) to the other language.
