"""Playwright automation for Threads, wrapped as a QObject worker.

Design: Playwright's SYNC api must live entirely in one thread. This worker is
moved onto a dedicated QThread; its slots (open_browser / scrape / post_reply /
close) therefore run in that thread, and it talks to the GUI purely via signals.

It drives your SYSTEM Chrome (channel="chrome") with a PERSISTENT profile, so you
log into Threads once inside this window and the session sticks across runs.

NOTE: Threads' DOM is not a stable public contract. The selectors below are
best-effort and may need one tuning pass against the live site (esp. posting).
Scraping + the whole DEMO path degrade gracefully; nothing is posted in DEMO.
"""
import os
import queue
import re
import subprocess
import threading
from urllib.parse import quote

from PySide6.QtCore import QObject, Signal, Slot

THREADS_HOME = "https://www.threads.com/"
# Threads dropped <article>; a post card is now this container (verified 2026-07).
POST_CONTAINER = '[data-pressable-container="true"]'


def _clean_post_text(raw: str, author: str = "") -> str:
    """Reduce a card's inner_text to just the post body — drop the author handle,
    a leading time token, pure engagement counts, and «Translate»."""
    out = []
    for ln in (raw or "").split("\n"):
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if low in ("translate", "перевод", "показать перевод"):
            continue
        if re.fullmatch(r"[\d][\d.,]*\s*(?:k|m|к|м|тыс|млн)?", low):
            continue                       # engagement counts (147, 2.9K …)
        if author and s == author:
            continue
        out.append(s)
    while out and re.fullmatch(r"\d+\s*(h|d|m|w|ч|д|м|нед)\.?", out[0].lower().replace(" ", "")):
        out.pop(0)                         # leading «19h» / «2d» time token
    return "\n".join(out).strip()


def _parse_count(tok) -> int | None:
    """«2.9K» → 2900, «1.2M» → 1_200_000, «1,234» → 1234."""
    if tok is None:
        return None
    t = str(tok).strip().replace(",", "").replace(" ", " ")
    m = re.match(r"^([\d]+(?:\.[\d]+)?)\s*(k|m|к|м|тыс|млн)?", t, re.I)
    if not m:
        return None
    v = float(m.group(1)); suf = (m.group(2) or "").lower()
    if suf in ("k", "к", "тыс"):
        v *= 1_000
    elif suf in ("m", "м", "млн"):
        v *= 1_000_000
    return int(v)


def _likes_from_text(raw: str) -> int:
    """Fallback: the like count is the FIRST of the trailing run of count tokens
    (Threads shows Like/Reply/Repost/Views last, in that order)."""
    lines = [l.strip() for l in (raw or "").split("\n") if l.strip()]
    run = []
    for l in reversed(lines):
        if re.fullmatch(r"[\d][\d.,]*\s*(?:k|m|к|м|тыс|млн)?", l, re.I):
            run.append(l)
        else:
            break
    run.reverse()
    return _parse_count(run[0]) or 0 if run else 0


# Read the like count straight off the DOM: find the Like button, take the
# adjacent count span. Robust vs prices/numbers inside the post body.
_LIKE_JS = r"""el=>{
  const s = el.querySelector('svg[aria-label="Like"], svg[aria-label="Unlike"]');
  if(!s) return null;
  const isCount = t => /^[\d][\d.,]*\s*[KkMm]?$/.test((t||'').trim());
  let n = s.parentElement;
  for(let k=0;k<6 && n;k++){
    if(isCount(n.innerText)) return n.innerText.trim();
    let sib = n.nextElementSibling, hop=0;
    while(sib && hop<3){ if(isCount(sib.innerText)) return sib.innerText.trim(); sib=sib.nextElementSibling; hop++; }
    n = n.parentElement;
  }
  return "";
}"""

