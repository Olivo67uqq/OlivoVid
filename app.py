from flask import Flask, request, send_from_directory, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os
import sqlite3

load_dotenv()

app = Flask(__name__)
app.secret_key = "olivovid_secret_123"
AVATAR_FOLDER = 'avatars'
os.makedirs(AVATAR_FOLDER, exist_ok=True)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

LIMIT_FILMOW_MIESIECZNIE = 5

def get_db():
    conn = sqlite3.connect('baza.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS uzytkownicy
                 (id INTEGER PRIMARY KEY, nazwa TEXT UNIQUE, haslo TEXT,
                  bio TEXT DEFAULT '', avatar TEXT DEFAULT '', is_admin INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS filmy
                 (id INTEGER PRIMARY KEY, cloudinary_id TEXT, url TEXT, tytul TEXT,
                  autor TEXT, data TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS lajki
                 (id INTEGER PRIMARY KEY, film_id INTEGER, uzytkownik TEXT,
                  UNIQUE(film_id, uzytkownik))''')
    c.execute('''CREATE TABLE IF NOT EXISTS komentarze
                 (id INTEGER PRIMARY KEY, film_id INTEGER, uzytkownik TEXT,
                  tresc TEXT, odpowiedz_na INTEGER DEFAULT NULL,
                  data TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS lajki_komentarzy
                 (id INTEGER PRIMARY KEY, komentarz_id INTEGER, uzytkownik TEXT,
                  UNIQUE(komentarz_id, uzytkownik))''')
    c.execute('''CREATE TABLE IF NOT EXISTS ustawienia
                 (klucz TEXT PRIMARY KEY, wartosc TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS obserwowania
                 (id INTEGER PRIMARY KEY, obserwujacy TEXT, obserwowany TEXT,
                  UNIQUE(obserwujacy, obserwowany))''')
    c.execute('''CREATE TABLE IF NOT EXISTS powiadomienia
                 (id INTEGER PRIMARY KEY, dla TEXT, od TEXT, typ TEXT,
                  film_id INTEGER, przeczytane INTEGER DEFAULT 0,
                  data TEXT DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    for col in [("bio", "TEXT DEFAULT ''"), ("avatar", "TEXT DEFAULT ''"), ("is_admin", "INTEGER DEFAULT 0")]:
        try:
            conn.execute(f"ALTER TABLE uzytkownicy ADD COLUMN {col[0]} {col[1]}")
            conn.commit()
        except: pass
    conn.execute("INSERT OR IGNORE INTO ustawienia VALUES ('wgrywanie_aktywne', '1')")
    conn.commit()
    conn.close()

init_db()

def is_admin():
    if 'uzytkownik' not in session:
        return False
    conn = get_db()
    user = conn.execute("SELECT is_admin FROM uzytkownicy WHERE nazwa=?", (session['uzytkownik'],)).fetchone()
    conn.close()
    return user and user['is_admin'] == 1

def filmy_w_tym_miesiacu(uzytkownik):
    from datetime import datetime
    conn = get_db()
    miesiac = datetime.now().strftime('%Y-%m')
    count = conn.execute(
        "SELECT COUNT(*) as c FROM filmy WHERE autor=? AND data LIKE ?",
        (uzytkownik, f"{miesiac}%")).fetchone()['c']
    conn.close()
    return count

def wgrywanie_aktywne():
    conn = get_db()
    val = conn.execute("SELECT wartosc FROM ustawienia WHERE klucz='wgrywanie_aktywne'").fetchone()
    conn.close()
    return val and val['wartosc'] == '1'

def ile_powiadomien(uzytkownik):
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) as c FROM powiadomienia WHERE dla=? AND przeczytane=0",
                     (uzytkownik,)).fetchone()['c']
    conn.close()
    return n

def avatar_html(nazwa, size="sm"):
    path = os.path.join(AVATAR_FOLDER, f"{nazwa}.jpg")
    if os.path.exists(path):
        return f'<img src="/avatar/{nazwa}" class="avatar-{size}" alt="{nazwa}">'
    return f'<div class="avatar-{size}-placeholder">{nazwa[0].upper()}</div>'

def nav_html(uzytkownik):
    admin_link = '<a href="/admin" class="nav-link">⚙️</a>' if is_admin() else ''
    n = ile_powiadomien(uzytkownik)
    notif_badge = f'<span class="notif-badge">{n}</span>' if n > 0 else ''
    return f'''
    <div class="nav">
        <a href="/" style="text-decoration:none;" class="logo">Olivo<span>Vid</span></a>
        <div class="nav-right">
            {admin_link}
            <a href="/powiadomienia" class="nav-link" style="position:relative;">
                <svg width="22" height="22" viewBox="0 0 24 24"><path fill="white" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>
                {notif_badge}
            </a>
            <a href="/upload_page" class="nav-link">
                <svg width="22" height="22" viewBox="0 0 24 24"><path fill="white" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
            </a>
            <a href="/profil/{uzytkownik}" class="nav-link">{avatar_html(uzytkownik, "sm")} {uzytkownik}</a>
            <a href="/wyloguj" class="nav-link" style="font-size:13px;">Wyloguj</a>
        </div>
    </div>'''

STYLE = '''
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: white; overflow: hidden; }
    .logo { font-size: 24px; font-weight: 900; color: white; letter-spacing: -1px; }
    .logo span { color: #fe2c55; }
    .nav { padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; position: fixed; top: 0; left: 0; right: 0; z-index: 100; background: linear-gradient(to bottom, rgba(0,0,0,0.7), transparent); }
    .nav-right { display: flex; align-items: center; gap: 14px; }
    .nav-link { color: white; text-decoration: none; font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 4px; }
    .notif-badge { position: absolute; top: -6px; right: -6px; background: #fe2c55; color: white; font-size: 10px; font-weight: 700; width: 16px; height: 16px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
    .avatar-sm { width: 28px; height: 28px; border-radius: 50%; object-fit: cover; border: 2px solid #fe2c55; }
    .avatar-sm-placeholder { width: 28px; height: 28px; border-radius: 50%; background: #333; border: 2px solid #fe2c55; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #fe2c55; flex-shrink: 0; }

    .feed { height: 100vh; overflow-y: scroll; scroll-snap-type: y mandatory; scrollbar-width: none; }
    .feed::-webkit-scrollbar { display: none; }
    .video-slide { height: 100vh; scroll-snap-align: start; position: relative; display: flex; align-items: center; justify-content: center; background: #000; }
    .video-slide video { height: 100vh; width: 100%; object-fit: contain; cursor: pointer; }

    .video-overlay { position: absolute; bottom: 80px; left: 16px; right: 80px; pointer-events: none; }
    .video-overlay-author { font-size: 15px; font-weight: 700; color: white; text-shadow: 0 1px 3px rgba(0,0,0,0.8); }
    .video-overlay-title { font-size: 14px; color: rgba(255,255,255,0.85); margin-top: 4px; text-shadow: 0 1px 3px rgba(0,0,0,0.8); }

    .video-side-actions { position: absolute; right: 12px; bottom: 80px; display: flex; flex-direction: column; align-items: center; gap: 20px; }
    .side-btn { display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: pointer; background: none; border: none; color: white; }
    .side-count { font-size: 12px; color: white; text-shadow: 0 1px 3px rgba(0,0,0,0.8); font-weight: 600; }

    /* SVG icons */
    .icon-heart { width: 38px; height: 38px; filter: drop-shadow(0 1px 3px rgba(0,0,0,0.8)); transition: transform 0.15s; }
    .icon-comment { width: 38px; height: 38px; filter: drop-shadow(0 1px 3px rgba(0,0,0,0.8)); }
    .icon-share { width: 34px; height: 34px; filter: drop-shadow(0 1px 3px rgba(0,0,0,0.8)); }
    .side-btn:active .icon-heart { transform: scale(1.3); }

    /* Pause indicator */
    .pause-indicator { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); opacity: 0; transition: opacity 0.2s; pointer-events: none; }
    .pause-indicator svg { width: 60px; height: 60px; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.8)); }
    .pause-indicator.show { opacity: 1; }

    .overlay-avatar { pointer-events: all; }
    .avatar-overlay-sm { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; border: 2px solid white; }
    .avatar-overlay-sm-placeholder { width: 40px; height: 40px; border-radius: 50%; background: #333; border: 2px solid white; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; color: white; }

    .comments-panel { display: none; position: fixed; bottom: 0; left: 0; right: 0; height: 60vh; background: #111; border-radius: 20px 20px 0 0; z-index: 200; overflow-y: auto; padding: 20px; }
    .comments-panel.open { display: block; }
    .comments-handle { width: 40px; height: 4px; background: #444; border-radius: 2px; margin: 0 auto 16px; }
    .comments-title { font-size: 16px; font-weight: 700; text-align: center; margin-bottom: 16px; }
    .comment { background: #1a1a1a; border-radius: 10px; padding: 10px 14px; margin: 8px 0; }
    .comment.reply { margin-left: 20px; background: #161616; border-left: 2px solid #333; }
    .comment-author { font-size: 13px; font-weight: 700; color: #fe2c55; text-decoration: none; }
    .comment-text { font-size: 14px; color: #ddd; margin: 4px 0; }
    .comment-actions { display: flex; align-items: center; gap: 12px; margin-top: 6px; }
    .comment-like-btn { display: flex; align-items: center; gap: 4px; background: none; border: none; color: #666; font-size: 12px; cursor: pointer; }
    .comment-like-btn.liked { color: #fe2c55; }
    .reply-toggle { background: none; border: none; color: #666; font-size: 12px; cursor: pointer; }
    .comment-form { display: flex; gap: 8px; margin-top: 14px; position: sticky; bottom: 0; background: #111; padding-top: 10px; }
    .comment-form input { flex: 1; background: #222; border: 1px solid #333; color: white; padding: 10px 14px; border-radius: 8px; font-size: 14px; outline: none; }
    .comment-form input:focus { border-color: #fe2c55; }
    .comment-form button { background: #fe2c55; color: white; border: none; padding: 10px 16px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 700; }
    .reply-form { display: none; margin-top: 8px; }
    .reply-form.active { display: flex; gap: 8px; }
    .reply-form input { flex: 1; background: #222; border: 1px solid #333; color: white; padding: 8px 12px; border-radius: 8px; font-size: 13px; outline: none; }
    .reply-form button { background: #333; color: white; border: none; padding: 8px 12px; border-radius: 8px; cursor: pointer; }
    .overlay-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 199; }
    .overlay-backdrop.open { display: block; }

    /* Share panel */
    .share-panel { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #111; border-radius: 20px 20px 0 0; z-index: 200; padding: 20px; }
    .share-panel.open { display: block; }
    .share-title { font-size: 16px; font-weight: 700; text-align: center; margin-bottom: 16px; }
    .share-link { background: #222; border-radius: 10px; padding: 12px 16px; font-size: 13px; color: #aaa; word-break: break-all; margin-bottom: 12px; }
    .share-copy-btn { width: 100%; background: #fe2c55; color: white; border: none; padding: 12px; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; }

    .upload-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
    .upload-box { background: #111; border: 2px dashed #333; border-radius: 16px; padding: 24px; max-width: 500px; margin: 24px auto; text-align: center; }
    .upload-box input[type=text] { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 12px 16px; border-radius: 10px; font-size: 15px; margin-bottom: 10px; outline: none; }
    .file-input { display: none; }
    .file-label { display: inline-block; background: #222; color: #aaa; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-bottom: 8px; border: 1px solid #333; }
    .upload-btn { background: #fe2c55; color: white; border: none; padding: 12px 28px; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; margin-top: 8px; }
    .upload-btn:disabled { background: #555; cursor: not-allowed; }
    .limit-info { color: #888; font-size: 13px; margin-top: 8px; }
    .limit-warn { color: #fe2c55; font-size: 13px; }

    .profile-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
    .profile-header { max-width: 600px; margin: 20px auto; padding: 0 16px; }
    .profile-top { display: flex; align-items: center; gap: 24px; margin-bottom: 20px; }
    .avatar-lg { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 3px solid #fe2c55; }
    .avatar-lg-placeholder { width: 80px; height: 80px; border-radius: 50%; background: #222; border: 3px solid #fe2c55; display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 700; color: #fe2c55; flex-shrink: 0; }
    .profile-name { font-size: 22px; font-weight: 700; }
    .profile-bio { color: #aaa; font-size: 14px; margin-top: 6px; }
    .profile-stats { display: flex; gap: 24px; margin-top: 12px; }
    .stat { text-align: center; }
    .stat-num { font-size: 18px; font-weight: 700; }
    .stat-label { font-size: 12px; color: #aaa; }
    .edit-btn { background: #222; color: white; border: 1px solid #333; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 12px; margin-right: 8px; }
    .follow-btn { background: #fe2c55; color: white; border: none; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 12px; font-weight: 700; }
    .follow-btn.following { background: #333; color: white; border: 1px solid #555; }
    .profile-videos { max-width: 600px; margin: 0 auto; padding: 0 16px 40px; }
    .profile-video-card { background: #111; border-radius: 12px; margin: 12px 0; overflow: hidden; }
    .profile-video-card video { width: 100%; display: block; }
    .profile-video-info { padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; }
    .delete-btn { background: #333; color: #fe2c55; border: 1px solid #fe2c55; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }

    /* Notifications */
    .notif-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
    .notif-list { max-width: 600px; margin: 20px auto; padding: 0 16px 40px; }
    .notif-item { background: #111; border-radius: 12px; padding: 14px 16px; margin: 10px 0; display: flex; align-items: center; gap: 12px; }
    .notif-item.unread { border-left: 3px solid #fe2c55; }
    .notif-text { font-size: 14px; color: #ddd; }
    .notif-text b { color: #fe2c55; }
    .notif-time { font-size: 12px; color: #555; margin-top: 4px; }

    .center { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; overflow-y: auto; }
    .card { background: #111; border: 1px solid #222; border-radius: 16px; padding: 40px; width: 100%; max-width: 380px; }
    .card input { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 14px 16px; border-radius: 10px; font-size: 15px; margin: 6px 0; outline: none; }
    .card input:focus { border-color: #fe2c55; }
    .btn { width: 100%; background: #fe2c55; color: white; border: none; padding: 14px; border-radius: 10px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 12px; }
    .divider { border: none; border-top: 1px solid #222; margin: 20px 0; }
    .link { color: #fe2c55; text-decoration: none; font-weight: 600; }
    .error { color: #fe2c55; font-size: 14px; margin: 8px 0; text-align: center; }
    h2 { color: white; font-size: 22px; font-weight: 700; margin: 12px 0 20px; text-align: center; }
    p.sub { color: #888; font-size: 14px; margin-top: 20px; text-align: center; }
    .edit-form { max-width: 500px; margin: 30px auto; padding: 30px; background: #111; border-radius: 16px; }
    .edit-form input[type=text], .edit-form textarea { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 12px 16px; border-radius: 10px; font-size: 15px; margin: 6px 0 14px; outline: none; }
    .edit-form textarea { height: 100px; resize: none; }
    .edit-form label { color: #aaa; font-size: 13px; }
    .save-btn { background: #fe2c55; color: white; border: none; padding: 12px 28px; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; }
    .admin-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
    .admin-panel { max-width: 600px; margin: 20px auto; padding: 0 16px 40px; }
    .admin-card { background: #111; border: 1px solid #222; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
    .admin-card h3 { font-size: 16px; margin-bottom: 12px; color: #aaa; }
    .toggle-btn { padding: 10px 20px; border-radius: 8px; border: none; cursor: pointer; font-size: 14px; font-weight: 700; }
    .toggle-on { background: #fe2c55; color: white; }
    .toggle-off { background: #333; color: #aaa; }
    .film-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #222; }
    .film-row:last-child { border-bottom: none; }
    .empty { text-align: center; padding: 60px 20px; color: #444; font-size: 18px; }

    /* Toast */
    .toast { position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); background: #333; color: white; padding: 10px 20px; border-radius: 20px; font-size: 14px; z-index: 999; opacity: 0; transition: opacity 0.3s; pointer-events: none; }
    .toast.show { opacity: 1; }
</style>
'''

def heart_svg(liked):
    fill = "#fe2c55" if liked else "white"
    return f'''<svg class="icon-heart" viewBox="0 0 24 24">
        <path fill="{fill}" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
    </svg>'''

def comment_svg():
    return '''<svg class="icon-comment" viewBox="0 0 24 24">
        <path fill="white" d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>'''

def share_svg():
    return '''<svg class="icon-share" viewBox="0 0 24 24">
        <path fill="white" d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/>
    </svg>'''

@app.route("/")
def strona_glowna():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    filmy = conn.execute("SELECT * FROM filmy ORDER BY data DESC").fetchall()
    uzytkownik = session['uzytkownik']
    filmy_html = ""
    for film in filmy:
        lajki = conn.execute("SELECT COUNT(*) as c FROM lajki WHERE film_id=?", (film['id'],)).fetchone()['c']
        czy_lajk = conn.execute("SELECT 1 FROM lajki WHERE film_id=? AND uzytkownik=?",
                                (film['id'], uzytkownik)).fetchone()
        ile_kom = conn.execute("SELECT COUNT(*) as c FROM komentarze WHERE film_id=?", (film['id'],)).fetchone()['c']
        komentarze = conn.execute(
            "SELECT * FROM komentarze WHERE film_id=? AND odpowiedz_na IS NULL ORDER BY data ASC",
            (film['id'],)).fetchall()
        komentarze_html = ""
        for kom in komentarze:
            lk = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (kom['id'],)).fetchone()['c']
            czy_lk = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?",
                                  (kom['id'], uzytkownik)).fetchone()
            odpowiedzi = conn.execute("SELECT * FROM komentarze WHERE odpowiedz_na=? ORDER BY data ASC", (kom['id'],)).fetchall()
            odp_html = ""
            for odp in odpowiedzi:
                lok = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (odp['id'],)).fetchone()['c']
                czy_lok = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?",
                                       (odp['id'], uzytkownik)).fetchone()
                odp_html += f'''
                <div class="comment reply">
                    <a href="/profil/{odp['uzytkownik']}" class="comment-author">@{odp['uzytkownik']}</a>
                    <p class="comment-text">{odp['tresc']}</p>
                    <div class="comment-actions">
                        <button class="comment-like-btn {'liked' if czy_lok else ''}" onclick="lajkujKomentarz({odp['id']}, this)">
                            <svg width="14" height="14" viewBox="0 0 24 24"><path fill="{'#fe2c55' if czy_lok else '#666'}" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
                            {lok}
                        </button>
                    </div>
                </div>'''
            komentarze_html += f'''
            <div class="comment" id="kom-{kom['id']}">
                <a href="/profil/{kom['uzytkownik']}" class="comment-author">@{kom['uzytkownik']}</a>
                <p class="comment-text">{kom['tresc']}</p>
                <div class="comment-actions">
                    <button class="comment-like-btn {'liked' if czy_lk else ''}" onclick="lajkujKomentarz({kom['id']}, this)">
                        <svg width="14" height="14" viewBox="0 0 24 24"><path fill="{'#fe2c55' if czy_lk else '#666'}" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
                        {lk}
                    </button>
                    <button class="reply-toggle" onclick="pokazOdpowiedz({kom['id']})">Odpowiedz</button>
                </div>
                <div class="reply-form" id="reply-{kom['id']}">
                    <input type="text" placeholder="Odpowiedź..." id="reply-input-{kom['id']}">
                    <button onclick="wyslijOdpowiedz({film['id']}, {kom['id']})">Wyślij</button>
                </div>
                {odp_html}
            </div>'''

        autor_avatar = avatar_html(film['autor'], 'overlay-sm')
        film_url = f"https://olivovid.onrender.com/film/{film['id']}"
        filmy_html += f'''
        <div class="video-slide" id="slide-{film['id']}">
            <video loop playsinline preload="metadata" id="video-{film['id']}">
                <source src="{film['url']}">
            </video>
            <div class="pause-indicator" id="pause-{film['id']}">
                <svg viewBox="0 0 24 24"><path fill="white" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
            </div>
            <div class="video-overlay">
                <a href="/profil/{film['autor']}" class="overlay-avatar">{autor_avatar}</a>
                <p class="video-overlay-author">@{film['autor']}</p>
                <p class="video-overlay-title">{film['tytul']}</p>
            </div>
            <div class="video-side-actions">
                <button class="side-btn" id="like-{film['id']}" onclick="lajkuj({film['id']}, this)">
                    {heart_svg(bool(czy_lajk))}
                    <span class="side-count" id="like-count-{film['id']}">{lajki}</span>
                </button>
                <button class="side-btn" onclick="toggleKomentarze({film['id']})">
                    {comment_svg()}
                    <span class="side-count">{ile_kom}</span>
                </button>
                <button class="side-btn" onclick="pokazUdostepnij({film['id']}, '{film_url}')">
                    {share_svg()}
                </button>
            </div>
            <div class="overlay-backdrop" id="backdrop-{film['id']}" onclick="zamknijWszystko({film['id']})"></div>
            <div class="comments-panel" id="panel-{film['id']}">
                <div class="comments-handle"></div>
                <p class="comments-title">Komentarze</p>
                <div id="komentarze-{film['id']}">{komentarze_html}</div>
                <div class="comment-form">
                    <input type="text" placeholder="Dodaj komentarz..." id="kom-input-{film['id']}">
                    <button onclick="wyslijKomentarz({film['id']})">Wyślij</button>
                </div>
            </div>
            <div class="share-panel" id="share-{film['id']}">
                <div class="comments-handle"></div>
                <p class="share-title">Udostępnij</p>
                <p class="share-link" id="share-link-{film['id']}">{film_url}</p>
                <button class="share-copy-btn" onclick="kopiujLink({film['id']})">📋 Kopiuj link</button>
            </div>
        </div>'''
    conn.close()
    if not filmy_html:
        filmy_html = '<div class="video-slide"><p class="empty">Brak filmów 🎬<br>Wgraj pierwszy!</p></div>'
    return f'''<!DOCTYPE html>
    <html>
    <head><title>OlivoVid</title>{STYLE}</head>
    <body>
        {nav_html(uzytkownik)}
        <div class="feed" id="feed">{filmy_html}</div>
        <div class="toast" id="toast"></div>
        <script>
        function pokazToast(msg) {{
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2000);
        }}

        // Auto-play + spacja
        const slides = document.querySelectorAll('.video-slide');
        const observer = new IntersectionObserver((entries) => {{
            entries.forEach(e => {{
                const video = e.target.querySelector('video');
                if (!video) return;
                if (e.isIntersecting) video.play();
                else {{ video.pause(); video.currentTime = 0; }}
            }});
        }}, {{ threshold: 0.7 }});
        slides.forEach(s => observer.observe(s));

        // Klik na wideo = pauza
        slides.forEach(slide => {{
            const video = slide.querySelector('video');
            const id = slide.id.replace('slide-', '');
            const indicator = document.getElementById('pause-' + id);
            if (video) {{
                video.addEventListener('click', function(e) {{
                    if (e.target.closest('.video-side-actions') || e.target.closest('.video-overlay')) return;
                    if (video.paused) {{ video.play(); indicator.classList.remove('show'); }}
                    else {{ video.pause(); indicator.classList.add('show'); setTimeout(() => indicator.classList.remove('show'), 800); }}
                }});
            }}
        }});

        // Spacja = pauza
        document.addEventListener('keydown', function(e) {{
            if (e.code === 'Space' && e.target.tagName !== 'INPUT') {{
                e.preventDefault();
                const feed = document.getElementById('feed');
                const visible = Array.from(slides).find(s => {{
                    const r = s.getBoundingClientRect();
                    return r.top >= -50 && r.top <= 50;
                }});
                if (visible) {{
                    const video = visible.querySelector('video');
                    const id = visible.id.replace('slide-', '');
                    const indicator = document.getElementById('pause-' + id);
                    if (video.paused) {{ video.play(); indicator.classList.remove('show'); }}
                    else {{ video.pause(); indicator.classList.add('show'); setTimeout(() => indicator.classList.remove('show'), 800); }}
                }}
            }}
        }});

        // Double tap to like
        slides.forEach(slide => {{
            let lastTap = 0;
            slide.addEventListener('touchend', function(e) {{
                if (e.target.closest('.video-side-actions') || e.target.closest('.comments-panel') || e.target.closest('.share-panel')) return;
                const now = Date.now();
                if (now - lastTap < 300) {{
                    const id = slide.id.replace('slide-', '');
                    const btn = document.getElementById('like-' + id);
                    if (btn) lajkuj(parseInt(id), btn);
                }}
                lastTap = now;
            }});
        }});

        function lajkuj(filmId, btn) {{
            fetch('/lajkuj/' + filmId, {{method: 'POST'}})
            .then(r => r.json())
            .then(d => {{
                document.getElementById('like-count-' + filmId).textContent = d.lajki;
                btn.querySelector('path').setAttribute('fill', d.lajkuje ? '#fe2c55' : 'white');
            }});
        }}
        function toggleKomentarze(filmId) {{
            document.getElementById('panel-' + filmId).classList.toggle('open');
            document.getElementById('backdrop-' + filmId).classList.toggle('open');
        }}
        function pokazUdostepnij(filmId, url) {{
            document.getElementById('share-' + filmId).classList.add('open');
            document.getElementById('backdrop-' + filmId).classList.add('open');
        }}
        function zamknijWszystko(filmId) {{
            document.getElementById('panel-' + filmId).classList.remove('open');
            document.getElementById('share-' + filmId).classList.remove('open');
            document.getElementById('backdrop-' + filmId).classList.remove('open');
        }}
        function kopiujLink(filmId) {{
            const link = document.getElementById('share-link-' + filmId).textContent;
            navigator.clipboard.writeText(link).then(() => pokazToast('✅ Link skopiowany!'));
            document.getElementById('share-' + filmId).classList.remove('open');
            document.getElementById('backdrop-' + filmId).classList.remove('open');
        }}
        function lajkujKomentarz(komId, btn) {{
            fetch('/lajkuj_komentarz/' + komId, {{method: 'POST'}})
            .then(r => r.json())
            .then(d => {{
                btn.querySelector('path').setAttribute('fill', d.lajkuje ? '#fe2c55' : '#666');
                btn.childNodes[2].textContent = ' ' + d.lajki;
                btn.classList.toggle('liked', d.lajkuje);
            }});
        }}
        function wyslijKomentarz(filmId) {{
            const input = document.getElementById('kom-input-' + filmId);
            if (!input.value.trim()) return;
            fetch('/komentarz/' + filmId, {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{tresc: input.value}})
            }})
            .then(r => r.json())
            .then(d => {{
                document.getElementById('komentarze-' + filmId).insertAdjacentHTML('beforeend', `
                    <div class="comment" id="kom-${{d.id}}">
                        <a href="/profil/${{d.uzytkownik}}" class="comment-author">@${{d.uzytkownik}}</a>
                        <p class="comment-text">${{d.tresc}}</p>
                        <div class="comment-actions">
                            <button class="comment-like-btn" onclick="lajkujKomentarz(${{d.id}}, this)">
                                <svg width="14" height="14" viewBox="0 0 24 24"><path fill="#666" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
                                0
                            </button>
                            <button class="reply-toggle" onclick="pokazOdpowiedz(${{d.id}})">Odpowiedz</button>
                        </div>
                        <div class="reply-form" id="reply-${{d.id}}">
                            <input type="text" placeholder="Odpowiedź..." id="reply-input-${{d.id}}">
                            <button onclick="wyslijOdpowiedz(${{filmId}}, ${{d.id}})">Wyślij</button>
                        </div>
                    </div>`);
                input.value = '';
            }});
        }}
        function pokazOdpowiedz(komId) {{
            document.getElementById('reply-' + komId).classList.toggle('active');
        }}
        function wyslijOdpowiedz(filmId, komId) {{
            const input = document.getElementById('reply-input-' + komId);
            if (!input.value.trim()) return;
            fetch('/komentarz/' + filmId, {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{tresc: input.value, odpowiedz_na: komId}})
            }})
            .then(r => r.json())
            .then(d => {{
                document.getElementById('kom-' + komId).insertAdjacentHTML('beforeend', `
                    <div class="comment reply">
                        <a href="/profil/${{d.uzytkownik}}" class="comment-author">@${{d.uzytkownik}}</a>
                        <p class="comment-text">${{d.tresc}}</p>
                        <div class="comment-actions">
                            <button class="comment-like-btn" onclick="lajkujKomentarz(${{d.id}}, this)">
                                <svg width="14" height="14" viewBox="0 0 24 24"><path fill="#666" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
                                0
                            </button>
                        </div>
                    </div>`);
                input.value = '';
                document.getElementById('reply-' + komId).classList.remove('active');
            }});
        }}
        </script>
    </body>
    </html>'''

