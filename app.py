"""Threads Commentator — local desktop app.

DEMO mode: scrapes/loads posts and generates witty Russian replies, but NEVER
posts. LIVE mode: same, plus a per-item "Approve & Post" that types the reply
into Threads via your logged-in browser. Human approves every single post.

Run in dev:  python app.py
Build .exe:  see build_exe.ps1
"""
import os
import random
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import (Qt, QThreadPool, QRunnable, QObject, Signal, Slot,
                            QByteArray, QSize, QTimer)
from PySide6.QtGui import (QFont, QFontDatabase, QColor, QIcon, QPixmap, QPainter)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QPlainTextEdit, QTextEdit, QScrollArea, QFrame,
    QCheckBox, QRadioButton, QButtonGroup, QDialog, QSpinBox,
    QDoubleSpinBox, QComboBox, QMessageBox, QSizePolicy, QGraphicsDropShadowEffect,
)

import config
import ai
import prefs
from samples import SAMPLE_POSTS
from threads_bot import ThreadsWorker, launch_debug_chrome

DEMO, LIVE = "DEMO", "LIVE"


# ── line-art icons (single-file, no assets) ─────────────────────────────────
ICONS = {
 "gear": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
 "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/>',
 "download": '<path d="M12 3v11"/><path d="M8 11l4 4 4-4"/><path d="M5 20h14"/>',
 "clipboard": '<rect x="7" y="4" width="10" height="17" rx="2"/><path d="M9 4h6v3H9z"/>',
 "flask": '<path d="M9 3h6"/><path d="M10 3v6l-4.5 8.5A2 2 0 0 0 7.3 21h9.4a2 2 0 0 0 1.8-3.5L14 9V3"/>',
 "trash": '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/>',
 "sparkles": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
 "refresh": '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/>',
 "check": '<path d="M5 12l4.5 4.5L19 7"/>',
 "power": '<path d="M12 4v8"/><path d="M6.3 7.3a8 8 0 1 0 11.4 0"/>',
 "ban": '<circle cx="12" cy="12" r="9"/><path d="M6 6l12 12"/>',
}


def svg_icon(key, color="#dfe2e5", size=16, sw=1.6):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
           f'stroke-linejoin="round">{ICONS[key]}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); r.render(p); p.end()
    return QIcon(pm)


def _tracked(label, px=11, spacing=18, upper=True, family="IBM Plex Mono", weight=QFont.Medium):
    f = QFont(family, px); f.setWeight(weight)
    f.setLetterSpacing(QFont.PercentageSpacing, 100 + spacing)
    if upper:
        f.setCapitalization(QFont.AllUppercase)
    label.setFont(f)


def section(text):
    """A tracked uppercase section label + hairline rule."""
    row = QHBoxLayout(); row.setSpacing(10)
    lab = QLabel(text); lab.setStyleSheet("color:#6b7178; background:transparent;")
    _tracked(lab, 10, 18)
    line = QFrame(); line.setFixedHeight(1)
    line.setStyleSheet("background:rgba(255,255,255,0.08);")
    line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    row.addWidget(lab); row.addWidget(line, 1)
    return row


def shadow(w, blur=26, dy=8, color=QColor(255, 255, 255, 55)):
    e = QGraphicsDropShadowEffect(w)
    e.setBlurRadius(blur); e.setXOffset(0); e.setYOffset(dy); e.setColor(color)
    w.setGraphicsEffect(e)


@dataclass
class PostItem:
    id: int
    author: str
    url: str
    text: str
    likes: int = 0
    replies: list = field(default_factory=list)
    chosen: int = 0
    posted: bool = False
    done: bool = False       # processed in a run (picked in DEMO / posted in LIVE)


# ----- AI generation on a thread pool ---------------------------------------
class _AISignals(QObject):
    done = Signal(int, list)   # item_id, replies
    error = Signal(int, str)   # item_id, message


class GenTask(QRunnable):
    def __init__(self, api_key, item, settings, signals):
        super().__init__()
        self.api_key = api_key
        self.item = item
        self.s = settings
        self.signals = signals

    def run(self):
        client = ai.OpenRouter(self.api_key, referer=self.s.target_link)
        prompt = config.compose_prompt(self.s)
        last = "unknown error"
        models = [self.s.model]
        if self.s.fallback_model and self.s.fallback_model != self.s.model:
            models.append(self.s.fallback_model)
        for model in models:
            try:
                replies = client.generate_replies(
                    self.item.text, self.s.replies_per_post, prompt,
                    model, self.s.temperature, self.s.max_tokens, self.s.target_link,
                    examples=prefs.examples())
                if replies:
                    self.signals.done.emit(self.item.id, replies)
                    return
                last = "пустой ответ модели"
            except Exception as e:  # noqa: BLE001
                last = str(e)
        self.signals.error.emit(self.item.id, last)


