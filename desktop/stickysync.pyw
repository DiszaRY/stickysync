"""StickySync — sticky notes on your desktop, synced with your phone via your own server.

Desktop app (PySide6): colored note "cards" on the desktop, system tray, settings,
opacity, smart lists (Tab/Enter), checkboxes, reminders, lock, duplicate, search,
RU/EN interface. Stores notes on a self-hosted server (see /server).

Run without a console window:  pythonw stickysync.pyw
Dependencies:  pip install PySide6   (Python 3.10+)
"""
import os, sys, json, time, re, queue, threading, subprocess, winsound
import ctypes, ctypes.wintypes
import urllib.request, urllib.error

from PySide6.QtCore import Qt, QTimer, QDateTime, QLocale
from PySide6.QtGui import QColor, QPixmap, QPainter, QIcon, QTextCursor, QCursor, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel,
    QFrame, QGraphicsDropShadowEffect, QSizeGrip, QDialog, QFormLayout, QLineEdit,
    QSpinBox, QCheckBox, QComboBox, QDialogButtonBox, QSystemTrayIcon, QMenu, QMessageBox,
    QInputDialog, QDateTimeEdit, QListWidget, QListWidgetItem,
)

APP_NAME = "StickySync"
FROZEN = getattr(sys, "frozen", False)          # True when packed by PyInstaller
APP_FILE = sys.executable if FROZEN else os.path.realpath(__file__)


def _cfg_path():
    """Config is kept next to the script (portable). Falls back to %APPDATA%
    only if the script's folder is read-only."""
    here = os.path.join(os.path.dirname(APP_FILE), "config.json")
    appdata = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "StickySync", "config.json")
    if os.path.exists(here):
        return here
    if os.path.exists(appdata):
        return appdata
    try:
        t = os.path.join(os.path.dirname(APP_FILE), ".stk_wtest")
        open(t, "w").close()
        os.remove(t)
        return here
    except Exception:
        return appdata


CFG_PATH = _cfg_path()
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
STARTUP_LNK = os.path.join(STARTUP_DIR, "StickySync.lnk")

SERVER_URL = ""

COLORS = {
    "yellow": {"bar": "#F5EAA6", "ink": "#6b5c12"},
    "pink":   {"bar": "#F4CDD8", "ink": "#7c3050"},
    "blue":   {"bar": "#CFE0F2", "ink": "#2c4f70"},
    "green":  {"bar": "#D2E8C6", "ink": "#3a6630"},
    "purple": {"bar": "#DCD0EE", "ink": "#4b3c79"},
    "orange": {"bar": "#F5D9BB", "ink": "#8a5520"},
}
ORDER = list(COLORS.keys())
BODY_INK = "#33312b"
LIST_RE = re.compile(r"^(\s*)([-•]\s|\[[ xX]\]\s|(\d+)\.\s)")