@app.route("/film/<int:film_id>")
def film_bezposredni(film_id):
    return redirect(url_for('strona_glowna'))

@app.route("/obserwuj/<nazwa>", methods=["POST"])
def obserwuj(nazwa):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    if nazwa == session['uzytkownik']:
        return jsonify({}), 400
    conn = get_db()
    czy = conn.execute("SELECT 1 FROM obserwowania WHERE obserwujacy=? AND obserwowany=?",
                       (session['uzytkownik'], nazwa)).fetchone()
    if czy:
        conn.execute("DELETE FROM obserwowania WHERE obserwujacy=? AND obserwowany=?",
                     (session['uzytkownik'], nazwa))
        obserwuje = False
    else:
        conn.execute("INSERT INTO obserwowania (obserwujacy, obserwowany) VALUES (?, ?)",
                     (session['uzytkownik'], nazwa))
        conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?, ?, 'obserwowanie', 0)",
                     (nazwa, session['uzytkownik']))
        obserwuje = True
    conn.commit()
    obserwujacych = conn.execute("SELECT COUNT(*) as c FROM obserwowania WHERE obserwowany=?", (nazwa,)).fetchone()['c']
    conn.close()
    return jsonify({'obserwuje': obserwuje, 'obserwujacych': obserwujacych})

