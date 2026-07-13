---
name: Plain workflow public HTTPS exposure on PNPM_WORKSPACE stack
description: Why a plain (non-artifact) workflow's port isn't reachable via the public repl domain on the PNPM_WORKSPACE stack, and how to fix it.
---

On a repl using `[agent] stack = "PNPM_WORKSPACE"`, public HTTPS routing is driven by
registered artifacts' `previewPath`/`services` in their `.replit-artifact/artifact.toml`.
A plain `configureWorkflow` service (not a registered artifact) binds and listens on its
port fine locally (`curl localhost:<port>` works), but the public `$REPLIT_DEV_DOMAIN`
request 404s — the proxy only forwards paths owned by a registered artifact, it does not
fall back to "whichever workflow happens to hold a port."

**Why:** this contradicts the older assumption (see `git-imported-api-server.md`) that a
plain workflow's port automatically "becomes the repl's exposed port." That held only when
no artifacts were registered yet; once even one artifact exists (e.g. an auto-registered
mockup-sandbox/design canvas), the proxy switches to artifact-based routing exclusively.

**How to apply:** if a service must be reachable over the public HTTPS domain (e.g. a
Telegram Mini App webapp URL) but you deliberately don't want it registered as an artifact,
add an explicit `[[ports]]` mapping in `.replit` (`localPort = <port>`, `externalPort = 80`)
via `verifyAndReplaceDotReplit` (write the full modified TOML to a temp file — must live inside
the workspace root, e.g. `.local/tmp_dotreplit.toml`, or the call is rejected — then call the
tool; never edit `.replit` by hand). Verify with `curl https://$REPLIT_DEV_DOMAIN/<path>`
after restarting the workflow, not just `curl localhost:<port>`.

This `[[ports]]` entry has been observed missing again in a later session despite being added
and verified working before (cause unconfirmed — possibly reverted by an unrelated `.replit`
change). Don't assume a past fix still holds: re-check `.replit` for the `[[ports]]` block and
re-curl the public domain whenever a "works locally, broken on the public URL / in the Telegram
Mini App" report comes in, even if this was already fixed in an earlier session.
