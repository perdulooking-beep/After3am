from flask import Flask, request, session, redirect, url_for, jsonify, send_from_directory, send_file, abort
import random
import urllib.parse
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "after3am_modern_features_key"

import os
import sqlite3
import base64
import re
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None
import webbrowser
import threading
from markupsafe import escape

app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024

# --- AFTER3AM paths: automatically use the existing project/media/database ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(SCRIPT_DIR)
_PATH_CANDIDATES = [
    SCRIPT_DIR,
    _PARENT_DIR,
    os.path.join(SCRIPT_DIR, "static"),
    os.path.join(_PARENT_DIR, "static"),
]

# The screenshots show the real media folder as static/videos. We also support
# the case where this file itself is placed inside static/.
_VIDEO_CANDIDATES = [
    # Preferred project folder.
    os.path.join(SCRIPT_DIR, "video"),
    os.path.join(_PARENT_DIR, "video"),
    # Legacy folders kept for compatibility.
    os.path.join(SCRIPT_DIR, "videos"),
    os.path.join(_PARENT_DIR, "videos"),
    os.path.join(SCRIPT_DIR, "static", "videos"),
    os.path.join(_PARENT_DIR, "static", "videos"),
]

_MEDIA_EXTENSIONS = {
    ".mp4", ".webm", ".mov", ".m4v", ".3gp", ".avi", ".mkv",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".txt", ".html", ".htm", ".md", ".pdf",
}

def _media_file_count(folder):
    if not os.path.isdir(folder):
        return 0
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if os.path.splitext(name)[1].lower() in _MEDIA_EXTENSIONS:
                total += 1
    return total

_existing_media_candidates = [
    os.path.abspath(x) for x in _VIDEO_CANDIDATES if os.path.isdir(x)
]
_with_media = [
    x for x in _existing_media_candidates if _media_file_count(x) > 0
]

if _with_media:
    _preferred = [
        os.path.abspath(os.path.join(SCRIPT_DIR, "video")),
        os.path.abspath(os.path.join(_PARENT_DIR, "video")),
    ]
    VIDEO_DIR = next((x for x in _preferred if x in _with_media), _with_media[0])
else:
    VIDEO_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "video"))

os.makedirs(VIDEO_DIR, exist_ok=True)

# Preserve the existing database. Never create a new DB if an existing one can
# be found in the common project/instance locations.
_DB_CANDIDATES = [
    os.environ.get("AFTER3AM_DB", ""),
    os.path.join(SCRIPT_DIR, "after3am.db"),
    os.path.join(SCRIPT_DIR, "instance", "after3am.db"),
    os.path.join(_PARENT_DIR, "after3am.db"),
    os.path.join(_PARENT_DIR, "instance", "after3am.db"),
    os.path.join(SCRIPT_DIR, "static", "after3am.db"),
    os.path.join(SCRIPT_DIR, "static", "instance", "after3am.db"),
    os.path.join(_PARENT_DIR, "static", "after3am.db"),
    os.path.join(_PARENT_DIR, "static", "instance", "after3am.db"),
]
DB_PATH = next((os.path.abspath(x) for x in _DB_CANDIDATES if x and os.path.isfile(x)),
               os.path.join(SCRIPT_DIR, "after3am.db"))

VIDEO_REELS_DIR = os.path.join(VIDEO_DIR, "reels")
VIDEO_IMAGES_DIR = os.path.join(VIDEO_DIR, "images")
VIDEO_ARTICLES_DIR = os.path.join(VIDEO_DIR, "articles")
os.makedirs(VIDEO_REELS_DIR, exist_ok=True)
os.makedirs(VIDEO_IMAGES_DIR, exist_ok=True)
os.makedirs(VIDEO_ARTICLES_DIR, exist_ok=True)
for _folder in (VIDEO_REELS_DIR, VIDEO_IMAGES_DIR, VIDEO_ARTICLES_DIR):
    os.makedirs(_folder, exist_ok=True)

# Also accept media directly inside the detected videos folder.
TOPICS = ["Diary", "Philosophy", "Confessions", "Memories", "Midnight Void", "Solitude", "Inner Voices"]
TYPE_LABELS = {"article": "Article", "image": "Image", "reel": "Reel"}
FA_URL = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"


def make_svg(c1, c2):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="' + c1 + '"/><stop offset="1" stop-color="' + c2 + '"/>'
        '</linearGradient></defs><rect width="800" height="600" fill="url(#g)"/>'
        '<circle cx="600" cy="150" r="60" fill="#f1f5f9" opacity="0.85"/></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# ---------------------------------------------------------------------------
