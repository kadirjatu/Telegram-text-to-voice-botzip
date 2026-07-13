---
name: Sharing Python logic between two same-language services
description: How to reuse an existing Python package's business logic from a second, new Python service in the same repo without duplicating it.
---

When both the existing service and the new one are Python, reuse the existing package by inserting its parent directory onto `sys.path` at import time (e.g. in the new service's config/bootstrap module) and importing it directly — `from tts import generator as bot_generator`. Call the existing module's real functions (including "private" underscore-prefixed ones if needed) instead of re-implementing the logic.

**Why:** The polyglot CLI-bridge pattern (`polyglot-cli-bridge.md`) exists to cross a language boundary (e.g. Node calling Python). It's unnecessary overhead — a subprocess per call, JSON serialization, no shared exception types — when both sides are already Python and can just import each other's modules in-process.

**How to apply:** New same-language service needs functionality that already exists in another Python package in the repo. Add a `sys.path.insert(0, str(path_to_sibling_dir))` in the new service's settings/bootstrap file (so it runs once, before other local modules import the sibling package), then import and call the sibling's real functions/classes. Re-export exception classes from the sibling if the new service needs to catch them by name.