# ----- one post card --------------------------------------------------------
class PostCard(QFrame):
    def __init__(self, item: PostItem, mode: str, on_regen, on_post):
        super().__init__()
        self.item = item
        self.on_regen = on_regen
        self.on_post = on_post
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 13, 14, 12)
        lay.setSpacing(9)

        head = QHBoxLayout(); head.setSpacing(9)
        av = QLabel((item.author or "?")[:1].lower())
        av.setObjectName("avatar"); av.setFixedSize(24, 24); av.setAlignment(Qt.AlignCenter)
        head.addWidget(av)
        name = QLabel(item.author or "(без автора)")
        name.setObjectName("cardhead")
        head.addWidget(name)
        if item.likes:
            lk = QLabel(f"♥ {item.likes}")
            lk.setStyleSheet("color:#ff8a8e; background:rgba(229,72,77,0.12); "
                             "border:1px solid rgba(229,72,77,0.22); border-radius:999px; "
                             "padding:1px 8px; font-family:'IBM Plex Mono',monospace; font-size:11px;")
            head.addWidget(lk)
        head.addStretch(1)
        if item.url:
            link = QLabel("↗ открыть"); link.setObjectName("cardlink")
            link.setToolTip(item.url)
            head.addWidget(link)
        lay.addLayout(head)

        post = QLabel(item.text)
        post.setWordWrap(True)
        post.setObjectName("posttext")
        lay.addWidget(post)

        self.var_row = QHBoxLayout()
        self.var_row.setSpacing(6)
        lay.addLayout(self.var_row)

        self.reply_box = QTextEdit()
        self.reply_box.setPlaceholderText("Здесь появится сгенерированный ответ…")
        self.reply_box.setFixedHeight(72)
        lay.addWidget(self.reply_box)

        row = QHBoxLayout()
        self.regen_btn = QPushButton("Ещё варианты")
        self.regen_btn.setIcon(svg_icon("refresh", "#a7abb0", 14))
        self.regen_btn.clicked.connect(lambda: self.on_regen(self.item.id))
        row.addWidget(self.regen_btn)
        row.addStretch(1)
        self._pick_mode = False
        self._on_pick = None
        self.action = QPushButton()
        self.action.clicked.connect(self._action_clicked)
        row.addWidget(self.action)
        lay.addLayout(row)

        self.status = QLabel("")
        self.status.setObjectName("cardstatus")
        lay.addWidget(self.status)

        self.set_mode(mode)
        if item.replies:
            self.set_replies(item.replies)

    def _clear_variants(self):
        while self.var_row.count():
            w = self.var_row.takeAt(0).widget()
            if w:
                w.deleteLater()

    def set_replies(self, replies):
        self.item.replies = replies
        self.item.chosen = 0
        self._clear_variants()
        for i in range(len(replies)):
            b = QPushButton(f"V{i+1}")
            b.setObjectName("vchip")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setFixedWidth(42)
            b.clicked.connect(lambda _=False, idx=i: self._choose(idx))
            self.var_row.addWidget(b)
        self.var_row.addStretch(1)
        self.reply_box.setPlainText(replies[0] if replies else "")

    def _choose(self, idx):
        self.item.chosen = idx
        for i in range(self.var_row.count()):
            w = self.var_row.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setChecked(w.text() == f"V{idx+1}")
        if idx < len(self.item.replies):
            self.reply_box.setPlainText(self.item.replies[idx])

    def current_text(self) -> str:
        return self.reply_box.toPlainText().strip()

    def set_mode(self, mode):
        if self.item.posted:
            return
        if mode == LIVE:
            self.action.setText("Одобрить и опубликовать")
            self.action.setObjectName("postbtn")
            self.action.setIcon(svg_icon("check", "#ffffff", 15))
            self.action.setEnabled(True)
        else:
            self.action.setText("Не публикуется")
            self.action.setObjectName("demobtn")
            self.action.setIcon(svg_icon("ban", "#6b7178", 14))
            self.action.setEnabled(False)
        self.action.style().unpolish(self.action)
        self.action.style().polish(self.action)

    def set_busy(self, busy):
        self.regen_btn.setEnabled(not busy)

    def mark_posted(self, ok, msg):
        self.status.setText(("✓ " if ok else "✗ ") + msg)
        self.status.setStyleSheet("color:%s; background:transparent;" % ("#3dd68c" if ok else "#ff8a8e"))
        if ok:
            self.item.posted = True
            self.item.done = True
            self.action.setEnabled(False)
            self.action.setText("Опубликовано")

    def _action_clicked(self):
        if self._pick_mode and self._on_pick:
            self._on_pick(self.item.id)
        else:
            self.on_post(self.item.id)

    def enable_pick(self, on_pick):
        """DEMO run: turn the action button into «✓ Выбрать лучший»."""
        self._pick_mode = True
        self._on_pick = on_pick
        self.action.setText("Выбрать лучший")
        self.action.setObjectName("pickbtn")
        self.action.setIcon(svg_icon("check", "#0b0b0d", 15))
        self.action.setEnabled(True)
        self.action.style().unpolish(self.action); self.action.style().polish(self.action)

    def mark_picked(self):
        self.item.done = True
        self._pick_mode = False
        self.action.setEnabled(False)
        self.action.setText("✓ Выбран")
        self.status.setText("🧠 добавлено в обучение")
        self.status.setStyleSheet("color:#7ee6b0; background:transparent;")


