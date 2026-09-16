"""Preference-learning store.

Records which reply variant the owner picked as BEST in DEMO, then feeds recent
picks back into the generation prompt as few-shot examples so the model mimics
the owner's taste over time. This is IN-CONTEXT learning (examples in the
prompt) — no model weights are trained (you can't fine-tune the API models here),
but in practice the output drifts toward what you keep choosing.
"""
import json
import config

MAX_KEEP = 400            # cap the file size
EXAMPLES_IN_PROMPT = 8    # recent picks injected into each generation


def _load() -> list:
    try:
        with open(config.PREFS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list) -> None:
    try:
        with open(config.PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(items[-MAX_KEEP:], f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def count() -> int:
    return len(_load())


def add(post: str, chosen: str, rejected=None, ts: str = "") -> int:
    items = _load()
    items.append({
        "post": (post or "")[:400],
        "chosen": (chosen or "")[:400],
        "rejected": [(r or "")[:300] for r in (rejected or [])][:3],
        "ts": ts,
    })
    _save(items)
    return len(items)


def examples(k: int = EXAMPLES_IN_PROMPT) -> list:
    """Most recent picks (newest last) for the prompt few-shot block."""
    return _load()[-k:]