# True when a card carries a photo/video/carousel (avatars ≤~48px are ignored).
# We skip these because the model has no vision — it can't reply with context.
_MEDIA_JS = r"""el=>{
  if (el.querySelector('video')) return true;
  const ml=['Video player','Audio is muted','Combine media into panorama'];
  for (const n of el.querySelectorAll('[aria-label]')) if (ml.includes(n.getAttribute('aria-label'))) return true;
  for (const img of el.querySelectorAll('img')) if (img.getBoundingClientRect().width > 100) return true;
  return false;
}"""


def find_chrome(explicit: str = "") -> str:
    if explicit and os.path.exists(explicit):
        return explicit
    for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ):
        if os.path.exists(p):
            return p
    return "chrome"


def launch_debug_chrome(port: int, user_data_dir: str, chrome_path: str = "") -> str:
    """Start a Chrome we can attach to over CDP. Uses a DEDICATED profile dir
    (modern Chrome blocks remote-debugging on the default profile). Returns a
    human-readable status string. Log into Threads once in the window it opens."""
    exe = find_chrome(chrome_path)
    os.makedirs(user_data_dir, exist_ok=True)
    args = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        THREADS_HOME,
    ]
    subprocess.Popen(args, close_fds=True)
    return f"Запущен Chrome с отладкой на порту {port}. Войди в Threads в этом окне."