# ----- settings dialog ------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, s: config.Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumSize(520, 720)
        self.s = s

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        host = QWidget()
        v = QVBoxLayout(host); v.setContentsMargins(18, 18, 18, 18); v.setSpacing(14)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        def cap(text):
            lab = QLabel(text); lab.setObjectName("fieldcap"); return lab

        def field(text, w):
            box = QVBoxLayout(); box.setSpacing(5); box.addWidget(cap(text)); box.addWidget(w)
            return box

        # ── AI · OpenRouter ──
        v.addLayout(section("AI · OpenRouter"))
        self.key = QLineEdit(s.openrouter_api_key)
        self.key.setEchoMode(QLineEdit.Password); self.key.setPlaceholderText("sk-or-…")
        v.addLayout(field("API-ключ", self.key))

        mrow = QHBoxLayout(); mrow.setSpacing(10)
        self.model = QComboBox(); self.model.setEditable(True)
        self.model.addItems(ai.MODEL_PRESETS); self.model.setCurrentText(s.model)
        self.fallback = QComboBox(); self.fallback.setEditable(True)
        self.fallback.addItems(ai.MODEL_PRESETS); self.fallback.setCurrentText(s.fallback_model)
        mrow.addLayout(field("Модель (primary)", self.model), 1)
        mrow.addLayout(field("Модель (fallback)", self.fallback), 1)
        v.addLayout(mrow)
        refresh = QPushButton("Обновить список из OpenRouter")
        refresh.clicked.connect(self._refresh_models)
        v.addWidget(refresh)

        # ── Бренд и оффер ──
        v.addLayout(section("Бренд и оффер"))
        self.brand_name = QLineEdit(s.brand_name)
        self.brand_pitch = QLineEdit(s.brand_pitch)
        self.target = QLineEdit(s.target_link)
        self.audience = QLineEdit(s.audience)
        v.addLayout(field("Бренд / магазин", self.brand_name))
        v.addLayout(field("Что продаём (одной строкой)", self.brand_pitch))
        v.addLayout(field("Ссылка", self.target))
        v.addLayout(field("Аудитория", self.audience))

        # ── Поведение AI ──
        v.addLayout(section("Поведение AI"))
        self.tone = QComboBox(); self.tone.addItems(config.TONES); self.tone.setCurrentText(s.tone)
        self.promo = QComboBox(); self.promo.addItems(config.PROMOS); self.promo.setCurrentText(s.promo)
        self.emoji = QComboBox(); self.emoji.addItems(config.EMOJIS); self.emoji.setCurrentText(s.emoji)
        self.length = QComboBox(); self.length.addItems(config.LENGTHS); self.length.setCurrentText(s.length)
        self.language = QComboBox(); self.language.addItems(config.LANGS); self.language.setCurrentText(s.language)
        r1 = QHBoxLayout(); r1.setSpacing(10)
        r1.addLayout(field("Тон", self.tone), 1)
        r1.addLayout(field("Промо-упоминание", self.promo), 1)
        v.addLayout(r1)
        r2 = QHBoxLayout(); r2.setSpacing(10)
        r2.addLayout(field("Эмодзи", self.emoji), 1)
        r2.addLayout(field("Длина", self.length), 1)
        r2.addLayout(field("Язык", self.language), 1)
        v.addLayout(r2)
        self.humor = QCheckBox("С юмором / иронией"); self.humor.setChecked(s.humor)
        v.addWidget(self.humor)
        self.extra = QPlainTextEdit(s.extra_instructions)
        self.extra.setFixedHeight(52)
        self.extra.setPlaceholderText("напр.: избегай политики; иногда добавляй казахские словечки")
        v.addLayout(field("Доп. указания (необязательно)", self.extra))

        # ── live prompt preview ──
        v.addLayout(section("Итоговый промпт (превью)"))
        pv_hint = QLabel("Это то, что реально уходит в модель. Меняй настройки выше — обновляется само.")
        pv_hint.setObjectName("hint"); pv_hint.setWordWrap(True); v.addWidget(pv_hint)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True)
        self.preview.setObjectName("preview"); self.preview.setFixedHeight(180)
        v.addWidget(self.preview)
        self.override = QPlainTextEdit(s.prompt_override)
        self.override.setFixedHeight(60)
        self.override.setPlaceholderText("Продвинутое: свой промпт целиком (перебивает всё выше). Пусто = собираем из настроек.")
        v.addLayout(field("Свой промпт — только для профи", self.override))

        # ── Генерация ──
        v.addLayout(section("Генерация"))
        self.nrep = QSpinBox(); self.nrep.setRange(1, 6); self.nrep.setValue(s.replies_per_post)
        self.temp = QDoubleSpinBox(); self.temp.setRange(0.0, 1.5); self.temp.setSingleStep(0.05)
        self.temp.setValue(s.temperature)
        self.cap = QSpinBox(); self.cap.setRange(1, 200); self.cap.setValue(s.daily_cap)
        self.scrape_limit = QSpinBox(); self.scrape_limit.setRange(1, 50); self.scrape_limit.setValue(s.scrape_limit)
        g1 = QHBoxLayout(); g1.setSpacing(10)
        g1.addLayout(field("Вариантов / пост", self.nrep), 1)
        g1.addLayout(field("Temperature", self.temp), 1)
        v.addLayout(g1)
        g2 = QHBoxLayout(); g2.setSpacing(10)
        g2.addLayout(field("Дневной лимит постов", self.cap), 1)
        g2.addLayout(field("Сколько постов собирать", self.scrape_limit), 1)
        v.addLayout(g2)
        self.keywords = QLineEdit(", ".join(s.keywords))
        v.addLayout(field("Ключевые слова (через запятую)", self.keywords))

        self.source = QComboBox()
        self.source.addItem("Лента (тренды)", "feed")
        self.source.addItem("Поиск (ключевые слова)", "search")
        self.source.addItem("Микс", "mix")
        self.source.setCurrentIndex({"feed": 0, "search": 1, "mix": 2}.get(s.source, 0))
        self.min_likes = QSpinBox(); self.min_likes.setRange(0, 100000); self.min_likes.setValue(s.min_likes)
        g3 = QHBoxLayout(); g3.setSpacing(10)
        g3.addLayout(field("Источник постов", self.source), 1)
        g3.addLayout(field("Мин. лайков (тренд)", self.min_likes), 1)
        v.addLayout(g3)
        self.text_only = QCheckBox("Только текстовые посты (у модели нет зрения на фото/видео)")
        self.text_only.setChecked(s.text_only)
        v.addWidget(self.text_only)

        # ── Браузер · CDP ──
        v.addLayout(section("Браузер · CDP"))
        self.attach = QCheckBox("Подключаться к уже открытому Chrome (CDP)")
        self.attach.setChecked(s.attach_mode); v.addWidget(self.attach)
        crow = QHBoxLayout(); crow.setSpacing(10)
        self.cdp = QLineEdit(s.cdp_url)
        self.cdpport = QSpinBox(); self.cdpport.setRange(1024, 65535); self.cdpport.setValue(s.cdp_port)
        crow.addLayout(field("CDP URL", self.cdp), 2)
        crow.addLayout(field("Порт", self.cdpport), 1)
        v.addLayout(crow)
        v.addStretch(1)

        # ── footer buttons ──
        footer = QFrame(); footer.setObjectName("dialogfooter")
        frow = QHBoxLayout(footer); frow.setContentsMargins(18, 12, 18, 12)
        frow.addStretch(1)
        cancel = QPushButton("Отмена"); cancel.clicked.connect(self.reject)
        ok = QPushButton("Сохранить"); ok.setObjectName("primary"); ok.clicked.connect(self.accept)
        frow.addWidget(cancel); frow.addWidget(ok)
        outer.addWidget(footer)

        # live preview wiring
        for w in (self.brand_name, self.brand_pitch, self.target, self.audience,
                  self.extra, self.override):
            w_signal = w.textChanged if hasattr(w, "textChanged") else None
            if w_signal:
                w_signal.connect(self._update_preview)
        for combo in (self.tone, self.promo, self.emoji, self.length, self.language):
            combo.currentTextChanged.connect(self._update_preview)
        self.humor.toggled.connect(self._update_preview)
        self._update_preview()

    def _collect(self) -> config.Settings:
        self.s.openrouter_api_key = self.key.text().strip()
        self.s.model = self.model.currentText().strip()
        self.s.fallback_model = self.fallback.currentText().strip()
        self.s.brand_name = self.brand_name.text().strip()
        self.s.brand_pitch = self.brand_pitch.text().strip()
        self.s.target_link = self.target.text().strip()
        self.s.audience = self.audience.text().strip()
        self.s.tone = self.tone.currentText()
        self.s.promo = self.promo.currentText()
        self.s.emoji = self.emoji.currentText()
        self.s.length = self.length.currentText()
        self.s.language = self.language.currentText()
        self.s.humor = self.humor.isChecked()
        self.s.extra_instructions = self.extra.toPlainText().strip()
        self.s.prompt_override = self.override.toPlainText().strip()
        self.s.replies_per_post = self.nrep.value()
        self.s.temperature = self.temp.value()
        self.s.daily_cap = self.cap.value()
        self.s.scrape_limit = self.scrape_limit.value()
        self.s.keywords = [k.strip() for k in self.keywords.text().split(",") if k.strip()]
        self.s.source = self.source.currentData()
        self.s.min_likes = self.min_likes.value()
        self.s.text_only = self.text_only.isChecked()
        self.s.attach_mode = self.attach.isChecked()
        self.s.cdp_url = self.cdp.text().strip()
        self.s.cdp_port = self.cdpport.value()
        return self.s

    def _update_preview(self):
        try:
            self.preview.setPlainText(config.compose_prompt(self._collect()))
        except Exception as e:
            self.preview.setPlainText(f"(ошибка сборки промпта: {e})")

    def _refresh_models(self):
        try:
            slugs = ai.OpenRouter(self.key.text()).list_models()
            cur_p, cur_f = self.model.currentText(), self.fallback.currentText()
            self.model.clear(); self.model.addItems(slugs); self.model.setCurrentText(cur_p)
            self.fallback.clear(); self.fallback.addItems(slugs); self.fallback.setCurrentText(cur_f)
            QMessageBox.information(self, "OK", f"Загружено моделей: {len(slugs)}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить список: {e}")

    def result_settings(self) -> config.Settings:
        return self._collect()