LANG = {
    "ru": {
        "new": "Новый стикер", "show_all": "Показать все", "hide_tray": "Свернуть в трей",
        "all_notes": "Все заметки…", "settings": "Настройки…", "quit": "Выход",
        "color": "Цвет", "add_check": "Добавить пункт-галочку", "reminder": "Будильник…",
        "rename": "Переименовать", "lock": "Заблокировать", "duplicate": "Создать копию",
        "on_top": "Поверх всех окон", "rollup": "Свернуть", "hide_all_m": "Скрыть все в трей",
        "delete": "Удалить", "delete_q": "Удалить этот стикер?",
        "rename_t": "Переименовать", "rename_p": "Название стикера:",
        "reminder_t": "Будильник", "reminder_when": "Когда напомнить:",
        "set": "Поставить", "clear": "Убрать", "cancel": "Отмена", "save": "Сохранить",
        "remind": "Напоминание:", "snooze": "Отложить 10 мин",
        "settings_t": "Настройки", "server": "Адрес сервера:",
        "old_pw": "Старый пароль:", "new_pw": "Новый пароль:",
        "passwd_ph": "пусто — не менять", "opacity": "Непрозрачность:",
        "refresh": "Частота обновления:", "font": "Размер шрифта:", "language": "Язык:",
        "ontop_cb": "Стикеры поверх всех окон", "autostart_cb": "Запускать при старте Windows",
        "pw_ok": "Пароль обновлён.", "pw_fail": "Старый пароль не подошёл.",
        "login_p": "Пароль:", "user_p": "Имя пользователя:", "wrong_pw": "Неверный логин или пароль",
        "no_conn": "Нет связи с сервером:\n", "server_q": "Адрес сервера (например https://notes.example.com):",
        "new_note_n": "Появился новый стикер.", "hidden_n": "Свёрнуто в трей. Клик по иконке — показать.",
        "quit_q": "Закрыть программу? Стикеры останутся на сервере.",
        "search_ph": "Поиск по заметкам…", "placeholder": "Напишите заметку…", "empty_note": "(пустой стикер)",
        "yellow": "Жёлтый", "pink": "Розовый", "blue": "Голубой",
        "green": "Зелёный", "purple": "Фиолетовый", "orange": "Оранжевый",
    },
    "en": {
        "new": "New note", "show_all": "Show all", "hide_tray": "Hide to tray",
        "all_notes": "All notes…", "settings": "Settings…", "quit": "Quit",
        "color": "Color", "add_check": "Add checkbox item", "reminder": "Reminder…",
        "rename": "Rename", "lock": "Lock", "duplicate": "Duplicate",
        "on_top": "Always on top", "rollup": "Roll up", "hide_all_m": "Hide all to tray",
        "delete": "Delete", "delete_q": "Delete this note?",
        "rename_t": "Rename", "rename_p": "Note title:",
        "reminder_t": "Reminder", "reminder_when": "Remind at:",
        "set": "Set", "clear": "Clear", "cancel": "Cancel", "save": "Save",
        "remind": "Reminder:", "snooze": "Snooze 10 min",
        "settings_t": "Settings", "server": "Server URL:",
        "old_pw": "Old password:", "new_pw": "New password:",
        "passwd_ph": "leave blank to keep", "opacity": "Opacity:",
        "refresh": "Refresh every:", "font": "Font size:", "language": "Language:",
        "ontop_cb": "Notes always on top", "autostart_cb": "Start with Windows",
        "pw_ok": "Password updated.", "pw_fail": "Old password did not match.",
        "login_p": "Password:", "user_p": "Username:", "wrong_pw": "Wrong username or password",
        "no_conn": "No connection to server:\n", "server_q": "Server URL (e.g. https://notes.example.com):",
        "new_note_n": "A new note appeared.", "hidden_n": "Hidden to tray. Click the icon to show.",
        "quit_q": "Quit the app? Your notes stay on the server.",
        "search_ph": "Search notes…", "placeholder": "Write a note…", "empty_note": "(empty note)",
        "yellow": "Yellow", "pink": "Pink", "blue": "Blue",
        "green": "Green", "purple": "Purple", "orange": "Orange",
    },
}
CUR_LANG = "en"


def T(key):
    return LANG.get(CUR_LANG, LANG["en"]).get(key, key)


def load_cfg():
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg):
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def http(method, path, token=None, body=None, timeout=8, retries=3):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(SERVER_URL + path, data=data, method=method)
            req.add_header("Content-Type", "application/json")
            if token:
                req.add_header("Authorization", "Bearer " + token)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            last = e
            time.sleep(0.4 * (attempt + 1))
    raise last


def _psq(s):
    return "'" + str(s).replace("'", "''") + "'"


def set_autostart(enabled):
    if enabled:
        target = APP_FILE if FROZEN else sys.executable
        args = "" if FROZEN else '"%s"' % APP_FILE
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
              "$s.TargetPath=%s;$s.Arguments=%s;$s.WorkingDirectory=%s;$s.Save()" %
              (_psq(STARTUP_LNK), _psq(target), _psq(args),
               _psq(os.path.dirname(APP_FILE))))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)
    else:
        try:
            os.remove(STARTUP_LNK)
        except FileNotFoundError:
            pass


def is_autostart():
    return os.path.exists(STARTUP_LNK)


def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FBE48A"))
    p.drawRoundedRect(8, 8, 48, 48, 11, 11)
    p.setPen(QColor("#8a7320"))
    for yy in (25, 34, 43):
        p.drawLine(19, yy, 45, yy)
    p.end()
    return QIcon(pm)


class NoteEdit(QTextEdit):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setFrameShape(QFrame.NoFrame)
        self.setPlaceholderText(T("placeholder"))

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.owner.refresh_opacity()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.owner.refresh_opacity()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            cur = self.textCursor()
            line = cur.block().text()
            m = LIST_RE.match(line)
            if m:
                if line[m.end():].strip() == "":
                    c = self.textCursor()
                    c.movePosition(QTextCursor.StartOfBlock)
                    c.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                    c.removeSelectedText()
                    return
                marker = m.group(2)
                if m.group(3):
                    marker = "%d. " % (int(m.group(3)) + 1)
                elif marker.strip().startswith("["):
                    marker = "[ ] "
                super().keyPressEvent(e)
                self.textCursor().insertText(m.group(1) + marker)
                return
            super().keyPressEvent(e)
            return
        if e.key() == Qt.Key_Tab:
            c = self.textCursor()
            c.movePosition(QTextCursor.StartOfBlock)
            c.insertText("  ")
            return
        if e.key() == Qt.Key_Backtab:
            c = self.textCursor()
            c.movePosition(QTextCursor.StartOfBlock)
            blk = c.block().text()
            for _ in range(min(2, len(blk) - len(blk.lstrip(" ")))):
                c.deleteChar()
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e):
        cur = self.cursorForPosition(e.pos())
        block = cur.block()
        m = re.match(r"^(\s*)\[([ xX])\]\s", block.text())
        if m and e.pos().x() < 32 and not self.isReadOnly():
            pos = block.position() + m.start(2)
            c = self.textCursor()
            c.setPosition(pos)
            c.setPosition(pos + 1, QTextCursor.KeepAnchor)
            c.insertText(" " if m.group(2) != " " else "x")
            return
        super().mousePressEvent(e)


