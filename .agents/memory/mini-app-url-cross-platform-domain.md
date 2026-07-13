---
name: Telegram Mini App URL must resolve a platform-specific public domain
description: Why a Telegram bot's WebApp button showed "Backend Not Configured" after moving from Replit to Railway, and how the domain is resolved now.
---

A Telegram bot's Mini App button/menu needs a real public HTTPS URL at
process-start time (`WebAppInfo(url=...)`). That URL was previously built
from `REPLIT_DEV_DOMAIN` only, which does not exist on Railway (or any other
host) — so the URL silently became `None`/stale there, and Telegram showed a
generic **"Backend Not Configured"** error inside the Mini App instead of a
clear failure.

**Why:** one env var name is not portable across hosting platforms; each
platform injects its own public-domain variable (or none, if public
networking isn't explicitly enabled).

**How to apply:** resolve the public domain with a priority chain instead of
a single hardcoded var: manual override first, then each platform's native
var, e.g. `MINI_APP_PUBLIC_DOMAIN` (manual) → `RAILWAY_PUBLIC_DOMAIN`
(Railway, requires "Public Networking" toggled on for the service) →
`REPLIT_DEV_DOMAIN` (Replit dev). If none resolve, skip showing the
Mini App button/menu entirely rather than pointing at a broken URL — a
missing feature is a better failure mode than a broken one.