@app.route("/powiadomienia")
def powiadomienia():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    notifs = conn.execute("SELECT * FROM powiadomienia WHERE dla=? ORDER BY data DESC LIMIT 50",
                          (session['uzytkownik'],)).fetchall()
    conn.execute("UPDATE powiadomienia SET przeczytane=1 WHERE dla=?", (session['uzytkownik'],))
    conn.commit()
    conn.close()
    notifs_html = ""
    for n in notifs:
        if n['typ'] == 'lajk':
            tekst = f'<b>@{n["od"]}</b> polubił Twoje wideo'
        elif n['typ'] == 'komentarz':
            tekst = f'<b>@{n["od"]}</b> skomentował Twoje wideo'
        elif n['typ'] == 'obserwowanie':
            tekst = f'<b>@{n["od"]}</b> zaczął Cię obserwować'
        else:
            tekst = f'<b>@{n["od"]}</b> zareagował'
        notifs_html += f'''
        <div class="notif-item {'unread' if not n['przeczytane'] else ''}">
            {avatar_html(n['od'], 'sm')}
            <div>
                <p class="notif-text">{tekst}</p>
                <p class="notif-time">{n['data'][:16]}</p>
            </div>
        </div>'''
    return f'''<!DOCTYPE html>
    <html>
    <head><title>Powiadomienia - OlivoVid</title>{STYLE}</head>
    <body>
        {nav_html(session['uzytkownik'])}
        <div class="notif-page">
            <div class="notif-list">
                <h2>🔔 Powiadomienia</h2>
                {notifs_html if notifs_html else '<p style="color:#666;text-align:center;padding:40px;">Brak powiadomień</p>'}
            </div>
        </div>
    </body>
    </html>'''

