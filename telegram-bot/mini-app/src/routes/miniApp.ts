import { Router, type IRouter } from "express";
import fs from "node:fs";
import path from "node:path";
import { runTtsCli, TTS_CACHE_DIR } from "../lib/pythonBridge";
import { logger } from "../lib/logger";

// Cache files are always "{sha256-hex}.ogg" -- validated before touching the
// filesystem so this route can never be used to read arbitrary paths.
const CACHE_FILENAME_RE = /^[a-f0-9]{64}\.ogg$/;

const router: IRouter = Router();

type LanguagesResult = {
  languages: string[];
  unsupported: Record<string, string>;
  defaultLanguage: string;
  defaultGender: string;
};

type GenerateResult =
  | { ok: true; path: string; language: string; gender: string; voice: string }
  | { ok: false; error: string; limit?: number };

router.get("/mini-app/languages", async (_req, res) => {
  try {
    const raw = await runTtsCli(["languages"]);
    const data = JSON.parse(raw) as LanguagesResult;
    res.json(data);
  } catch (err) {
    logger.error({ err }, "mini-app languages lookup failed");
    res.status(502).json({ error: "Could not load the language list right now." });
  }
});

router.post("/mini-app/generate", async (req, res) => {
  const body = (req.body ?? {}) as Record<string, unknown>;
  const text = typeof body["text"] === "string" ? body["text"] : "";
  const language = typeof body["language"] === "string" ? body["language"] : "";
  const gender = body["gender"] === "male" || body["gender"] === "female" ? body["gender"] : "";
  const rate = typeof body["rate"] === "string" ? body["rate"] : undefined;
  const pitch = typeof body["pitch"] === "string" ? body["pitch"] : undefined;
  const volume = typeof body["volume"] === "string" ? body["volume"] : undefined;

  if (!text.trim()) {
    res.status(400).json({ error: "Please type some text to convert." });
    return;
  }
  if (!language) {
    res.status(400).json({ error: "Please choose a language." });
    return;
  }
  if (!gender) {
    res.status(400).json({ error: "Please choose a voice: male or female." });
    return;
  }

  try {
    const raw = await runTtsCli(["generate"], { text, language, gender, rate, pitch, volume });
    const result = JSON.parse(raw) as GenerateResult;

    if (!result.ok) {
      const messages: Record<string, string> = {
        empty_text: "Please type some text to convert.",
        voice_not_available: "That language/voice combination isn't available yet.",
        too_long: `That's too long for one voice message (max ${result.limit ?? 5000} characters). Please shorten it.`,
        invalid_json: "Something went wrong reading your request. Please try again.",
      };
      res.status(422).json({ error: messages[result.error] ?? `Could not generate the voice: ${result.error}` });
      return;
    }

    if (!fs.existsSync(result.path)) {
      res.status(500).json({ error: "The generated voice file went missing. Please try again." });
      return;
    }

    res.setHeader("Content-Type", "audio/ogg");
    res.setHeader("X-Voice-Used", result.voice);
    // Lets the mini app build a real, direct download URL (see /mini-app/file
    // below) instead of only having the one-shot blob from this response --
    // Telegram's in-app WebView often won't trigger a download from a blob:
    // URL, but it will from a normal https link.
    res.setHeader("X-Cache-File", path.basename(result.path));
    fs.createReadStream(result.path).pipe(res);
  } catch (err) {
    logger.error({ err }, "mini-app generate failed");
    res.status(502).json({ error: "The voice generation service is unavailable right now." });
  }
});

// Serves an already-generated cache file directly (real URL, not a blob:),
// with Content-Disposition so it downloads instead of just playing inline.
// Filename is validated against the cache's own naming pattern, so this can
// only ever read files inside TTS_CACHE_DIR.
router.get("/mini-app/file/:filename", (req, res) => {
  const filename = req.params.filename;
  if (!CACHE_FILENAME_RE.test(filename)) {
    res.status(400).json({ error: "Invalid file reference." });
    return;
  }

  const filePath = path.join(TTS_CACHE_DIR, filename);
  if (!fs.existsSync(filePath)) {
    res.status(404).json({ error: "That voice message has expired. Please generate it again." });
    return;
  }

  res.setHeader("Content-Type", "audio/ogg");
  res.setHeader("Content-Disposition", 'attachment; filename="voice-message.ogg"');
  fs.createReadStream(filePath).pipe(res);
});

export default router;
