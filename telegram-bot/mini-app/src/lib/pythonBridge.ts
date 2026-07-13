import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import { spawn } from "node:child_process";

// After the esbuild bundle step every module in this server ends up inside
// a single dist/index.mjs file, so import.meta.url is the same no matter
// which source file this runs from -- always telegram-bot/mini-app/dist.
// Walking up from there gives a stable, cwd-independent path to the repo
// root, whether this process was started from the package dir (dev) or the
// repo root (production).
const DIST_DIR = path.dirname(fileURLToPath(import.meta.url));
const API_SERVER_DIR = path.resolve(DIST_DIR, "..");
const TELEGRAM_BOT_PARENT_DIR = path.resolve(API_SERVER_DIR, "..");
const REPO_ROOT = path.resolve(TELEGRAM_BOT_PARENT_DIR, "..");

export const TELEGRAM_BOT_DIR = path.join(REPO_ROOT, "telegram-bot");
export const MINI_APP_PUBLIC_DIR = path.join(API_SERVER_DIR, "public", "webapp");
// Same cache dir tts/config.py writes generated .ogg files into -- used to
// serve a direct, real (non-blob) download URL for the Telegram mini app.
export const TTS_CACHE_DIR = path.join(TELEGRAM_BOT_DIR, "data", "cache");

const PYTHON_BIN_CANDIDATES = [
  path.join(REPO_ROOT, ".venv", "bin", "python3"),          // uv / Docker (Railway)
  path.join(REPO_ROOT, ".pythonlibs", "bin", "python3"),    // Replit dev
  "python3",
];

function resolvePythonBin(): string {
  for (const candidate of PYTHON_BIN_CANDIDATES) {
    if (candidate === "python3" || fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return "python3";
}

/**
 * Runs `python -m tts.cli <args>` from the telegram-bot directory, reusing
 * the exact same TTS pipeline (voices, cache, error handling) the Telegram
 * bot itself uses -- no separate implementation to keep in sync.
 */
export function runTtsCli(args: string[], stdinPayload?: unknown): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(resolvePythonBin(), ["-m", "tts.cli", ...args], {
      cwd: TELEGRAM_BOT_DIR,
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    child.on("error", (err) => reject(err));

    child.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            `tts.cli ${args.join(" ")} exited with code ${code}: ${stderr.slice(-500)}`,
          ),
        );
        return;
      }
      resolve(stdout.trim());
    });

    if (stdinPayload !== undefined) {
      child.stdin.write(JSON.stringify(stdinPayload));
    }
    child.stdin.end();
  });
}