@app.route("/upload_page")
def upload_page():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    aktywne = wgrywanie_aktywne()
    filmy_w_miesiacu = filmy_w_tym_miesiacu(session['uzytkownik'])
    if not aktywne:
        upload_html = '<p class="limit-warn">⛔ Wgrywanie filmów jest tymczasowo wyłączone.</p>'
    elif filmy_w_miesiacu >= LIMIT_FILMOW_MIESIECZNIE:
        upload_html = f'<p class="limit-warn">⛔ Osiągnąłeś limit {LIMIT_FILMOW_MIESIECZNIE} filmów w tym miesiącu.</p>'
    else:
        pozostalo = LIMIT_FILMOW_MIESIECZNIE - filmy_w_miesiacu
        upload_html = f'''
        <form method="POST" action="/upload" enctype="multipart/form-data" id="uploadForm">
            <input type="text" name="tytul" placeholder="Tytuł wideo" required>
            <label for="fileInput" class="file-label">📁 Wybierz wideo</label>
            <input type="file" name="wideo" accept="video/*" class="file-input" id="fileInput"
                   onchange="document.getElementById('fileName').textContent = this.files[0].name">
            <p style="color:#666; font-size:13px; margin:4px 0;" id="fileName">Nie wybrano pliku</p>
            <button type="submit" class="upload-btn" id="uploadBtn">⬆️ Wgraj wideo</button>
            <p class="limit-info">Pozostało: <b>{pozostalo}</b> / {LIMIT_FILMOW_MIESIECZNIE} w tym miesiącu</p>
        </form>'''
    return f'''<!DOCTYPE html>
    <html>
    <head><title>Wgraj - OlivoVid</title>{STYLE}</head>
    <body>
        {nav_html(session['uzytkownik'])}
        <div class="upload-page">
            <div class="upload-box">
                <h2>Wgraj wideo</h2>
                {upload_html}
            </div>
        </div>
        <script>
        document.getElementById('uploadForm') && document.getElementById('uploadForm').addEventListener('submit', function() {{
            const btn = document.getElementById('uploadBtn');
            if(btn) {{ btn.disabled = true; btn.textContent = '⏳ Wgrywanie...'; }}
        }});
        </script>
    </body>
    </html>'''

