"""Settings + prompt composition for Threads Commentator.

Settings live in %APPDATA%/ThreadsCommentator/settings.json. Instead of making
the user hand-write a system prompt, we keep structured brand info + behaviour
knobs and COMPOSE the prompt from them (see compose_prompt). The Settings dialog
shows a live read-only preview of the composed prompt.
"""
import json
import os
from dataclasses import dataclass, field, asdict

APP_NAME = "ThreadsCommentator"


def _data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


DATA_DIR = _data_dir()
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
PREFS_PATH = os.path.join(DATA_DIR, "preferences.json")   # learned best-comment picks
PROFILE_DIR = os.path.join(DATA_DIR, "chrome_profile")
CDP_PROFILE_DIR = os.path.join(DATA_DIR, "chrome_cdp")

# Option lists for the settings UI dropdowns
TONES = ["мягко", "дружелюбно", "остро", "дерзко"]
PROMOS = ["не упоминать", "ненавязчиво", "прямо"]
EMOJIS = ["нет", "мало", "нормально"]
LENGTHS = ["очень коротко", "коротко", "средне"]
LANGS = ["русский", "казахский", "микс рус+каз"]


@dataclass
class Settings:
    openrouter_api_key: str = ""
    model: str = "x-ai/grok-4-fast"
    fallback_model: str = "deepseek/deepseek-v3.2"
    keywords: list = field(default_factory=lambda: [
        "скидки", "распродажа", "шопинг", "находка", "дёшево",
    ])
    # ── Brand / offer (the "key info" the owner fills in) ──
    brand_name: str = "outlet.market.kz"
    brand_pitch: str = "аутлет: дёшево продаём дедсток и распродажи"
    target_link: str = "https://outlet.market.kz"
    audience: str = "Казахстан, люди ищут скидки и выгодные находки"
    # ── Behaviour knobs ──
    tone: str = "остро"            # TONES
    promo: str = "ненавязчиво"     # PROMOS
    emoji: str = "мало"            # EMOJIS
    length: str = "коротко"        # LENGTHS
    humor: bool = True
    language: str = "русский"      # LANGS
    extra_instructions: str = ""   # additive, optional
    prompt_override: str = ""      # advanced: if set, used verbatim
    # ── Generation ──
    replies_per_post: int = 3
    temperature: float = 0.95
    max_tokens: int = 300
    # ── App / browser ──
    always_on_top: bool = True
    daily_cap: int = 15
    min_delay_sec: int = 180
    max_delay_sec: int = 600
    scrape_limit: int = 8
    # Scrape source & trend filter
    source: str = "feed"        # feed = scroll For You for trending · search = keywords · mix
    min_likes: int = 200        # only keep posts with at least this many likes
    text_only: bool = True      # only comment on text-only posts (model has no vision)
    attach_mode: bool = False
    cdp_url: str = "http://127.0.0.1:9222"
    cdp_port: int = 9222
    chrome_path: str = ""

    @classmethod
    def load(cls) -> "Settings":
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**known)
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)


# ── Prompt composition ───────────────────────────────────────────────────────
_TONE = {
    "мягко": ("мягко, тепло и вежливо",
              "Будь деликатным и поддержи человека — без сарказма."),
    "дружелюбно": ("дружелюбно и легко",
              "Пиши по-приятельски, на «ты», непринуждённо."),
    "остро": ("остроумно, с иронией и характером",
              "Добавь острый угол или ироничное наблюдение — по-доброму, без токсичности."),
    "дерзко": ("дерзко, саркастично и цепляюще",
              "Смело подколи ситуацию из поста и сыронизируй, будь смешным и живым — "
              "но БЕЗ оскорблений человека, грубости и мата."),
}
_PROMO = {
    "не упоминать": "НЕ упоминай бренд и ссылку вообще — только живой комментарий по теме.",
    "ненавязчиво": "Упомяни {brand} максимум в ОДНОМ из вариантов и только если это звучит "
                   "органично; остальные варианты — чистая реакция на пост.",
    "прямо": "Можешь открыто предложить {brand} как решение проблемы из поста — но без "
             "давления и без «спешите/успейте».",
}
_EMOJI = {"нет": "Без эмодзи.",
          "мало": "Максимум один эмодзи и только по делу.",
          "нормально": "Уместные эмодзи — ок (1–2)."}
_LENGTH = {"очень коротко": "Очень коротко: до ~8 слов, панч.",
           "коротко": "Коротко: одно предложение.",
           "средне": "1–2 предложения, не длиннее."}
_LANG = {"русский": "Пиши на грамотном русском.",
         "казахский": "Пиши на казахском.",
         "микс рус+каз": "Можно естественно смешивать русский и казахский, как в реальных комментах."}


def compose_prompt(s: "Settings") -> str:
    """Build the system prompt from the structured knobs. If prompt_override is
    set, use it verbatim (advanced escape hatch)."""
    if (s.prompt_override or "").strip():
        return s.prompt_override.strip()
    tone_desc, tone_rule = _TONE.get(s.tone, _TONE["остро"])
    promo = _PROMO.get(s.promo, _PROMO["ненавязчиво"]).format(brand=s.brand_name or "бренд")
    lines = [
        f"Ты — живой человек в комментариях Threads, который {tone_desc} отвечает на чужие "
        f"посты. Ты НЕ маркетолог и НЕ бот. Комментарий должен цеплять и звучать как реальный "
        f"человек в комментах, а не как реклама.",
        "",
        "Контекст (используй ТОЛЬКО когда это уместно посту):",
        f"— Бренд: {s.brand_name} — {s.brand_pitch}." if s.brand_name else "",
        f"— Ссылка: {s.target_link}." if s.target_link else "",
        f"— Аудитория: {s.audience}." if s.audience else "",
        "",
        "Правила:",
        f"— {tone_rule}",
        f"— {promo}",
        f"— {_LENGTH.get(s.length, _LENGTH['коротко'])}",
        f"— {_EMOJI.get(s.emoji, _EMOJI['мало'])}",
        ("— Обязательно с юмором или иронией." if s.humor else "— Без шуток, строго по делу."),
        f"— {_LANG.get(s.language, _LANG['русский'])}",
        "— Цепляйся за КОНКРЕТНУЮ деталь поста, а не общими словами.",
        "— Категорически без рекламных штампов: «отличный выбор», «рекомендую», «спешите», "
        "«успейте», без канцелярита и пафоса.",
        "— Без хэштегов и без «ссылка в био».",
    ]
    if (s.extra_instructions or "").strip():
        lines += ["", f"Доп. указания владельца: {s.extra_instructions.strip()}"]
    return "\n".join(x for x in lines if x is not None)
