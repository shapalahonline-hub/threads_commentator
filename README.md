# Threads Commentator

Local always-on-top desktop app. Pulls (or accepts) trending Threads posts,
generates witty **Russian** reply variants via **OpenRouter**, and — in LIVE
mode only — posts a reply you approve into Threads through your logged-in Chrome.

- **DEMO mode** (default): generates comments, **never posts**. This is what you
  look at first.
- **LIVE mode**: adds a per-post *“Одобрить и опубликовать”* button. **You approve
  every single post by hand** (there is a confirm dialog + a daily cap).

Brands: `outlet.market.kz` (dead-stock outlet) + Envizhl. Model default:
`x-ai/grok-4-fast` (cheap, low-refusal), fallback `deepseek/deepseek-v3.2`.

## Run in dev (fastest way to see the DEMO)
```powershell
cd C:\Users\Tard\Documents\work\threads_commentator
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```
1. Click **⚙** → paste your **OpenRouter API key** → Save.
2. Click **🧪 Примеры** (or **📋 Вставить посты**) → **✨ Сгенерировать комментарии**.
   You'll see 3 Russian reply variants per post. Nothing is posted in DEMO.
3. For real posts: **🌐 Открыть браузер / Войти** → log into Threads in the window
   that opens (session is saved) → **⤓ Собрать посты**.

## Go LIVE (when you're happy with the comments)
Switch the toggle to **LIVE**. Only *scraped* posts (which have a URL) can be
posted to. Each post asks for confirmation and counts against the daily cap.

## Build the .exe
```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
# -> dist\ThreadsCommentator\ThreadsCommentator.exe
```
Uses your **system Chrome** (nothing bundled). If Chrome isn't found:
`.venv\Scripts\python -m playwright install chromium`.

## Files
- `app.py` — GUI (PySide6), DEMO/LIVE, wiring.
- `ai.py` — OpenRouter client + reply parsing.
- `threads_bot.py` — Playwright automation (open browser, scrape, post).
- `config.py` — settings (in `%APPDATA%\ThreadsCommentator`).
- `samples.py` — built-in demo posts.

## Known caveats (honest)
- **Threads selectors aren't a public contract.** Scraping + posting selectors in
  `threads_bot.py` are best-effort and may need one tuning pass against live
  Threads. The DEMO (generation) path works regardless via Примеры/Вставить.
- **Browser automation of Threads is against Meta ToS** — run slow, few accounts,
  approve each post. Don't attach anything irreplaceable to the account.
- Posting only works on **scraped** posts (they carry the post URL); pasted/sample
  posts are for judging comment quality, not for posting.
