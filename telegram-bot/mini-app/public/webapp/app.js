// Same-origin app served under /api/app, calling the API under /api/mini-app.
// No build step -- plain HTML/CSS/JS, kept intentionally simple.
const API_BASE = "/api/mini-app";

const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const textEl = document.getElementById("text");
const charCountEl = document.getElementById("charCount");
const languageGrid = document.getElementById("languageGrid");
const genderButtons = Array.from(document.querySelectorAll(".gender-btn"));
const generateBtn = document.getElementById("generateBtn");
const generateBtnLabel = document.getElementById("generateBtnLabel");
const statusMsg = document.getElementById("statusMsg");
const playerWrap = document.getElementById("playerWrap");
const player = document.getElementById("player");
const downloadLink = document.getElementById("downloadLink");
const rateSelect = document.getElementById("rateSelect");
const pitchSelect = document.getElementById("pitchSelect");
const volumeSelect = document.getElementById("volumeSelect");

let selectedLanguage = null;  // null = none chosen, "auto" = auto-detect
let selectedGender = "female";
let currentAudioUrl = null;

textEl.addEventListener("input", () => {
  charCountEl.textContent = String(textEl.value.length);
  updateGenerateEnabled();
});

genderButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    genderButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    selectedGender = btn.dataset.gender;
  });
});

function updateGenerateEnabled() {
  // "auto" counts as a valid language selection
  generateBtn.disabled = !(textEl.value.trim() && selectedLanguage);
}

function setStatus(message, isError) {
  statusMsg.textContent = message || "";
  statusMsg.classList.toggle("error", Boolean(isError));
}

async function loadLanguages() {
  try {
    const res = await fetch(`${API_BASE}/languages`);
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    renderLanguages(data.languages || [], data.unsupported || {}, data.defaultLanguage);
  } catch (err) {
    languageGrid.innerHTML = "";
    setStatus("Language list load nahi hui. Page refresh karke dekho.", true);
  }
}

function renderLanguages(languages, unsupported, defaultLanguage) {
  languageGrid.innerHTML = "";

  // Auto-detect chip — first in the list
  const autoChip = document.createElement("button");
  autoChip.type = "button";
  autoChip.className = "chip auto-chip";
  autoChip.textContent = "🔍 Auto-detect";
  autoChip.title = "Automatically detect the language from your text";
  autoChip.addEventListener("click", () => {
    selectedLanguage = "auto";
    Array.from(languageGrid.querySelectorAll(".chip")).forEach((c) => c.classList.remove("active"));
    autoChip.classList.add("active");
    updateGenerateEnabled();
  });
  languageGrid.appendChild(autoChip);

  languages.forEach((name) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = name;
    chip.addEventListener("click", () => {
      selectedLanguage = name;
      Array.from(languageGrid.querySelectorAll(".chip")).forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      updateGenerateEnabled();
    });
    languageGrid.appendChild(chip);

    if (name === defaultLanguage) {
      chip.click();
    }
  });

  Object.entries(unsupported).forEach(([name, note]) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip unsupported";
    chip.textContent = `${name} 🚫`;
    chip.title = note;
    chip.addEventListener("click", () => setStatus(note, true));
    languageGrid.appendChild(chip);
  });
}

generateBtn.addEventListener("click", async () => {
  const text = textEl.value.trim();
  if (!text || !selectedLanguage) return;

  generateBtn.disabled = true;
  generateBtnLabel.textContent = "🎤 Generating…";
  setStatus("Voice generate ho rahi hai, thoda ruko...");
  playerWrap.classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        language: selectedLanguage,   // "auto" or a language name
        gender: selectedGender,
        rate: rateSelect.value,
        pitch: pitchSelect.value,
        volume: volumeSelect.value,
      }),
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.error || `Server error (${res.status})`);
    }

    const cacheFile = res.headers.get("X-Cache-File");
    const blob = await res.blob();
    if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = URL.createObjectURL(blob);

    player.src = currentAudioUrl;
    // Telegram's in-app WebView frequently ignores blob: URLs / the anchor
    // "download" attribute (silent no-op on tap). A real https URL to this
    // same server survives that -- use it when we have one, falling back to
    // the blob URL (still fine in a normal desktop/mobile browser).
    downloadLink.href = cacheFile ? `${API_BASE}/file/${cacheFile}` : currentAudioUrl;
    playerWrap.classList.remove("hidden");
    setStatus("✅ Voice ban gayi!");

    if (tg && tg.HapticFeedback) {
      tg.HapticFeedback.notificationOccurred("success");
    }
  } catch (err) {
    setStatus(err.message || "Kuch gadbad ho gayi, dobara try karo.", true);
  } finally {
    generateBtn.disabled = false;
    generateBtnLabel.textContent = "✨ Generate Voice";
    updateGenerateEnabled();
  }
});

// Inside Telegram's in-app WebView, tapping a normal <a> (even with a real
// https URL and download attribute) often does nothing -- the WebView
// doesn't have a download manager for it. Telegram.WebApp.openLink() hands
// the URL to the device's real browser, which does know how to download it.
downloadLink.addEventListener("click", (e) => {
  if (tg && typeof tg.openLink === "function" && downloadLink.href.startsWith("http")) {
    e.preventDefault();
    tg.openLink(downloadLink.href);
  }
  // Otherwise (plain browser, no Telegram WebApp, or still a blob: URL
  // fallback), let the anchor's normal/download behavior proceed untouched.
});

loadLanguages();