# ----- paste dialog ---------------------------------------------------------
class PasteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вставить посты")
        self.setMinimumSize(480, 340)
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 18, 18, 18); lay.setSpacing(12)
        hint = QLabel("Вставь посты — по одному на абзац (разделяй пустой строкой):")
        hint.setObjectName("hint"); hint.setWordWrap(True)
        lay.addWidget(hint)
        self.box = QPlainTextEdit()
        lay.addWidget(self.box, 1)
        row = QHBoxLayout(); row.addStretch(1)
        cancel = QPushButton("Отмена"); cancel.clicked.connect(self.reject)
        ok = QPushButton("Добавить"); ok.setObjectName("primary"); ok.clicked.connect(self.accept)
        row.addWidget(cancel); row.addWidget(ok); lay.addLayout(row)

    def posts(self):
        raw = self.box.toPlainText().strip()
        blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
        return [{"author": "(вставлено)", "url": "", "text": b} for b in blocks]


# ----- main window ----------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.s = config.Settings.load()
        self.mode = DEMO
        self.items = {}
        self.cards = {}
        self._next_id = 1
        self.posted_today = 0
        self.browser_open = False
        self.running = False
        self.run_order = []
        self.run_pos = 0

        self.setWindowTitle("Threads Commentator — Envizhl")
        self.resize(580, 860)
        self.setMinimumWidth(500)

        self._build_ui()
        self._apply_on_top(self.s.always_on_top)

        # AI signals
        self.ai_signals = _AISignals()
        self.ai_signals.done.connect(self.on_ai_done)
        self.ai_signals.error.connect(self.on_ai_error)
        self.pool = QThreadPool.globalInstance()

        # Threads worker owns its own Playwright daemon thread (see threads_bot).
        self.worker = ThreadsWorker(config.PROFILE_DIR)
        self.worker.log.connect(self.log)
        self.worker.browserReady.connect(self.on_browser_ready)
        self.worker.loginState.connect(self.on_login_state)
        self.worker.postsScraped.connect(self.on_posts_scraped)
        self.worker.replyPosted.connect(self.on_reply_posted)

        if not self.s.openrouter_api_key:
            self.log("⚠ Не задан OpenRouter API-ключ — открой Настройки (⚙).")

    # ---- UI ----
    def _build_ui(self):
        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(14, 12, 14, 12); v.setSpacing(10)

        # header — brand mark + title/subtitle + on-top + gear
        top = QHBoxLayout(); top.setSpacing(11)
        mark = QFrame(); mark.setObjectName("brandmark"); mark.setFixedSize(13, 13)
        top.addWidget(mark)
        tcol = QVBoxLayout(); tcol.setSpacing(1)
        title = QLabel("Threads Commentator"); title.setObjectName("title")
        sub = QLabel("Reply studio · outlet.market.kz"); sub.setObjectName("subtitle")
        _tracked(sub, 9, 12)
        tcol.addWidget(title); tcol.addWidget(sub)
        top.addLayout(tcol)
        top.addStretch(1)
        self.ontop = QCheckBox("Поверх окон")
        self.ontop.setChecked(self.s.always_on_top)
        self.ontop.toggled.connect(self._apply_on_top)
        top.addWidget(self.ontop)
        gear = QPushButton(); gear.setObjectName("gearbtn"); gear.setFixedSize(36, 34)
        gear.setIcon(svg_icon("gear", "#c9cdd1", 17)); gear.setIconSize(QSize(17, 17))
        gear.clicked.connect(self.open_settings)
        top.addWidget(gear)
        v.addLayout(top)

        # mode segmented control
        seg = QFrame(); seg.setObjectName("modeseg")
        sl = QHBoxLayout(seg); sl.setContentsMargins(4, 4, 4, 4); sl.setSpacing(4)
        self.rb_demo = QRadioButton("DEMO"); self.rb_demo.setObjectName("rbdemo")
        self.rb_live = QRadioButton("LIVE"); self.rb_live.setObjectName("rblive")
        for rb in (self.rb_demo, self.rb_live):
            rb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            sl.addWidget(rb, 1)
        self.rb_demo.setChecked(True)
        grp = QButtonGroup(self); grp.addButton(self.rb_demo); grp.addButton(self.rb_live)
        self.rb_demo.toggled.connect(self._mode_changed)
        v.addWidget(seg)

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setAlignment(Qt.AlignCenter)
        v.addWidget(self.banner)

        # SOURCE section
        v.addLayout(section("Источник"))
        self.kw = QLineEdit(", ".join(self.s.keywords))
        self.kw.setPlaceholderText("ключевые слова через запятую")
        v.addWidget(self.kw)

        self.btn_debugchrome = QPushButton("  Запустить Chrome (attach)")
        self.btn_debugchrome.setObjectName("attachbtn")
        self.btn_debugchrome.setIcon(svg_icon("power", "#3dd68c", 15))
        self.btn_debugchrome.setToolTip(
            "Запускает Chrome с отладкой (отдельный профиль). Войди в Threads в этом окне,\n"
            "включи в ⚙ «Подключаться к открытому Chrome», затем «Открыть браузер».")
        self.btn_debugchrome.clicked.connect(self.launch_debug_chrome)
        v.addWidget(self.btn_debugchrome)

        b = QHBoxLayout(); b.setSpacing(8)
        self.btn_browser = QPushButton("  Открыть браузер")
        self.btn_browser.setIcon(svg_icon("globe", "#dfe2e5", 15))
        self.btn_browser.clicked.connect(self.open_browser)
        self.btn_scrape = QPushButton("  Собрать посты")
        self.btn_scrape.setIcon(svg_icon("download", "#dfe2e5", 15))
        self.btn_scrape.clicked.connect(self.scrape)
        b.addWidget(self.btn_browser); b.addWidget(self.btn_scrape)
        v.addLayout(b)

        b2 = QHBoxLayout(); b2.setSpacing(8)
        btn_paste = QPushButton("  Вставить"); btn_paste.setObjectName("ghost")
        btn_paste.setIcon(svg_icon("clipboard", "#a7abb0", 14)); btn_paste.clicked.connect(self.paste_posts)
        btn_samples = QPushButton("  Примеры"); btn_samples.setObjectName("ghost")
        btn_samples.setIcon(svg_icon("flask", "#a7abb0", 14)); btn_samples.clicked.connect(self.load_samples)
        btn_clear = QPushButton("  Очистить"); btn_clear.setObjectName("ghost")
        btn_clear.setIcon(svg_icon("trash", "#a7abb0", 14)); btn_clear.clicked.connect(self.clear_items)
        b2.addWidget(btn_paste); b2.addWidget(btn_samples); b2.addWidget(btn_clear)
        v.addLayout(b2)

        self.btn_gen = QPushButton("  Сгенерировать комментарии")
        self.btn_gen.setObjectName("genbtn")
        self.btn_gen.setIcon(svg_icon("sparkles", "#0b0b0d", 18)); self.btn_gen.setIconSize(QSize(18, 18))
        self.btn_gen.clicked.connect(self.generate_all)
        v.addWidget(self.btn_gen)
        shadow(self.btn_gen, 22, 7, QColor(255, 255, 255, 45))

        # run loop — go through posts 1-by-1 (DEMO: pick+learn · LIVE: auto-post)
        runrow = QHBoxLayout(); runrow.setSpacing(8)
        self.btn_run = QPushButton("  Старт прогон")
        self.btn_run.setObjectName("runbtn")
        self.btn_run.setIcon(svg_icon("power", "#08130d", 15)); self.btn_run.setIconSize(QSize(15, 15))
        self.btn_run.setToolTip("Идёт по постам по одному. DEMO: показывает 3 варианта, ты жмёшь "
                                "«Выбрать лучший» — он учится. LIVE: сам публикует лучший с паузами.")
        self.btn_run.clicked.connect(self.toggle_run)
        runrow.addWidget(self.btn_run, 1)
        self.learn_lab = QLabel(); self.learn_lab.setObjectName("learnlab")
        runrow.addWidget(self.learn_lab)
        v.addLayout(runrow)
        self._update_learn_label()

        # QUEUE section
        v.addLayout(section("Очередь"))
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_v = QVBoxLayout(self.list_host)
        self.list_v.setContentsMargins(0, 0, 0, 0)
        self.list_v.setSpacing(10); self.list_v.addStretch(1)
        self.scroll.setWidget(self.list_host)
        v.addWidget(self.scroll, 1)

        # log
        self.logbox = QPlainTextEdit(); self.logbox.setReadOnly(True)
        self.logbox.setFixedHeight(90); self.logbox.setObjectName("log")
        v.addWidget(self.logbox)

        self._update_banner()

    def _apply_on_top(self, on):
        self.s.always_on_top = on
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(on))
        self.show()

    def _mode_changed(self):
        self.mode = DEMO if self.rb_demo.isChecked() else LIVE
        if self.mode == LIVE:
            QMessageBox.warning(self, "LIVE-режим",
                                "LIVE публикует по-настоящему. Ручная кнопка требует подтверждения; "
                                "«Старт прогон» публикует лучший вариант АВТОМАТИЧЕСКИ — с паузами "
                                "и дневным лимитом. Следи за логом и жми «Стоп» при необходимости.")
        self._update_banner()
        for card in self.cards.values():
            card.set_mode(self.mode)

    def _update_banner(self):
        if self.mode == DEMO:
            self.banner.setText("DEMO — комментарии генерируются, но НЕ публикуются")
            self.banner.setProperty("live", False)
        else:
            self.banner.setText("● LIVE — одобренные комментарии будут ОПУБЛИКОВАНЫ")
            self.banner.setProperty("live", True)
        self.banner.style().unpolish(self.banner); self.banner.style().polish(self.banner)

    # ---- helpers ----
    def log(self, msg):
        self.logbox.appendPlainText(str(msg))

    def _keywords(self):
        return [k.strip() for k in self.kw.text().split(",") if k.strip()]

    def add_items(self, dicts):
        added = 0
        for d in dicts:
            text = (d.get("text") or "").strip()
            if not text:
                continue
            item = PostItem(id=self._next_id, author=d.get("author", ""),
                            url=d.get("url", ""), text=text, likes=int(d.get("likes") or 0))
            self._next_id += 1
            self.items[item.id] = item
            card = PostCard(item, self.mode, self.regenerate_one, self.post_item)
            self.cards[item.id] = card
            self.list_v.insertWidget(self.list_v.count() - 1, card)
            added += 1
        if added:
            self.log(f"Добавлено постов: {added}")

    def clear_items(self):
        for card in self.cards.values():
            card.setParent(None); card.deleteLater()
        self.items.clear(); self.cards.clear()

    # ---- actions ----
    def open_settings(self):
        dlg = SettingsDialog(config.Settings.load(), self)
        if dlg.exec() == QDialog.Accepted:
            self.s = dlg.result_settings()
            self.s.save()
            self.kw.setText(", ".join(self.s.keywords))
            self.log("Настройки сохранены.")

    def load_samples(self):
        self.add_items(SAMPLE_POSTS)

    def paste_posts(self):
        dlg = PasteDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.add_items(dlg.posts())

    def launch_debug_chrome(self):
        try:
            msg = launch_debug_chrome(self.s.cdp_port, config.CDP_PROFILE_DIR, self.s.chrome_path)
            self.log(msg)
            if not self.s.attach_mode:
                self.log("Совет: включи в ⚙ «Подключаться к открытому Chrome», затем «Открыть браузер».")
        except Exception as e:
            self.log(f"Не удалось запустить Chrome: {e}")

    def open_browser(self):
        self.log("Подключаюсь к открытому Chrome…" if self.s.attach_mode else "Открываю браузер…")
        self.worker.open_browser(self.s.attach_mode, self.s.cdp_url)

    def scrape(self):
        if not self.browser_open:
            self.log("Сначала открой браузер (кнопка слева).")
            return
        self.log("Собираю посты…")
        self.worker.scrape(self._keywords(), self.s.scrape_limit, self.s.min_likes,
                           self.s.source, self.s.text_only)

    def generate_all(self):
        if not self.s.openrouter_api_key:
            self.open_settings(); return
        todo = [it for it in self.items.values() if not it.replies and not it.posted]
        if not todo:
            self.log("Нет новых постов для генерации (загрузи/собери/вставь).")
            return
        self.log(f"Генерирую комментарии для {len(todo)} постов ({self.s.model})…")
        for it in todo:
            self.cards[it.id].set_busy(True)
            self.pool.start(GenTask(self.s.openrouter_api_key, it, self.s, self.ai_signals))

    def regenerate_one(self, item_id):
        it = self.items.get(item_id)
        if not it:
            return
        self.cards[item_id].set_busy(True)
        self.pool.start(GenTask(self.s.openrouter_api_key, it, self.s, self.ai_signals))

    # ---- run loop: go through posts one by one ----
    def toggle_run(self):
        self.stop_run() if self.running else self.start_run()

    def start_run(self):
        if not self.s.openrouter_api_key:
            self.open_settings(); return
        self.run_order = [iid for iid, it in self.items.items() if not it.done and not it.posted]
        if not self.run_order:
            self.log("Нет постов для прогона — собери/загрузи посты.")
            return
        if self.mode == LIVE and not self.browser_open:
            self.log("LIVE-прогон публикует по-настоящему — сначала открой браузер.")
            return
        self.running = True
        self.run_pos = 0
        self._set_run_button(True)
        self.log(f"▶ Прогон ({self.mode}) — постов в очереди: {len(self.run_order)}")
        self._process_current()

    def stop_run(self):
        self.running = False
        self._set_run_button(False)
        self.log("⏸ Прогон остановлен.")

    def _set_run_button(self, running):
        self.btn_run.setText("  Стоп" if running else "  Старт прогон")
        self.btn_run.setIcon(svg_icon("ban" if running else "power", "#08130d", 15))

    def _process_current(self):
        if not self.running:
            return
        while self.run_pos < len(self.run_order):
            it = self.items.get(self.run_order[self.run_pos])
            if it and not it.done:
                break
            self.run_pos += 1
        if self.run_pos >= len(self.run_order):
            self.log("✓ Прогон завершён."); self.stop_run(); return
        iid = self.run_order[self.run_pos]
        it = self.items[iid]; card = self.cards[iid]
        self.scroll.ensureWidgetVisible(card)
        if it.replies:
            self._act_on_current()
        else:
            card.set_busy(True)
            self.pool.start(GenTask(self.s.openrouter_api_key, it, self.s, self.ai_signals))

    def _act_on_current(self):
        if not self.running:
            return
        iid = self.run_order[self.run_pos]
        it = self.items.get(iid); card = self.cards.get(iid)
        if not it or not card:
            self._advance(); return
        if self.mode == DEMO:
            card.enable_pick(self._on_pick_best)
            self.log(f"Выбери лучший для @{it.author or '—'} (или «Ещё варианты»).")
        else:
            if not it.url:
                self.log(f"Пропуск @{it.author}: нет ссылки."); self._advance(); return
            if self.posted_today >= self.s.daily_cap:
                self.log(f"Дневной лимит ({self.s.daily_cap}) — стоп."); self.stop_run(); return
            text = card.current_text()
            if not text:
                self._advance(); return
            self.posted_today += 1
            card.status.setText("публикую…")
            self.worker.post_reply(iid, it.url, text)   # advance in on_reply_posted

    def _on_pick_best(self, item_id):
        it = self.items.get(item_id); card = self.cards.get(item_id)
        if it and card:
            chosen = card.current_text()
            rejected = [r for i, r in enumerate(it.replies) if i != it.chosen]
            n = prefs.add(post=it.text, chosen=chosen, rejected=rejected)
            card.mark_picked()
            self._update_learn_label()
            self.log(f"🧠 Пример #{n} сохранён — учусь на твоём выборе.")
        self._advance()

    def _advance(self):
        self.run_pos += 1
        if self.running:
            QTimer.singleShot(250, self._process_current)

    def _update_learn_label(self):
        self.learn_lab.setText(f"🧠 {prefs.count()}")
        self.learn_lab.setToolTip("Сохранённых примеров обучения (твои выборы «лучшего»).")

    @Slot(int, list)
    def on_ai_done(self, item_id, replies):
        card = self.cards.get(item_id)
        if card:
            card.set_busy(False)
            card.set_replies(replies)
        if (self.running and self.run_pos < len(self.run_order)
                and self.run_order[self.run_pos] == item_id):
            self._act_on_current()

    @Slot(int, str)
    def on_ai_error(self, item_id, msg):
        card = self.cards.get(item_id)
        if card:
            card.set_busy(False)
        self.log(f"AI-ошибка (пост {item_id}): {msg}")

    def post_item(self, item_id):
        if self.mode != LIVE:
            return
        it = self.items.get(item_id)
        card = self.cards.get(item_id)
        if not it or not card:
            return
        text = card.current_text()
        if not text:
            self.log("Пустой комментарий — нечего публиковать.")
            return
        if not it.url:
            QMessageBox.information(self, "Нет ссылки",
                                    "У этого поста нет URL (примеры/вставка). Публиковать можно "
                                    "только собранные из Threads посты.")
            return
        if self.posted_today >= self.s.daily_cap:
            QMessageBox.warning(self, "Лимит", f"Достигнут дневной лимит ({self.s.daily_cap}).")
            return
        confirm = QMessageBox.question(
            self, "Опубликовать?",
            f"Опубликовать комментарий в Threads?\n\n{text}\n\nПост: {it.url}")
        if confirm != QMessageBox.Yes:
            return
        self.posted_today += 1
        card.status.setText("публикую…")
        self.worker.post_reply(item_id, it.url, text)

    @Slot(bool)
    def on_browser_ready(self, ok):
        self.browser_open = ok
        self.log("Браузер готов." if ok else "Браузер не открылся.")

    @Slot(bool)
    def on_login_state(self, logged):
        self.log("Сессия Threads активна." if logged
                 else "Войди в Threads в окне браузера, потом собирай посты.")

    @Slot(list)
    def on_posts_scraped(self, posts):
        if posts:
            self.add_items(posts)
        else:
            self.log("Постов не собрано. Проверь логин/ключевые слова "
                     "(или пользуйся «Вставить посты» / «Примеры»).")

    @Slot(int, bool, str)
    def on_reply_posted(self, item_id, ok, msg):
        card = self.cards.get(item_id)
        if card:
            card.mark_posted(ok, msg)
        if not ok:
            self.posted_today = max(0, self.posted_today - 1)
        if self.running and self.mode == LIVE:
            lo, hi = self.s.min_delay_sec, self.s.max_delay_sec
            delay = random.randint(lo, hi) if hi >= lo > 0 else 60
            self.log(f"Пауза ~{delay // 60} мин {delay % 60} сек до следующего…")
            QTimer.singleShot(max(1, delay) * 1000, self._advance)

    def closeEvent(self, e):
        try:
            self.worker.close()
        except Exception:
            pass
        super().closeEvent(e)


