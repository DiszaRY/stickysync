"""StickySync server: stores notes (SQLite) and serves the web board.

v2: multi-user accounts (register/login), per-user notes, trash with restore
(30 days), password change. Backwards compatible with v1 single-password
setups: on first start, if no users exist and STICKERS_PASSWORD is set, an
'admin' user is created with that password (and STICKERS_TOKEN as its token),
and any existing notes are assigned to it — old clients keep working as-is.

Environment:
  DB_PATH                sqlite file (default /data/stickers.db)
  STICKERS_PASSWORD      legacy bootstrap password for the 'admin' user
  STICKERS_TOKEN         legacy bootstrap token for the 'admin' user
  STICKERS_REGISTRATION  "true" to allow open sign-ups (default "false";
                         the very first user can always register)
"""
import os, time, hashlib, secrets, sqlite3
from contextlib import closing
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = os.environ.get("DB_PATH", "/data/stickers.db")
LEGACY_PASSWORD = os.environ.get("STICKERS_PASSWORD", "")
LEGACY_TOKEN = os.environ.get("STICKERS_TOKEN", "")
REGISTRATION = os.environ.get("STICKERS_REGISTRATION", "false").lower() == "true"
TRASH_DAYS = 30

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_pw(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def check_pw(password, stored):
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_pw(password, salt), stored)


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
        pinned integer not null default 0,
        updated real not null default 0,
        deleted integer not null default 0,
        user_id integer not null default 0
    )""")
    c.execute("""create table if not exists users(
        id integer primary key autoincrement,
        username text not null unique,
        pw_hash text not null,
        token text not null unique,
        created real not null default 0
    )""")
    cols = [r[1] for r in c.execute("pragma table_info(notes)")]
    for col, ddl in (("w", "w integer not null default 230"),
                     ("h", "h integer not null default 200"),
                     ("title", "title text not null default ''"),
                     ("alarm", "alarm real not null default 0"),
                     ("locked", "locked integer not null default 0"),
                     ("pinned", "pinned integer not null default 0"),
                     ("user_id", "user_id integer not null default 0")):
        if col not in cols:
            c.execute("alter table notes add column " + ddl)
    # v1 -> v2 bootstrap: create 'admin' from legacy env and adopt orphan notes
    if not c.execute("select id from users limit 1").fetchone() and LEGACY_PASSWORD:
        token = LEGACY_TOKEN or secrets.token_hex(32)
        c.execute("insert into users(username,pw_hash,token,created) values(?,?,?,?)",
                  ("admin", hash_pw(LEGACY_PASSWORD), token, time.time()))
    row = c.execute("select id from users order by id limit 1").fetchone()
    if row:
        c.execute("update notes set user_id=? where user_id=0", (row["id"],))
    c.commit()

app = FastAPI(title="stickysync")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def purge_trash(c):
    c.execute("delete from notes where deleted=1 and updated < ?",
              (time.time() - TRASH_DAYS * 86400,))
    c.commit()


def auth(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="unauthorized")
    token = authorization[7:]
    with closing(db()) as c:
        row = c.execute("select * from users where token=?", (token,)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="unauthorized")
    return dict(row)


class Credentials(BaseModel):
    username: str = "admin"
    password: str


class PasswordChange(BaseModel):
    old: str
    new: str


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
    pinned: int = 0


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
    pinned: int | None = None


@app.get("/api/info")
def info():
    with closing(db()) as c:
        has_users = bool(c.execute("select id from users limit 1").fetchone())
    return {"app": "stickysync", "version": 2,
            "registration_enabled": REGISTRATION or not has_users}


@app.post("/api/register")
def register(body: Credentials):
    username = body.username.strip().lower()
    if not (3 <= len(username) <= 32) or not username.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="bad username")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="password too short")
    with closing(db()) as c:
        has_users = bool(c.execute("select id from users limit 1").fetchone())
        if has_users and not REGISTRATION:
            raise HTTPException(status_code=403, detail="registration disabled")
        if c.execute("select id from users where username=?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="username taken")
        token = secrets.token_hex(32)
        c.execute("insert into users(username,pw_hash,token,created) values(?,?,?,?)",
                  (username, hash_pw(body.password), token, time.time()))
        c.commit()
    return {"token": token}


@app.post("/api/login")
def login(body: Credentials):
    username = body.username.strip().lower()
    with closing(db()) as c:
        purge_trash(c)
        row = c.execute("select * from users where username=?", (username,)).fetchone()
    if not row or not check_pw(body.password, row["pw_hash"]):
        raise HTTPException(status_code=401, detail="wrong credentials")
    return {"token": row["token"]}


@app.post("/api/password")
def change_password(body: PasswordChange, user=Depends(auth)):
    if not check_pw(body.old, user["pw_hash"]):
        raise HTTPException(status_code=401, detail="wrong password")
    if len(body.new) < 6:
        raise HTTPException(status_code=400, detail="password too short")
    token = secrets.token_hex(32)
    with closing(db()) as c:
        c.execute("update users set pw_hash=?, token=? where id=?",
                  (hash_pw(body.new), token, user["id"]))
        c.commit()
    return {"token": token}


@app.get("/api/notes")
def list_notes(user=Depends(auth)):
    with closing(db()) as c:
        rows = c.execute("select * from notes where deleted=0 and user_id=? order by id",
                         (user["id"],)).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/notes")
def create_note(n: NoteIn, user=Depends(auth)):
    with closing(db()) as c:
        cur = c.execute(
            "insert into notes(text,color,x,y,w,h,title,alarm,locked,pinned,updated,user_id) "
            "values(?,?,?,?,?,?,?,?,?,?,?,?)",
            (n.text, n.color, n.x, n.y, n.w, n.h, n.title, n.alarm, n.locked, n.pinned,
             time.time(), user["id"]))
        c.commit()
        row = c.execute("select * from notes where id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


@app.put("/api/notes/{nid}")
def update_note(nid: int, p: NotePatch, user=Depends(auth)):
    fields = {k: v for k, v in p.model_dump().items() if v is not None}
    with closing(db()) as c:
        row = c.execute("select id from notes where id=? and deleted=0 and user_id=?",
                        (nid, user["id"])).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            c.execute(f"update notes set {sets}, updated=? where id=?",
                      (*fields.values(), time.time(), nid))
            c.commit()
        return dict(c.execute("select * from notes where id=?", (nid,)).fetchone())


@app.delete("/api/notes/{nid}")
def delete_note(nid: int, user=Depends(auth)):
    with closing(db()) as c:
        c.execute("update notes set deleted=1, updated=? where id=? and user_id=?",
                  (time.time(), nid, user["id"]))
        c.commit()
    return {"ok": True}


@app.get("/api/trash")
def list_trash(user=Depends(auth)):
    with closing(db()) as c:
        purge_trash(c)
        rows = c.execute(
            "select * from notes where deleted=1 and user_id=? order by updated desc",
            (user["id"],)).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/notes/{nid}/restore")
def restore_note(nid: int, user=Depends(auth)):
    with closing(db()) as c:
        row = c.execute("select id from notes where id=? and deleted=1 and user_id=?",
                        (nid, user["id"])).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        c.execute("update notes set deleted=0, updated=? where id=?", (time.time(), nid))
        c.commit()
        return dict(c.execute("select * from notes where id=?", (nid,)).fetchone())


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()