class DragBar(QWidget):
    def __init__(self, win, on_drop, on_dblclick, on_menu):
        super().__init__()
        self.win = win
        self.on_drop = on_drop
        self.on_dblclick = on_dblclick
        self.on_menu = on_menu
        self._press = None
        self.setCursor(Qt.SizeAllCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.on_menu(e.globalPosition().toPoint())
            return
        if e.button() == Qt.LeftButton and not self.win.locked:
            self._press = e.globalPosition().toPoint() - self.win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._press is not None and (e.buttons() & Qt.LeftButton) and not self.win.locked:
            self.win.move(e.globalPosition().toPoint() - self._press)

    def mouseReleaseEvent(self, e):
        self._press = None
        self.on_drop()

    def mouseDoubleClickEvent(self, e):
        self.on_dblclick()


class AlarmDialog(QDialog):
    def __init__(self, parent, current_ts):
        super().__init__(parent)
        self.setWindowTitle(T("reminder_t"))
        self.value = None
        v = QVBoxLayout(self)
        v.addWidget(QLabel(T("reminder_when")))
        self.dt = QDateTimeEdit()
        self.dt.setCalendarPopup(True)
        self.dt.setDisplayFormat("dd.MM.yyyy  HH:mm")
        base = QDateTime.currentDateTime().addSecs(3600)
        if current_ts and current_ts > 0:
            base = QDateTime.fromSecsSinceEpoch(int(current_ts))
        self.dt.setDateTime(base)
        v.addWidget(self.dt)
        row = QHBoxLayout()
        b_set = QPushButton(T("set"))
        b_clear = QPushButton(T("clear"))
        b_cancel = QPushButton(T("cancel"))
        for b in (b_set, b_clear, b_cancel):
            row.addWidget(b)
        v.addLayout(row)
        b_set.clicked.connect(lambda: (setattr(self, "value", self.dt.dateTime().toSecsSinceEpoch()), self.accept()))
        b_clear.clicked.connect(lambda: (setattr(self, "value", 0), self.accept()))
        b_cancel.clicked.connect(self.reject)
        self.setStyleSheet(
            "QDialog{background:#f6f4ee;} QLabel{color:#222;font-family:'Segoe UI';}"
            "QDateTimeEdit{background:#fff;color:#222;border:1px solid #c9c4b8;border-radius:6px;padding:5px;}"
            "QPushButton{background:#2b2b2b;color:#fff;border:none;border-radius:6px;padding:6px 12px;}"
            "QPushButton:hover{background:#444;}")


class StickyWindow(QWidget):
    def __init__(self, app, note):
        super().__init__()
        self.app = app
        self.id = note.get("id")
        self.color = note.get("color", "yellow")
        if self.color not in COLORS:
            self.color = "yellow"
        self.title = note.get("title", "") or ""
        self.alarm = float(note.get("alarm", 0) or 0)
        self.locked = bool(note.get("locked", 0))
        self.last_edit = 0.0
        self._applying = False
        self._ready = False
        self._dirty = False
        self.collapsed = False
        self._full_h = int(note.get("h", 210))

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(app.cfg.get("on_top")))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame()
        self.card.setObjectName("card")
        outer.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.card.setGraphicsEffect(shadow)

        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self.bar = DragBar(self, self._geom_saved, self.toggle_rollup, self.show_menu)
        self.bar.setFixedHeight(32)
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(12, 0, 7, 0)
        bl.setSpacing(5)
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("status")
        self.status_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("title")
        self.title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        bl.addWidget(self.status_lbl)
        bl.addWidget(self.title_lbl, 1)
        self.btn_menu = self._btn("⋯", lambda: self.show_menu(
            self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomLeft())), T("settings"))
        self.btn_close = self._btn("✕", self.delete, T("delete"))
        bl.addWidget(self.btn_menu)
        bl.addWidget(self.btn_close)
        cl.addWidget(self.bar)

        self.text = NoteEdit(self)
        self.text.setPlainText(note.get("text", ""))
        self.text.setReadOnly(self.locked)
        cl.addWidget(self.text, 1)

        self.grip_holder = QWidget()
        gl = QHBoxLayout(self.grip_holder)
        gl.setContentsMargins(0, 0, 4, 4)
        gl.addStretch(1)
        gl.addWidget(QSizeGrip(self.card))
        cl.addWidget(self.grip_holder)

        self.resize(int(note.get("w", 240)), int(note.get("h", 210)))
        self.move(int(note.get("x", 80)), int(note.get("y", 80)))
        self._apply_style()
        self._update_title()
        self._update_status()
        if self.locked:
            self.grip_holder.hide()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_text)
        self._geom_timer = QTimer(self)
        self._geom_timer.setSingleShot(True)
        self._geom_timer.timeout.connect(self._geom_saved)
        self.text.textChanged.connect(self._on_text)

        for seq, fn in (("Alt+N", self.app.add_note), ("Alt+A", self.set_alarm),
                        ("Alt+D", self.duplicate), ("Alt+T", self.toggle_pin),
                        ("Alt+L", self.toggle_lock), ("Alt+M", self.toggle_rollup),
                        ("Alt+F", self.app.open_manager), ("F2", self.rename),
                        ("Alt+Delete", self.delete)):
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(Qt.WidgetWithChildrenShortcut)
            s.activated.connect(fn)

        self.show()
        self._ready = True
        self.refresh_opacity()

    def _btn(self, ch, cb, tip):
        b = QPushButton(ch)
        b.setFixedSize(24, 24)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setObjectName("hbtn")
        b.clicked.connect(cb)
        return b

    def _apply_style(self):
        c = COLORS[self.color]
        font = self.app.cfg.get("font", 11)
        self.card.setStyleSheet(
            "#card{background:#ffffff;border-radius:14px;border:0.5px solid rgba(0,0,0,0.08);}"
            "QTextEdit{background:transparent;color:%s;border:none;"
            "font-family:'Segoe UI';font-size:%dpt;padding:9px 13px;}"
            "#title{color:%s;font-family:'Segoe UI';font-size:10pt;font-weight:600;background:transparent;}"
            "#status{color:%s;font-size:10pt;background:transparent;}"
            "#hbtn{background:transparent;border:none;color:%s;font-size:14px;border-radius:12px;}"
            "#hbtn:hover{background:rgba(0,0,0,0.13);}"
            % (BODY_INK, font, c["ink"], c["ink"], c["ink"])
        )
        self.bar.setStyleSheet(
            "background:%s;border-top-left-radius:14px;border-top-right-radius:14px;"
            "border-bottom:0.5px solid rgba(0,0,0,0.05);" % c["bar"])

    def _update_title(self):
        self.title_lbl.setText(self.title)

    def _update_status(self):
        marks = ""
        if self.locked:
            marks += "🔒 "
        if self.alarm and self.alarm > 0:
            marks += "⏰ "
            self.status_lbl.setToolTip(
                QDateTime.fromSecsSinceEpoch(int(self.alarm)).toString("dd.MM HH:mm"))
        else:
            self.status_lbl.setToolTip("")
        self.status_lbl.setText(marks)
        self.status_lbl.setVisible(bool(marks))

    def refresh_opacity(self):
        base = self.app.cfg.get("opacity", 100) / 100.0
        hover = self.frameGeometry().contains(QCursor.pos())
        self.setWindowOpacity(1.0 if (hover or self.text.hasFocus()) else base)

    def enterEvent(self, e):
        self.refresh_opacity()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.refresh_opacity()
        super().leaveEvent(e)

    def _on_text(self):
        if self._applying:
            return
        self.last_edit = time.monotonic()
        if self.id:
            self._save_timer.start(700)
        else:
            self._dirty = True

    def _save_text(self):
        if self.id:
            self.app.enqueue(("update", self.id, {"text": self.text.toPlainText()}))

    def moveEvent(self, e):
        if self._ready and not self._applying and not self.collapsed:
            self._geom_timer.start(500)
        super().moveEvent(e)

    def resizeEvent(self, e):
        if self._ready and not self._applying and not self.collapsed:
            self._geom_timer.start(500)
        super().resizeEvent(e)

    def _geom_saved(self):
        if self.id and self._ready and not self.collapsed:
            self.app.enqueue(("update", self.id,
                              {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()}))

    def show_menu(self, global_pos):
        m = QMenu()
        m.addAction(T("new") + "\tAlt+N", self.app.add_note)
        cm = m.addMenu(T("color"))
        for name in ORDER:
            cm.addAction(T(name), lambda _=False, n=name: self.set_color(n))
        m.addAction(T("add_check"), self.add_checkbox)
        m.addSeparator()
        m.addAction(T("reminder") + "\tAlt+A", self.set_alarm)
        m.addAction(T("rename") + "\tF2", self.rename)
        a_lock = m.addAction(T("lock") + "\tAlt+L", self.toggle_lock)
        a_lock.setCheckable(True)
        a_lock.setChecked(self.locked)
        m.addAction(T("duplicate") + "\tAlt+D", self.duplicate)
        a_top = m.addAction(T("on_top") + "\tAlt+T", self.toggle_pin)
        a_top.setCheckable(True)
        a_top.setChecked(bool(self.windowFlags() & Qt.WindowStaysOnTopHint))
        m.addAction(T("rollup") + "\tAlt+M", self.toggle_rollup)
        m.addSeparator()
        m.addAction(T("all_notes") + "\tAlt+F", self.app.open_manager)
        m.addAction(T("hide_all_m"), self.app.hide_all)
        m.addSeparator()
        m.addAction(T("delete") + "\tAlt+Del", self.delete)
        m.exec(global_pos)

    def set_color(self, name):
        self.color = name
        self._apply_style()
        if self.id:
            self.app.enqueue(("update", self.id, {"color": self.color}))

    def add_checkbox(self):
        if self.locked:
            return
        c = self.text.textCursor()
        c.movePosition(QTextCursor.EndOfLine)
        c.insertText("[ ] " if c.atBlockStart() else "\n[ ] ")
        self.text.setTextCursor(c)
        self.text.setFocus()

    def rename(self):
        t, ok = QInputDialog.getText(self, T("rename_t"), T("rename_p"), QLineEdit.Normal, self.title)
        if ok:
            self.title = t.strip()
            self._update_title()
            if self.id:
                self.app.enqueue(("update", self.id, {"title": self.title}))

    def toggle_lock(self):
        self.locked = not self.locked
        self.text.setReadOnly(self.locked)
        if self.locked:
            self.grip_holder.hide()
        elif not self.collapsed:
            self.grip_holder.show()
        self._update_status()
        if self.id:
            self.app.enqueue(("update", self.id, {"locked": 1 if self.locked else 0}))

    def duplicate(self):
        self.app.spawn({"text": self.text.toPlainText(), "color": self.color, "title": self.title,
                        "x": self.x() + 28, "y": self.y() + 28, "w": self.width(), "h": self.height()})

    def set_alarm(self):
        dlg = AlarmDialog(self, self.alarm)
        if dlg.exec() and dlg.value is not None:
            self.alarm = float(dlg.value)
            self._update_status()
            if self.id:
                self.app.enqueue(("update", self.id, {"alarm": self.alarm}))

    def trigger_alarm(self):
        self.alarm = 0
        if self.collapsed:
            self.toggle_rollup()
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
        self._update_status()
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText(T("remind") + "\n" + (self.title or self.text.toPlainText()[:80].strip() or "—"))
        snooze = box.addButton(T("snooze"), QMessageBox.AcceptRole)
        box.addButton("OK", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is snooze:
            self.alarm = time.time() + 600
        self._update_status()
        if self.id:
            self.app.enqueue(("update", self.id, {"alarm": self.alarm}))

    def toggle_rollup(self):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self._full_h = self.height()
            self.text.hide()
            self.grip_holder.hide()
            self.setFixedHeight(self.bar.height() + 24)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.text.show()
            if not self.locked:
                self.grip_holder.show()
            self.resize(self.width(), self._full_h)

    def toggle_pin(self):
        on = not bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    def apply_remote(self, note):
        self._applying = True
        try:
            col = note.get("color")
            if col in COLORS and col != self.color:
                self.color = col
                self._apply_style()
            nt = note.get("title", "")
            if nt != self.title:
                self.title = nt
                self._update_title()
            lk = bool(note.get("locked", 0))
            if lk != self.locked:
                self.locked = lk
                self.text.setReadOnly(lk)
                if lk:
                    self.grip_holder.hide()
                elif not self.collapsed:
                    self.grip_holder.show()
            al = float(note.get("alarm", 0) or 0)
            if al != self.alarm:
                self.alarm = al
            self._update_status()
            recent = (time.monotonic() - self.last_edit) < 3
            if not recent and not self.text.hasFocus():
                rt = note.get("text", "")
                if rt != self.text.toPlainText():
                    pos = self.text.textCursor().position()
                    self.text.setPlainText(rt)
                    c = self.text.textCursor()
                    c.setPosition(min(pos, len(rt)))
                    self.text.setTextCursor(c)
        finally:
            self._applying = False

    def delete(self):
        if QMessageBox.question(self, APP_NAME, T("delete_q")) != QMessageBox.Yes:
            return
        if self.id:
            self.app.enqueue(("delete", self.id))
        self.app.drop(self)
        self.close()


class SettingsDialog(QDialog):
    def __init__(self, app):
        super().__init__()
        self.setWindowTitle(T("settings_t") + " — " + APP_NAME)
        self.setWindowIcon(make_icon())
        self.setMinimumWidth(420)
        self.setStyleSheet(
            "QDialog{background:#f6f4ee;}"
            "QLabel,QCheckBox{font-family:'Segoe UI';font-size:10pt;color:#2b2b2b;}"
            "QLineEdit,QSpinBox,QComboBox{background:#ffffff;color:#222;border:1px solid #c9c4b8;"
            "border-radius:6px;padding:5px 7px;font-size:10pt;}"
            "QPushButton{background:#2b2b2b;color:#fff;border:none;border-radius:6px;padding:7px 18px;}"
            "QPushButton:hover{background:#444;}")
        form = QFormLayout(self)
        form.setSpacing(10)
        self.server = QLineEdit(app.cfg.get("server", ""))
        self.pw_old = QLineEdit()
        self.pw_old.setEchoMode(QLineEdit.Password)
        self.pw_new = QLineEdit()
        self.pw_new.setEchoMode(QLineEdit.Password)
        self.pw_new.setPlaceholderText(T("passwd_ph"))
        self.lang = QComboBox()
        self.lang.addItem("Русский", "ru")
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(0 if CUR_LANG == "ru" else 1)
        self.opacity = QSpinBox(); self.opacity.setRange(40, 100)
        self.opacity.setValue(app.cfg.get("opacity", 100)); self.opacity.setSuffix(" %")
        self.poll = QSpinBox(); self.poll.setRange(2, 60)
        self.poll.setValue(app.cfg.get("poll", 4)); self.poll.setSuffix(" s")
        self.font = QSpinBox(); self.font.setRange(9, 22)
        self.font.setValue(app.cfg.get("font", 11)); self.font.setSuffix(" pt")
        self.ontop = QCheckBox(T("ontop_cb")); self.ontop.setChecked(bool(app.cfg.get("on_top")))
        self.autostart = QCheckBox(T("autostart_cb")); self.autostart.setChecked(is_autostart())
        form.addRow(T("server"), self.server)
        form.addRow(T("old_pw"), self.pw_old)
        form.addRow(T("new_pw"), self.pw_new)
        form.addRow(T("language"), self.lang)
        form.addRow(T("opacity"), self.opacity)
        form.addRow(T("refresh"), self.poll)
        form.addRow(T("font"), self.font)
        form.addRow(self.ontop)
        form.addRow(self.autostart)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText(T("save"))
        bb.button(QDialogButtonBox.Cancel).setText(T("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)


class ManagerDialog(QDialog):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle(T("all_notes").rstrip("…"))
        self.setWindowIcon(make_icon())
        self.resize(360, 440)
        self.setStyleSheet(
            "QDialog{background:#f6f4ee;}"
            "QLineEdit{background:#fff;color:#222;border:1px solid #c9c4b8;border-radius:8px;padding:8px 10px;font-size:11pt;}"
            "QListWidget{background:#fff;color:#222;border:1px solid #e0dac9;border-radius:8px;font-size:11pt;padding:4px;}"
            "QListWidget::item{padding:7px 8px;border-radius:6px;}"
            "QListWidget::item:selected{background:#ede7d6;color:#222;}")
        v = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(T("search_ph"))
        self.search.setClearButtonEnabled(True)
        v.addWidget(self.search)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        self.search.textChanged.connect(self.refresh)
        self.list.itemActivated.connect(self._open)
        self.list.itemClicked.connect(self._open)
        self.refresh()

    def refresh(self):
        q = self.search.text().strip().lower()
        self.list.clear()
        for w in self.app.windows.values():
            label = (w.title.strip() or w.text.toPlainText().strip().split("\n")[0] or T("empty_note"))
            hay = (w.title + " " + w.text.toPlainText()).lower()
            if q and q not in hay:
                continue
            it = QListWidgetItem(label[:80])
            it.setData(Qt.UserRole, w.id)
            self.list.addItem(it)

    def _open(self, item):
        nid = item.data(Qt.UserRole)
        w = self.app.windows.get(nid)
        if w:
            w.show()
            w.raise_()
            w.activateWindow()


class StickerApp:
    def __init__(self, qapp, cfg, token):
        self.qapp = qapp
        self.cfg = cfg
        self.token = token
        self.windows = {}
        self.pending = []
        self.local_created = set()
        self.op_q = queue.Queue()
        self.ui_q = queue.Queue()
        self.stop = False
        self.started = False
        self.cascade = 0
        self.manager = None
        self._build_tray()
        threading.Thread(target=self._worker, daemon=True).start()
        self.timer = QTimer(); self.timer.timeout.connect(self._pump); self.timer.start(300)
        self.alarm_timer = QTimer(); self.alarm_timer.timeout.connect(self._check_alarms); self.alarm_timer.start(10000)
        threading.Thread(target=self._hotkey_loop, daemon=True).start()

    def _hotkey_loop(self):
        """Global Ctrl+Alt+N -> new note. WM_HOTKEY needs a message loop on the
        registering thread, so it lives in its own daemon thread."""
        user32 = ctypes.windll.user32
        MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("N")):
            return  # combination taken by another app — silently skip
        msg = ctypes.wintypes.MSG()
        while not self.stop and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                self.ui_q.put(("hotkey",))

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction(T("new"), self.add_note)
        m.addAction(T("show_all"), self.show_all)
        m.addAction(T("all_notes"), self.open_manager)
        m.addAction(T("hide_tray"), self.hide_all)
        m.addSeparator()
        m.addAction(T("settings"), self.open_settings)
        m.addSeparator()
        m.addAction(T("quit"), self.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_all()

    def _all(self):
        return list(self.windows.values()) + list(self.pending)

    def toggle_all(self):
        if any(w.isVisible() for w in self._all()):
            self.hide_all()
        else:
            self.show_all()

    def show_all(self):
        for w in self._all():
            w.show(); w.raise_()

    def hide_all(self):
        for w in self._all():
            w.hide()
        self.tray.showMessage(APP_NAME, T("hidden_n"), make_icon(), 2500)

    def open_manager(self):
        if self.manager is None:
            self.manager = ManagerDialog(self)
            self.manager.finished.connect(lambda _: setattr(self, "manager", None))
        else:
            self.manager.refresh()
        self.manager.show()
        self.manager.raise_()
        self.manager.activateWindow()

    def spawn(self, payload):
        data = {"id": None, "text": "", "color": "yellow", "title": "",
                "x": 80, "y": 80, "w": 240, "h": 210, "alarm": 0, "locked": 0}
        data.update(payload)
        s = StickyWindow(self, data)
        self.pending.append(s)
        body = {k: data[k] for k in ("text", "color", "title", "x", "y", "w", "h")}
        self.enqueue(("create", s, body))
        return s

    def add_note(self):
        self.cascade = (self.cascade + 1) % 8
        scr = QApplication.primaryScreen().availableGeometry()
        s = self.spawn({"color": self.cfg.get("default_color", "yellow"),
                        "x": scr.center().x() - 120 + self.cascade * 28,
                        "y": scr.center().y() - 105 + self.cascade * 28})
        s.text.setFocus()

    def enqueue(self, op):
        self.op_q.put(op)

    def drop(self, s):
        if s.id in self.windows:
            del self.windows[s.id]
        if s in self.pending:
            self.pending.remove(s)

    def _check_alarms(self):
        now = time.time()
        for w in list(self.windows.values()):
            if w.alarm and 0 < w.alarm <= now:
                w.trigger_alarm()

    def open_settings(self):
        global SERVER_URL, CUR_LANG
        dlg = SettingsDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.cfg["server"] = dlg.server.text().strip()
        self.cfg["poll"] = dlg.poll.value()
        self.cfg["font"] = dlg.font.value()
        self.cfg["opacity"] = dlg.opacity.value()
        self.cfg["on_top"] = dlg.ontop.isChecked()
        self.cfg["lang"] = dlg.lang.currentData()
        SERVER_URL = self.cfg["server"]
        CUR_LANG = self.cfg["lang"]
        try:
            set_autostart(dlg.autostart.isChecked())
        except Exception:
            pass
        for w in self.windows.values():
            w._apply_style()
            w.setWindowFlag(Qt.WindowStaysOnTopHint, self.cfg["on_top"])
            if w.isVisible():
                w.show()
            w.refresh_opacity()
        if dlg.pw_new.text():
            try:
                d = http("POST", "/api/password",
                         body={"old": dlg.pw_old.text(), "new": dlg.pw_new.text()},
                         token=self.token)
                self.token = d["token"]; self.cfg["token"] = self.token
                QMessageBox.information(None, APP_NAME, T("pw_ok"))
            except Exception:
                QMessageBox.warning(None, APP_NAME, T("pw_fail"))
        save_cfg(self.cfg)

    def quit(self):
        if QMessageBox.question(None, APP_NAME, T("quit_q")) != QMessageBox.Yes:
            return
        self.stop = True
        self.tray.hide()
        self.qapp.quit()

    def _worker(self):
        last = 0.0
        while not self.stop:
            try:
                op = self.op_q.get(timeout=0.2)
                self._do_op(op)
            except queue.Empty:
                pass
            except Exception:
                pass
            now = time.monotonic()
            if now - last >= self.cfg.get("poll", 4):
                last = now
                try:
                    notes = http("GET", "/api/notes", token=self.token)
                    self.ui_q.put(("notes", notes))
                except Exception:
                    pass

    def _do_op(self, op):
        k = op[0]
        if k == "create":
            _, s, p = op
            n = http("POST", "/api/notes", token=self.token, body=p)
            self.ui_q.put(("created", s, n))
        elif k == "update":
            _, nid, f = op
            http("PUT", "/api/notes/%d" % nid, token=self.token, body=f)
        elif k == "delete":
            _, nid = op
            http("DELETE", "/api/notes/%d" % nid, token=self.token)

    def _pump(self):
        try:
            while True:
                self._handle(self.ui_q.get_nowait())
        except queue.Empty:
            pass

    def _handle(self, msg):
        k = msg[0]
        if k == "hotkey":
            self.add_note()
            return
        if k == "created":
            _, s, n = msg
            if s in self.pending:
                self.pending.remove(s)
            s.id = n["id"]
            self.windows[s.id] = s
            self.local_created.add(s.id)
            txt = s.text.toPlainText()
            if s._dirty or txt:
                self.enqueue(("update", s.id, {"text": txt}))
        elif k == "notes":
            self._reconcile(msg[1])

    def _reposition(self, s):
        self.cascade = (self.cascade + 1) % 8
        scr = QApplication.primaryScreen().availableGeometry()
        nx = scr.center().x() - s.width() // 2 + self.cascade * 28
        ny = scr.center().y() - s.height() // 2 + self.cascade * 28
        s._applying = True
        s.move(nx, ny)
        s._applying = False
        if s.id:
            self.enqueue(("update", s.id, {"x": nx, "y": ny}))

    def _reconcile(self, notes):
        ids = set()
        for n in notes:
            ids.add(n["id"])
            if n["id"] in self.windows:
                self.windows[n["id"]].apply_remote(n)
            else:
                s = StickyWindow(self, n)
                self.windows[n["id"]] = s
                if int(n.get("x", 80)) <= 80 and int(n.get("y", 80)) <= 80:
                    self._reposition(s)
                if self.started and n["id"] not in self.local_created:
                    s.show(); s.raise_()
                    self.tray.showMessage(APP_NAME, T("new_note_n"), make_icon(), 2500)
        for nid in list(self.windows):
            if nid not in ids:
                self.windows[nid].close()
                del self.windows[nid]
        if self.manager is not None:
            self.manager.refresh()
        self.started = True


def setup_flow(cfg):
    """Ask for server URL (first run) and sign in; returns token or None."""
    global SERVER_URL
    server = cfg.get("server", "")
    if not server:
        server, ok = QInputDialog.getText(None, APP_NAME, T("server_q"), QLineEdit.Normal,
                                          "https://")
        if not ok or not server.strip():
            return None
        server = server.strip().rstrip("/")
        cfg["server"] = server
        save_cfg(cfg)
    SERVER_URL = cfg["server"]
    token = cfg.get("token")
    if token:
        try:
            http("GET", "/api/notes", token=token)
            return token
        except urllib.error.HTTPError:
            pass
        except Exception:
            return token
    while True:
        user, ok = QInputDialog.getText(None, APP_NAME, T("user_p"), QLineEdit.Normal,
                                        cfg.get("username", "admin"))
        if not ok:
            return None
        pw, ok = QInputDialog.getText(None, APP_NAME, T("login_p"), QLineEdit.Password)
        if not ok:
            return None
        try:
            d = http("POST", "/api/login",
                     body={"username": user.strip() or "admin", "password": pw})
            cfg["token"] = d["token"]
            cfg["username"] = user.strip() or "admin"
            save_cfg(cfg)
            return d["token"]
        except urllib.error.HTTPError:
            QMessageBox.warning(None, APP_NAME, T("wrong_pw"))
        except Exception as e:
            QMessageBox.warning(None, APP_NAME, T("no_conn") + str(e))
            return None


def main():
    global CUR_LANG
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(make_icon())
    app.setQuitOnLastWindowClosed(False)
    cfg = load_cfg()
    CUR_LANG = cfg.get("lang") or ("ru" if QLocale.system().name().startswith("ru") else "en")
    token = setup_flow(cfg)
    if not token:
        return
    StickerApp(app, cfg, token)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
