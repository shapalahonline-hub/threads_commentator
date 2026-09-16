# Threads Commentator — Design Handoff

**Goal for you (design pass):** make this look good and on-brand. It's fully functional but visually plain (hand-rolled dark theme). Keep it a tight, premium, **always-on-top side panel**.

---

## What the app is
A local **Windows desktop app** (Python + **PySide6 / Qt**). It's an AI "reply-hijack" tool for **Threads**: attaches to a logged-in Chrome, scrapes trending Kazakh/Russian posts, generates witty **Russian** reply variants via OpenRouter (Grok), and — only in LIVE mode — posts a human-approved reply. Promotes **Envizhl** + **outlet.market.kz**.

Two modes, and the distinction is **safety-critical, not decorative**:
- **DEMO** (default) — generates comments, **never posts**. Signalled **green**.
- **LIVE** — posts approved replies. Signalled **red**.

---

## Hard constraints (it's Qt, not web — read this)
- **All styling = Qt Style Sheets (QSS) + widget layout, and it ALL lives in `app.py`.** The QSS is the `STYLE` string near the bottom of `app.py`. Widget construction is in `MainWindow._build_ui`, and the `PostCard`, `SettingsDialog`, `PasteDialog` classes.
- **Do NOT touch** `threads_bot.py`, `ai.py`, `config.py`, `samples.py` — that's logic. Stay in `app.py`.
- **Don't break these hooks the code relies on** (rename only if you update `app.py` too):
  - objectNames used for state styling: `#genbtn`, `#postbtn` (LIVE action), `#demobtn` (DEMO disabled action), `#banner`, and the dynamic `banner[live="true"]` property selector, `#card`, `#title`, `#log`, `#posttext`, `#cardhead`, `#cardstatus`.
  - The mode banner text/colour is set in `MainWindow._update_banner`; the DEMO/LIVE action button swaps in `PostCard.set_mode`.
- Keep it **single-file / dependency-light** — no extra pip libs, no QML rewrite. Button icons are currently emoji in the label text; you may keep them or swap for inline SVG, your call.
- **Keep always-on-top** and keep the **green(DEMO)/red(LIVE) cue unmistakable**.
- The window is **narrow (~560px) and tall** — a docked control panel. Keep it compact; assume it sits on the side of the screen.

## Brand (Envizhl)
Black-first, minimal, **one red accent**, white / line-art, mono-blueprint feel. Type: **Exo 2 / Montserrat**, and **IBM Plex** for RU/KZ + ₸. The app is already dark (`#0e0e0e`) — push it from "plain dark" to **intentional and premium**: real type scale, spacing rhythm, a proper accent system (one red), clear card hierarchy, nicer buttons, a defined header. (Ask the owner for the Envizhl brandbook — it's in the Obsidian vault under `Envizhl/Бренд/`.)

## UI inventory (everything to restyle)
1. **Header** — title "Threads Commentator", a "Поверх окон" (always-on-top) checkbox, a ⚙ settings button.
2. **Mode row** — `DEMO` / `LIVE` radio buttons, then the big **colour banner** (green vs red).
3. **Source controls** —
   - keywords text field;
   - `🟢 Запустить Chrome (attach)`;
   - `🌐 Открыть браузер / Войти` + `⤓ Собрать посты`;
   - `📋 Вставить посты` / `🧪 Примеры` / `🗑 Очистить`.
4. **Primary action** — `✨ Сгенерировать комментарии` (currently the single inverted/light button — treat as the hero CTA).
5. **Post cards** (scrolling list) — each: author handle, the post text, variant chips `V1 / V2 / V3`, an editable reply textbox, `↻ Ещё варианты`, and the **mode-dependent action** (DEMO = disabled grey "не публикуется"; LIVE = red "✓ Одобрить и опубликовать"), plus a per-card status line.
6. **Log console** at the bottom (monospace, muted).
7. **Settings dialog** + **Paste dialog** — plain Qt forms (API key, model, prompt, keywords, delays, CDP settings). Give them the same polish.

## How to preview & deliver
- Run it live (real Cyrillic renders here, unlike the static shot): `.venv\Scripts\python app.py`, then click `🧪 Примеры` to fill the card list.
- **Deliver back the edited `app.py`** (or just the new `STYLE` block + any `_build_ui`/`PostCard` layout tweaks).

## Current look
See `ui_current.png` — **layout/proportions reference only**; the text shows as boxes because it was captured headless (no font). On Windows it renders normal Russian text.