# القائمة اليدوية (Seed): استبدل هذه العناصر التجريبية بالحسابات والروابط الحقيقية
# التي اخترتها بنفسك. للريلز ضع رابط فيديو مباشر أو مسار ملف داخل static/ في الحقل url.
# type: article / image / reel
# ---------------------------------------------------------------------------
SEED_CONTENT = [
    {"author": "Perdu", "handle": "perdu._", "type": "article", "topic": "Philosophy",
     "title": "On Silence and Midnight Thoughts",
     "body": "There is a unique kind of clarity that arrives only after 3 AM...", "url": "",
     "created_at": "2026-11-10T03:00:00"},
    {"author": "Sample Writer", "handle": "sample.writer", "type": "article", "topic": "Memories",
     "title": "Letters I Never Sent",
     "body": "Some letters are written only to be kept.\nThey carry the weight of what we could not say out loud, and the quiet relief of having said it at all.",
     "url": "", "created_at": "2026-11-09T02:40:00"},
    {"author": "Night Diary", "handle": "night.diary", "type": "article", "topic": "Solitude",
     "title": "Rain on the Window",
     "body": "The rain does not ask for anything.\nIt falls, it fills the silence, and for a while the room feels less empty.",
     "url": "", "created_at": "2026-11-08T01:15:00"},
    {"author": "Ink After Dark", "handle": "ink.after.dark", "type": "article", "topic": "Philosophy",
     "title": "The Weight of Unfinished Thoughts",
     "body": "Not every thought needs a conclusion.\nSome are meant to stay open, like a window left ajar in a quiet house.",
     "url": "", "created_at": "2026-11-07T04:05:00"},
    {"author": "Moon Frames", "handle": "moon.frames", "type": "image", "topic": "Midnight Void",
     "title": "Quiet Streets at Midnight", "body": "Nobody here but the lamps.",
     "url": make_svg("#0b1020", "#2c1f80"), "created_at": "2026-11-09T23:30:00"},
    {"author": "Dusk Notes", "handle": "dusk.notes", "type": "image", "topic": "Philosophy",
     "title": "The Last Light", "body": "Every ending is also a quiet beginning.",
     "url": make_svg("#1a1450", "#5b49d6"), "created_at": "2026-11-08T18:20:00"},
    {"author": "Night Diary", "handle": "night.diary", "type": "image", "topic": "Solitude",
     "title": "Empty Chair, Full Moon", "body": "",
     "url": make_svg("#050510", "#3b2fb8"), "created_at": "2026-11-06T22:10:00"},
    {"author": "Moon Frames", "handle": "moon.frames", "type": "reel", "topic": "Philosophy",
     "title": "Why we think more at night", "body": "", "url": "",
     "created_at": "2026-11-10T00:10:00"},
    {"author": "Dusk Notes", "handle": "dusk.notes", "type": "reel", "topic": "Philosophy",
     "title": "Three questions before sleep", "body": "", "url": "",
     "created_at": "2026-11-09T00:50:00"},
    {"author": "Night Diary", "handle": "night.diary", "type": "reel", "topic": "Solitude",
     "title": "A walk with no destination", "body": "", "url": "",
     "created_at": "2026-11-08T23:00:00"},
    {"author": "Sample Writer", "handle": "sample.writer", "type": "reel", "topic": "Solitude",
     "title": "The sound of an empty apartment", "body": "", "url": "",
     "created_at": "2026-11-07T23:45:00"},
    {"author": "Ink After Dark", "handle": "ink.after.dark", "type": "reel", "topic": "Diary",
     "title": "Page one of tonight", "body": "", "url": "",
     "created_at": "2026-11-06T01:30:00"},
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            handle TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL CHECK (type IN ('article', 'image', 'reel')),
            topic TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stars (
            content_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (content_id, user_id),
            FOREIGN KEY (content_id) REFERENCES contents(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            author TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (content_id) REFERENCES contents(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_contents_type_topic ON contents(type, topic);
        CREATE INDEX IF NOT EXISTS idx_comments_content ON comments(content_id);
        CREATE TABLE IF NOT EXISTS users (
            handle TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            bio TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS follows (
            follower_id TEXT NOT NULL,
            followee_handle TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (follower_id, followee_handle)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(sender, recipient);
        CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient, is_read);
    """)
    if conn.execute("SELECT COUNT(*) FROM contents").fetchone()[0] == 0:
        for it in SEED_CONTENT:
            conn.execute(
                "INSERT INTO contents (author, handle, title, body, url, type, topic, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (it["author"], it["handle"], it["title"], it["body"], it["url"], it["type"], it["topic"], it["created_at"]),
            )
    conn.commit()
    conn.close()


def repair_existing_schema():
    """
    Keep the user's existing database, but repair old table layouts that were
    created by earlier versions of AFTER3AM. CREATE TABLE IF NOT EXISTS cannot
    change an existing table, so old comments tables may not have content_id.
    """
    conn = get_db()
    try:
        # ---- comments compatibility ----
        comment_cols = [
            row["name"] for row in
            conn.execute("PRAGMA table_info(comments)").fetchall()
        ]
        if comment_cols and "content_id" not in comment_cols:
            # Find the most likely old foreign-key column, if one exists.
            old_fk = next(
                (c for c in ("entry_id", "post_id", "cid", "content", "item_id")
                 if c in comment_cols),
                None,
            )
            old_user = next(
                (c for c in ("user_id", "username", "user", "author_id")
                 if c in comment_cols),
                None,
            )
            old_author = next(
                (c for c in ("author", "name", "username")
                 if c in comment_cols),
                None,
            )
            old_text = next(
                (c for c in ("text", "comment", "body", "content_text")
                 if c in comment_cols),
                None,
            )
            old_date = next(
                (c for c in ("created_at", "date", "timestamp")
                 if c in comment_cols),
                None,
            )

            conn.execute("ALTER TABLE comments RENAME TO comments_legacy")
            conn.execute("""
                CREATE TABLE comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (content_id) REFERENCES contents(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_content ON comments(content_id)")

            # Preserve legacy comments when their old schema is recognizable.
            if old_fk and old_text:
                def qident(name):
                    return '"' + name.replace('"', '""') + '"'

                fk_expr = qident(old_fk)
                text_expr = qident(old_text)
                user_expr = qident(old_user) if old_user else "''"
                author_expr = qident(old_author) if old_author else "''"
                date_expr = qident(old_date) if old_date else "''"

                conn.execute(f"""
                    INSERT INTO comments
                        (content_id, user_id, author, text, created_at)
                    SELECT
                        CAST({fk_expr} AS INTEGER),
                        COALESCE(CAST({user_expr} AS TEXT), ''),
                        COALESCE(CAST({author_expr} AS TEXT), ''),
                        CAST({text_expr} AS TEXT),
                        COALESCE(CAST({date_expr} AS TEXT), '')
                    FROM comments_legacy
                    WHERE CAST({fk_expr} AS INTEGER) IN (SELECT id FROM contents)
                """)

        # ---- stars compatibility ----
        star_cols = [
            row["name"] for row in
            conn.execute("PRAGMA table_info(stars)").fetchall()
        ]
        if star_cols and ("content_id" not in star_cols or "user_id" not in star_cols):
            # The current application needs this exact pair of columns.
            conn.execute("ALTER TABLE stars RENAME TO stars_legacy")
            conn.execute("""
                CREATE TABLE stars (
                    content_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (content_id, user_id),
                    FOREIGN KEY (content_id) REFERENCES contents(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stars_content ON stars(content_id)")

        conn.commit()
    finally:
        conn.close()


init_db()
repair_existing_schema()


def _safe_media_url(relative_path):
    """Build a browser-safe internal URL for a local media file."""
    parts = [p for p in relative_path.replace("\\", "/").split("/") if p not in ("", ".")]
    return "/local-media/" + "/".join(urllib.parse.quote(p, safe="") for p in parts)


def _topic_from_media_path(relative_path):
    """Choose a topic from an optional topic folder without changing old content."""
    topic_names = {t.lower(): t for t in TOPICS}
    parts = [p for p in relative_path.replace("\\", "/").split("/") if p]
    for part in parts[:-1]:
        key = part.strip().lower()
        if key in topic_names:
            return topic_names[key]
    return "Diary"


def _clean_title(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    name = re.sub(r"[_-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() or "Untitled"


def _user_from_media_path(relative_path):
    """If a file lives in video/users/<handle>/..., return (author, handle).
    Each folder under video/users/ is treated as a separate user account.
    Otherwise return None so the default AFTER3AM author is used."""
    parts = [p for p in relative_path.replace("\\", "/").split("/") if p]
    if len(parts) >= 3 and parts[0].lower() == "users":
        handle = parts[1].strip().lower()
        name = re.sub(r"[._-]+", " ", handle).strip().title() or handle
        return name, handle
    return None


def sync_video_folder():
    """Import local reels, images and articles from video/ without changing
    existing database content. Files may be placed directly in video/ or in
    its existing reels/images/articles subfolders.
    """
    conn = get_db()
    imported = 0
    type_by_ext = {
        ".mp4": "reel", ".webm": "reel", ".mov": "reel",
        ".m4v": "reel", ".3gp": "reel", ".avi": "reel", ".mkv": "reel",
        ".jpg": "image", ".jpeg": "image", ".png": "image",
        ".gif": "image", ".webp": "image",
        ".txt": "article", ".html": "article", ".htm": "article", ".md": "article", ".pdf": "article",
    }
    for root, _dirs, files in os.walk(VIDEO_DIR):
        for filename in sorted(files):
            ext = os.path.splitext(filename)[1].lower()
            content_type = type_by_ext.get(ext)
            if not content_type:
                continue
            absolute = os.path.join(root, filename)
            rel = os.path.relpath(absolute, VIDEO_DIR).replace(os.sep, "/")
            media_url = _safe_media_url(rel)
            exists = conn.execute(
                "SELECT 1 FROM contents WHERE url = ? LIMIT 1", (media_url,)
            ).fetchone()
            if exists:
                continue
            title = _clean_title(filename)
            body = ""
            if content_type == "article" and ext != ".pdf":
                try:
                    with open(absolute, "r", encoding="utf-8") as f:
                        body = f.read()[:50000]
                except UnicodeDecodeError:
                    with open(absolute, "r", encoding="utf-8", errors="replace") as f:
                        body = f.read()[:50000]
            created_at = datetime.fromtimestamp(os.path.getmtime(absolute)).isoformat(timespec="seconds")
            topic = _topic_from_media_path(rel)
            who = _user_from_media_path(rel)
            author_name, author_handle = who if who else ("AFTER3AM", "after3am")
            conn.execute(
                "INSERT INTO contents (author, handle, title, body, url, type, topic, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (author_name, author_handle, title, body, media_url, content_type, topic, created_at),
            )
            imported += 1
    # If the database already contains the original demo reels with an empty
    # URL, connect them to real local videos instead of showing "Video source
    # not set". This preserves the existing entries while making them usable.
    local_reels = []
    for root, _dirs, files in os.walk(VIDEO_DIR):
        for filename in sorted(files):
            if os.path.splitext(filename)[1].lower() in {
                ".mp4", ".webm", ".mov", ".m4v", ".3gp", ".avi", ".mkv"
            }:
                absolute = os.path.join(root, filename)
                rel = os.path.relpath(absolute, VIDEO_DIR).replace(os.sep, "/")
                # Per-user reels (video/users/<handle>/...) belong to their
                # own users and must not be reused for the demo seed reels.
                if _user_from_media_path(rel):
                    continue
                local_reels.append(_safe_media_url(rel))

    if local_reels:
        empty_seed_reels = conn.execute(
            """SELECT id FROM contents
               WHERE type = 'reel' AND (url IS NULL OR TRIM(url) = '')
               AND handle IN ('moon.frames','dusk.notes','night.diary',
                              'sample.writer','ink.after.dark')
               ORDER BY id ASC"""
        ).fetchall()
        for row, media_url in zip(empty_seed_reels, local_reels):
            conn.execute(
                "UPDATE contents SET url = ? WHERE id = ?",
                (media_url, row["id"])
            )

    conn.commit()
    conn.close()
    return imported


try:
    sync_video_folder()
except Exception as _media_sync_error:
    print("AFTER3AM media sync warning:", repr(_media_sync_error))


# Short demo bios, applied only to users whose bio is still empty.
DEMO_BIOS = {
    "perdu._": "Writing what the night tells me.",
    "moon.frames": "Frames from the quiet hours.",
    "dusk.notes": "Notes between the light and the dark.",
    "night.diary": "A diary that only opens after midnight.",
    "ink.after.dark": "Ink, insomnia and unfinished pages.",
    "sample.writer": "Letters I never sent.",
    "silent.owl": "Awake, watching, saying little.",
    "velvet.hours": "Confessions in a soft voice.",
    "lost.signal": "Somewhere between static and sleep.",
    "paper.moon": "Small thoughts on folded paper.",
}


def sync_users():
    """Make sure every handle that has content also has a row in users."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (handle, name, bio, created_at) "
            "SELECT handle, MIN(author), '', ? FROM contents GROUP BY handle",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        for h, b in DEMO_BIOS.items():
            conn.execute("UPDATE users SET bio = ? WHERE handle = ? AND bio = ''", (b, h))
        conn.commit()
    finally:
        conn.close()


try:
    sync_users()
except Exception as _users_sync_error:
    print("AFTER3AM users sync warning:", repr(_users_sync_error))


@app.route("/local-media/<path:filename>")
def local_media(filename):
    """Safely serve only files inside the local video/ directory."""
    requested = os.path.abspath(os.path.join(VIDEO_DIR, filename))
    video_root = os.path.abspath(VIDEO_DIR)
    if os.path.commonpath([requested, video_root]) != video_root or not os.path.isfile(requested):
        abort(404)
    return send_from_directory(VIDEO_DIR, filename, conditional=True)


def fmt_date(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y")
    except Exception:
        return iso


def fetch_items(where="", params=(), order="c.created_at DESC, c.id DESC", limit=None):
    uid = session.get('user_id', '')
    sql = (
        "SELECT c.*, "
        "(SELECT COUNT(*) FROM stars s WHERE s.content_id = c.id) AS stars, "
        "(SELECT COUNT(*) FROM comments m WHERE m.content_id = c.id) AS comments_n, "
        "EXISTS(SELECT 1 FROM stars s WHERE s.content_id = c.id AND s.user_id = ?) AS starred "
        "FROM contents c " + where + " ORDER BY " + order
    )
    if limit:
        sql += " LIMIT " + str(int(limit))
    conn = get_db()
    rows = conn.execute(sql, (uid,) + tuple(params)).fetchall()
    conn.close()
    return rows


def entries_for_handle(handle):
    out = []
    for it in fetch_items("WHERE c.handle = ?", (handle,)):
        out.append({
            "id": it["id"],
            "author": str(escape(it["author"])),
            "handle": str(escape(it["handle"])),
            "title": str(escape(it["title"])),
            "content": str(escape((it["body"] or "")[:90])),
            "topic": it["topic"],
            "date": fmt_date(it["created_at"]),
            "image": it["url"] if it["type"] == "image" else "",
            "appreciations": it["stars"],
            "responses_count": it["comments_n"],
        })
    return out


def action_bar(it):
    starred = bool(it["starred"])
    star_icon = "fa-solid" if starred else "fa-regular"
    on_cls = " on" if starred else ""
    return f"""
    <div class="ab">
        <button type="button" class="ab-btn star-btn{on_cls}" data-id="{it['id']}" aria-label="Appreciate"><i class="{star_icon} fa-star"></i><span class="star-count">{it['stars']}</span></button>
        <a class="ab-btn" href="/entry/{it['id']}#comments" aria-label="Comments"><i class="fa-regular fa-comment"></i><span>{it['comments_n']}</span></a>
        <button type="button" class="ab-btn share-btn" data-id="{it['id']}" data-title="{escape(it['title'])}" aria-label="Share"><i class="fa-solid fa-arrow-up-from-bracket"></i></button>
    </div>
    """


def desc_block(body):
    """One-line description with a 'more' toggle for reading the rest."""
    body = (body or "").strip()
    if not body:
        return ""
    return (
        '<div class="desc">'
        f'<span class="desc-text">{escape(body)}</span>'
        '<button type="button" class="desc-more" hidden>more</button>'
        '</div>'
    )


def feed_card(it):
    t = it["type"]
    title = escape(it["title"])
    body = it["body"] or ""
    href = f"/reels/{it['id']}" if t == "reel" else f"/entry/{it['id']}"
    meta = (
        f'<div class="fc-meta"><strong>{escape(it["author"])}</strong>'
        f'<span>@{escape(it["handle"])}</span>'
        f'<span class="fc-badge">{escape(it["topic"])}</span>'
        f'<span class="fc-badge type">{TYPE_LABELS.get(t, str(t).title() if t else "Entry")}</span></div>'
    )
    media = ""
    if t == "image":
        media = f'<a class="fc-media" href="{href}"><img src="{escape(it["url"])}" alt="{title}"></a>'
    elif t == "reel":
        if it["url"]:
            inner = f'<video src="{escape(it["url"])}" muted playsinline preload="metadata"></video>'
        else:
            inner = '<div class="fc-nosrc">Video source not set</div>'
        media = f'<a class="fc-reel" href="{href}">{inner}<span class="fc-play"><i class="fa-solid fa-play"></i></span></a>'
    # PDF articles are rendered by the Flask server as images. This avoids
    # Android browsers replacing the PDF with their own "Open" viewer.
    article_content = ""
    if t == "article":
        if str(it["url"]).lower().endswith(".pdf"):
            pdf_id = str(it["id"])
            page_count = 1
            if fitz:
                try:
                    rel = str(it["url"]).split("/local-media/", 1)[1]
                    pdf_path = os.path.abspath(os.path.join(VIDEO_DIR, urllib.parse.unquote(rel)))
                    base_dir = os.path.abspath(VIDEO_DIR)
                    if os.path.commonpath([base_dir, pdf_path]) == base_dir and os.path.isfile(pdf_path):
                        with fitz.open(pdf_path) as _doc:
                            page_count = max(1, _doc.page_count)
                except Exception:
                    page_count = 1
            article_content = f"""
                <div class="fc-article-pdf" id="pdf_{pdf_id}_box" data-pages="{page_count}">
                    <div class="pdf-toolbar">
                        <button type="button" onclick="pdfPrev('{pdf_id}')">‹</button>
                        <span id="pdf_{pdf_id}_page">Page 1 / {page_count}</span>
                        <button type="button" onclick="pdfNext('{pdf_id}')">›</button>
                        <a href="{escape(it["url"])}" target="_blank" rel="noopener">Open PDF</a>
                    </div>
                    <img id="pdf_{pdf_id}_img" src="/pdf-page/{pdf_id}/1" alt="{title} - Page 1" loading="lazy">
                </div>
                <script>
                (function() {{
                    window._pdfPages = window._pdfPages || {{}};
                    window._pdfPages['{pdf_id}'] = {{page: 1, total: {page_count}}};
                    window.pdfShow = function(id) {{
                        var v = window._pdfPages[id];
                        if (!v) return;
                        var img = document.getElementById('pdf_' + id + '_img');
                        var label = document.getElementById('pdf_' + id + '_page');
                        if (!img) return;
                        img.src = '/pdf-page/' + id + '/' + v.page;
                        img.alt = 'PDF page ' + v.page;
                        if (label) label.textContent = 'Page ' + v.page + ' / ' + v.total;
                    }};
                    window.pdfPrev = function(id) {{
                        var v = window._pdfPages[id];
                        if (v && v.page > 1) {{ v.page--; window.pdfShow(id); }}
                    }};
                    window.pdfNext = function(id) {{
                        var v = window._pdfPages[id];
                        if (v && v.page < v.total) {{ v.page++; window.pdfShow(id); }}
                    }};
                }})();
                </script>
            """
    snippet = ""
    if t != "article" and body:
        snippet = desc_block(body)

    return f"""
    <div class="fc-card">
        {meta}
        <a href="{href}" class="fc-title">{title}</a>
        {media}
        {article_content}
        {snippet}
        <div class="fc-foot">
            <span>{fmt_date(it['created_at'])}</span>
            {action_bar(it)}
        </div>
    </div>
    """


FEED_CSS = """
<style>
.fc-wrap{padding:16px 14px 24px 14px;}
.fc-label{font-size:.85rem;color:#8d8ba8;margin:4px 6px 12px 6px;}
.fc-card{margin:0 0 16px 0;padding:18px 18px 12px 18px;border-radius:24px;border:1px solid #3d3590;background:linear-gradient(145deg,rgba(40,32,100,.3),rgba(12,11,30,.92));box-shadow:0 0 16px rgba(99,82,255,.12);}
.fc-meta{display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:.85rem;color:#7d7b99;margin-bottom:10px;}
.fc-meta strong{color:#c9c6e6;}
.fc-badge{background:#1a1a2e;color:#8ab4f8;padding:3px 9px;border-radius:12px;font-size:.72rem;}
.fc-badge.type{color:#b3a8ff;border:1px solid #3a3480;background:transparent;}
.fc-title{display:block;font-size:1.3rem;color:#fff;text-decoration:none;line-height:1.3;margin-bottom:10px;}
.fc-snippet{color:#8d86c0;font-size:.98rem;line-height:1.55;margin-bottom:12px;}
.fc-media{display:block;margin:0 0 12px 0;border-radius:16px;overflow:hidden;background:#0d0d1a;}
.fc-media img{display:block;width:100%;max-height:340px;object-fit:cover;}
.fc-reel{position:relative;display:block;min-height:220px;border-radius:16px;overflow:hidden;margin-bottom:12px;background:#000;}
.desc{display:flex;align-items:baseline;gap:8px;color:#8d86c0;font-size:.98rem;line-height:1.5;margin-bottom:12px;}
.desc-text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.desc.open{display:block;}
.desc.open .desc-text{white-space:pre-line;overflow:visible;text-overflow:clip;}
.desc-more{flex:0 0 auto;background:none;border:none;padding:0;color:#a99bff;font-weight:600;font-size:.92rem;font-family:inherit;cursor:pointer;pointer-events:auto;}
.desc.open .desc-more{display:block;margin-top:4px;}

.fc-article-body{
    margin: 10px 0 14px;
    padding: 14px 15px;
    white-space: pre-wrap;
    line-height: 1.65;
    color: #e8e8ee;
    background: rgba(255,255,255,.035);
    border-radius: 14px;
    overflow-wrap: anywhere;
}
.fc-article-pdf{
    margin: 10px 0 14px;
    width: 100%;
    background: #111;
    border-radius: 14px;
    overflow: hidden;
}
.fc-article-pdf .pdf-toolbar{
    min-height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 6px 10px;
    background: #17181c;
    color: #fff;
}
.fc-article-pdf .pdf-toolbar button,
.fc-article-pdf .pdf-toolbar a{
    border: 0;
    border-radius: 9px;
    padding: 7px 12px;
    background: #292b31;
    color: #fff;
    text-decoration: none;
    font-size: 14px;
}
.fc-article-pdf canvas{
    display: block;
    width: 100%;
    height: auto;
    background: #fff;
}
.fc-article-pdf .pdf-loading{
    padding: 24px;
    text-align: center;
    color: #bbb;
    background: #111;
}
.fc-reel video{width:100%;height:auto;max-height:75vh;object-fit:contain;display:block;background:#000;}
.fc-play{position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:2.2rem;text-shadow:0 0 18px rgba(0,0,0,.6);}
.fc-nosrc{position:absolute;left:0;right:0;bottom:12px;text-align:center;color:#7d7b99;font-size:.75rem;}
.fc-foot{display:flex;justify-content:space-between;align-items:center;border-top:1px solid #1d1b45;padding-top:8px;color:#7d7b99;font-size:.8rem;}
.ab{display:flex;align-items:center;gap:4px;}
.ab-btn{background:none;border:none;color:#8d8ba8;font-size:1rem;display:flex;align-items:center;gap:6px;padding:7px 10px;border-radius:20px;cursor:pointer;text-decoration:none;font-family:inherit;-webkit-tap-highlight-color:transparent;}
.ab-btn span{font-size:.82rem;}
.ab-btn:hover{background:rgba(124,108,255,.12);color:#fff;}
.ab-btn.on{color:#a99bff;}
.fc-empty{color:#666;text-align:center;padding:40px 20px;}
.fc-toast{position:fixed;left:50%;bottom:90px;transform:translateX(-50%) translateY(10px);background:#1a1844;color:#fff;border:1px solid #4b3fb5;padding:11px 18px;border-radius:24px;font-size:.88rem;opacity:0;pointer-events:none;transition:all .25s ease;z-index:300;max-width:90%;text-align:center;}
.fc-toast.show{opacity:1;transform:translateX(-50%) translateY(0);}
.ch-row{display:flex;gap:8px;overflow-x:auto;padding:4px 0 10px 0;}
.ch{flex:0 0 auto;padding:8px 16px;border-radius:20px;border:1px solid #2d2a66;color:#9a98c4;text-decoration:none;font-size:.88rem;background:rgba(18,17,42,.7);}
.ch.active{background:#5b49d6;color:#fff;border-color:#5b49d6;}
.fc-search{position:relative;margin-bottom:12px;}
.fc-search i{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:#77759f;}
.fc-search input{width:100%;box-sizing:border-box;background:rgba(18,17,42,.85);border:1px solid #26244f;color:#fff;border-radius:16px;padding:14px 16px 14px 44px;font-size:1rem;font-family:inherit;}
.fc-search input:focus{outline:none;border-color:#7c6cff;box-shadow:0 0 0 3px rgba(124,108,255,.18);}
.fc-sec{color:#8d8ba8;font-size:.8rem;letter-spacing:1px;margin:14px 6px 8px 6px;}
.en-title{color:#fff;font-weight:600;font-size:1.6rem;margin:8px 0 6px 0;line-height:1.3;}
.en-date{font-size:.75rem;color:#666;margin-bottom:18px;}
.en-media{margin-bottom:16px;border-radius:16px;overflow:hidden;}
.en-media img,.en-media video{display:block;width:100%;}
.en-media.pdf-viewer{background:#111;min-height:70vh;}
.en-media.pdf-viewer iframe{display:block;width:100%;height:75vh;min-height:520px;border:0;background:#fff;}
.en-body{line-height:1.8;font-size:1.05rem;color:#ddd;white-space:pre-line;margin-bottom:16px;}
.cm{padding:12px 0;border-top:1px solid #1d1b45;color:#cfcdea;font-size:.95rem;line-height:1.5;}
.cm b{color:#fff;margin-right:6px;}
.cm small{display:block;color:#7d7b99;margin-top:3px;}
.cm-form textarea{width:100%;box-sizing:border-box;height:84px;resize:none;background:rgba(18,17,42,.85);border:1px solid #26244f;color:#fff;border-radius:14px;padding:12px 14px;font-size:.95rem;font-family:inherit;margin:10px 0;}
.cm-form textarea:focus{outline:none;border-color:#7c6cff;}
.cm-btn{background:linear-gradient(90deg,#8ea2ff,#a45cff);color:#0d0b2a;border:none;border-radius:16px;padding:11px 22px;font-weight:700;cursor:pointer;font-family:inherit;}
.rv-body{margin:0;background:#000;display:flex;justify-content:center;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.rv-wrap{position:relative;width:100%;max-width:600px;height:100vh;height:100dvh;background:#000;}
.rv-top{position:absolute;top:0;left:0;right:0;z-index:20;display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:linear-gradient(180deg,rgba(0,0,0,.65),transparent);}
.rv-icon{background:rgba(10,10,25,.55);border:none;color:#fff;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;text-decoration:none;font-size:1rem;cursor:pointer;}
.rv-topic{color:#fff;font-weight:600;}
.rv-scroll{position:relative;height:100%;overflow-y:scroll;scroll-snap-type:y mandatory;-webkit-overflow-scrolling:touch;}
.rv-item{position:relative;height:100%;scroll-snap-align:start;scroll-snap-stop:always;background:#07070f;overflow:hidden;}
.rv-video{width:100%;height:100%;object-fit:contain;display:block;background:#000;}
.rv-item[data-orientation="portrait"] .rv-video{object-fit:contain;}
.rv-item[data-orientation="landscape"] .rv-video{object-fit:contain;}
.rv-item[data-orientation="square"] .rv-video{object-fit:contain;}
.rv-fallback{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#7d7b99;background:linear-gradient(160deg,#1a1450,#07070f);font-size:.9rem;}
.rv-fallback i{font-size:2.4rem;color:#5b49d6;}
.rv-shade{position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(0deg,rgba(0,0,0,.7) 0%,transparent 45%);pointer-events:none;}
.rv-info{position:absolute;left:16px;right:96px;bottom:28px;color:#fff;pointer-events:none;}
.rv-info .desc{color:#e8e6ff;font-size:.92rem;margin:8px 0 0 0;pointer-events:auto;}
.rv-info .desc.open{max-height:38vh;overflow-y:auto;background:rgba(0,0,0,.45);border-radius:12px;padding:8px 10px;}
.rv-author{font-weight:700;margin-bottom:6px;}
.rv-title{font-size:1.05rem;margin-bottom:8px;line-height:1.35;}
.rv-actions{position:absolute;right:10px;bottom:28px;z-index:5;}
.rv-actions .ab{flex-direction:column;gap:12px;}
.rv-actions .ab-btn{flex-direction:column;gap:4px;color:#fff;font-size:1.4rem;background:rgba(10,10,25,.4);width:54px;padding:10px 0;justify-content:center;}
</style>
"""

FEED_JS = """
<script>
(function () {
    var toast = document.getElementById('fcToast');
    var timer = null;
    function showToast(msg) {
        if (!toast) { return; }
        toast.textContent = msg;
        toast.classList.add('show');
        clearTimeout(timer);
        timer = setTimeout(function () { toast.classList.remove('show'); }, 2400);
    }
    function copyFallback(text) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
        document.body.removeChild(ta);
        showToast(ok ? 'Link copied' : 'Copy this link: ' + text);
    }
    function shareItem(btn) {
        var url = window.location.origin + '/entry/' + btn.dataset.id;
        var payload = { title: btn.dataset.title, text: btn.dataset.title + ' on AFTER3AM', url: url };
        if (navigator.share) {
            navigator.share(payload).catch(function (err) {
                if (err && err.name === 'AbortError') { return; }
                copyFallback(url);
            });
        } else if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(url).then(function () { showToast('Link copied'); })
                .catch(function () { copyFallback(url); });
        } else {
            copyFallback(url);
        }
    }
    function toggleStar(btn) {
        if (btn.dataset.busy) { return; }
        btn.dataset.busy = '1';
        var id = btn.dataset.id;
        fetch('/api/star/' + id, { method: 'POST', credentials: 'same-origin' })
            .then(function (r) {
                if (r.status === 401) { window.location.href = '/login'; return null; }
                return r.json();
            })
            .then(function (d) {
                if (!d || d.error) { return; }
                var all = document.querySelectorAll('.star-btn[data-id="' + id + '"]');
                for (var i = 0; i < all.length; i++) {
                    var b = all[i];
                    if (d.starred) { b.classList.add('on'); } else { b.classList.remove('on'); }
                    b.querySelector('i').className = (d.starred ? 'fa-solid' : 'fa-regular') + ' fa-star';
                    b.querySelector('.star-count').textContent = d.stars;
                }
            })
            .catch(function () { showToast('Could not save your appreciation'); })
            .then(function () { delete btn.dataset.busy; });
    }
    function initDesc() {
        var all = document.querySelectorAll('.desc');
        for (var i = 0; i < all.length; i++) {
            var d = all[i], t = d.querySelector('.desc-text'), b = d.querySelector('.desc-more');
            if (!t || !b || d.classList.contains('open')) { continue; }
            b.hidden = !(t.scrollWidth > t.clientWidth + 1);
        }
    }
    initDesc();
    window.addEventListener('load', initDesc);
    window.addEventListener('resize', initDesc);
    document.addEventListener('click', function (e) {
        var more = e.target.closest('.desc-more');
        if (more) {
            var d = more.closest('.desc');
            var open = d.classList.toggle('open');
            more.hidden = false;
            more.textContent = open ? 'less' : 'more';
            if (!open) { initDesc(); }
            return;
        }
        var star = e.target.closest('.star-btn');
        if (star) { toggleStar(star); return; }
        var sh = e.target.closest('.share-btn');
        if (sh) { shareItem(sh); }
    });
})();
</script>
"""

REEL_JS = """
<script>
(function () {
    var scroller = document.getElementById('rvScroll');
    // Adapt each reel to its real video dimensions instead of forcing every
    // video into a YouTube-style crop. Portrait videos behave like Instagram
    // Reels, landscape videos keep their 16:9 shape, and square videos stay square.
    scroller.querySelectorAll('.rv-item').forEach(function (item) {
        var video = item.querySelector('video');
        if (!video) return;
        function updateOrientation() {
            if (!video.videoWidth || !video.videoHeight) return;
            var ratio = video.videoWidth / video.videoHeight;
            var orientation = ratio < 0.9 ? 'portrait' : (ratio > 1.1 ? 'landscape' : 'square');
            item.setAttribute('data-orientation', orientation);
        }
        video.addEventListener('loadedmetadata', updateOrientation);
        if (video.readyState >= 1) updateOrientation();
    });

    var start = document.getElementById('reel-' + scroller.dataset.start);
    if (start) { scroller.scrollTop = start.offsetTop; }
    var vids = scroller.querySelectorAll('video');
    var muted = true;
    var muteBtn = document.getElementById('rvMute');
    function applyMute() {
        for (var i = 0; i < vids.length; i++) { vids[i].muted = muted; }
        muteBtn.querySelector('i').className = muted ? 'fa-solid fa-volume-xmark' : 'fa-solid fa-volume-high';
    }
    muteBtn.addEventListener('click', function () { muted = !muted; applyMute(); });
    var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
            var v = en.target.querySelector('video');
            if (!v) { return; }
            if (en.isIntersecting) {
                var p = v.play();
                if (p && p.catch) { p.catch(function () {}); }
            } else {
                v.pause();
            }
        });
    }, { root: scroller, threshold: 0.65 });
    var items = scroller.querySelectorAll('.rv-item');
    for (var i = 0; i < items.length; i++) { io.observe(items[i]); }
    for (var j = 0; j < vids.length; j++) {
        vids[j].addEventListener('click', function (e) {
            var v = e.currentTarget;
            if (v.paused) { v.play(); } else { v.pause(); }
        });
    }
})();
</script>
"""

if 'all_users' not in app.config:
    app.config['all_users'] = {"perdu._"}

if 'user_profile' not in app.config:
    app.config['user_profile'] = {
        "name": "Perdu",
        "handle": "perdu._",
        "bio": "",
        "website": "",
        "location": "",
        "birthday": "",
        "privacy": "Public",
        "avatar": "",
        "name_last_changed": None,
        "username_changes_today": 0,
        "username_last_date": None
    }

NW_CSS = """
<style>
.nw-page{position:relative;min-height:calc(100vh - 52px);overflow:hidden;overflow:clip;background:radial-gradient(120% 60% at 100% 0%,#150f3a 0%,transparent 55%),radial-gradient(100% 50% at 0% 100%,#120d33 0%,transparent 55%),#07070f;}
.nw-page::before{content:'';position:absolute;top:-95px;right:-95px;width:230px;height:230px;border-radius:50%;background:radial-gradient(circle at 30% 70%,#4c3bd6 0%,#1a1250 55%,transparent 72%);box-shadow:0 0 60px rgba(99,82,255,.35);opacity:.85;pointer-events:none;}
.nw-page::after{content:'';position:absolute;bottom:-150px;left:-130px;width:320px;height:320px;border-radius:50%;background:radial-gradient(circle at 70% 30%,#3b2fb8 0%,#150f40 55%,transparent 72%);box-shadow:0 0 70px rgba(99,82,255,.3);opacity:.8;pointer-events:none;}
.nw-page .top-bar{justify-content:flex-start;gap:22px;background:rgba(7,7,15,.72);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid #1c1b3d;}
.nw-back{display:flex;align-items:center;}
.nw-body{position:relative;z-index:1;padding:22px 18px 30px 18px;}
.nw-sub{color:#9a98c4;font-size:.95rem;text-align:center;margin:4px 0 24px 0;}
.nw-card{display:flex;align-items:center;gap:16px;padding:20px 16px;margin-bottom:16px;border-radius:22px;background:linear-gradient(145deg,rgba(30,27,70,.55),rgba(14,13,34,.85));border:1px solid #26244f;color:#fff;text-decoration:none;transition:all .25s ease;}
.nw-card.featured,.nw-card:hover,.nw-card:active{border-color:#7c6cff;box-shadow:0 0 24px rgba(124,108,255,.35),inset 0 0 18px rgba(124,108,255,.12);}
.nw-icon{flex:0 0 64px;height:64px;border-radius:18px;background:linear-gradient(145deg,#2a2660,#15133a);display:flex;align-items:center;justify-content:center;}
.nw-divider{width:1px;align-self:stretch;background:#2d2b5c;margin:6px 0;}
.nw-text{flex:1;min-width:0;}
.nw-title{font-weight:600;font-size:1.15rem;}
.nw-desc{color:#8f8db8;font-size:.82rem;margin-top:4px;line-height:1.4;}
.nw-chev{flex:0 0 34px;height:34px;border-radius:50%;background:#1f1d45;display:flex;align-items:center;justify-content:center;}
.nw-field{position:relative;margin-bottom:14px;}
.nw-field .lead{position:absolute;left:16px;top:50%;transform:translateY(-50%);pointer-events:none;}
.nw-field.tall .lead{top:20px;transform:none;}
.nw-field .sel-chev{position:absolute;right:16px;top:50%;transform:translateY(-50%);pointer-events:none;}
.nw-input{width:100%;box-sizing:border-box;background:rgba(18,17,42,.85);border:1px solid #26244f;color:#fff;border-radius:16px;padding:16px 16px 16px 52px;font-size:1rem;font-family:inherit;transition:border-color .2s,box-shadow .2s;}
.nw-input::placeholder{color:#77759f;}
.nw-input:focus{outline:none;border-color:#7c6cff;box-shadow:0 0 0 3px rgba(124,108,255,.18);}
select.nw-input{appearance:none;-webkit-appearance:none;font-weight:500;}
textarea.nw-input{height:210px;resize:none;padding-top:18px;padding-bottom:38px;line-height:1.5;}
.nw-count{position:absolute;right:16px;bottom:12px;font-size:.8rem;color:#7c7aa8;}
.nw-upload-label{display:flex;align-items:center;gap:10px;color:#e8e6ff;font-weight:500;margin-bottom:10px;}
.nw-upload-label svg{width:24px;height:24px;}
.nw-upload{border:2px dashed #4b43a8;border-radius:18px;background:rgba(18,17,42,.6);padding:26px 16px;text-align:center;cursor:pointer;margin-bottom:16px;transition:all .2s;}
.nw-upload:hover{border-color:#7c6cff;background:rgba(24,22,56,.8);}
.nw-upload img{max-width:100%;max-height:240px;border-radius:12px;object-fit:cover;}
.nw-publish{width:100%;border:none;border-radius:20px;padding:16px;font-size:1.1rem;font-weight:700;color:#0d0b2a;background:linear-gradient(90deg,#8ea2ff,#a45cff);display:flex;align-items:center;justify-content:center;gap:12px;cursor:pointer;box-shadow:0 0 24px rgba(140,110,255,.35);margin-top:10px;transition:opacity .2s;}
.nw-publish:hover{opacity:.92;}
</style>
"""

ICON_BACK = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#e8e6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>'
ICON_CHEV = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>'
ICON_SEL = '<svg class="sel-chev" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>'
ICON_T = '<svg class="lead" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#a99bff" stroke-width="2.6" stroke-linecap="round"><path d="M5 6h14M12 6v13"/></svg>'
ICON_BOOK = '<svg class="lead" width="24" height="24" viewBox="0 0 24 24" fill="#c9c0ff" stroke="#a99bff" stroke-width="1.6" stroke-linejoin="round"><path d="M12 6c-2-1.5-5-2-8-1.5v13c3-.5 6 0 8 1.5 2-1.5 5-2 8-1.5v-13c-3-.5-6 0-8 1.5zM12 6v13"/></svg>'
ICON_PEN = '<svg class="lead" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#a99bff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20l1-4L16 5l3 3L8 19l-4 1zM14 7l3 3"/></svg>'
ICON_PLANE = '<svg width="26" height="26" viewBox="0 0 24 24" fill="#0d0b2a"><path d="M21 3L3 10.5l6.5 2.5L12 20l2.5-6.5L21 3z"/></svg>'
ICON_IMG = '<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#a99bff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="16" cy="8.5" r="1.6" fill="#a99bff"/><path d="M3 17l5-5 4 4 3-3 6 6"/></svg>'
ICON_CAM = '<svg width="38" height="38" viewBox="0 0 24 24" fill="#f1efff"><path d="M9 4l-1.5 2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-2.5L15 4H9zm3 4.5a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zm0 2.2a2.3 2.3 0 1 0 0 4.6 2.3 2.3 0 0 0 0-4.6z"/><path d="M19 1l.9 2.1L22 4l-2.1.9L19 7l-.9-2.1L16 4l2.1-.9z" fill="#7c6cff"/></svg>'
ICON_EDIT = '<svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#a99bff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h9M3 11h7M3 16h6"/><path d="M12 19l.8-3.2L19 9.6l2.4 2.4-6.2 6.2L12 19z" fill="#7c6cff" stroke="#7c6cff"/></svg>'

def base_layout(title, content_html, error_msg=None, active_page="home"):
    err_banner = f"""
    <div style="background: #2c1515; border-bottom: 1px solid #ff5555; color: #ff8888; padding: 10px 20px; font-size: 0.85rem; text-align: center; font-family: sans-serif;">
        {error_msg}
    </div>
    """ if error_msg else ""
    
    home_style = "color: #6a8caf; font-weight: bold;" if active_page == "home" else "color: #777; text-decoration: none;"
    discover_style = "color: #6a8caf; font-weight: bold;" if active_page == "discover" else "color: #777; text-decoration: none;"
    write_style = "color: #6a8caf; font-weight: bold;" if active_page == "write" else "color: #777; text-decoration: none;"
    activity_style = "color: #6a8caf; font-weight: bold;" if active_page == "activity" else "color: #777; text-decoration: none;"
    space_style = "color: #6a8caf; font-weight: bold;" if active_page == "space" else "color: #777; text-decoration: none;"

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} — AFTER3AM</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
        <style>
            body {{ background: #0d0d0d; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; display: flex; justify-content: center; }}
            .container {{ width: 100%; max-width: 600px; min-height: 100vh; background: #0d0d0d; border-left: 1px solid #222; border-right: 1px solid #222; display: flex; flex-direction: column; justify-content: space-between; box-sizing: border-box; }}
            .top-bar {{ display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; border-bottom: 1px solid #1a1a1a; background: #0d0d0d; position: sticky; top: 0; z-index: 10; }}
            .top-bar a {{ color: #fff; text-decoration: none; font-size: 1rem; }}
            .top-bar-title {{ font-size: 1.05rem; font-weight: 600; color: #fff; }}
            .content {{ padding: 0; flex: 1; overflow-y: auto; }}
            
            .profile-banner {{ 
                width: 100%; 
                height: 140px; 
                background: linear-gradient(135deg, #020408 0%, #060913 50%, #0d0d0d 100%);
                border-bottom: 1px solid #1a1a1a;
                position: relative;
                overflow: hidden;
            }}
            .profile-banner::before {{
                content: "";
                position: absolute;
                top: 40%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 26px;
                height: 26px;
                background: #f8fafc;
                clip-path: polygon(50% 0%, 63% 37%, 100% 50%, 63% 63%, 50% 100%, 37% 63%, 0% 50%, 37% 37%);
                box-shadow: 0 0 25px #60a5fa, 0 0 50px #1d4ed8;
            }}
            .profile-banner::after {{
                content: "";
                position: absolute;
                top: 15px;
                right: 30px;
                width: 30px;
                height: 30px;
                background: radial-gradient(circle, #f1f5f9 60%, #64748b 100%);
                border-radius: 50%;
                box-shadow: 0 0 15px rgba(241, 245, 249, 0.5);
            }}

            .profile-header-area {{ padding: 0 20px; position: relative; margin-bottom: 20px; border-bottom: 1px solid #1a1a1a; padding-bottom: 15px; }}
            .profile-avatar {{ width: 80px; height: 80px; border-radius: 50%; background: #2a2a2a; border: 4px solid #0d0d0d; position: absolute; top: -45px; left: 20px; display: flex; align-items: center; justify-content: center; font-size: 1.8rem; color: #fff; background-size: cover; background-position: center; }}
            .profile-actions {{ display: flex; justify-content: flex-end; padding-top: 10px; gap: 10px; }}
            .btn-action {{ background: transparent; border: 1px solid #333; color: #fff; padding: 6px 16px; border-radius: 20px; font-size: 0.85rem; cursor: pointer; text-decoration: none; display: inline-block; }}
            .btn-action:hover {{ background: #222; }}
            .profile-names {{ margin-top: 35px; }}
            .profile-names h2 {{ margin: 0; font-size: 1.2rem; color: #fff; font-weight: 600; }}
            .profile-handle {{ color: #777; font-size: 0.85rem; margin-top: 2px; }}
            .profile-bio {{ font-size: 0.9rem; color: #ccc; margin-top: 10px; line-height: 1.5; }}
            .profile-stats {{ display: flex; gap: 15px; font-size: 0.85rem; margin-top: 12px; color: #888; }}
            .profile-stats strong {{ color: #fff; }}
            .profile-tabs {{ display: flex; justify-content: space-around; border-bottom: 1px solid #1a1a1a; font-size: 0.85rem; }}
            .profile-tabs a {{ padding: 12px 0; color: #777; text-decoration: none; border-bottom: 2px solid transparent; }}
            .profile-tabs a.active {{ color: #fff; border-bottom: 2px solid #fff; }}
            
            .edit-avatar-section {{ display: flex; flex-direction: column; align-items: center; margin: 25px 0; cursor: pointer; }}
            .edit-avatar-circle {{ width: 96px; height: 96px; border-radius: 50%; background: #1a1a1a; display: flex; align-items: center; justify-content: center; position: relative; color: #888; font-size: 2rem; border: 2px solid #333; overflow: hidden; background-size: cover; background-position: center; }}
            .camera-badge {{ position: absolute; bottom: 0; right: 0; background: #222; border-radius: 50%; padding: 6px; border: 2px solid #0d0d0d; font-size: 0.8rem; color: #fff; }}
            .edit-form-group {{ padding: 0 20px; margin-bottom: 20px; }}
            .edit-label {{ font-size: 0.85rem; color: #aaa; margin-bottom: 6px; display: block; }}
            
            /* حقول الإدخال والنصوص الموحدة والعصرية (Dark Mode) */
            .edit-input, .edit-textarea {{ 
                width: 100%; 
                background: #141414; 
                color: #fff; 
                border: 1px solid #262626; 
                padding: 12px 15px; 
                border-radius: 10px; 
                box-sizing: border-box; 
                font-size: 0.95rem; 
                font-family: inherit; 
                transition: border-color 0.2s, background 0.2s;
            }}
            .edit-input:focus, .edit-textarea:focus {{
                border-color: #6a8caf;
                background: #181818;
                outline: none;
            }}
            .edit-textarea {{ resize: none; height: 140px; }}
            .char-count {{ text-align: right; font-size: 0.75rem; color: #666; margin-top: 4px; }}
            
            /* واجهة رفع الصور التفاعلية الاحترافية (Modern Upload Box) */
            .modern-upload-box {{
                border: 2px dashed #333;
                background: #141414;
                padding: 25px;
                text-align: center;
                border-radius: 12px;
                cursor: pointer;
                transition: all 0.2s ease;
                margin-bottom: 15px;
            }}
            .modern-upload-box:hover {{
                border-color: #6a8caf;
                background: #181818;
            }}
            .modern-upload-box img {{
                max-width: 100%;
                max-height: 240px;
                border-radius: 8px;
                margin-top: 8px;
                object-fit: cover;
            }}

            /* تصميم عصري لبطاقات الخيارات (Choice Cards) */
            .choice-card {{ 
                display: block; 
                background: #141414; 
                border: 1px solid #222; 
                padding: 25px; 
                border-radius: 14px; 
                color: #fff; 
                text-decoration: none; 
                text-align: center; 
                margin-bottom: 15px; 
                transition: all 0.25s ease; 
            }}
            .choice-card:hover {{ 
                border-color: #6a8caf; 
                background: #181818; 
                transform: translateY(-2px); 
                box-shadow: 0 4px 20px rgba(106, 140, 175, 0.15); 
            }}

            .interactive-menu-item {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-top: 1px solid #161616; color: #fff; text-decoration: none; font-size: 0.9rem; cursor: pointer; transition: background 0.2s; }}
            .interactive-menu-item:hover {{ background: #141414; }}
            .interactive-menu-item span {{ color: #777; font-size: 0.85rem; }}
            
            .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 100; justify-content: center; align-items: flex-end; }}
            .modal-content {{ background: #141414; border: 1px solid #262626; border-top-left-radius: 16px; border-top-right-radius: 16px; width: 100%; max-width: 600px; padding: 25px; box-sizing: border-box; }}
            .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; color: #fff; font-weight: 600; font-size: 1.05rem; }}
            .modal-close {{ background: none; border: none; color: #777; font-size: 1.2rem; cursor: pointer; }}
            .modal-option {{ padding: 14px; background: #1a1a1a; border: 1px solid #262626; border-radius: 8px; color: #fff; margin-bottom: 10px; cursor: pointer; text-align: center; font-size: 0.95rem; }}
            .modal-option:hover {{ background: #222; border-color: #6a8caf; }}

            .entry-card {{ background: #141414; border: 1px solid #222; padding: 20px; border-radius: 8px; margin: 15px 20px; }}
            .author-info {{ font-size: 0.85rem; color: #888; margin-bottom: 8px; }}
            .entry-title {{ font-size: 1.2rem; color: #fff; text-decoration: none; display: block; margin-bottom: 8px; }}
            .entry-snippet {{ font-size: 0.9rem; color: #bbb; line-height: 1.5; margin-bottom: 12px; }}
            .entry-footer {{ display: flex; justify-content: space-between; font-size: 0.75rem; color: #666; border-top: 1px solid #1a1a1a; padding-top: 10px; }}
            .bottom-nav {{ display: flex; justify-content: space-around; background: #0d0d0d; border-top: 1px solid #1a1a1a; padding: 12px 0; position: sticky; bottom: 0; font-size: 0.8rem; }}
            .bottom-nav a {{ text-decoration: none; text-align: center; }}
            button.submit-btn {{ background: #6a8caf; color: #0d0d0d; border: none; padding: 12px 15px; font-weight: bold; border-radius: 8px; cursor: pointer; width: 100%; font-size: 1rem; transition: opacity 0.2s; }}
            button.submit-btn:hover {{ opacity: 0.9; }}
            .badge {{ background: #1a1a1a; color: #8ab4f8; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; }}
        </style>
</head>
    <body>
        <div class="container">
            <div class="content">
                {err_banner}
                {content_html}
            </div>
            <nav class="bottom-nav">
                <a href="/" style="{home_style}">Home</a>
                <a href="/discover" style="{discover_style}">Discover</a>
                <a href="/write_choice" style="{write_style}">+ Write</a>
                <a href="/activity" style="{activity_style}">Activity</a>
                <a href="/space" style="{space_style}">My Space</a>
            </nav>
        </div>
    </body>
    </html>
    """

@app.errorhandler(Exception)
def after3am_internal_error(error):
    import traceback
    traceback.print_exc()
    safe_error = escape(str(error))
    return f"""
    <!doctype html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>AFTER3AM Error</title>
      <style>
        body{{background:#0d0d0d;color:#fff;font-family:sans-serif;padding:24px}}
        .box{{max-width:600px;margin:40px auto;background:#151515;border:1px solid #333;border-radius:14px;padding:22px}}
        h2{{margin-top:0;color:#ff7777}}
        .err{{color:#ffb0b0;background:#241515;border:1px solid #552222;border-radius:8px;padding:12px;word-break:break-word}}
        a{{color:#8ab4f8}}
      </style>
    </head>
    <body><div class="box">
      <h2>AFTER3AM encountered an error</h2>
      <p>The project itself is still intact. The exact error is:</p>
      <div class="err">{safe_error}</div>
    </div></body>
    </html>
    """, 500

@app.route("/")
def home():
    if 'identity' not in session: return redirect(url_for('login'))
    items = fetch_items()
    header_nav = """
    <div class="top-bar">
        <a href="/" style="font-weight: bold; letter-spacing: 1px;">AFTER3AM</a>
        <div style="display: flex; gap: 15px;">
            <a href="/letters">✉️</a>
            <a href="/logout" style="color: #ff5555;">⎋</a>
        </div>
    </div>
    """
    cards = "".join(feed_card(it) for it in items)
    if not cards:
        cards = '<p class="fc-empty">Nothing here yet.</p>'
    body = (
        FEED_CSS + header_nav
        + '<div class="fc-wrap"><div class="fc-label">Reading Feed</div>' + cards + '</div>'
        + '<div class="fc-toast" id="fcToast"></div>' + FEED_JS
    )
    return base_layout("Home", body, active_page="home")

def discover_url(q="", ctype="all", topic=""):
    params = {}
    if q: params["q"] = q
    if ctype and ctype != "all": params["type"] = ctype
    if topic: params["topic"] = topic
    qs = urllib.parse.urlencode(params)
    return "/discover" + ("?" + qs if qs else "")


@app.route("/discover")
def discover():
    if 'identity' not in session: return redirect(url_for('login'))
    q = request.args.get("q", "").strip()[:80]
    ctype = request.args.get("type", "all")
    if ctype not in TYPE_LABELS: ctype = "all"
    topic = request.args.get("topic", "")
    if topic not in TOPICS: topic = ""

    clauses, params = [], []
    if ctype != "all":
        clauses.append("c.type = ?"); params.append(ctype)
    if topic:
        clauses.append("c.topic = ?"); params.append(topic)
    if q:
        like = "%" + q + "%"
        clauses.append("(c.title LIKE ? OR c.body LIKE ? OR c.author LIKE ? OR c.handle LIKE ? OR c.topic LIKE ?)")
        params.extend([like] * 5)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    items = fetch_items(where, params)

    type_chips = "".join(
        f'<a class="ch{" active" if ctype == key else ""}" href="{discover_url(q, key, topic)}">{label}</a>'
        for key, label in [("all", "All"), ("article", "Articles"), ("image", "Images"), ("reel", "Reels")]
    )
    topic_chips = f'<a class="ch{" active" if not topic else ""}" href="{discover_url(q, ctype, "")}">All topics</a>' + "".join(
        f'<a class="ch{" active" if topic == t else ""}" href="{discover_url(q, ctype, t)}">{t}</a>' for t in TOPICS
    )
    hidden = ""
    if ctype != "all": hidden += f'<input type="hidden" name="type" value="{ctype}">'
    if topic: hidden += f'<input type="hidden" name="topic" value="{escape(topic)}">'

    cards = "".join(feed_card(it) for it in items) or '<p class="fc-empty">No results.</p>'
    content = FEED_CSS + f"""
    <div class="top-bar"><span class="top-bar-title">Discover</span></div>
    <div class="fc-wrap">
        <form method="GET" action="/discover" class="fc-search">
            <i class="fa-solid fa-magnifying-glass"></i>
            <input type="text" name="q" value="{escape(q)}" placeholder="Search entries, topics, or writers...">
            {hidden}
        </form>
        <div class="ch-row">{type_chips}</div>
        <div class="ch-row">{topic_chips}</div>
        <div class="fc-sec">{len(items)} RESULTS</div>
        {cards}
    </div>
    <div class="fc-toast" id="fcToast"></div>
    """ + FEED_JS
    return base_layout("Discover", content, active_page="discover")


@app.route("/topic/<name>")
def topic_filter(name):
    if 'identity' not in session: return redirect(url_for('login'))
    if name not in TOPICS: return redirect(url_for('discover'))
    return redirect(url_for('discover', topic=name, type=request.args.get("type")))


@app.route("/reels/<int:rid>")
def reel_viewer(rid):
    if 'identity' not in session: return redirect(url_for('login'))
    current = fetch_items("WHERE c.id = ? AND c.type = 'reel'", (rid,))
    if not current: return "Reel not found", 404
    topic = current[0]["topic"]
    reels = fetch_items("WHERE c.type = 'reel' AND c.topic = ?", (topic,), order="c.created_at DESC, c.id DESC")
    sections = ""
    for it in reels:
        if it["url"]:
            media = f'<video class="rv-video" src="{escape(it["url"])}" loop muted playsinline preload="metadata"></video>'
        else:
            media = '<div class="rv-fallback"><i class="fa-solid fa-film"></i><span>Video source not set</span></div>'
        sections += f"""
        <section class="rv-item" id="reel-{it['id']}" data-orientation="unknown">
            {media}
            <div class="rv-shade"></div>
            <div class="rv-info">
                <div class="rv-author">@{escape(it['handle'])}</div>
                <div class="rv-title">{escape(it['title'])}</div>
                <span class="fc-badge">{escape(it['topic'])}</span>
                {desc_block(it['body'])}
            </div>
            <div class="rv-actions">{action_bar(it)}</div>
        </section>
        """
    back = discover_url("", "reel", topic)
    return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reels — AFTER3AM</title>
        <link rel="stylesheet" href="{FA_URL}">
        {FEED_CSS}
    </head>
    <body class="rv-body">
        <div class="rv-wrap">
            <div class="rv-top">
                <a href="{back}" class="rv-icon" aria-label="Back"><i class="fa-solid fa-arrow-left"></i></a>
                <span class="rv-topic">{escape(topic)}</span>
                <button type="button" class="rv-icon" id="rvMute" aria-label="Sound"><i class="fa-solid fa-volume-xmark"></i></button>
            </div>
            <div class="rv-scroll" id="rvScroll" data-start="{rid}">{sections}</div>
        </div>
        <div class="fc-toast" id="fcToast"></div>
        {FEED_JS}
        {REEL_JS}
    </body>
    </html>
    """


@app.route("/api/star/<int:cid>", methods=["POST"])
def api_star(cid):
    uid = session.get('user_id')
    if not uid:
        return jsonify(error="login required"), 401
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM contents WHERE id = ?", (cid,)).fetchone():
            return jsonify(error="not found"), 404
        cur = conn.execute("DELETE FROM stars WHERE content_id = ? AND user_id = ?", (cid, uid))
        starred = False
        if cur.rowcount == 0:
            conn.execute("INSERT INTO stars (content_id, user_id, created_at) VALUES (?, ?, ?)",
                         (cid, uid, datetime.now().isoformat(timespec='seconds')))
            starred = True
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM stars WHERE content_id = ?", (cid,)).fetchone()[0]
    finally:
        conn.close()
    return jsonify(starred=starred, stars=total)


@app.route("/comment/<int:cid>", methods=["POST"])
def add_comment(cid):
    uid = session.get('user_id')
    if not uid: return redirect(url_for('login'))
    text = request.form.get("text", "").strip()[:500]
    conn = get_db()
    if text and conn.execute("SELECT 1 FROM contents WHERE id = ?", (cid,)).fetchone():
        conn.execute(
            "INSERT INTO comments (content_id, user_id, author, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (cid, uid, app.config['user_profile']['name'], text, datetime.now().isoformat(timespec='seconds')),
        )
        conn.commit()
    conn.close()
    return redirect(url_for('view_entry', entry_id=cid) + "#comments")

@app.route("/write_choice")
def write_choice():
    if 'identity' not in session: return redirect(url_for('login'))
    content = NW_CSS + f"""
    <div class="nw-page">
        <div class="top-bar">
            <a href="/" class="nw-back">{ICON_BACK}</a>
            <span class="top-bar-title">Create New Entry</span>
        </div>
        <div class="nw-body">
            <p class="nw-sub">How would you like to share your thoughts tonight?</p>

            <a href="/write?type=photo" class="nw-card featured">
                <div class="nw-icon">{ICON_CAM}</div>
                <div class="nw-divider"></div>
                <div class="nw-text">
                    <div class="nw-title">Photo Entry</div>
                    <div class="nw-desc">Share a visual moment alongside your words</div>
                </div>
                <div class="nw-chev">{ICON_CHEV}</div>
            </a>

            <a href="/write?type=text" class="nw-card">
                <div class="nw-icon">{ICON_EDIT}</div>
                <div class="nw-divider"></div>
                <div class="nw-text">
                    <div class="nw-title">Text Entry</div>
                    <div class="nw-desc">Express purely through diary or thoughts</div>
                </div>
                <div class="nw-chev">{ICON_CHEV}</div>
            </a>
        </div>
    </div>
    """
    return base_layout("Choose Entry Type", content, active_page="write")

@app.route("/write", methods=["GET", "POST"])
def write():
    if 'identity' not in session: return redirect(url_for('login'))
    entry_type = request.args.get("type", "text")
    
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        topic = request.form.get("topic")
        profile = app.config['user_profile']
        
        img_data = ""
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                file_bytes = file.read()
                import base64
                encoded_img = base64.b64encode(file_bytes).decode('utf-8')
                img_data = f"data:{file.mimetype or 'image/png'};base64,{encoded_img}"

        # في وضع الصورة يجب اختيار صورة (بديل عن required في الحقل المخفي)
        if entry_type == "photo" and not img_data:
            return redirect(url_for('write', type='photo'))

        if topic not in TOPICS:
            topic = "Diary"
        conn = get_db()
        conn.execute(
            "INSERT INTO contents (author, handle, title, body, url, type, topic, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (profile['name'], profile['handle'], title, content, img_data,
             "image" if entry_type == "photo" else "article", topic,
             datetime.now().isoformat(timespec='seconds')),
        )
        conn.commit()
        conn.close()
        return redirect(url_for('space'))
    
    img_upload_html = ""
    if entry_type == "photo":
        img_upload_html = f"""
        <div class="nw-upload-label">{ICON_IMG}<span>Upload Image</span></div>
        <div class="nw-upload" onclick="document.getElementById('hiddenFileInput').click();">
            <div id="uploadPrompt">
                {ICON_IMG}
                <div style="color: #fff; font-weight: 600; font-size: 1.05rem; margin-top: 10px;">Tap to select photo</div>
                <div style="color: #8f8db8; font-size: 0.8rem; margin-top: 4px;">Supports JPG, PNG</div>
            </div>
            <img id="livePreview" style="display: none;">
        </div>
        <input type="file" id="hiddenFileInput" name="image_file" accept="image/*" style="display: none;" onchange="handleImageSelection(event)">
        """

    content = NW_CSS + f"""
    <div class="nw-page">
        <div class="top-bar">
            <a href="/write_choice" class="nw-back">{ICON_BACK}</a>
            <span class="top-bar-title">New {entry_type.capitalize()} Entry</span>
        </div>
        <div class="nw-body">
            <form method="POST" enctype="multipart/form-data">
                {img_upload_html}
                <div class="nw-field">
                    {ICON_T}
                    <input type="text" name="title" placeholder="Title..." required class="nw-input">
                </div>
                <div class="nw-field">
                    {ICON_BOOK}
                    <select name="topic" class="nw-input">
                        <option value="Diary">Diary</option>
                        <option value="Philosophy">Philosophy</option>
                        <option value="Confessions">Confessions</option>
                        <option value="Memories">Memories</option>
                        <option value="Midnight Void">Midnight Void</option>
                        <option value="Solitude">Solitude</option>
                        <option value="Inner Voices">Inner Voices</option>
                    </select>
                    {ICON_SEL}
                </div>
                <div class="nw-field tall">
                    {ICON_PEN}
                    <textarea name="content" placeholder="Write your thoughts..." required maxlength="5000" class="nw-input" oninput="updateCount(this)"></textarea>
                    <div class="nw-count" id="charCount">0/5000</div>
                </div>
                <button type="submit" class="nw-publish">{ICON_PLANE}<span>Publish</span></button>
            </form>
        </div>
    </div>
    <script>
    function updateCount(t) {{
        document.getElementById('charCount').innerText = t.value.length + '/5000';
    }}
    function handleImageSelection(evt) {{
        var f = evt.target.files[0];
        if (f) {{
            var r = new FileReader();
            r.onload = function(e) {{
                var p = document.getElementById('livePreview');
                p.src = e.target.result;
                p.style.display = 'block';
                document.getElementById('uploadPrompt').style.display = 'none';
            }};
            r.readAsDataURL(f);
        }}
    }}
    </script>
    """
    return base_layout("New Entry", content, active_page="write")

@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if 'identity' not in session: return redirect(url_for('login'))
    profile = app.config['user_profile']
    error_msg = None
    now = datetime.now()
    
    if request.method == "POST":
        new_name = request.form.get("name", profile['name']).strip()
        new_handle = request.form.get("handle", profile['handle']).strip().lower()
        new_bio = request.form.get("bio", profile['bio'])
        
        if 'avatar_file' in request.files:
            file = request.files['avatar_file']
            if file and file.filename != '':
                file_bytes = file.read()
                import base64
                encoded_img = base64.b64encode(file_bytes).decode('utf-8')
                profile['avatar'] = f"data:image/png;base64,{encoded_img}"

        if new_name != profile['name']:
            if profile['name_last_changed']:
                last_changed = datetime.fromisoformat(profile['name_last_changed'])
                if (now - last_changed) < timedelta(days=14):
                    days_left = 14 - (now - last_changed).days
                    error_msg = f"You can change your name twice every 14 days. Please wait {days_left} more days."
            if not error_msg:
                profile['name'] = new_name
                profile['name_last_changed'] = now.isoformat()

        if not error_msg and new_handle != profile['handle']:
            if new_handle in app.config['all_users']:
                error_msg = "Username is already taken. Please choose another one."
            else:
                last_date = datetime.fromisoformat(profile['username_last_date']) if profile['username_last_date'] else None
                if last_date and last_date.date() == now.date():
                    if profile['username_changes_today'] >= 2:
                        error_msg = "You have reached the maximum limit of 2 username changes per day."
                    else:
                        profile['username_changes_today'] += 1
                else:
                    profile['username_changes_today'] = 1
                    profile['username_last_date'] = now.isoformat()
                
                if not error_msg:
                    app.config['all_users'].discard(profile['handle'])
                    app.config['all_users'].add(new_handle)
                    profile['handle'] = new_handle

        if not error_msg:
            profile['bio'] = new_bio
            profile['website'] = request.form.get("website", profile['website'])
            profile['location'] = request.form.get("location", profile['location'])
            profile['birthday'] = request.form.get("birthday", profile['birthday'])
            profile['privacy'] = request.form.get("privacy", profile['privacy'])
            return redirect(url_for('space'))
        
    avatar_style = f"background-image: url('{profile['avatar']}');" if profile['avatar'] else ""
    avatar_text = "" if profile['avatar'] else "👤"
    
    website_val = profile['website'] if profile['website'] else 'Add a link'
    location_val = profile['location'] if profile['location'] else 'Add location'
    birthday_val = profile['birthday'] if profile['birthday'] else 'Add birthday'
    privacy_val = profile['privacy'] if profile['privacy'] else 'Public'
    
    avatar_icon = "" if profile['avatar'] else ICON_USER

    content = PF_CSS + PF_EDIT_CSS + f"""
    <div class="pf-page">
    <form method="POST" enctype="multipart/form-data" id="profileForm">
        <div class="top-bar">
            <a href="/space" class="pf-back">{ICON_BACK}</a>
            <span class="top-bar-title">Edit Profile</span>
            <button type="submit" class="pe-save">Save</button>
        </div>

        <div class="pf-banner">{ICON_STAR}</div>

        <div class="pf-head pe-head">
            <div class="pf-avatar" id="avatarPreview" style="{avatar_style} cursor: pointer;" onclick="document.getElementById('fileInput').click();">
                {avatar_icon}
                <div class="camera-badge">📷</div>
            </div>
            <input type="file" id="fileInput" name="avatar_file" accept="image/*" style="display: none;" onchange="previewImage(event)">
            <div class="pe-change" onclick="document.getElementById('fileInput').click();">Change Photo</div>
        </div>

        <div class="pe-fields">
            <div class="pe-group">
                <label class="pe-label">Display Name</label>
                <input type="text" name="name" value="{profile['name']}" class="pe-input" required>
            </div>
            <div class="pe-group">
                <label class="pe-label">Username</label>
                <input type="text" name="handle" value="{profile['handle']}" class="pe-input" required>
            </div>
            <div class="pe-group">
                <label class="pe-label">Bio</label>
                <textarea name="bio" maxlength="150" placeholder="Tell us about yourself..." class="pe-input pe-ta" oninput="updateBio(this)">{profile['bio']}</textarea>
                <div class="pe-count" id="bioCount">{len(profile['bio'])}/150</div>
            </div>
        </div>

        <div class="pe-list">
            <div class="interactive-menu-item" onclick="openModal('websiteModal')">
                Website <span id="websiteDisplay">{website_val} ›</span>
            </div>
            <div class="interactive-menu-item" onclick="openModal('locationModal')">
                Location <span id="locationDisplay">{location_val} ›</span>
            </div>
            <div class="interactive-menu-item" onclick="openModal('birthdayModal')">
                Birthday <span id="birthdayDisplay">{birthday_val} ›</span>
            </div>
            <div class="interactive-menu-item" onclick="openModal('privacyModal')">
                Privacy Settings <span id="privacyDisplay">{privacy_val} ›</span>
            </div>
        </div>

        <input type="hidden" id="websiteInput" name="website" value="{profile['website']}">
        <input type="hidden" id="locationInput" name="location" value="{profile['location']}">
        <input type="hidden" id="birthdayInput" name="birthday" value="{profile['birthday']}">
        <input type="hidden" id="privacyInput" name="privacy" value="{profile['privacy']}">

        <div class="pe-list">
            <div class="interactive-menu-item" onclick="openModal('notificationsModal')">Notifications <span>›</span></div>
            <div class="interactive-menu-item" onclick="openModal('securityModal')">Account Security <span>›</span></div>
            <div class="interactive-menu-item" style="color: #ff5555;" onclick="openModal('deleteModal')">Delete Account <span>›</span></div>
            <a href="/logout" class="interactive-menu-item" style="color: #ff9966;">Log Out <span>⎋</span></a>
        </div>
    </form>

    <div id="websiteModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header"><span>Add Website</span><button type="button" class="modal-close" onclick="closeModal('websiteModal')">X</button></div>
            <input type="text" id="tempWebsite" placeholder="https://yourwebsite.com" class="edit-input" style="margin-bottom: 15px;" value="{profile['website']}">
            <button type="button" class="submit-btn" onclick="saveField('website')">Confirm</button>
        </div>
    </div>

    <div id="locationModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header"><span>Select Location</span><button type="button" class="modal-close" onclick="closeModal('locationModal')">X</button></div>
            <input type="text" id="tempLocation" placeholder="e.g. Casablanca, Morocco" class="edit-input" style="margin-bottom: 15px;" value="{profile['location']}">
            <button type="button" class="submit-btn" onclick="saveField('location')">Confirm</button>
        </div>
    </div>

    <div id="birthdayModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header"><span>Select Birthday</span><button type="button" class="modal-close" onclick="closeModal('birthdayModal')">X</button></div>
            <input type="date" id="tempBirthday" class="edit-input" style="margin-bottom: 15px;" value="{profile['birthday']}">
            <button type="button" class="submit-btn" onclick="saveField('birthday')">Confirm</button>
        </div>
    </div>

    <div id="privacyModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header"><span>Privacy Settings</span><button type="button" class="modal-close" onclick="closeModal('privacyModal')">X</button></div>
            <div class="modal-option" onclick="setPrivacy('Public')">🌐 Public (Everyone)</div>
            <div class="modal-option" onclick="setPrivacy('After-Hours Only')">🌙 After-Hours Only (Midnight mode)</div>
            <div class="modal-option" onclick="setPrivacy('Private')">🔒 Private (Sanctuary)</div>
        </div>
    </div>

    <div id="notificationsModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header"><span>Notifications</span><button type="button" class="modal-close" onclick="closeModal('notificationsModal')">X</button></div>
            <div style="color: #aaa; font-size: 0.9rem; margin-bottom: 15px; line-height: 1.5;">Manage your quiet hours and alerts when thoughts are appreciated.</div>
            <button type="button" class="submit-btn" onclick="closeModal('notificationsModal')">Done</button>
        </div>
    </div>

    <div id="securityModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header"><span>Account Security</span><button type="button" class="modal-close" onclick="closeModal('securityModal')">X</button></div>
            <div style="color: #aaa; font-size: 0.9rem; margin-bottom: 15px; line-height: 1.5;">Your account is securely linked via phone and WhatsApp verification.</div>
            <button type="button" class="submit-btn" onclick="closeModal('securityModal')">Close</button>
        </div>
    </div>

    <div id="deleteModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header"><span style="color: #ff5555;">Delete Account</span><button type="button" class="modal-close" onclick="closeModal('deleteModal')">X</button></div>
            <div style="color: #aaa; font-size: 0.9rem; margin-bottom: 20px; line-height: 1.5;">Leaving the sanctuary? This will erase all your midnight traces and entries permanently.</div>
            <a href="/logout" style="display: block; text-align: center; background: #ff5555; color: #fff; padding: 11px; font-weight: bold; border-radius: 6px; text-decoration: none;">Confirm Deletion</a>
        </div>
    </div>
    </div>

    <script>
    function previewImage(event) {{
        var file = event.target.files[0];
        if (!file) {{ return; }}
        var reader = new FileReader();
        reader.onload = function() {{
            var output = document.getElementById('avatarPreview');
            output.style.backgroundImage = 'url(' + reader.result + ')';
            output.innerHTML = '<div class="camera-badge">📷</div>';
        }};
        reader.readAsDataURL(file);
    }}

    function updateBio(t) {{
        document.getElementById('bioCount').innerText = t.value.length + '/150';
    }}

    function openModal(modalId) {{
        document.getElementById(modalId).style.display = 'flex';
    }}
    function closeModal(modalId) {{
        document.getElementById(modalId).style.display = 'none';
    }}

    function saveField(field) {{
        var val = document.getElementById('temp' + field.charAt(0).toUpperCase() + field.slice(1)).value;
        document.getElementById(field + 'Display').innerText = (val ? val : 'Add ' + field) + ' ›';
        document.getElementById(field + 'Input').value = val;
        closeModal(field + 'Modal');
    }}

    function setPrivacy(val) {{
        document.getElementById('privacyDisplay').innerText = val + ' ›';
        document.getElementById('privacyInput').value = val;
        closeModal('privacyModal');
    }}
    </script>
    """
    return base_layout("Edit Profile", content, error_msg=error_msg, active_page="space")

@app.route("/pdf-page/<int:entry_id>/<int:page>")
def pdf_page(entry_id, page):
    if 'identity' not in session:
        return redirect(url_for('login'))
    if fitz is None:
        return "PDF renderer is not installed", 503
    rows = fetch_items("WHERE c.id = ?", (entry_id,))
    if not rows:
        return "PDF not found", 404
    it = rows[0]
    if it["type"] != "article" or not str(it["url"]).lower().endswith(".pdf"):
        return "Not a PDF", 404
    try:
        rel = str(it["url"]).split("/local-media/", 1)[1]
        pdf_path = os.path.abspath(os.path.join(VIDEO_DIR, urllib.parse.unquote(rel)))
        base_dir = os.path.abspath(VIDEO_DIR)
        if os.path.commonpath([base_dir, pdf_path]) != base_dir or not os.path.isfile(pdf_path):
            return "PDF file not found", 404
        with fitz.open(pdf_path) as doc:
            if page < 1 or page > doc.page_count:
                return "Page not found", 404
            pix = doc.load_page(page - 1).get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            data = pix.tobytes("png")
        return send_file(__import__('io').BytesIO(data), mimetype="image/png", max_age=0)
    except Exception as exc:
        return f"Could not render PDF: {escape(str(exc))}", 500

@app.route("/entry/<int:entry_id>")
def view_entry(entry_id):
    if 'identity' not in session: return redirect(url_for('login'))
    rows = fetch_items("WHERE c.id = ?", (entry_id,))
    if not rows: return "Entry not found", 404
    it = rows[0]
    t = it["type"]

    media = ""
    if t == "image":
        media = f'<div class="en-media"><img src="{escape(it["url"])}" alt="{escape(it["title"])}"></div>'
    elif t == "article" and str(it["url"]).lower().endswith(".pdf"):
        media = f'<div class="en-media pdf-viewer"><iframe src="{escape(it["url"])}" title="{escape(it["title"])}"></iframe></div>'
    elif t == "reel":
        if it["url"]:
            media = f'<div class="en-media"><video src="{escape(it["url"])}" controls playsinline preload="metadata"></video></div>'
        media += f'<a class="ch" href="/reels/{it["id"]}"><i class="fa-solid fa-play"></i> Watch in reels</a><div style="height: 16px;"></div>'
    body_html = f'<div class="en-body">{escape(it["body"])}</div>' if it["body"] else ""

    if t == "reel":
        related = fetch_items("WHERE c.type = 'reel' AND c.topic = ? AND c.id != ?", (it["topic"], it["id"]), limit=5)
        related_title = "MORE REELS IN " + it["topic"].upper()
    else:
        related = fetch_items("WHERE c.type IN ('article', 'image') AND c.topic = ? AND c.id != ?", (it["topic"], it["id"]), limit=6)
        related_title = "SIMILAR IN " + it["topic"].upper()
    related_html = ""
    if related:
        related_html = f'<div class="fc-sec">{escape(related_title)}</div>' + "".join(feed_card(r) for r in related)

    conn = get_db()
    comments = conn.execute("SELECT author, text, created_at FROM comments WHERE content_id = ? ORDER BY id ASC", (entry_id,)).fetchall()
    conn.close()
    comments_html = "".join(
        f'<div class="cm"><b>{escape(c["author"])}</b>{escape(c["text"])}<small>{fmt_date(c["created_at"])}</small></div>'
        for c in comments
    )

    content = FEED_CSS + f"""
    <div class="top-bar"><a href="/">‹ Back</a><span class="top-bar-title">{TYPE_LABELS[t]}</span><span></span></div>
    <div class="fc-wrap">
        <div class="fc-meta"><strong>{escape(it['author'])}</strong><span>@{escape(it['handle'])}</span><span class="fc-badge">{escape(it['topic'])}</span></div>
        <h1 class="en-title">{escape(it['title'])}</h1>
        <div class="en-date">Published on {fmt_date(it['created_at'])}</div>
        {media}
        {body_html}
        <div class="fc-foot" style="border-top: none; padding-top: 0;">{action_bar(it)}</div>

        <div id="comments">
            <div class="fc-sec">COMMENTS ({len(comments)})</div>
            {comments_html}
            <form method="POST" action="/comment/{it['id']}" class="cm-form">
                <textarea name="text" maxlength="500" required placeholder="Write a comment..."></textarea>
                <button type="submit" class="cm-btn">Post</button>
            </form>
        </div>

        {related_html}
    </div>
    <div class="fc-toast" id="fcToast"></div>
    """ + FEED_JS
    return base_layout(it['title'], content, active_page="home")

PF_CSS = """
<style>
.pf-page{position:relative;min-height:calc(100vh - 52px);overflow:hidden;overflow:clip;background:radial-gradient(90% 40% at 100% 0%,#150f3a 0%,transparent 60%),#07070f;}
.pf-page .top-bar{background:rgba(7,7,15,.7);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid #14142a;}
.pf-back{display:flex;align-items:center;}
.pf-banner{position:relative;width:100%;height:150px;overflow:hidden;box-sizing:border-box;border:1px solid #1a1a30;border-radius:18px 18px 0 0;background:linear-gradient(135deg,#020408 0%,#05060f 55%,#0a0a18 100%);}
.pf-banner::before{content:'';position:absolute;right:-70px;top:-150px;width:460px;height:330px;border-radius:50%;background:radial-gradient(ellipse at 70% 25%,#2c1f80 0%,#140d40 50%,transparent 72%);border-bottom:2px solid rgba(124,108,255,.75);box-shadow:0 12px 40px rgba(99,82,255,.35);}
.pf-star{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:1;}
.pf-head{position:relative;padding:0 20px 18px 20px;border-bottom:1px solid #14142a;}
.pf-avatar{position:absolute;top:-56px;left:20px;width:112px;height:112px;border-radius:50%;border:2px solid #5b49d6;background:#23232e;background-size:cover;background-position:center;box-shadow:0 0 22px rgba(99,82,255,.35);display:flex;align-items:center;justify-content:center;z-index:2;}
.pf-actions{display:flex;justify-content:flex-end;margin-top:-22px;position:relative;z-index:2;}
.pf-edit{border:1px solid #5b49d6;border-radius:26px;padding:11px 24px;color:#fff;text-decoration:none;font-size:1rem;background:rgba(10,10,25,.92);box-shadow:0 0 14px rgba(99,82,255,.25);}
.pf-names{margin-top:40px;}
.pf-names h2{margin:0;font-size:1.7rem;font-weight:700;color:#fff;}
.pf-handle{color:#7d7b99;font-size:1.05rem;margin-top:4px;}
.pf-bio{color:#8d8ba8;font-size:1.05rem;margin-top:14px;line-height:1.5;}
.pf-stats{display:flex;gap:22px;margin-top:16px;color:#8d8ba8;font-size:1rem;}
.pf-stats strong{color:#fff;font-weight:700;}
.pf-tabs{display:flex;justify-content:space-around;border-bottom:1px solid #14142a;}
.pf-tabs a{padding:16px 4px 12px 4px;color:#7d7b99;text-decoration:none;font-size:1rem;border-bottom:3px solid transparent;}
.pf-tabs a.active{color:#fff;font-weight:700;border-bottom-color:#8b6cff;}
.pf-card{position:relative;margin:18px 14px;padding:22px 24px;border-radius:24px;border:1px solid #4b3fb5;background:linear-gradient(145deg,rgba(40,32,100,.35),rgba(12,11,30,.92));box-shadow:0 0 18px rgba(99,82,255,.15);}
.pf-author{font-size:.95rem;color:#7d7b99;margin-bottom:10px;}
.pf-author strong{color:#c9c6e6;margin-right:6px;}
.pf-title{display:block;font-size:1.5rem;font-weight:400;color:#fff;text-decoration:none;margin-bottom:10px;line-height:1.3;}
.pf-snippet{color:#8d86c0;font-size:1.05rem;line-height:1.55;margin-bottom:18px;}
.pf-foot{display:flex;justify-content:space-between;align-items:center;color:#7d7b99;font-size:.95rem;}
.pf-foot span{display:flex;align-items:center;gap:8px;}
.pf-empty{color:#666;text-align:center;padding:30px;}
</style>
"""

ICON_USER = '<svg width="58" height="58" viewBox="0 0 24 24" fill="#4d4d5c"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7z"/></svg>'
ICON_DOTS = '<svg width="26" height="26" viewBox="0 0 24 24" fill="#fff"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>'
ICON_STAR = '<svg class="pf-star" width="48" height="48" viewBox="0 0 24 24" fill="#f8fafc" style="filter:drop-shadow(0 0 10px #8b7cff);"><path d="M12 1l2.2 8.8L23 12l-8.8 2.2L12 23l-2.2-8.8L1 12l8.8-2.2z"/></svg>'
ICON_CAL = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#8d8ba8" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>'
ICON_SPARK = '<svg width="20" height="20" viewBox="0 0 24 24" fill="#7c6cff"><path d="M12 1l2.2 8.8L23 12l-8.8 2.2L12 23l-2.2-8.8L1 12l8.8-2.2z"/></svg>'

PF_EDIT_CSS = """
<style>
.pe-save{background:rgba(10,10,25,.92);border:1px solid #5b49d6;color:#fff;border-radius:22px;padding:8px 20px;font-size:.95rem;font-weight:600;cursor:pointer;box-shadow:0 0 14px rgba(99,82,255,.25);font-family:inherit;}
.pe-head{padding-top:70px;padding-bottom:6px;border-bottom:none;}
.pe-change{color:#8b6cff;font-size:.9rem;font-weight:600;cursor:pointer;display:inline-block;}
.pe-fields{padding:14px 20px 0 20px;}
.pe-group{margin-bottom:18px;position:relative;}
.pe-label{display:block;font-size:.85rem;color:#8d8ba8;margin-bottom:7px;}
.pe-input{width:100%;box-sizing:border-box;background:rgba(18,17,42,.85);border:1px solid #26244f;color:#fff;border-radius:16px;padding:15px 16px;font-size:1rem;font-family:inherit;transition:border-color .2s,box-shadow .2s;}
.pe-input::placeholder{color:#77759f;}
.pe-input:focus{outline:none;border-color:#7c6cff;box-shadow:0 0 0 3px rgba(124,108,255,.18);}
.pe-ta{height:120px;resize:none;line-height:1.5;}
.pe-count{text-align:right;font-size:.75rem;color:#7c7aa8;margin-top:5px;}
.pe-list{margin:8px 14px 18px 14px;border:1px solid #4b3fb5;border-radius:22px;background:linear-gradient(145deg,rgba(40,32,100,.3),rgba(12,11,30,.92));overflow:hidden;box-shadow:0 0 18px rgba(99,82,255,.12);}
.pe-list .interactive-menu-item{border-top:1px solid #1d1b45;padding:17px 20px;font-size:.98rem;}
.pe-list .interactive-menu-item:first-child{border-top:none;}
.pe-list .interactive-menu-item:hover{background:rgba(124,108,255,.1);}
.pe-list .interactive-menu-item span{color:#8d8ba8;}
.pf-page .modal-overlay{background:rgba(2,2,10,.78);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);}
.pf-page .modal-content{background:linear-gradient(145deg,#171540,#0d0c22);border:1px solid #3a3480;border-bottom:none;border-radius:24px 24px 0 0;box-shadow:0 0 40px rgba(99,82,255,.3);}
.pf-page .edit-input{background:rgba(18,17,42,.9);border:1px solid #26244f;border-radius:14px;}
.pf-page .edit-input:focus{border-color:#7c6cff;box-shadow:0 0 0 3px rgba(124,108,255,.18);background:rgba(18,17,42,.9);}
.pf-page .submit-btn{background:linear-gradient(90deg,#8ea2ff,#a45cff);color:#0d0b2a;border-radius:18px;box-shadow:0 0 20px rgba(140,110,255,.3);}
.pf-page .modal-option{background:rgba(18,17,42,.9);border-radius:14px;border-color:#26244f;}
.pf-page .modal-option:hover{background:rgba(124,108,255,.14);border-color:#7c6cff;}
</style>
"""

PF_MENU_CSS = """
<style>
.pf-menu-wrap{position:relative;display:flex;align-items:center;}
.pf-dots-btn{background:none;border:none;padding:6px;margin:-6px;cursor:pointer;display:flex;align-items:center;border-radius:50%;-webkit-tap-highlight-color:transparent;}
.pf-dots-btn:active{background:rgba(124,108,255,.18);}
.pf-menu{position:absolute;right:0;top:calc(100% + 12px);min-width:250px;background:#10102a;border:1px solid #2d2a66;border-radius:16px;padding:6px;box-shadow:0 14px 40px rgba(0,0,0,.65),0 0 22px rgba(99,82,255,.22);opacity:0;visibility:hidden;transform:translateY(-8px) scale(.97);transform-origin:top right;transition:opacity .18s ease,transform .18s ease,visibility .18s;z-index:60;}
.pf-menu.open{opacity:1;visibility:visible;transform:translateY(0) scale(1);}
.pf-menu-item{display:flex;align-items:center;gap:12px;width:100%;box-sizing:border-box;padding:13px 14px;background:none;border:none;color:#e8e6ff;font-size:.95rem;font-family:inherit;text-align:left;text-decoration:none;border-radius:11px;cursor:pointer;transition:background .15s;}
.pf-menu-item:hover,.pf-menu-item:active{background:rgba(124,108,255,.14);}
.pf-menu-item .ico{width:22px;text-align:center;font-size:1.05rem;}
.pf-menu-item .pf-pill{margin-left:auto;font-size:.7rem;font-weight:700;padding:3px 9px;border-radius:20px;background:#1d1b45;color:#8d8ba8;letter-spacing:.5px;}
.pf-menu-item .pf-pill.on{background:#5b49d6;color:#fff;}
.pf-menu-sep{height:1px;background:#222048;margin:5px 8px;}
.pf-menu-item.danger{color:#ff6b6b;}
.pf-menu-item.danger:hover,.pf-menu-item.danger:active{background:rgba(255,80,80,.12);}
.pf-badge{display:inline-block;margin-left:8px;font-size:.72rem;padding:2px 9px;border-radius:20px;background:#1d1b45;color:#b3a8ff;border:1px solid #3a3480;vertical-align:middle;}
.pf-modal{position:fixed;inset:0;background:rgba(2,2,10,.78);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);display:none;align-items:center;justify-content:center;z-index:200;padding:20px;box-sizing:border-box;}
.pf-modal.open{display:flex;}
.pf-modal-card{width:100%;max-width:420px;background:linear-gradient(145deg,#171540,#0d0c22);border:1px solid #3a3480;border-radius:22px;padding:22px;box-shadow:0 0 40px rgba(99,82,255,.3);}
.pf-modal-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;color:#fff;font-weight:700;font-size:1.15rem;}
.pf-modal-close{background:none;border:none;color:#8d8ba8;font-size:1.3rem;cursor:pointer;padding:4px 8px;}
.pf-stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.pf-stat{background:rgba(18,17,42,.9);border:1px solid #26244f;border-radius:14px;padding:14px;}
.pf-stat b{display:block;font-size:1.5rem;color:#fff;}
.pf-stat span{font-size:.8rem;color:#8d8ba8;}
.pf-modal-note{margin-top:14px;color:#7d7b99;font-size:.8rem;line-height:1.5;text-align:center;}
.pf-toast{position:fixed;left:50%;bottom:90px;transform:translateX(-50%) translateY(10px);background:#1a1844;color:#fff;border:1px solid #4b3fb5;padding:11px 18px;border-radius:24px;font-size:.88rem;opacity:0;pointer-events:none;transition:all .25s ease;z-index:300;max-width:90%;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.5);}
.pf-toast.show{opacity:1;transform:translateX(-50%) translateY(0);}
</style>
"""

PF_MENU_JS = """
<script>
(function () {
    var wrap = document.getElementById('pfMenuWrap');
    var btn = document.getElementById('pfDotsBtn');
    var menu = document.getElementById('pfMenu');
    var data = document.getElementById('pfMenuData').dataset;
    var modal = document.getElementById('pfStatsModal');
    var toast = document.getElementById('pfToast');
    var pill = document.getElementById('pfStealthPill');
    var badge = document.getElementById('pfStealthBadge');
    var toastTimer = null;

    function showToast(msg) {
        toast.textContent = msg;
        toast.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toast.classList.remove('show'); }, 2600);
    }
    function openMenu() { menu.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); }
    function closeMenu() { menu.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }
    function openModal() { modal.classList.add('open'); }
    function closeModal() { modal.classList.remove('open'); }

    btn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (menu.classList.contains('open')) { closeMenu(); } else { openMenu(); }
    });
    document.addEventListener('click', function (e) {
        if (!wrap.contains(e.target)) { closeMenu(); }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { closeMenu(); closeModal(); }
    });
    modal.addEventListener('click', function (e) {
        if (e.target === modal) { closeModal(); }
    });
    document.getElementById('pfModalClose').addEventListener('click', closeModal);

    function renderStealth(on) {
        pill.textContent = on ? 'ON' : 'OFF';
        pill.className = 'pf-pill' + (on ? ' on' : '');
        badge.style.display = on ? 'inline-block' : 'none';
    }

    document.getElementById('pfStealth').addEventListener('click', function () {
        closeMenu();
        fetch('/toggle_stealth', { method: 'POST', credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                renderStealth(!!d.stealth);
                showToast(d.stealth ? '\\ud83c\\udf19 Stealth mode is ON' : 'Stealth mode is OFF');
            })
            .catch(function () { showToast('Could not change stealth mode'); });
    });

    document.getElementById('pfStats').addEventListener('click', function () {
        closeMenu();
        openModal();
    });

    function fallbackCopy(text) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
        document.body.removeChild(ta);
        showToast(ok ? 'Profile link copied' : 'Copy this link: ' + text);
    }

    document.getElementById('pfShare').addEventListener('click', function () {
        closeMenu();
        var url = window.location.origin + '/space';
        var payload = { title: data.name + ' on AFTER3AM', text: 'Read my midnight thoughts on AFTER3AM', url: url };
        if (navigator.share) {
            navigator.share(payload).catch(function (err) {
                if (err && err.name === 'AbortError') { return; }
                fallbackCopy(url);
            });
        } else if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(url).then(function () {
                showToast('Profile link copied');
            }).catch(function () { fallbackCopy(url); });
        } else {
            fallbackCopy(url);
        }
    });
})();
</script>
"""

@app.route("/toggle_stealth", methods=["POST"])
def toggle_stealth():
    if 'identity' not in session:
        return jsonify(error="unauthorized"), 401
    session['stealth'] = not session.get('stealth', False)
    return jsonify(stealth=session['stealth'])

@app.route("/settings")
def settings():
    if 'identity' not in session: return redirect(url_for('login'))
    stealth_txt = "On" if session.get('stealth') else "Off"
    content = f"""
    <div class="top-bar"><a href="/space">‹ Back</a><span class="top-bar-title">Account Settings</span><span></span></div>
    <div class="interactive-menu-item" style="cursor: default;">Stealth Mode <span>{stealth_txt}</span></div>
    <a href="/logout" class="interactive-menu-item" style="color: #ff6b6b;">Log Out <span>⎋</span></a>
    """
    return base_layout("Settings", content, active_page="space")

@app.route("/space")
def space():
    if 'identity' not in session: return redirect(url_for('login'))
    profile = app.config['user_profile']
    user_entries = entries_for_handle(profile['handle'])
    
    avatar_style = f"background-image: url('{profile['avatar']}');" if profile['avatar'] else ""
    avatar_icon = "" if profile['avatar'] else ICON_USER
    stealth = bool(session.get('stealth', False))
    total_appr = sum(e.get('appreciations', 0) for e in user_entries)
    total_resp = sum(e.get('responses_count', 0) for e in user_entries)
    name_attr = profile['name'].replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')
    
    body = PF_CSS + PF_MENU_CSS + f"""
    <div class="pf-page">
        <div class="top-bar">
            <a href="/" class="pf-back">{ICON_BACK}</a>
            <span class="top-bar-title">{profile['name']}</span>
            <div class="pf-menu-wrap" id="pfMenuWrap">
                <button type="button" class="pf-dots-btn" id="pfDotsBtn" aria-label="More options" aria-haspopup="true" aria-expanded="false">{ICON_DOTS}</button>
                <div class="pf-menu" id="pfMenu" role="menu">
                    <button type="button" class="pf-menu-item" id="pfStealth" role="menuitem"><span class="ico">🌙</span>Stealth Mode<span class="pf-pill{' on' if stealth else ''}" id="pfStealthPill">{'ON' if stealth else 'OFF'}</span></button>
                    <button type="button" class="pf-menu-item" id="pfStats" role="menuitem"><span class="ico">📊</span>Night Stats</button>
                    <button type="button" class="pf-menu-item" id="pfShare" role="menuitem"><span class="ico">🔗</span>Share Profile</button>
                    <div class="pf-menu-sep"></div>
                    <a href="/settings" class="pf-menu-item" role="menuitem"><span class="ico">⚙️</span>Account Settings</a>
                    <a href="/logout" class="pf-menu-item danger" role="menuitem"><span class="ico">🚪</span>Log Out</a>
                </div>
            </div>
        </div>

        <div class="pf-banner">{ICON_STAR}</div>

        <div class="pf-head">
            <div class="pf-avatar" style="{avatar_style}">{avatar_icon}</div>
            <div class="pf-actions">
                <a href="/edit_profile" class="pf-edit">Edit Profile</a>
            </div>
            <div class="pf-names">
                <h2>{profile['name']}</h2>
                <div class="pf-handle">@{profile['handle']}<span class="pf-badge" id="pfStealthBadge" style="display: {'inline-block' if stealth else 'none'};">🌙 Stealth</span></div>
            </div>
            <div class="pf-bio">
                {profile['bio'] if profile['bio'] else 'No bio yet.'}
            </div>
            <div class="pf-stats">
                <div><strong>{len(user_entries)}</strong> Entries</div>
                <div><strong>590</strong> Readers</div>
                <div><strong>217</strong> Following</div>
            </div>
        </div>

        <div class="pf-tabs">
            <a href="#" class="active">Posts</a>
            <a href="#">Replies</a>
            <a href="#">Media</a>
            <a href="#">Likes</a>
        </div>
    """
    for entry in user_entries:
        img_preview = f'<div style="margin-bottom: 14px;"><img src="{entry["image"]}" style="width: 100%; max-height: 220px; object-fit: cover; border-radius: 14px;"></div>' if entry.get('image') else ''
        body += f"""
        <div class="pf-card">
            <div class="pf-author"><strong>{entry['author']}</strong> <span>@{entry['handle']}</span></div>
            <a href="/entry/{entry['id']}" class="pf-title">{entry['title']}</a>
            {img_preview}
            <div class="pf-snippet">{entry['content'][:90]}...</div>
            <div class="pf-foot">
                <span>{ICON_CAL}{entry['date']}</span>
                <span>{ICON_SPARK}{entry['appreciations']} Appreciations</span>
            </div>
        </div>
        """
    if not user_entries:
        body += '<p class="pf-empty">No entries published yet.</p>'
    body += '</div>'
    body += f"""
    <div id="pfMenuData" data-name="{name_attr}" style="display: none;"></div>
    <div class="pf-modal" id="pfStatsModal">
        <div class="pf-modal-card">
            <div class="pf-modal-head"><span>🌙 Night Stats</span><button type="button" class="pf-modal-close" id="pfModalClose">✕</button></div>
            <div class="pf-stat-grid">
                <div class="pf-stat"><b>{len(user_entries)}</b><span>Entries</span></div>
                <div class="pf-stat"><b>{total_appr}</b><span>Appreciations</span></div>
                <div class="pf-stat"><b>{total_resp}</b><span>Responses</span></div>
                <div class="pf-stat"><b>590</b><span>Readers</span></div>
            </div>
            <div class="pf-modal-note">A summary of your midnight activity on AFTER3AM.</div>
        </div>
    </div>
    <div class="pf-toast" id="pfToast"></div>
    """ + PF_MENU_JS
    return base_layout("My Space", body, active_page="space")

@app.route("/letters")
def letters():
    if 'identity' not in session: return redirect(url_for('login'))
    content = '<div class="top-bar"><span class="top-bar-title">Letters</span></div><div style="padding: 20px; text-align: center; color: #666; margin-top: 40px;">No active letters yet.</div>'
    return base_layout("Letters", content, active_page="home")

@app.route("/activity")
def activity():
    if 'identity' not in session: return redirect(url_for('login'))
    content = '<div class="top-bar"><span class="top-bar-title">Activity</span></div><div style="padding: 20px;"><div style="font-size: 0.9rem; color: #aaa; padding: 12px 0; border-bottom: 1px solid #1a1a1a;">✨ Someone appreciated your thoughts.</div></div>'
    return base_layout("Activity", content, active_page="activity")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("captcha_answer", "").strip() != str(session.get('captcha_result', '')):
            n1, n2 = random.randint(1, 9), random.randint(1, 9)
            session['captcha_result'] = n1 + n2
            return login_page(n1, n2, "Incorrect security answer.")
        code = request.form.get("code")
        phone = request.form.get("phone").strip()
        full_phone = f"{code}{phone}"
        gen_code = str(random.randint(1000, 9999))
        session['gen_code'] = gen_code
        session['pending_identity'] = full_phone
        session['action_link'] = f"https://wa.me/{full_phone}?text={urllib.parse.quote(f'Your verification code: {gen_code}')}"
        return redirect(url_for('verify'))
    n1, n2 = random.randint(1, 9), random.randint(1, 9)
    session['captcha_result'] = n1 + n2
    return login_page(n1, n2, None)

def login_page(n1, n2, error):
    err = f'<div style="color:#e57373; font-size:0.8rem; margin-bottom:12px;">{error}</div>' if error else ''
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sign In — AFTER3AM</title>
        <style>
            @keyframes pulseGlow {{
                0% {{ transform: scale(0.95); opacity: 0.7; filter: drop-shadow(0 0 10px rgba(96,165,250,0.3)); }}
                50% {{ transform: scale(1.05); opacity: 1; filter: drop-shadow(0 0 25px rgba(96,165,250,0.8)); }}
                100% {{ transform: scale(0.95); opacity: 0.7; filter: drop-shadow(0 0 10px rgba(96,165,250,0.3)); }}
            }}
            .logo-anim {{
                width: 48px;
                height: 48px;
                background: #6a8caf;
                clip-path: polygon(50% 0%, 63% 37%, 100% 50%, 63% 63%, 50% 100%, 37% 63%, 0% 50%, 37% 37%);
                margin: 0 auto 15px auto;
                animation: pulseGlow 3s infinite ease-in-out;
            }}
        </style>
    </head>
    <body style="background:#0d0d0d; color:#fff; display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; margin:0;">
        <div style="background:#141414; padding:30px; border:1px solid #222; border-radius:12px; width:320px; text-align:center;">
            <div class="logo-anim"></div>
            <h2 style="color:#fff; margin-bottom:5px; font-size: 1.2rem;">AFTER3AM</h2>
            <p style="color:#777; font-size:0.8rem; margin-bottom:20px;">Sign in with your phone</p>
            {err}
            <form method="POST">
                <div style="display:flex; gap:8px; margin-bottom:12px;">
                    <select name="code" style="width:40%; background:#1a1a1a; color:#fff; border:1px solid #333; padding:10px; border-radius:6px;">
                        <option value="+212">🇲🇦 +212</option>
                        <option value="+1">🇺🇸 +1</option>
                        <option value="+33">🇫🇷 +33</option>
                    </select>
                    <input type="tel" name="phone" placeholder="Number" required style="width:60%; background:#1a1a1a; color:#fff; border:1px solid #333; padding:10px; border-radius:6px; box-sizing:border-box;">
                </div>
                <div style="background:#1a1a1a; border:1px solid #262626; padding:10px; border-radius:6px; margin-bottom:15px; text-align:left;">
                    <label style="display:block; font-size:0.75rem; color:#888; margin-bottom:4px;">Security Check: <strong>{n1} + {n2}</strong></label>
                    <input type="text" name="captcha_answer" placeholder="Answer" required style="width:100%; background:#121212; color:#fff; border:1px solid #333; padding:8px; border-radius:4px; box-sizing:border-box; text-align:center;">
                </div>
                <button type="submit" style="background:#6a8caf; color:#0d0d0d; border:none; padding:11px; font-weight:bold; border-radius:6px; cursor:pointer; width:100%;">Continue</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.route("/verify", methods=["GET", "POST"])
def verify():
    if request.method == "POST":
        expected = session.get('gen_code')
        pending = session.get('pending_identity')
        if expected and pending and request.form.get("entered_code", "").strip() == expected:
            session['identity'] = pending
            session['user_id'] = pending
            session.pop('gen_code', None)
            session.pop('pending_identity', None)
            return redirect(url_for('home'))
        return "<body style='background:#0d0d0d; color:#ff5555; text-align:center; padding-top:20vh;'><h2>Invalid Code</h2><a href='/verify' style='color:#8ab4f8;'>Try Again</a></body>"
    link = session.get('action_link', '#')
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Verify</title></head>
    <body style="background:#0d0d0d; color:#fff; display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; margin:0;">
        <div style="background:#141414; padding:30px; border:1px solid #222; border-radius:12px; width:320px; text-align:center; color:#fff;">
            <h2>Verify Code</h2>
            <p style="color:#777; font-size:0.85rem; margin-bottom:20px;">Open WhatsApp to get your code.</p>
            <a href="{link}" target="_blank" style="display:block; width:100%; padding:11px; background:#25D366; color:#fff; text-decoration:none; font-weight:600; border-radius:6px; box-sizing:border-box; margin-bottom:15px;">Open WhatsApp</a>
            <form method="POST">
                <input type="text" name="entered_code" placeholder="4-digit code" maxlength="4" required style="width:100%; padding:11px; background:#1a1a1a; color:#fff; border:1px solid #333; text-align:center; border-radius:6px; margin-bottom:15px; box-sizing:border-box; font-size:1.1rem; letter-spacing:2px;">
                <button type="submit" style="background:#6a8caf; color:#0d0d0d; border:none; padding:11px; font-weight:bold; border-radius:6px; cursor:pointer; width:100%;">Verify</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == "__main__":
    PORT = 5001
    url = f"http://127.0.0.1:{PORT}/"
    def _open_after3am():
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Timer(1.5, _open_after3am).start()
    print("AFTER3AM is running at " + url)
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