STYLE = """
/* ---------- base ---------- */
* { font-family: "IBM Plex Sans", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow, QDialog { background: #0e0f12; }
QWidget { background: transparent; color: #eceef0; }
#root { background: #0e0f12; }
QScrollArea > QWidget > QWidget { background: transparent; }
QToolTip { background:#1a1b1f; color:#dfe2e5; border:1px solid rgba(255,255,255,0.12);
    border-radius:6px; padding:5px 8px; }

/* ---------- header ---------- */
#title { font-family:"Exo 2"; font-size:19px; font-weight:600; color:#f4f5f6; }
#subtitle { color:#6b7178; }
#brandmark { background:#e5484d; border-radius:3px; }
#gearbtn { background: rgba(255,255,255,0.045); border:1px solid rgba(255,255,255,0.09); border-radius:10px; }
#gearbtn:hover { background: rgba(255,255,255,0.09); }

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: rgba(255,255,255,0.035); color:#eceef0;
    border:1px solid rgba(255,255,255,0.09); border-radius:10px; padding:8px 11px;
    selection-background-color:#e5484d; selection-color:#ffffff; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border:1px solid rgba(255,255,255,0.28); background: rgba(255,255,255,0.05); }
QComboBox::drop-down { border:none; width:24px; }
QComboBox::down-arrow { image:none; width:0; height:0;
    border-left:4px solid transparent; border-right:4px solid transparent;
    border-top:5px solid #6b7178; margin-right:10px; }
QComboBox QAbstractItemView { background:#17181c; color:#dfe2e5;
    border:1px solid rgba(255,255,255,0.1); border-radius:8px; padding:4px; outline:none;
    selection-background-color: rgba(255,255,255,0.09); }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button { width:16px; background:transparent; border:none; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image:none;
    border-left:4px solid transparent; border-right:4px solid transparent; border-bottom:5px solid #8b9096; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image:none;
    border-left:4px solid transparent; border-right:4px solid transparent; border-top:5px solid #8b9096; }
#fieldcap { color:#8b9096; font-size:11px; }
#hint { color:#6b7178; font-size:11px; }
#preview { background: rgba(0,0,0,0.30); color:#b6babf;
    font-family:"IBM Plex Mono","Consolas",monospace; font-size:11px; }

/* ---------- buttons (secondary default) ---------- */
QPushButton { background: rgba(255,255,255,0.045); color:#dfe2e5;
    border:1px solid rgba(255,255,255,0.09); border-radius:10px; padding:9px 12px; font-weight:500; }
QPushButton:hover { background: rgba(255,255,255,0.09); }

/* ---------- run loop + learning ---------- */
#runbtn { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #7ee6b0, stop:1 #3dd68c);
    color:#08130d; font-family:"Exo 2"; font-weight:600; border:none; border-radius:11px; padding:11px; }
#runbtn:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #90edbe, stop:1 #4cdd97); }
#pickbtn { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #7ee6b0, stop:1 #3dd68c);
    color:#08130d; border:none; border-radius:10px; font-weight:600; padding:9px 15px; }
#pickbtn:hover { background:#4cdd97; }
#learnlab { color:#7ee6b0; font-family:"IBM Plex Mono",monospace; font-size:12px;
    background:rgba(61,214,140,0.10); border:1px solid rgba(61,214,140,0.22);
    border-radius:999px; padding:6px 11px; }
QPushButton:pressed { background: rgba(255,255,255,0.06); }
QPushButton:disabled { color:#5a5f65; background: rgba(255,255,255,0.02); border-color: rgba(255,255,255,0.06); }
#ghost { background: transparent; color:#a7abb0; border:1px solid rgba(255,255,255,0.07);
    border-radius:9px; padding:7px 10px; font-size:12px; }
#ghost:hover { background: rgba(255,255,255,0.045); color:#dfe2e5; }
#attachbtn { background: rgba(61,214,140,0.06); border:1px solid rgba(61,214,140,0.18); }
#attachbtn:hover { background: rgba(61,214,140,0.11); }

/* ---------- hero: Generate (neutral / mode-agnostic) ---------- */
#genbtn { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fbfbfc, stop:1 #e7e8ea);
    color:#0b0b0d; font-family:"Exo 2"; font-weight:600; font-size:14px;
    border:none; border-radius:12px; padding:14px; }
#genbtn:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #eeeff1); }
#genbtn:pressed { background:#e2e3e5; }

/* ---------- LIVE post button (red) ---------- */
#postbtn { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0555a, stop:1 #e5484d);
    color:#ffffff; border:none; border-radius:10px; font-weight:600; padding:9px 15px; }
#postbtn:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff6166, stop:1 #ef4f54); }
#postbtn:pressed { background:#d43f44; }
#demobtn { background: rgba(255,255,255,0.03); color:#6b7178;
    border:1px dashed rgba(255,255,255,0.14); border-radius:10px; padding:9px 14px; }

/* ---------- mode segmented ---------- */
#modeseg { background: rgba(0,0,0,0.28); border:1px solid rgba(255,255,255,0.07); border-radius:13px; }
#modeseg QRadioButton { padding:9px 0; border-radius:10px; color:#7a8087; font-weight:600;
    qproperty-alignment:'AlignCenter'; }
#modeseg QRadioButton::indicator { width:0; height:0; }
#rbdemo:checked { background: rgba(61,214,140,0.15); color:#7ee6b0; }
#rblive:checked { background: rgba(229,72,77,0.17); color:#ff8a8e; }

/* ---------- mode banner ---------- */
#banner { border-radius:11px; padding:11px 14px; font-weight:600; font-size:12px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(61,214,140,0.16), stop:1 rgba(61,214,140,0.04));
    color:#9fecc4; border:1px solid rgba(61,214,140,0.24); border-left:3px solid #3dd68c; }
#banner[live="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(229,72,77,0.18), stop:1 rgba(229,72,77,0.05));
    color:#ffb3b6; border:1px solid rgba(229,72,77,0.32); border-left:3px solid #e5484d; }

/* ---------- post card ---------- */
#card { background: rgba(255,255,255,0.028); border:1px solid rgba(255,255,255,0.08); border-radius:14px; }
#avatar { background: rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1);
    border-radius:12px; color:#9aa0a6; font-family:"IBM Plex Mono",monospace; font-size:12px; }
#cardhead { color:#dfe2e5; font-size:13px; font-weight:500; }
#cardlink { color:#6b7178; font-family:"IBM Plex Mono",monospace; font-size:11px; }
#posttext { color:#b6babf; font-size:13px; padding:2px 0 2px 12px; border-left:2px solid rgba(255,255,255,0.1); }
#cardstatus { color:#5a5f65; font-family:"IBM Plex Mono","Consolas",monospace; font-size:11px; }
#vchip { font-family:"IBM Plex Mono",monospace; font-size:12px; border-radius:8px;
    background:transparent; color:#8b9096; border:1px solid rgba(255,255,255,0.09); padding:4px 0; }
#vchip:checked { background: rgba(255,255,255,0.1); color:#f4f5f6; border:1px solid rgba(255,255,255,0.18); }

/* ---------- log ---------- */
#log { background: rgba(0,0,0,0.38); color:#6f757b; border:1px solid rgba(255,255,255,0.06);
    border-radius:11px; font-family:"IBM Plex Mono","Consolas",monospace; font-size:11px; padding:9px 12px; }

/* ---------- checkboxes ---------- */
QCheckBox { color:#a7abb0; spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border-radius:5px;
    border:1px solid rgba(255,255,255,0.22); background: rgba(255,255,255,0.04); }
QCheckBox::indicator:checked { background:#e5484d; border-color:#e5484d; }

/* ---------- dialog footer + primary ---------- */
#dialogfooter { background: rgba(0,0,0,0.22); border-top:1px solid rgba(255,255,255,0.07); }
#primary { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fbfbfc, stop:1 #e7e8ea);
    color:#0b0b0d; font-family:"Exo 2"; font-weight:600; border:none; border-radius:10px; padding:9px 22px; }
#primary:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #eeeff1); }

/* ---------- scroll ---------- */
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { background:transparent; width:8px; margin:2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.14); border-radius:4px; min-height:30px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.24); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
"""


def _load_fonts():
    """Load bundled TTFs if present in ./fonts (optional premium finish)."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        fdir = os.path.join(base, "fonts")
        if os.path.isdir(fdir):
            for fn in os.listdir(fdir):
                if fn.lower().endswith((".ttf", ".otf")):
                    QFontDatabase.addApplicationFont(os.path.join(fdir, fn))
    except Exception:
        pass


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    _load_fonts()
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