@app.route("/upload", methods=["POST"])
def upload():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    if not wgrywanie_aktywne():
        return redirect(url_for('strona_glowna'))
    if filmy_w_tym_miesiacu(session['uzytkownik']) >= LIMIT_FILMOW_MIESIECZNIE:
        return redirect(url_for('strona_glowna'))
    plik = request.files["wideo"]
    tytul = request.form["tytul"]
    plik.seek(0, 2)
    rozmiar = plik.tell()
    plik.seek(0)
    if rozmiar > 50 * 1024 * 1024:
        return "<h1 style='color:white;text-align:center;padding:40px;'>Plik za duży! Max 50MB.</h1>"
    wynik = cloudinary.uploader.upload(plik, resource_type="video", folder="olivovid")
    conn = get_db()
    conn.execute("INSERT INTO filmy (cloudinary_id, url, tytul, autor) VALUES (?, ?, ?, ?)",
                 (wynik['public_id'], wynik['secure_url'], tytul, session['uzytkownik']))
    conn.commit()
    conn.close()
    return redirect(url_for('strona_glowna'))

@app.route("/profil/<nazwa>")
def profil(nazwa):
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    user = conn.execute("SELECT * FROM uzytkownicy WHERE nazwa=?", (nazwa,)).fetchone()
    if not user:
        return f'''<!DOCTYPE html><html><head>{STYLE}</head><body>
            {nav_html(session['uzytkownik'])}
            <p style="color:white;text-align:center;padding:40px;">Użytkownik nie istnieje</p>
        </body></html>'''
    filmy = conn.execute("SELECT * FROM filmy WHERE autor=? ORDER BY data DESC", (nazwa,)).fetchall()
    ile_lajkow = conn.execute(
        "SELECT COUNT(*) as c FROM lajki WHERE film_id IN (SELECT id FROM filmy WHERE autor=?)",
        (nazwa,)).fetchone()['c']
    obserwujacych = conn.execute("SELECT COUNT(*) as c FROM obserwowania WHERE obserwowany=?", (nazwa,)).fetchone()['c']
    obserwuje = conn.execute("SELECT 1 FROM obserwowania WHERE obserwujacy=? AND obserwowany=?",
                             (session['uzytkownik'], nazwa)).fetchone()
    conn.close()
    jest_swoj = session['uzytkownik'] == nazwa
    filmy_html = ""
    for film in filmy:
        usun_btn = f'<button class="delete-btn" onclick="usunSwojFilm({film["id"]})">🗑️</button>' if jest_swoj else ''
        filmy_html += f'''
        <div class="profile-video-card" id="film-{film['id']}">
            <video controls><source src="{film['url']}"></video>
            <div class="profile-video-info">
                <p style="font-size:14px;">{film['tytul']}</p>
                {usun_btn}
            </div>
        </div>'''
    if jest_swoj:
        follow_btn = f'<a href="/edytuj_profil"><button class="edit-btn">✏️ Edytuj</button></a>'
    else:
        follow_btn = f'<button class="follow-btn {"following" if obserwuje else ""}" id="follow-btn" onclick="toggleObserwuj(\'{nazwa}\')">' \
                     f'{"Obserwujesz" if obserwuje else "Obserwuj"}</button>'
    return f'''<!DOCTYPE html>
    <html>
    <head><title>@{nazwa} - OlivoVid</title>{STYLE}</head>
    <body>
        {nav_html(session['uzytkownik'])}
        <div class="profile-page">
            <div class="profile-header">
                <div class="profile-top">
                    {avatar_html(nazwa, 'lg')}
                    <div>
                        <p class="profile-name">@{nazwa}</p>
                        <p class="profile-bio">{user['bio'] or 'Brak opisu'}</p>
                        <div class="profile-stats">
                            <div class="stat"><p class="stat-num">{len(filmy)}</p><p class="stat-label">filmów</p></div>
                            <div class="stat"><p class="stat-num">{ile_lajkow}</p><p class="stat-label">lajków</p></div>
                            <div class="stat"><p class="stat-num" id="obserwujacych-count">{obserwujacych}</p><p class="stat-label">obserwujących</p></div>
                        </div>
                        {follow_btn}
                    </div>
                </div>
            </div>
            <div class="profile-videos">
                <h3 style="color:#aaa; font-size:16px; padding:0 0 10px; border-bottom:1px solid #222; margin-bottom:16px;">Filmy @{nazwa}</h3>
                {filmy_html if filmy_html else '<p style="color:#666;text-align:center;padding:20px;">Brak filmów</p>'}
            </div>
        </div>
        <script>
        function toggleObserwuj(nazwa) {{
            fetch('/obserwuj/' + nazwa, {{method: 'POST'}})
            .then(r => r.json())
            .then(d => {{
                const btn = document.getElementById('follow-btn');
                btn.textContent = d.obserwuje ? 'Obserwujesz' : 'Obserwuj';
                btn.className = 'follow-btn ' + (d.obserwuje ? 'following' : '');
                document.getElementById('obserwujacych-count').textContent = d.obserwujacych;
            }});
        }}
        function usunSwojFilm(filmId) {{
            if (!confirm('Usunąć ten film?')) return;
            fetch('/usun_film/' + filmId, {{method: 'POST'}})
            .then(r => r.json())
            .then(d => {{ if(d.ok) document.getElementById('film-' + filmId).remove(); }});
        }}
        </script>
    </body>
    </html>'''

