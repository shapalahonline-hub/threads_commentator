"""OpenRouter client — generates witty Russian reply variants for a post.

Endpoint + headers verified against OpenRouter docs (July 2026):
  POST https://openrouter.ai/api/v1/chat/completions   (Bearer auth, OpenAI-compatible body)
  GET  https://openrouter.ai/api/v1/models             (no auth; for the live model dropdown)
"""
import json
import re
import requests

BASE = "https://openrouter.ai/api/v1"

# Handy presets for the dropdown (user can type any slug; app also fetches the live list).
MODEL_PRESETS = [
    "x-ai/grok-4-fast",        # primary: cheap, fast, low-refusal, edgy-capable
    "x-ai/grok-4.1-fast",      # newer sibling, same price
    "deepseek/deepseek-v3.2",  # cheapest strong-Russian fallback
    "deepseek/deepseek-chat",  # alias tracking latest DeepSeek V3
    "qwen/qwen-2.5-72b-instruct",
]


class OpenRouterError(Exception):
    pass


class OpenRouter:
    def __init__(self, api_key: str,
                 referer: str = "https://outlet.market.kz",
                 title: str = "Threads Commentator"):
        self.api_key = (api_key or "").strip()
        self.referer = referer
        self.title = title

    def _headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Optional (ranking only) — harmless to send.
        if self.referer:
            h["HTTP-Referer"] = self.referer
        if self.title:
            h["X-Title"] = self.title
        return h

    def list_models(self) -> list:
        """Return sorted list of available model slugs (no auth needed)."""
        r = requests.get(f"{BASE}/models", timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        return sorted(m["id"] for m in data if "id" in m)

    def generate_replies(self, post_text: str, n: int, system_prompt: str,
                         model: str, temperature: float = 0.9,
                         max_tokens: int = 220, target_link: str = "",
                         examples: list = None) -> list:
        if not self.api_key:
            raise OpenRouterError("Не задан OpenRouter API-ключ (Настройки).")
        sys_msg = system_prompt
        if examples:
            picked = [f'- «{(e.get("chosen") or "").strip()}»'
                      for e in examples if (e.get("chosen") or "").strip()]
            if picked:
                sys_msg += ("\n\nВЛАДЕЛЕЦ РАНЬШЕ ОТМЕЧАЛ такие комменты как ЛУЧШИЕ — "
                            "подражай их манере, длине, тону и юмору (НЕ копируй дословно, "
                            "пиши новое под конкретный пост):\n" + "\n".join(picked[-8:]))
        user = (
            "Вот пост в Threads, на который надо ответить:\n"
            f'"""\n{post_text.strip()}\n"""\n\n'
            f"Сгенерируй {n} ЗАМЕТНО РАЗНЫХ по подходу варианта комментария — разные шутки и "
            f"углы, не перефразируй один и тот же. Каждый цепляющий и живой, как реальный "
            f"коммент, а не реклама. Верни СТРОГО JSON-массив из {n} строк и больше ничего. "
            'Пример: ["вариант 1", "вариант 2"].'
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            r = requests.post(f"{BASE}/chat/completions", headers=self._headers(),
                              json=payload, timeout=90)
        except requests.RequestException as e:
            raise OpenRouterError(f"Сеть: {e}")
        if r.status_code >= 400:
            raise OpenRouterError(f"HTTP {r.status_code}: {r.text[:300]}")
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise OpenRouterError(f"Неожиданный ответ API: {e}")
        return _parse_replies(content, n)


def _parse_replies(content: str, n: int) -> list:
    content = (content or "").strip()
    # strip ```json fences if present
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content).strip()
    # 1) whole thing is a JSON array
    for candidate in (content, _first_array(content)):
        if not candidate:
            continue
        try:
            arr = json.loads(candidate)
            if isinstance(arr, list) and arr:
                out = [str(x).strip() for x in arr if str(x).strip()]
                if out:
                    return out[:n]
        except Exception:
            pass
    # 2) fallback: split into lines, strip bullets/numbering/quotes
    lines = []
    for ln in content.splitlines():
        ln = re.sub(r'^\s*(?:[-*•]|\d+[.)])\s*', '', ln).strip().strip('"').strip()
        if ln:
            lines.append(ln)
    if lines:
        return lines[:n]
    return [content][:n]


def _first_array(text: str):
    m = re.search(r"\[.*\]", text, re.DOTALL)
    return m.group(0) if m else None