class ThreadsWorker(QObject):
    log = Signal(str)
    browserReady = Signal(bool)           # ok?
    loginState = Signal(bool)             # logged in?
    postsScraped = Signal(list)           # [{author,url,text}, ...]
    replyPosted = Signal(int, bool, str)  # item_id, ok, message
    closed = Signal()

    def __init__(self, profile_dir: str, chrome_path: str = ""):
        super().__init__()
        self.profile_dir = profile_dir
        self.chrome_path = chrome_path or ""
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._attached = False
        # Playwright's SYNC api SEGFAULTS inside a Qt QThread (greenlet vs the Qt
        # event loop). So ALL Playwright work runs in a plain daemon thread fed by
        # a queue; we talk to the GUI only via signals (safe to emit cross-thread).
        self._q = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="pw-worker", daemon=True)
        self._thread.start()

    # ---- public API (called from the GUI thread — just enqueue) ------------
    def open_browser(self, attach_mode: bool = False, cdp_url: str = "http://127.0.0.1:9222"):
        self._q.put(("open", (attach_mode, cdp_url)))

    def scrape(self, keywords: list, limit: int, min_likes: int = 0, source: str = "feed",
               text_only: bool = True):
        self._q.put(("scrape", (list(keywords or []), int(limit), int(min_likes),
                                 source, bool(text_only))))

    def post_reply(self, item_id: int, post_url: str, reply_text: str):
        self._q.put(("post", (item_id, post_url, reply_text)))

    def close(self):
        self._q.put(("close", ()))

    def _run(self):
        while True:
            cmd, args = self._q.get()
            try:
                if cmd == "open":
                    self._do_open(*args)
                elif cmd == "scrape":
                    self._do_scrape(*args)
                elif cmd == "post":
                    self._do_post(*args)
                elif cmd == "close":
                    self._do_close()
            except Exception as e:      # never let the worker thread die
                try:
                    self.log.emit(f"Ошибка воркера: {e}")
                except Exception:
                    pass
            finally:
                self._q.task_done()
            if cmd == "close":
                break

    # ---- Playwright work (runs in the daemon thread) -----------------------
    def _do_open(self, attach_mode: bool = False, cdp_url: str = "http://127.0.0.1:9222"):
        if self._ctx is not None:
            self.browserReady.emit(True)
            self._emit_login()
            return
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            if attach_mode:
                self.log.emit(f"Подключаюсь к уже открытому Chrome ({cdp_url}) …")
                self._browser = self._pw.chromium.connect_over_cdp(cdp_url)
                ctxs = self._browser.contexts
                self._ctx = ctxs[0] if ctxs else self._browser.new_context()
                pages = self._ctx.pages
                self._page = pages[0] if pages else self._ctx.new_page()
                self._attached = True
                self.log.emit("Подключено к уже открытому Chrome.")
            else:
                kwargs = dict(
                    user_data_dir=self.profile_dir,
                    headless=False,
                    viewport={"width": 460, "height": 880},
                    args=["--disable-blink-features=AutomationControlled"],
                )
                if self.chrome_path:
                    kwargs["executable_path"] = self.chrome_path
                else:
                    kwargs["channel"] = "chrome"
                self._ctx = self._pw.chromium.launch_persistent_context(**kwargs)
                self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
                self._attached = False
                self.log.emit("Браузер открыт. Если не залогинен — войди в Threads в этом окне.")
            try:
                if "threads.com" not in (self._page.url or ""):
                    self._page.goto(THREADS_HOME, wait_until="domcontentloaded")
            except Exception:
                pass
            self.browserReady.emit(True)
            self._emit_login()
        except Exception as e:
            self.log.emit(f"Не удалось открыть/подключить браузер: {e}")
            if self.log:  # give a hint for the common CDP failure
                if attach_mode:
                    self.log.emit("Подсказка: сначала «🟢 Запустить Chrome (attach)» и войди в Threads.")
            self.browserReady.emit(False)

    def _emit_login(self):
        try:
            self._page.wait_for_timeout(1200)
            login_markers = ['a[href*="/login"]', 'text=Log in', 'text=Войти']
            logged = True
            for sel in login_markers:
                try:
                    if self._page.locator(sel).count() > 0:
                        logged = False
                        break
                except Exception:
                    continue
            self.loginState.emit(logged)
            self.log.emit("Похоже, ты залогинен." if logged
                          else "Не вижу активной сессии — войди в Threads в окне браузера.")
        except Exception:
            self.loginState.emit(False)

    def _do_close(self):
        try:
            # In attach mode DON'T close the user's Chrome — just drop our link.
            if not self._attached and self._ctx:
                self._ctx.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        finally:
            self._ctx = self._page = self._pw = self._browser = None
            self._attached = False
            self.closed.emit()

    # ---- scraping ----------------------------------------------------------
    def _do_scrape(self, keywords: list, limit: int, min_likes: int = 0, source: str = "feed",
                   text_only: bool = True):
        """source: 'feed' = infinite-scroll the For You feed for trending posts;
        'search' = keyword search; 'mix' = feed first, then top up via keywords.
        Only posts with >= min_likes are kept."""
        posts = []
        if self._page is None:
            self.log.emit("Сначала открой браузер.")
            self.postsScraped.emit(posts)
            return
        try:
            seen = set()
            if source in ("feed", "mix"):
                self.log.emit(f"Листаю ленту, ищу тренды (лайков ≥ {min_likes})…")
                try:
                    self._page.goto(THREADS_HOME, wait_until="domcontentloaded", timeout=30000)
                    self._page.wait_for_timeout(3500)
                    self._scroll_collect(posts, seen, limit, min_likes, text_only=text_only)
                except Exception as e:
                    self.log.emit(f"Лента не открылась: {e}")
            if source in ("search", "mix") and len(posts) < limit:
                for kw in (keywords or []):
                    if len(posts) >= limit:
                        break
                    kw = (kw or "").strip()
                    if not kw:
                        continue
                    self.log.emit(f"Поиск «{kw}»…")
                    try:
                        self._page.goto("https://www.threads.com/search?q=" + quote(kw),
                                        wait_until="domcontentloaded", timeout=30000)
                        self._page.wait_for_timeout(3000)
                        self._scroll_collect(posts, seen, limit, min_likes, text_only=text_only)
                    except Exception as e:
                        self.log.emit(f"Поиск «{kw}» не открылся: {e}")
            posts.sort(key=lambda p: p.get("likes", 0), reverse=True)
            tail = "" if posts else " (ничего ≥ порога — снизь «мин. лайков» или проверь логин)"
            self.log.emit(f"Собрано постов: {len(posts)}{tail}")
        except Exception as e:
            self.log.emit(f"Ошибка сбора постов: {e}")
        self.postsScraped.emit(posts)

    def _scroll_collect(self, posts, seen, limit, min_likes, text_only=True, max_scrolls=45):
        """Scroll whatever page is loaded, collecting NEW cards until we have
        `limit` posts >= min_likes, or the feed stops loading (3 stale rounds)."""
        stale = 0
        for _ in range(max_scrolls):
            if len(posts) >= limit:
                break
            cards = self._page.locator(POST_CONTAINER)
            n = cards.count()
            new_seen = 0
            for i in range(n):
                if len(posts) >= limit:
                    break
                try:
                    card = cards.nth(i)
                    raw = (card.inner_text(timeout=1200) or "").strip()
                except Exception:
                    continue
                if not raw:
                    continue
                key = " ".join(raw.split())[:100]
                if key in seen:
                    continue
                seen.add(key); new_seen += 1
                likes = self._extract_like(card)
                if likes < min_likes:
                    continue
                if text_only and self._has_media(card):
                    continue                # skip photo/video posts (no vision)
                author = ""
                try:
                    ah = card.locator('a[href^="/@"]').first
                    if ah.count() > 0:
                        author = (ah.inner_text(timeout=800) or "").strip().split("\n")[0]
                except Exception:
                    pass
                href = ""
                try:
                    a = card.locator('a[href*="/post/"]').first
                    if a.count() > 0:
                        href = a.get_attribute("href") or ""
                        if href.startswith("/"):
                            href = "https://www.threads.com" + href
                except Exception:
                    pass
                text = _clean_post_text(raw, author)
                if len(text) < 8:
                    continue
                posts.append({"author": author, "url": href, "text": text[:600], "likes": likes})
            stale = stale + 1 if new_seen == 0 else 0
            if stale >= 3:
                break                       # feed stopped loading new cards
            try:
                self._page.mouse.wheel(0, 2600)
            except Exception:
                break
            self._page.wait_for_timeout(1400)

    def _extract_like(self, card) -> int:
        try:
            n = _parse_count(card.evaluate(_LIKE_JS))
            if n is not None:
                return n
        except Exception:
            pass
        try:
            return _likes_from_text(card.inner_text(timeout=1000))
        except Exception:
            return 0

    def _has_media(self, card) -> bool:
        try:
            return bool(card.evaluate(_MEDIA_JS))
        except Exception:
            return False

    # ---- posting (LIVE only; GUI never calls this in DEMO) -----------------
    def _do_post(self, item_id: int, post_url: str, reply_text: str):
        if self._page is None:
            self.replyPosted.emit(item_id, False, "Браузер не открыт")
            return
        try:
            if post_url:
                self._page.goto(post_url, wait_until="domcontentloaded")
                self._page.wait_for_timeout(1800)
            # open the reply composer
            opened = False
            for sel in ['[aria-label="Reply"]', '[aria-label="Ответить"]',
                        'svg[aria-label="Reply"]', 'svg[aria-label="Ответить"]']:
                loc = self._page.locator(sel).first
                if loc.count() > 0:
                    loc.click()
                    opened = True
                    break
            if not opened:
                self.replyPosted.emit(item_id, False,
                                      "Не нашёл кнопку «Ответить» — нужна донастройка селекторов")
                return
            self._page.wait_for_timeout(1200)
            box = self._page.locator('[contenteditable="true"]').last
            box.click()
            box.type(reply_text, delay=45)  # human-ish typing
            self._page.wait_for_timeout(700)
            posted = False
            for sel in ['div[role="button"]:has-text("Post")',
                        'div[role="button"]:has-text("Опубликовать")',
                        'text=Опубликовать', 'text=Post']:
                b = self._page.locator(sel).last
                if b.count() > 0 and b.is_enabled():
                    b.click()
                    posted = True
                    break
            if not posted:
                self._page.keyboard.press("Control+Enter")
                posted = True
            self._page.wait_for_timeout(1500)
            self.replyPosted.emit(item_id, True, "Отправлено — проверь в окне браузера")
        except Exception as e:
            self.replyPosted.emit(item_id, False, f"Ошибка публикации: {e}")