@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for('strona_glowna'))
    conn = get_db()
    filmy = conn.execute("SELECT * FROM filmy ORDER BY data DESC").fetchall()
    aktywne = wgrywanie_aktywne()
    conn.close()
    filmy_html = ""
    for film in filmy:
        filmy_html += f'''
        <div class="film-row">
            <div>
                <p style="font-weight:700;">{film['tytul']}</p>
                <p style="color:#888; font-size:13px;">@{film['autor']} • {film['data'][:10]}</p>
            </div>
            <button class="delete-btn" onclick="usunFilm({film['id']})">🗑️ Usuń</button>
        </div>'''
    return f'''<!DOCTYPE html>
    <html>
    <head><title>Admin - OlivoVid</title>{STYLE}</head>
    <body>
        {nav_html(session['uzytkownik'])}
        <div class="admin-page">
            <div class="admin-panel">
                <h2>⚙️ Panel Admina</h2>
                <div class="admin-card">
                    <h3>Wgrywanie filmów</h3>
                    <button class="toggle-btn {'toggle-on' if aktywne else 'toggle-off'}"
                            onclick="toggleWgrywanie()" id="toggleBtn">
                        {'✅ Włączone' if aktywne else '⛔ Wyłączone'}
                    </button>
                </div>
                <div class="admin-card">
                    <h3>Wszystkie filmy ({len(filmy)})</h3>
                    {filmy_html if filmy_html else '<p style="color:#666;">Brak filmów</p>'}
                </div>
            </div>
        </div>
        <script>
        function toggleWgrywanie() {{
            fetch('/admin/toggle_wgrywanie', {{method: 'POST'}})
            .then(r => r.json())
            .then(d => {{
                const btn = document.getElementById('toggleBtn');
                btn.textContent = d.aktywne ? '✅ Włączone' : '⛔ Wyłączone';
                btn.className = 'toggle-btn ' + (d.aktywne ? 'toggle-on' : 'toggle-off');
            }});
        }}
        function usunFilm(filmId) {{
            if (!confirm('Usunąć ten film?')) return;
            fetch('/admin/usun_film/' + filmId, {{method: 'POST'}})
            .then(r => r.json())
            .then(d => {{ if(d.ok) location.reload(); }});
        }}
        </script>
    </body>
    </html>'''

