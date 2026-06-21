"""Личный сервер стикеров: хранит заметки (SQLite) и отдаёт страницу для телефона.
Один пользователь, доступ по паролю. ПК-программа и телефон ходят в одни и те же ручки."""
import os, time, secrets, sqlite3
from contextlib import closing
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = os.environ.get("DB_PATH", "/data/stickers.db")
PASSWORD = os.environ["STICKERS_PASSWORD"]   # что вводишь на телефоне
TOKEN = os.environ["STICKERS_TOKEN"]         # ключ доступа после входа

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


with closing(db()) as c:
    c.execute("""create table if not exists notes(
        id integer primary key autoincrement,
        text text not null default '',
        color text not null default 'yellow',
        x integer not null default 60,
        y integer not null default 60,
        w integer not null default 230,
        h integer not null default 200,
        title text not null default '',
        alarm real not null default 0,
        locked integer not null default 0,
        updated real not null default 0,
        deleted integer not null default 0
    )""")
    cols = [r[1] for r in c.execute("pragma table_info(notes)")]
    for col, ddl in (("w", "w integer not null default 230"),
                     ("h", "h integer not null default 200"),
                     ("title", "title text not null default ''"),
                     ("alarm", "alarm real not null default 0"),
                     ("locked", "locked integer not null default 0")):
        if col not in cols:
            c.execute("alter table notes add column " + ddl)
    c.commit()

app = FastAPI(title="stickers")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def auth(authorization: str = Header(default="")):
    expected = f"Bearer {TOKEN}"
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


class Login(BaseModel):
    password: str


class NoteIn(BaseModel):
    text: str = ""
    color: str = "yellow"
    x: int = 60
    y: int = 60
    w: int = 230
    h: int = 200
    title: str = ""
    alarm: float = 0.0
    locked: int = 0


class NotePatch(BaseModel):
    text: str | None = None
    color: str | None = None
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None
    title: str | None = None
    alarm: float | None = None
    locked: int | None = None


@app.post("/api/login")
def login(body: Login):
    if not secrets.compare_digest(body.password, PASSWORD):
        raise HTTPException(status_code=401, detail="wrong password")
    return {"token": TOKEN}


@app.get("/api/notes", dependencies=[Depends(auth)])
def list_notes():
    with closing(db()) as c:
        rows = c.execute("select * from notes where deleted=0 order by id").fetchall()
        return [dict(r) for r in rows]


@app.post("/api/notes", dependencies=[Depends(auth)])
def create_note(n: NoteIn):
    with closing(db()) as c:
        cur = c.execute(
            "insert into notes(text,color,x,y,w,h,title,alarm,locked,updated) "
            "values(?,?,?,?,?,?,?,?,?,?)",
            (n.text, n.color, n.x, n.y, n.w, n.h, n.title, n.alarm, n.locked, time.time()))
        c.commit()
        row = c.execute("select * from notes where id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


@app.put("/api/notes/{nid}", dependencies=[Depends(auth)])
def update_note(nid: int, p: NotePatch):
    fields = {k: v for k, v in p.model_dump().items() if v is not None}
    with closing(db()) as c:
        row = c.execute("select id from notes where id=? and deleted=0", (nid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            c.execute(f"update notes set {sets}, updated=? where id=?",
                      (*fields.values(), time.time(), nid))
            c.commit()
        return dict(c.execute("select * from notes where id=?", (nid,)).fetchone())


@app.delete("/api/notes/{nid}", dependencies=[Depends(auth)])
def delete_note(nid: int):
    with closing(db()) as c:
        c.execute("update notes set deleted=1, updated=? where id=?", (time.time(), nid))
        c.commit()
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()