@app.route("/admin/toggle_wgrywanie", methods=["POST"])
def toggle_wgrywanie():
    if not is_admin():
        return jsonify({}), 403
    conn = get_db()
    aktywne = wgrywanie_aktywne()
    conn.execute("UPDATE ustawienia SET wartosc=? WHERE klucz='wgrywanie_aktywne'",
                 ('0' if aktywne else '1',))
    conn.commit()
    conn.close()
    return jsonify({'aktywne': not aktywne})

@app.route("/admin/usun_film/<int:film_id>", methods=["POST"])
def usun_film(film_id):
    if not is_admin():
        return jsonify({}), 403
    conn = get_db()
    film = conn.execute("SELECT cloudinary_id FROM filmy WHERE id=?", (film_id,)).fetchone()
    if film and film['cloudinary_id']:
        try:
            cloudinary.uploader.destroy(film['cloudinary_id'], resource_type="video")
        except: pass
    conn.execute("DELETE FROM filmy WHERE id=?", (film_id,))
    conn.execute("DELETE FROM lajki WHERE film_id=?", (film_id,))
    conn.execute("DELETE FROM komentarze WHERE film_id=?", (film_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route("/usun_film/<int:film_id>", methods=["POST"])
def usun_film_uzytkownik(film_id):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    conn = get_db()
    film = conn.execute("SELECT * FROM filmy WHERE id=? AND autor=?",
                        (film_id, session['uzytkownik'])).fetchone()
    if not film:
        conn.close()
        return jsonify({}), 403
    if film['cloudinary_id']:
        try:
            cloudinary.uploader.destroy(film['cloudinary_id'], resource_type="video")
        except: pass
    conn.execute("DELETE FROM filmy WHERE id=?", (film_id,))
    conn.execute("DELETE FROM lajki WHERE film_id=?", (film_id,))
    conn.execute("DELETE FROM komentarze WHERE film_id=?", (film_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route("/lajkuj/<int:film_id>", methods=["POST"])
def lajkuj(film_id):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    conn = get_db()
    czy = conn.execute("SELECT 1 FROM lajki WHERE film_id=? AND uzytkownik=?",
                       (film_id, session['uzytkownik'])).fetchone()
    if czy:
        conn.execute("DELETE FROM lajki WHERE film_id=? AND uzytkownik=?", (film_id, session['uzytkownik']))
        lajkuje = False
    else:
        conn.execute("INSERT INTO lajki (film_id, uzytkownik) VALUES (?, ?)", (film_id, session['uzytkownik']))
        lajkuje = True
        film = conn.execute("SELECT autor FROM filmy WHERE id=?", (film_id,)).fetchone()
        if film and film['autor'] != session['uzytkownik']:
            conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?, ?, 'lajk', ?)",
                         (film['autor'], session['uzytkownik'], film_id))
    conn.commit()
    lajki = conn.execute("SELECT COUNT(*) as c FROM lajki WHERE film_id=?", (film_id,)).fetchone()['c']
    conn.close()
    return jsonify({'lajki': lajki, 'lajkuje': lajkuje})

@app.route("/lajkuj_komentarz/<int:kom_id>", methods=["POST"])
def lajkuj_komentarz(kom_id):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    conn = get_db()
    czy = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?",
                       (kom_id, session['uzytkownik'])).fetchone()
    if czy:
        conn.execute("DELETE FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?", (kom_id, session['uzytkownik']))
        lajkuje = False
    else:
        conn.execute("INSERT INTO lajki_komentarzy (komentarz_id, uzytkownik) VALUES (?, ?)", (kom_id, session['uzytkownik']))
        lajkuje = True
    conn.commit()
    lajki = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (kom_id,)).fetchone()['c']
    conn.close()
    return jsonify({'lajki': lajki, 'lajkuje': lajkuje})

@app.route("/komentarz/<int:film_id>", methods=["POST"])
def komentarz(film_id):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    data = request.get_json()
    tresc = data.get('tresc', '').strip()
    odpowiedz_na = data.get('odpowiedz_na', None)
    if not tresc:
        return jsonify({}), 400
    conn = get_db()
    cur = conn.execute("INSERT INTO komentarze (film_id, uzytkownik, tresc, odpowiedz_na) VALUES (?, ?, ?, ?)",
                       (film_id, session['uzytkownik'], tresc, odpowiedz_na))
    conn.commit()
    kom_id = cur.lastrowid
    film = conn.execute("SELECT autor FROM filmy WHERE id=?", (film_id,)).fetchone()
    if film and film['autor'] != session['uzytkownik']:
        conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?, ?, 'komentarz', ?)",
                     (film['autor'], session['uzytkownik'], film_id))
        conn.commit()
    conn.close()
    return jsonify({'id': kom_id, 'uzytkownik': session['uzytkownik'], 'tresc': tresc})

@app.route("/edytuj_profil", methods=["GET", "POST"])
def edytuj_profil():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    if request.method == "POST":
        bio = request.form.get("bio", "")[:150]
        if 'avatar' in request.files and request.files['avatar'].filename:
            plik = request.files['avatar']
            img = Image.open(plik)
            img = img.convert('RGB')
            img.thumbnail((200, 200))
            img.save(os.path.join(AVATAR_FOLDER, f"{session['uzytkownik']}.jpg"), "JPEG")
        conn.execute("UPDATE uzytkownicy SET bio=? WHERE nazwa=?", (bio, session['uzytkownik']))
        conn.commit()
        conn.close()
        return redirect(url_for('profil', nazwa=session['uzytkownik']))
    user = conn.execute("SELECT * FROM uzytkownicy WHERE nazwa=?", (session['uzytkownik'],)).fetchone()
    conn.close()
    return f'''<!DOCTYPE html>
    <html>
    <head><title>Edytuj profil - OlivoVid</title>{STYLE}</head>
    <body>
        {nav_html(session['uzytkownik'])}
        <div class="upload-page">
            <div style="max-width:500px; margin:20px auto; padding:0 16px;">
                <div class="edit-form">
                    <h2>Edytuj profil</h2>
                    <form method="POST" enctype="multipart/form-data">
                        <label>Zdjęcie profilowe</label><br><br>
                        {avatar_html(session['uzytkownik'], 'lg')}
                        <br><br>
                        <input type="file" name="avatar" accept="image/*" style="color:white; margin-bottom:14px;">
                        <label>Bio (max 150 znaków)</label>
                        <textarea name="bio" placeholder="Napisz coś o sobie...">{user['bio'] or ''}</textarea>
                        <button type="submit" class="save-btn">💾 Zapisz</button>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>'''

@app.route("/avatar/<nazwa>")
def avatar(nazwa):
    return send_from_directory(AVATAR_FOLDER, f"{nazwa}.jpg")

@app.route("/setup_admin/<klucz>/<nazwa>")
def setup_admin(klucz, nazwa):
    if klucz != "olivovid_tajny_klucz_2026":
        return "Błędny klucz", 403
    conn = get_db()
    conn.execute("UPDATE uzytkownicy SET is_admin=1 WHERE nazwa=?", (nazwa,))
    conn.commit()
    conn.close()
    return f"Konto {nazwa} jest teraz adminem!"

@app.route("/logowanie", methods=["GET", "POST"])
def logowanie():
    error = ""
    if request.method == "POST":
        nazwa = request.form["nazwa"]
        haslo = request.form["haslo"]
        conn = get_db()
        wynik = conn.execute("SELECT haslo FROM uzytkownicy WHERE nazwa=?", (nazwa,)).fetchone()
        conn.close()
        if wynik and check_password_hash(wynik['haslo'], haslo):
            session['uzytkownik'] = nazwa
            return redirect(url_for('strona_glowna'))
        error = "Błędny login lub hasło!"
    return f'''<!DOCTYPE html>
    <html>
    <head><title>OlivoVid - Logowanie</title>{STYLE}</head>
    <body>
        <div class="center">
            <div class="card">
                <div style="text-align:center; margin-bottom:8px;" class="logo">Olivo<span>Vid</span></div>
                <h2>Zaloguj się</h2>
                <form method="POST">
                    <input type="text" name="nazwa" placeholder="Nazwa użytkownika" required>
                    <input type="password" name="haslo" placeholder="Hasło" required>
                    {"<p class='error'>"+error+"</p>" if error else ""}
                    <button type="submit" class="btn">Zaloguj się</button>
                </form>
                <hr class="divider">
                <p class="sub">Nie masz konta? <a href="/rejestracja" class="link">Zarejestruj się</a></p>
            </div>
        </div>
    </body>
    </html>'''

@app.route("/rejestracja", methods=["GET", "POST"])
def rejestracja():
    error = ""
    if request.method == "POST":
        nazwa = request.form["nazwa"]
        haslo_raw = request.form["haslo"]
        if not nazwa or not haslo_raw:
            error = "Wypełnij wszystkie pola!"
        else:
            haslo = generate_password_hash(haslo_raw)
            conn = get_db()
            try:
                conn.execute("INSERT INTO uzytkownicy (nazwa, haslo) VALUES (?, ?)", (nazwa, haslo))
                conn.commit()
                conn.close()
                session['uzytkownik'] = nazwa
                return redirect(url_for('strona_glowna'))
            except:
                conn.close()
                error = "Ta nazwa użytkownika jest zajęta!"
    return f'''<!DOCTYPE html>
    <html>
    <head><title>OlivoVid - Rejestracja</title>{STYLE}</head>
    <body>
        <div class="center">
            <div class="card">
                <div style="text-align:center; margin-bottom:8px;" class="logo">Olivo<span>Vid</span></div>
                <h2>Utwórz konto</h2>
                <form method="POST">
                    <input type="text" name="nazwa" placeholder="Nazwa użytkownika" required>
                    <input type="password" name="haslo" placeholder="Hasło" required>
                    {"<p class='error'>"+error+"</p>" if error else ""}
                    <button type="submit" class="btn">Zarejestruj się</button>
                </form>
                <hr class="divider">
                <p class="sub">Masz już konto? <a href="/logowanie" class="link">Zaloguj się</a></p>
            </div>
        </div>
    </body>
    </html>'''

@app.route("/wyloguj")
def wyloguj():
    session.pop('uzytkownik', None)
    return redirect(url_for('logowanie'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)