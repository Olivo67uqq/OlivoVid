from flask import Flask, request, send_from_directory, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os
import sqlite3
import random
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.secret_key = "olivovid_secret_123"
AVATAR_FOLDER = 'avatars'
CHAT_FOLDER = 'chat_imgs'
RELACJE_FOLDER = 'relacje_imgs'
os.makedirs(AVATAR_FOLDER, exist_ok=True)
os.makedirs(CHAT_FOLDER, exist_ok=True)
os.makedirs(RELACJE_FOLDER, exist_ok=True)

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
    c.execute('''CREATE TABLE IF NOT EXISTS reposty
                 (id INTEGER PRIMARY KEY, film_id INTEGER, uzytkownik TEXT,
                  data TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(film_id, uzytkownik))''')
    c.execute('''CREATE TABLE IF NOT EXISTS wiadomosci
                 (id INTEGER PRIMARY KEY, od TEXT, do TEXT, tresc TEXT,
                  typ TEXT DEFAULT 'tekst', reakcja TEXT DEFAULT NULL,
                  przeczytana INTEGER DEFAULT 0,
                  data TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS prosby_chat
                 (id INTEGER PRIMARY KEY, od TEXT, do TEXT, wiadomosc TEXT,
                  status TEXT DEFAULT 'oczekuje',
                  data TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(od, do))''')
    c.execute('''CREATE TABLE IF NOT EXISTS relacje
                 (id INTEGER PRIMARY KEY, autor TEXT, plik TEXT,
                  opis TEXT DEFAULT '',
                  widocznosc TEXT DEFAULT 'wszyscy',
                  wygasa TEXT,
                  data TEXT DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    for col in [("bio","TEXT DEFAULT ''"),("avatar","TEXT DEFAULT ''"),("is_admin","INTEGER DEFAULT 0")]:
        try:
            conn.execute("ALTER TABLE uzytkownicy ADD COLUMN " + col[0] + " " + col[1])
            conn.commit()
        except: pass
    conn.execute("INSERT OR IGNORE INTO ustawienia VALUES ('wgrywanie_aktywne','1')")
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
    conn = get_db()
    miesiac = datetime.now().strftime('%Y-%m')
    count = conn.execute("SELECT COUNT(*) as c FROM filmy WHERE autor=? AND data LIKE ?",
                         (uzytkownik, miesiac + '%')).fetchone()['c']
    conn.close()
    return count

def wgrywanie_aktywne():
    conn = get_db()
    val = conn.execute("SELECT wartosc FROM ustawienia WHERE klucz='wgrywanie_aktywne'").fetchone()
    conn.close()
    return val and val['wartosc'] == '1'

def ile_powiadomien(uzytkownik):
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) as c FROM powiadomienia WHERE dla=? AND przeczytane=0", (uzytkownik,)).fetchone()['c']
    conn.close()
    return n

def ile_wiadomosci(uzytkownik):
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) as c FROM wiadomosci WHERE do=? AND przeczytana=0", (uzytkownik,)).fetchone()['c']
    p = conn.execute("SELECT COUNT(*) as c FROM prosby_chat WHERE do=? AND status='oczekuje'", (uzytkownik,)).fetchone()['c']
    conn.close()
    return n + p

def czy_moze_pisac(uzytkownik, do, conn):
    obs1 = conn.execute("SELECT 1 FROM obserwowania WHERE obserwujacy=? AND obserwowany=?", (uzytkownik, do)).fetchone()
    obs2 = conn.execute("SELECT 1 FROM obserwowania WHERE obserwujacy=? AND obserwowany=?", (do, uzytkownik)).fetchone()
    wzajemne = obs1 and obs2
    zaakceptowany = conn.execute(
        "SELECT 1 FROM prosby_chat WHERE ((od=? AND do=?) OR (od=? AND do=?)) AND status='zaakceptowana'",
        (uzytkownik, do, do, uzytkownik)).fetchone()
    return wzajemne or zaakceptowany

def avatar_html(nazwa, size="sm"):
    path = os.path.join(AVATAR_FOLDER, nazwa + ".jpg")
    if os.path.exists(path):
        return '<img src="/avatar/' + nazwa + '" class="avatar-' + size + '" alt="' + nazwa + '">'
    return '<div class="avatar-' + size + '-placeholder">' + nazwa[0].upper() + '</div>'

def bottom_nav_html(aktywna, uzytkownik):
    m = ile_wiadomosci(uzytkownik)
    msg_badge = '<span class="bn-badge">' + str(m) + '</span>' if m > 0 else ''
    ikony = [
        ('/', 'home', aktywna == 'home', '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>', ''),
        ('/filmy', 'filmy', aktywna == 'filmy', '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M4 6.47L5.76 10H20v8H4V6.47M22 4h-4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4z"/></svg>', ''),
        ('/dodaj', 'dodaj', aktywna == 'dodaj', '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>', 'plus'),
        ('/wiadomosci', 'wiad', aktywna == 'wiad', '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>', msg_badge),
        ('/profil/' + uzytkownik, 'profil', aktywna == 'profil', '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/></svg>', ''),
    ]
    html = '<div class="bottom-nav">'
    for href, key, active, icon, badge in ikony:
        plus_cls = ' bn-plus' if key == 'dodaj' else ''
        active_cls = ' active' if active else ''
        html += ('<a href="' + href + '" class="bn-item' + active_cls + plus_cls + '">'
                 + icon + badge + '</a>')
    html += '</div>'
    return html

def top_nav_html(uzytkownik):
    n = ile_powiadomien(uzytkownik)
    notif_badge = '<span class="notif-badge">' + str(n) + '</span>' if n > 0 else ''
    admin_link = '<a href="/admin" class="nav-icon-btn"><svg viewBox="0 0 24 24"><path fill="white" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg></a>' if is_admin() else ''
    return ('''<div class="nav">
        <a href="/" style="text-decoration:none;" class="logo">Olivo<span>Vid</span></a>
        <div class="nav-right">
            <a href="/szukaj" class="nav-icon-btn"><svg viewBox="0 0 24 24"><path fill="white" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg></a>
            <a href="/powiadomienia" class="nav-icon-btn" style="position:relative;"><svg viewBox="0 0 24 24"><path fill="white" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>''' + notif_badge + '''</a>
            ''' + admin_link + '''
        </div>
    </div>''')

STYLE = '''<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #000; font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: white; overflow: hidden; }
    .logo { font-size: 22px; font-weight: 900; color: white; letter-spacing: -1px; }
    .logo span { color: #fe2c55; }
    .nav { padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; position: fixed; top: 0; left: 0; right: 0; z-index: 100; background: linear-gradient(to bottom, rgba(0,0,0,0.95), rgba(0,0,0,0.0)); }
    .nav-right { display: flex; align-items: center; gap: 6px; }
    .nav-icon-btn { display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: 50%; background: rgba(255,255,255,0.1); color: white; text-decoration: none; position: relative; }
    .nav-icon-btn svg { width: 22px; height: 22px; }
    .notif-badge { position: absolute; top: 4px; right: 4px; background: #fe2c55; color: white; font-size: 9px; font-weight: 700; width: 14px; height: 14px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
    .bottom-nav { position: fixed; bottom: 0; left: 0; right: 0; height: 60px; background: #000; border-top: 1px solid #222; display: flex; align-items: center; justify-content: space-around; z-index: 100; padding-bottom: env(safe-area-inset-bottom); }
    .bn-item { display: flex; flex-direction: column; align-items: center; justify-content: center; color: #666; text-decoration: none; width: 48px; height: 48px; border-radius: 50%; position: relative; transition: color 0.15s; }
    .bn-item svg { width: 26px; height: 26px; }
    .bn-item.active { color: white; }
    .bn-item.bn-plus { background: #fe2c55; color: white; width: 48px; height: 48px; border-radius: 14px; }
    .bn-item.bn-plus svg { width: 28px; height: 28px; }
    .bn-badge { position: absolute; top: 4px; right: 4px; background: #fe2c55; color: white; font-size: 9px; font-weight: 700; width: 14px; height: 14px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
    .avatar-sm { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; border: 2px solid #fe2c55; }
    .avatar-sm-placeholder { width: 32px; height: 32px; border-radius: 50%; background: #333; border: 2px solid #fe2c55; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; color: #fe2c55; flex-shrink: 0; }
    .avatar-lg { width: 76px; height: 76px; border-radius: 50%; object-fit: cover; border: 3px solid #fe2c55; }
    .avatar-lg-placeholder { width: 76px; height: 76px; border-radius: 50%; background: #222; border: 3px solid #fe2c55; display: flex; align-items: center; justify-content: center; font-size: 26px; font-weight: 700; color: #fe2c55; flex-shrink: 0; }
    .main-page { height: 100vh; overflow-y: auto; padding-top: 64px; padding-bottom: 68px; }
    .relacje-row { display: flex; gap: 12px; overflow-x: auto; padding: 12px 16px; scrollbar-width: none; }
    .relacje-row::-webkit-scrollbar { display: none; }
    .relacja-item { display: flex; flex-direction: column; align-items: center; gap: 6px; cursor: pointer; flex-shrink: 0; }
    .relacja-ring { width: 64px; height: 64px; border-radius: 50%; padding: 2px; background: linear-gradient(45deg, #fe2c55, #ff9f43); }
    .relacja-ring.widziana { background: #333; }
    .relacja-ring img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; border: 2px solid #000; }
    .relacja-ring-placeholder { width: 100%; height: 100%; border-radius: 50%; background: #222; border: 2px solid #000; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 700; color: white; }
    .relacja-nazwa { font-size: 11px; color: #aaa; max-width: 64px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; }
    .relacja-dodaj { width: 64px; height: 64px; border-radius: 50%; background: #1a1a1a; border: 2px dashed #444; display: flex; align-items: center; justify-content: center; }
    .relacja-dodaj svg { width: 28px; height: 28px; color: #fe2c55; }
    .filmy-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 2px; padding: 2px; }
    .film-card { position: relative; aspect-ratio: 9/16; background: #111; overflow: hidden; cursor: pointer; }
    .film-card video { width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
    .film-card-overlay { position: absolute; bottom: 0; left: 0; right: 0; padding: 8px 10px; background: linear-gradient(transparent, rgba(0,0,0,0.8)); }
    .film-card-autor { font-size: 12px; color: #aaa; }
    .film-card-tytul { font-size: 13px; font-weight: 700; color: white; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .feed { height: 100vh; overflow-y: scroll; scroll-snap-type: y mandatory; scrollbar-width: none; }
    .feed::-webkit-scrollbar { display: none; }
    .video-slide { height: 100vh; scroll-snap-align: start; position: relative; display: flex; align-items: center; justify-content: center; background: #000; }
    .video-slide video { height: 100vh; width: 100%; object-fit: contain; cursor: pointer; }
    .repost-label { position: absolute; top: 64px; left: 16px; display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.5); padding: 5px 10px; border-radius: 20px; font-size: 12px; color: #aaa; }
    .repost-label a { color: #fe2c55; text-decoration: none; font-weight: 700; }
    .video-overlay { position: absolute; bottom: 80px; left: 16px; right: 90px; pointer-events: none; }
    .video-overlay-author { font-size: 16px; font-weight: 700; color: white; text-shadow: 0 1px 4px rgba(0,0,0,0.9); }
    .video-overlay-title { font-size: 14px; color: rgba(255,255,255,0.9); margin-top: 5px; text-shadow: 0 1px 4px rgba(0,0,0,0.9); }
    .video-side-actions { position: absolute; right: 10px; bottom: 80px; display: flex; flex-direction: column; align-items: center; gap: 24px; }
    .side-btn { display: flex; flex-direction: column; align-items: center; gap: 5px; cursor: pointer; background: none; border: none; color: white; padding: 4px; }
    .side-count { font-size: 13px; color: white; text-shadow: 0 1px 3px rgba(0,0,0,0.9); font-weight: 700; }
    .icon-heart { width: 48px; height: 48px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8)); transition: transform 0.15s; }
    .icon-comment { width: 46px; height: 46px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }
    .icon-share { width: 42px; height: 42px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }
    .icon-repost { width: 42px; height: 42px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8)); transition: transform 0.15s; }
    .side-btn:active .icon-heart { transform: scale(1.3); }
    .pause-indicator { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); opacity: 0; transition: opacity 0.2s; pointer-events: none; background: rgba(0,0,0,0.4); border-radius: 50%; padding: 16px; }
    .pause-indicator svg { width: 56px; height: 56px; }
    .pause-indicator.show { opacity: 1; }
    .overlay-avatar { pointer-events: all; }
    .avatar-overlay-sm { width: 44px; height: 44px; border-radius: 50%; object-fit: cover; border: 2px solid white; }
    .avatar-overlay-sm-placeholder { width: 44px; height: 44px; border-radius: 50%; background: #333; border: 2px solid white; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700; color: white; }
    .comments-panel { display: none; position: fixed; bottom: 60px; left: 0; right: 0; height: 60vh; background: #111; border-radius: 20px 20px 0 0; z-index: 200; padding: 16px 16px 0; }
    .comments-panel.open { display: flex; flex-direction: column; }
    .panel-handle { width: 44px; height: 5px; background: #444; border-radius: 3px; margin: 0 auto 14px; flex-shrink: 0; }
    .panel-title { font-size: 16px; font-weight: 700; text-align: center; margin-bottom: 14px; flex-shrink: 0; }
    .comments-scroll { flex: 1; overflow-y: auto; }
    .comment { background: #1a1a1a; border-radius: 12px; padding: 12px 14px; margin: 8px 0; }
    .comment.reply { margin-left: 24px; background: #161616; border-left: 3px solid #333; }
    .comment-author { font-size: 13px; font-weight: 700; color: #fe2c55; text-decoration: none; }
    .comment-text { font-size: 14px; color: #ddd; margin: 5px 0; line-height: 1.4; }
    .comment-actions { display: flex; align-items: center; gap: 14px; margin-top: 6px; }
    .comment-like-btn { display: flex; align-items: center; gap: 5px; background: none; border: none; color: #666; font-size: 13px; cursor: pointer; padding: 4px; }
    .comment-like-btn.liked { color: #fe2c55; }
    .reply-toggle { background: none; border: none; color: #666; font-size: 13px; cursor: pointer; padding: 4px; }
    .comment-form { display: flex; gap: 8px; padding: 12px 0; background: #111; flex-shrink: 0; }
    .comment-form input { flex: 1; background: #222; border: 1px solid #333; color: white; padding: 12px 16px; border-radius: 24px; font-size: 14px; outline: none; }
    .comment-form input:focus { border-color: #fe2c55; }
    .comment-form button { background: #fe2c55; color: white; border: none; padding: 12px 18px; border-radius: 24px; cursor: pointer; font-size: 14px; font-weight: 700; }
    .reply-form { display: none; margin-top: 8px; }
    .reply-form.active { display: flex; gap: 8px; }
    .reply-form input { flex: 1; background: #222; border: 1px solid #333; color: white; padding: 10px 14px; border-radius: 20px; font-size: 13px; outline: none; }
    .reply-form button { background: #333; color: white; border: none; padding: 10px 14px; border-radius: 20px; cursor: pointer; font-size: 13px; }
    .share-panel { display: none; position: fixed; bottom: 60px; left: 0; right: 0; background: #111; border-radius: 20px 20px 0 0; z-index: 200; padding: 16px; }
    .share-panel.open { display: block; }
    .share-link { background: #222; border-radius: 10px; padding: 14px 16px; font-size: 13px; color: #aaa; word-break: break-all; margin-bottom: 12px; }
    .share-copy-btn { width: 100%; background: #fe2c55; color: white; border: none; padding: 14px; border-radius: 12px; font-size: 15px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; }
    .overlay-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 199; }
    .overlay-backdrop.open { display: block; }
    .relacja-viewer { display: none; position: fixed; inset: 0; background: #000; z-index: 500; flex-direction: column; }
    .relacja-viewer.open { display: flex; }
    .relacja-viewer-img { flex: 1; object-fit: contain; width: 100%; }
    .relacja-viewer-header { position: absolute; top: 0; left: 0; right: 0; padding: 50px 16px 16px; background: linear-gradient(to bottom, rgba(0,0,0,0.7), transparent); display: flex; align-items: center; gap: 12px; z-index: 10; }
    .relacja-viewer-opis { position: absolute; bottom: 80px; left: 16px; right: 16px; font-size: 15px; color: white; text-shadow: 0 1px 4px rgba(0,0,0,0.9); }
    .relacja-viewer-close { position: absolute; top: 50px; right: 16px; background: rgba(0,0,0,0.5); border: none; color: white; width: 36px; height: 36px; border-radius: 50%; cursor: pointer; font-size: 18px; display: flex; align-items: center; justify-content: center; z-index: 11; }
    .relacja-progress { position: absolute; top: 44px; left: 8px; right: 8px; height: 2px; background: rgba(255,255,255,0.3); border-radius: 2px; z-index: 11; }
    .relacja-progress-fill { height: 100%; background: white; border-radius: 2px; transition: width linear; }
    .search-page { height: 100vh; overflow-y: auto; padding-top: 70px; padding-bottom: 68px; }
    .search-box { max-width: 600px; margin: 20px auto; padding: 0 16px; }
    .search-input-wrap { display: flex; gap: 10px; }
    .search-input { flex: 1; background: #222; border: 1px solid #333; color: white; padding: 14px 18px; border-radius: 24px; font-size: 15px; outline: none; }
    .search-input:focus { border-color: #fe2c55; }
    .search-btn { background: #fe2c55; color: white; border: none; padding: 14px 22px; border-radius: 24px; font-size: 15px; font-weight: 700; cursor: pointer; }
    .search-section { max-width: 600px; margin: 0 auto; padding: 0 16px 40px; }
    .search-section h3 { font-size: 15px; color: #888; margin: 20px 0 12px; }
    .user-row { display: flex; align-items: center; gap: 12px; background: #111; border-radius: 12px; padding: 12px 16px; margin: 8px 0; text-decoration: none; color: white; }
    .user-info { flex: 1; }
    .user-name { font-size: 15px; font-weight: 700; }
    .user-bio { font-size: 13px; color: #888; margin-top: 2px; }
    .video-row { display: flex; align-items: center; gap: 12px; background: #111; border-radius: 12px; padding: 12px 16px; margin: 8px 0; text-decoration: none; color: white; }
    .video-thumb { width: 50px; height: 50px; border-radius: 8px; background: #222; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    .video-row-title { font-size: 14px; font-weight: 700; }
    .video-row-author { font-size: 13px; color: #888; margin-top: 2px; }
    .profile-page { height: 100vh; overflow-y: auto; padding-top: 70px; padding-bottom: 68px; }
    .profile-header { max-width: 600px; margin: 16px auto; padding: 0 16px; }
    .profile-top { display: flex; align-items: center; gap: 20px; margin-bottom: 16px; }
    .profile-name { font-size: 20px; font-weight: 700; }
    .profile-bio { color: #aaa; font-size: 13px; margin-top: 5px; line-height: 1.4; }
    .profile-stats { display: flex; gap: 20px; margin-top: 10px; }
    .stat { text-align: center; }
    .stat-num { font-size: 17px; font-weight: 700; }
    .stat-label { font-size: 11px; color: #aaa; }
    .edit-btn { background: #222; color: white; border: 1px solid #444; padding: 9px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 10px; margin-right: 8px; }
    .follow-btn { background: #fe2c55; color: white; border: none; padding: 9px 22px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 10px; font-weight: 700; }
    .follow-btn.following { background: #333; color: white; border: 1px solid #555; }
    .msg-btn { background: #222; color: white; border: 1px solid #444; padding: 9px 18px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 10px; margin-left: 8px; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
    .profile-tabs { max-width: 600px; margin: 0 auto; display: flex; border-bottom: 1px solid #222; }
    .profile-tab { flex: 1; text-align: center; padding: 12px; font-size: 14px; font-weight: 600; color: #666; cursor: pointer; border-bottom: 2px solid transparent; }
    .profile-tab.active { color: white; border-bottom-color: #fe2c55; }
    .profile-grid { max-width: 600px; margin: 0 auto; display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; padding-bottom: 40px; }
    .profile-grid-item { position: relative; aspect-ratio: 9/16; background: #111; cursor: pointer; overflow: hidden; border-radius: 8px; border: 1px solid #222; display: block; }
    .profile-grid-item video { width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
    .grid-overlay { position: absolute; bottom: 0; left: 0; right: 0; padding: 6px 8px; background: linear-gradient(transparent, rgba(0,0,0,0.7)); }
    .grid-title { font-size: 11px; color: white; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .grid-delete { position: absolute; top: 6px; right: 6px; background: rgba(0,0,0,0.6); border: none; color: #fe2c55; border-radius: 50%; width: 28px; height: 28px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
    .grid-delete svg { width: 16px; height: 16px; }
    .repost-badge { position: absolute; top: 6px; left: 6px; background: rgba(0,0,0,0.6); border-radius: 10px; padding: 3px 7px; font-size: 10px; color: #fe2c55; font-weight: 700; }
    .upload-page { height: 100vh; overflow-y: auto; padding-top: 70px; padding-bottom: 68px; }
    .upload-box { background: #111; border: 2px dashed #333; border-radius: 16px; padding: 24px; max-width: 500px; margin: 24px auto; text-align: center; }
    .upload-box input[type=text], .upload-box textarea { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 14px 16px; border-radius: 12px; font-size: 15px; margin-bottom: 12px; outline: none; }
    .upload-box textarea { height: 80px; resize: none; }
    .file-input { display: none; }
    .file-label { display: inline-flex; align-items: center; gap: 8px; background: #222; color: #aaa; padding: 12px 22px; border-radius: 12px; cursor: pointer; font-size: 14px; margin-bottom: 8px; border: 1px solid #333; }
    .upload-btn { background: #fe2c55; color: white; border: none; padding: 14px 32px; border-radius: 12px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 10px; width: 100%; }
    .upload-btn:disabled { background: #555; cursor: not-allowed; }
    .limit-info { color: #888; font-size: 13px; margin-top: 10px; }
    .limit-warn { color: #fe2c55; font-size: 14px; }
    .select-style { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 14px 16px; border-radius: 12px; font-size: 15px; margin-bottom: 12px; outline: none; appearance: none; }
    .tabs-dodaj { display: flex; gap: 0; margin-bottom: 20px; border-radius: 12px; overflow: hidden; border: 1px solid #333; }
    .tab-dodaj { flex: 1; padding: 12px; text-align: center; background: #1a1a1a; color: #666; cursor: pointer; font-size: 14px; font-weight: 600; border: none; }
    .tab-dodaj.active { background: #fe2c55; color: white; }
    .center { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; overflow-y: auto; }
    .card { background: #111; border: 1px solid #222; border-radius: 16px; padding: 36px; width: 100%; max-width: 380px; }
    .card input { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 14px 16px; border-radius: 12px; font-size: 15px; margin: 6px 0; outline: none; }
    .card input:focus { border-color: #fe2c55; }
    .btn { width: 100%; background: #fe2c55; color: white; border: none; padding: 15px; border-radius: 12px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 12px; }
    .divider { border: none; border-top: 1px solid #222; margin: 20px 0; }
    .link { color: #fe2c55; text-decoration: none; font-weight: 600; }
    .error { color: #fe2c55; font-size: 14px; margin: 8px 0; text-align: center; }
    h2 { color: white; font-size: 22px; font-weight: 700; margin: 12px 0 20px; text-align: center; }
    p.sub { color: #888; font-size: 14px; margin-top: 20px; text-align: center; }
    .edit-form { max-width: 500px; margin: 30px auto; padding: 28px; background: #111; border-radius: 16px; }
    .edit-form input[type=text], .edit-form textarea { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 14px 16px; border-radius: 12px; font-size: 15px; margin: 6px 0 14px; outline: none; }
    .edit-form textarea { height: 100px; resize: none; }
    .edit-form label { color: #aaa; font-size: 13px; }
    .save-btn { background: #fe2c55; color: white; border: none; padding: 14px 32px; border-radius: 12px; font-size: 15px; font-weight: 700; cursor: pointer; }
    .notif-page { height: 100vh; overflow-y: auto; padding-top: 70px; padding-bottom: 68px; }
    .notif-list { max-width: 600px; margin: 20px auto; padding: 0 16px 40px; }
    .notif-item { background: #111; border-radius: 12px; padding: 14px 16px; margin: 10px 0; display: flex; align-items: center; gap: 12px; }
    .notif-item.unread { border-left: 3px solid #fe2c55; }
    .notif-text { font-size: 14px; color: #ddd; line-height: 1.4; }
    .notif-text b { color: #fe2c55; }
    .notif-time { font-size: 12px; color: #555; margin-top: 4px; }
    .admin-page { height: 100vh; overflow-y: auto; padding-top: 70px; padding-bottom: 68px; }
    .admin-panel { max-width: 600px; margin: 20px auto; padding: 0 16px 40px; }
    .admin-card { background: #111; border: 1px solid #222; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
    .admin-card h3 { font-size: 16px; margin-bottom: 12px; color: #aaa; }
    .toggle-btn { padding: 12px 24px; border-radius: 10px; border: none; cursor: pointer; font-size: 14px; font-weight: 700; }
    .toggle-on { background: #fe2c55; color: white; }
    .toggle-off { background: #333; color: #aaa; }
    .film-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #222; }
    .film-row:last-child { border-bottom: none; }
    .delete-btn { background: #1a1a1a; color: #fe2c55; border: 1px solid #fe2c55; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; }
    .toast { position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); background: rgba(50,50,50,0.95); color: white; padding: 12px 24px; border-radius: 24px; font-size: 14px; font-weight: 600; z-index: 999; opacity: 0; transition: opacity 0.3s; pointer-events: none; white-space: nowrap; }
    .toast.show { opacity: 1; }
    .empty { text-align: center; padding: 60px 20px; color: #444; font-size: 18px; line-height: 1.6; }
    .typing-dots { display:flex; gap:4px; align-items:center; height:16px; }
    .typing-dots span { width:8px; height:8px; background:#888; border-radius:50%; animation:bounce 1.2s infinite; }
    .typing-dots span:nth-child(2) { animation-delay:0.2s; }
    .typing-dots span:nth-child(3) { animation-delay:0.4s; }
    @keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-6px)} }
    .chat-page { height: 100vh; overflow-y: auto; padding-top: 70px; padding-bottom: 68px; }
    .chat-list { max-width: 600px; margin: 0 auto; padding: 16px 16px 40px; }
    .chat-row { display: flex; align-items: center; gap: 14px; background: #111; border-radius: 14px; padding: 14px 16px; margin: 8px 0; text-decoration: none; color: white; position: relative; }
    .chat-row.unread { border-left: 3px solid #fe2c55; }
    .chat-row-info { flex: 1; min-width: 0; }
    .chat-row-name { font-size: 15px; font-weight: 700; }
    .chat-row-preview { font-size: 13px; color: #666; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .chat-row-preview.unread-text { color: #aaa; font-weight: 600; }
    .chat-row-time { font-size: 11px; color: #555; position: absolute; top: 14px; right: 16px; }
    .prosba-card { background: #111; border: 1px solid #333; border-radius: 14px; padding: 16px; margin: 10px 0; }
    .prosba-msg { font-size: 14px; color: #ddd; margin: 10px 0; padding: 10px 14px; background: #1a1a1a; border-radius: 10px; }
    .prosba-btns { display: flex; gap: 10px; margin-top: 12px; }
    .akceptuj-btn { background: #fe2c55; color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 700; flex: 1; }
    .odrzuc-btn { background: #333; color: #aaa; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; font-size: 14px; flex: 1; }
    .conv-page { height: 100vh; display: flex; flex-direction: column; }
    .conv-header { padding: 12px 16px; background: #111; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #222; padding-top: 56px; flex-shrink: 0; }
    .conv-header-name { font-size: 16px; font-weight: 700; }
    .conv-back { color: white; text-decoration: none; display: flex; align-items: center; }
    .conv-back svg { width: 24px; height: 24px; }
    .conv-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
    .msg-bubble { max-width: 75%; padding: 10px 14px; border-radius: 18px; font-size: 14px; line-height: 1.4; position: relative; word-break: break-word; margin-bottom: 8px; }
    .msg-bubble.sent { background: #fe2c55; color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
    .msg-bubble.received { background: #222; color: white; align-self: flex-start; border-bottom-left-radius: 4px; }
    .msg-bubble img { max-width: 200px; border-radius: 12px; display: block; }
    .msg-time { font-size: 10px; color: rgba(255,255,255,0.5); margin-top: 4px; text-align: right; }
    .msg-reakcja { position: absolute; bottom: -12px; right: 8px; font-size: 16px; background: #111; border-radius: 10px; padding: 2px 6px; cursor: pointer; border: 1px solid #333; }
    .msg-reakcja.left { right: auto; left: 8px; }
    .conv-input-bar { padding: 10px 12px; background: #111; border-top: 1px solid #222; display: flex; align-items: center; gap: 8px; flex-shrink: 0; padding-bottom: max(10px, env(safe-area-inset-bottom)); }
    .conv-input { flex: 1; background: #222; border: 1px solid #333; color: white; padding: 12px 16px; border-radius: 24px; font-size: 14px; outline: none; min-width: 0; }
    .conv-input:focus { border-color: #fe2c55; }
    .conv-send-btn { background: #fe2c55; color: white; border: none; width: 44px; height: 44px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    .conv-send-btn svg { width: 20px; height: 20px; }
    .conv-img-btn { background: #222; border: 1px solid #333; color: white; width: 44px; height: 44px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    .conv-img-btn svg { width: 20px; height: 20px; }
    .reakcja-picker { display: none; position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); background: #222; border-radius: 24px; padding: 10px 16px; z-index: 300; gap: 12px; border: 1px solid #333; }
    .reakcja-picker.open { display: flex; }
    .reakcja-opt { font-size: 24px; cursor: pointer; padding: 4px; }
    .prosba-send-box { background: #111; border-radius: 16px; padding: 20px; max-width: 500px; margin: 20px auto; }
    .prosba-send-box textarea { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 12px 16px; border-radius: 12px; font-size: 14px; outline: none; resize: none; height: 80px; margin: 10px 0; }
    .prosba-send-btn { background: #fe2c55; color: white; border: none; padding: 12px 28px; border-radius: 12px; font-size: 15px; font-weight: 700; cursor: pointer; width: 100%; }
</style>'''

def heart_svg(liked):
    fill = "#fe2c55" if liked else "white"
    return '<svg class="icon-heart" viewBox="0 0 24 24"><path fill="' + fill + '" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>'

def comment_svg():
    return '<svg class="icon-comment" viewBox="0 0 24 24"><path fill="white" d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'

def share_svg():
    return '<svg class="icon-share" viewBox="0 0 24 24"><path fill="white" d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/></svg>'

def repost_svg(reposted):
    fill = "#fe2c55" if reposted else "white"
    return '<svg class="icon-repost" viewBox="0 0 24 24"><path fill="' + fill + '" d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/></svg>'

def build_feed(conn, uzytkownik):
    filmy = conn.execute("SELECT * FROM filmy").fetchall()
    if not filmy:
        return []
    lajkowane = conn.execute(
        "SELECT f.autor, COUNT(*) as ile FROM lajki l JOIN filmy f ON l.film_id=f.id WHERE l.uzytkownik=? GROUP BY f.autor",
        (uzytkownik,)).fetchall()
    ulubieni = {r['autor']: r['ile'] for r in lajkowane}
    repost_film_ids = set(r['film_id'] for r in conn.execute("SELECT film_id FROM reposty").fetchall())
    pool = []
    for film in filmy:
        waga = 2
        if film['autor'] in ulubieni:
            waga += ulubieni[film['autor']] * 2
        if film['id'] in repost_film_ids:
            waga += 1
        pool.extend([dict(film)] * min(waga, 10))
    random.shuffle(pool)
    seen = set()
    result = []
    for film in pool:
        if film['id'] not in seen:
            seen.add(film['id'])
            result.append(film)
    return result

def render_komentarze(conn, film_id, uzytkownik):
    komentarze = conn.execute(
        "SELECT * FROM komentarze WHERE film_id=? AND odpowiedz_na IS NULL ORDER BY data ASC", (film_id,)).fetchall()
    html = ""
    for kom in komentarze:
        lk = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (kom['id'],)).fetchone()['c']
        czy_lk = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?", (kom['id'], uzytkownik)).fetchone()
        odpowiedzi = conn.execute("SELECT * FROM komentarze WHERE odpowiedz_na=? ORDER BY data ASC", (kom['id'],)).fetchall()
        odp_html = ""
        for odp in odpowiedzi:
            lok = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (odp['id'],)).fetchone()['c']
            czy_lok = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?", (odp['id'], uzytkownik)).fetchone()
            lf = "#fe2c55" if czy_lok else "#666"
            odp_html += ('<div class="comment reply"><a href="/profil/' + odp['uzytkownik'] + '" class="comment-author">@' + odp['uzytkownik'] + '</a>'
                '<p class="comment-text">' + odp['tresc'] + '</p>'
                '<div class="comment-actions"><button class="comment-like-btn ' + ('liked' if czy_lok else '') + '" onclick="lajkujKomentarz(' + str(odp['id']) + ',this)">'
                '<svg width="16" height="16" viewBox="0 0 24 24"><path fill="' + lf + '" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>'
                ' ' + str(lok) + '</button></div></div>')
        kf = "#fe2c55" if czy_lk else "#666"
        html += ('<div class="comment" id="kom-' + str(kom['id']) + '"><a href="/profil/' + kom['uzytkownik'] + '" class="comment-author">@' + kom['uzytkownik'] + '</a>'
            '<p class="comment-text">' + kom['tresc'] + '</p>'
            '<div class="comment-actions"><button class="comment-like-btn ' + ('liked' if czy_lk else '') + '" onclick="lajkujKomentarz(' + str(kom['id']) + ',this)">'
            '<svg width="16" height="16" viewBox="0 0 24 24"><path fill="' + kf + '" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>'
            ' ' + str(lk) + '</button>'
            '<button class="reply-toggle" onclick="pokazOdpowiedz(' + str(kom['id']) + ')">Odpowiedz</button></div>'
            '<div class="reply-form" id="reply-' + str(kom['id']) + '">'
            '<input type="text" placeholder="Odpowiedź..." id="reply-input-' + str(kom['id']) + '">'
            '<button onclick="wyslijOdpowiedz(' + str(film_id) + ',' + str(kom['id']) + ')">Wyślij</button>'
            '</div>' + odp_html + '</div>')
    return html

def get_relacje_html(conn, uzytkownik):
    teraz = datetime.now().isoformat()
    # Usuń wygasłe
    conn.execute("DELETE FROM relacje WHERE wygasa IS NOT NULL AND wygasa < ?", (teraz,))
    conn.commit()
    # Pobierz relacje obserwowanych + własne
    obserwowani = [r['obserwowany'] for r in conn.execute(
        "SELECT obserwowany FROM obserwowania WHERE obserwujacy=?", (uzytkownik,)).fetchall()]
    autorzy = [uzytkownik] + obserwowani
    relacje_per_autor = {}
    for autor in autorzy:
        r = conn.execute(
            "SELECT * FROM relacje WHERE autor=? AND (widocznosc='wszyscy' OR (widocznosc='znajomi' AND ? IN "
            "(SELECT obserwowany FROM obserwowania WHERE obserwujacy=?))) ORDER BY data DESC LIMIT 1",
            (autor, uzytkownik, autor)).fetchone()
        if r:
            relacje_per_autor[autor] = r
    html = '<div class="relacje-row">'
    # Najpierw własna relacja / dodaj
    wlasna = relacje_per_autor.get(uzytkownik)
    if wlasna:
        html += ('<div class="relacja-item" onclick="pokazRelacje(' + str(wlasna['id']) + ')">'
                 '<div class="relacja-ring">' + avatar_html(uzytkownik, 'relacja') + '</div>'
                 '<span class="relacja-nazwa">Ty</span></div>')
    else:
        html += ('<a href="/dodaj#relacja" class="relacja-item">'
                 '<div class="relacja-dodaj"><svg viewBox="0 0 24 24"><path fill="#fe2c55" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg></div>'
                 '<span class="relacja-nazwa">Dodaj</span></a>')
    for autor in obserwowani:
        r = relacje_per_autor.get(autor)
        if r:
            html += ('<div class="relacja-item" onclick="pokazRelacje(' + str(r['id']) + ')">'
                     '<div class="relacja-ring">' + avatar_html(autor, 'relacja') + '</div>'
                     '<span class="relacja-nazwa">@' + autor + '</span></div>')
    html += '</div>'
    return html

@app.route("/")
def strona_glowna():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    uzytkownik = session['uzytkownik']
    relacje_html = get_relacje_html(conn, uzytkownik)
    filmy = build_feed(conn, uzytkownik)
    filmy_html = ""
    for film in filmy:
        filmy_html += ('<a href="/ogladaj/' + str(film['id']) + '" class="film-card">'
            '<video preload="metadata" muted><source src="' + film['url'] + '"></video>'
            '<div class="film-card-overlay">'
            '<p class="film-card-autor">@' + film['autor'] + '</p>'
            '<p class="film-card-tytul">' + film['tytul'] + '</p>'
            '</div></a>')
    # Pobierz wszystkie relacje do viewera
    teraz = datetime.now().isoformat()
    wszystkie_relacje = conn.execute(
        "SELECT * FROM relacje WHERE wygasa IS NULL OR wygasa > ? ORDER BY data DESC", (teraz,)).fetchall()
    relacje_data = []
    for r in wszystkie_relacje:
        relacje_data.append({'id': r['id'], 'autor': r['autor'], 'plik': r['plik'], 'opis': r['opis'] or ''})
    conn.close()
    import json
    relacje_json = json.dumps(relacje_data)
    return ('<!DOCTYPE html><html><head><title>OlivoVid</title><meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>'
            + top_nav_html(uzytkownik) +
            '<div class="main-page">'
            + relacje_html +
            '<div class="filmy-grid">' + (filmy_html if filmy_html else '<p class="empty" style="grid-column:1/-1;">Brak filmów</p>') + '</div>'
            '</div>'
            + bottom_nav_html('home', uzytkownik) +
            '<div class="toast" id="toast"></div>'
            '<div class="relacja-viewer" id="relViewer">'
            '<div class="relacja-progress"><div class="relacja-progress-fill" id="relProgress"></div></div>'
            '<button class="relacja-viewer-close" onclick="zamknijRelacje()">✕</button>'
            '<div class="relacja-viewer-header" id="relHeader"></div>'
            '<img class="relacja-viewer-img" id="relImg" src="" alt="">'
            '<p class="relacja-viewer-opis" id="relOpis"></p>'
            '</div>'
            '<script>'
            'const relacje=' + relacje_json + ';'
            'let relTimer=null;'
            'function pokazRelacje(id){'
            'const r=relacje.find(x=>x.id===id);if(!r)return;'
            'document.getElementById("relImg").src="/relacja_img/"+r.plik;'
            'document.getElementById("relOpis").textContent=r.opis;'
            'document.getElementById("relHeader").innerHTML=\'<div style="width:40px;height:40px;border-radius:50%;overflow:hidden;border:2px solid white;">\'+\'<img src="/avatar/\'+r.autor+\'" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display=\'none\'">\'+\'</div><span style="font-weight:700;">@\'+r.autor+\'</span>\';'
            'document.getElementById("relViewer").classList.add("open");'
            'const prog=document.getElementById("relProgress");'
            'prog.style.width="0%";prog.style.transition="none";'
            'setTimeout(()=>{prog.style.transition="width 5s linear";prog.style.width="100%";},50);'
            'if(relTimer)clearTimeout(relTimer);relTimer=setTimeout(zamknijRelacje,5000);'
            '}'
            'function zamknijRelacje(){'
            'document.getElementById("relViewer").classList.remove("open");'
            'if(relTimer)clearTimeout(relTimer);'
            'document.getElementById("relProgress").style.width="0%";'
            '}'
            'function pokazToast(msg){const t=document.getElementById("toast");t.textContent=msg;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2000);}'
            '</script>'
            '</body></html>')

@app.route("/filmy")
def filmy_page():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    uzytkownik = session['uzytkownik']
    filmy = build_feed(conn, uzytkownik)
    filmy_html = ""
    for film in filmy:
        fid = film['id']
        lajki = conn.execute("SELECT COUNT(*) as c FROM lajki WHERE film_id=?", (fid,)).fetchone()['c']
        czy_lajk = conn.execute("SELECT 1 FROM lajki WHERE film_id=? AND uzytkownik=?", (fid, uzytkownik)).fetchone()
        ile_kom = conn.execute("SELECT COUNT(*) as c FROM komentarze WHERE film_id=?", (fid,)).fetchone()['c']
        ile_repostow = conn.execute("SELECT COUNT(*) as c FROM reposty WHERE film_id=?", (fid,)).fetchone()['c']
        czy_repost = conn.execute("SELECT 1 FROM reposty WHERE film_id=? AND uzytkownik=?", (fid, uzytkownik)).fetchone()
        repost_info = conn.execute(
            "SELECT r.uzytkownik FROM reposty r JOIN obserwowania o ON r.uzytkownik=o.obserwowany "
            "WHERE r.film_id=? AND o.obserwujacy=? AND r.uzytkownik!=? LIMIT 1",
            (fid, uzytkownik, film['autor'])).fetchone()
        komentarze_html = render_komentarze(conn, fid, uzytkownik)
        autor_avatar = avatar_html(film['autor'], 'overlay-sm')
        film_url = "https://olivovid.onrender.com/film/" + str(fid)
        repost_label = ""
        if repost_info:
            repost_label = ('<div class="repost-label"><svg viewBox="0 0 24 24" style="width:14px;height:14px;"><path fill="#aaa" d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/></svg>'
                'Repost od <a href="/profil/' + repost_info['uzytkownik'] + '">@' + repost_info['uzytkownik'] + '</a></div>')
        filmy_html += ('<div class="video-slide" id="slide-' + str(fid) + '">'
            '<video loop playsinline preload="metadata" id="video-' + str(fid) + '"><source src="' + film['url'] + '"></video>'
            '<div class="pause-indicator" id="pause-' + str(fid) + '"><svg viewBox="0 0 24 24"><path fill="white" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg></div>'
            + repost_label +
            '<div class="video-overlay"><a href="/profil/' + film['autor'] + '" class="overlay-avatar">' + autor_avatar + '</a>'
            '<p class="video-overlay-author">@' + film['autor'] + '</p>'
            '<p class="video-overlay-title">' + film['tytul'] + '</p></div>'
            '<div class="video-side-actions">'
            '<button class="side-btn" id="like-' + str(fid) + '" onclick="lajkuj(' + str(fid) + ',this)">' + heart_svg(bool(czy_lajk)) + '<span class="side-count" id="like-count-' + str(fid) + '">' + str(lajki) + '</span></button>'
            '<button class="side-btn" onclick="toggleKomentarze(' + str(fid) + ')">' + comment_svg() + '<span class="side-count">' + str(ile_kom) + '</span></button>'
            '<button class="side-btn" id="repost-' + str(fid) + '" onclick="repostuj(' + str(fid) + ',this)">' + repost_svg(bool(czy_repost)) + '<span class="side-count" id="repost-count-' + str(fid) + '">' + str(ile_repostow) + '</span></button>'
            '<button class="side-btn" onclick="pokazUdostepnij(' + str(fid) + ')">' + share_svg() + '</button>'
            '</div>'
            '<div class="overlay-backdrop" id="backdrop-' + str(fid) + '" onclick="zamknijWszystko(' + str(fid) + ')"></div>'
            '<div class="comments-panel" id="panel-' + str(fid) + '"><div class="panel-handle"></div><p class="panel-title">Komentarze</p>'
            '<div class="comments-scroll" id="komentarze-' + str(fid) + '">' + komentarze_html + '</div>'
            '<div class="comment-form"><input type="text" placeholder="Dodaj komentarz..." id="kom-input-' + str(fid) + '">'
            '<button onclick="wyslijKomentarz(' + str(fid) + ')">Wyślij</button></div></div>'
            '<div class="share-panel" id="share-' + str(fid) + '"><div class="panel-handle"></div><p class="panel-title">Udostępnij</p>'
            '<p class="share-link">' + film_url + '</p>'
            '<button class="share-copy-btn" onclick="kopiujLink(\'' + film_url + '\',' + str(fid) + ')">'
            '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="white" d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>'
            'Kopiuj link</button></div></div>')
    conn.close()
    if not filmy_html:
        filmy_html = '<div class="video-slide"><p class="empty">Brak filmów</p></div>'
    js = '''<script>
    function pokazToast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000);}
    const slides=document.querySelectorAll('.video-slide');
    const observer=new IntersectionObserver((e)=>{e.forEach(e=>{const v=e.target.querySelector('video');if(!v)return;if(e.isIntersecting)v.play();else{v.pause();v.currentTime=0;}});},{threshold:0.7});
    slides.forEach(s=>observer.observe(s));
    slides.forEach(slide=>{const video=slide.querySelector('video');const id=slide.id.replace('slide-','');const ind=document.getElementById('pause-'+id);
        if(video){video.addEventListener('click',function(e){if(e.target.closest('.video-side-actions')||e.target.closest('.video-overlay'))return;
            if(video.paused){video.play();ind.classList.remove('show');}else{video.pause();ind.classList.add('show');setTimeout(()=>ind.classList.remove('show'),800);}});}});
    document.addEventListener('keydown',function(e){if(e.code==='Space'&&e.target.tagName!=='INPUT'){e.preventDefault();
        const v=Array.from(slides).find(s=>{const r=s.getBoundingClientRect();return r.top>=-50&&r.top<=50;});
        if(v){const vid=v.querySelector('video');const id=v.id.replace('slide-','');const ind=document.getElementById('pause-'+id);
            if(vid.paused){vid.play();ind.classList.remove('show');}else{vid.pause();ind.classList.add('show');setTimeout(()=>ind.classList.remove('show'),800);}}}});
    slides.forEach(slide=>{let last=0;slide.addEventListener('touchend',function(e){
        if(e.target.closest('.video-side-actions')||e.target.closest('.comments-panel')||e.target.closest('.share-panel'))return;
        const now=Date.now();if(now-last<300){const id=slide.id.replace('slide-','');lajkuj(parseInt(id),document.getElementById('like-'+id));}last=now;});});
    function lajkuj(fid,btn){fetch('/lajkuj/'+fid,{method:'POST'}).then(r=>r.json()).then(d=>{document.getElementById('like-count-'+fid).textContent=d.lajki;btn.querySelector('path').setAttribute('fill',d.lajkuje?'#fe2c55':'white');});}
    function repostuj(fid,btn){fetch('/repostuj/'+fid,{method:'POST'}).then(r=>r.json()).then(d=>{document.getElementById('repost-count-'+fid).textContent=d.reposty;btn.querySelector('path').setAttribute('fill',d.repostuje?'#fe2c55':'white');pokazToast(d.repostuje?'Repostowano!':'Usunięto repost');});}
    function toggleKomentarze(fid){document.getElementById('panel-'+fid).classList.toggle('open');document.getElementById('backdrop-'+fid).classList.toggle('open');}
    function pokazUdostepnij(fid){document.getElementById('share-'+fid).classList.add('open');document.getElementById('backdrop-'+fid).classList.add('open');}
    function zamknijWszystko(fid){document.getElementById('panel-'+fid).classList.remove('open');document.getElementById('share-'+fid).classList.remove('open');document.getElementById('backdrop-'+fid).classList.remove('open');}
    function kopiujLink(url,fid){navigator.clipboard.writeText(url).then(()=>pokazToast('Link skopiowany!'));zamknijWszystko(fid);}
    function lajkujKomentarz(kid,btn){fetch('/lajkuj_komentarz/'+kid,{method:'POST'}).then(r=>r.json()).then(d=>{btn.querySelector('path').setAttribute('fill',d.lajkuje?'#fe2c55':'#666');btn.childNodes[2].textContent=' '+d.lajki;btn.classList.toggle('liked',d.lajkuje);});}
    function wyslijKomentarz(fid){const inp=document.getElementById('kom-input-'+fid);if(!inp.value.trim())return;
        fetch('/komentarz/'+fid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tresc:inp.value})}).then(r=>r.json()).then(d=>{
            document.getElementById('komentarze-'+fid).insertAdjacentHTML('beforeend','<div class="comment" id="kom-'+d.id+'"><a href="/profil/'+d.uzytkownik+'" class="comment-author">@'+d.uzytkownik+'</a><p class="comment-text">'+d.tresc+'</p><div class="comment-actions"><button class="comment-like-btn" onclick="lajkujKomentarz('+d.id+',this)"><svg width="16" height="16" viewBox="0 0 24 24"><path fill="#666" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg> 0</button><button class="reply-toggle" onclick="pokazOdpowiedz('+d.id+')">Odpowiedz</button></div><div class="reply-form" id="reply-'+d.id+'"><input type="text" placeholder="Odpowiedź..." id="reply-input-'+d.id+'"><button onclick="wyslijOdpowiedz('+fid+','+d.id+')">Wyślij</button></div></div>');
            inp.value='';});}
    function pokazOdpowiedz(kid){document.getElementById('reply-'+kid).classList.toggle('active');}
    function wyslijOdpowiedz(fid,kid){const inp=document.getElementById('reply-input-'+kid);if(!inp.value.trim())return;
        fetch('/komentarz/'+fid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tresc:inp.value,odpowiedz_na:kid})}).then(r=>r.json()).then(d=>{
            document.getElementById('kom-'+kid).insertAdjacentHTML('beforeend','<div class="comment reply"><a href="/profil/'+d.uzytkownik+'" class="comment-author">@'+d.uzytkownik+'</a><p class="comment-text">'+d.tresc+'</p></div>');
            inp.value='';document.getElementById('reply-'+kid).classList.remove('active');});}
    </script>'''
    return ('<!DOCTYPE html><html><head><title>Filmy - OlivoVid</title><meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>'
            + '<div class="feed">' + filmy_html + '</div>'
            + bottom_nav_html('filmy', uzytkownik)
            + '<div class="toast" id="toast"></div>' + js + '</body></html>')

@app.route("/dodaj")
def dodaj_page():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    aktywne = wgrywanie_aktywne()
    fwm = filmy_w_tym_miesiacu(session['uzytkownik'])
    if not aktywne:
        film_html = '<p class="limit-warn">Wgrywanie filmów jest tymczasowo wyłączone.</p>'
    elif fwm >= LIMIT_FILMOW_MIESIECZNIE:
        film_html = '<p class="limit-warn">Osiągnąłeś limit filmów w tym miesiącu.</p>'
    else:
        pozostalo = LIMIT_FILMOW_MIESIECZNIE - fwm
        film_html = ('<form method="POST" action="/upload" enctype="multipart/form-data" id="uploadForm">'
            '<input type="text" name="tytul" placeholder="Tytuł wideo" required style="width:100%;background:#222;border:1px solid #333;color:white;padding:14px 16px;border-radius:12px;font-size:15px;margin-bottom:12px;outline:none;">'
            '<label for="fileInput" class="file-label"><svg width="20" height="20" viewBox="0 0 24 24"><path fill="#aaa" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>Wybierz wideo</label>'
            '<input type="file" name="wideo" accept="video/*" class="file-input" id="fileInput" onchange="document.getElementById(\'fileName\').textContent=this.files[0].name">'
            '<p style="color:#555;font-size:13px;margin:8px 0;" id="fileName">Nie wybrano pliku</p>'
            '<button type="submit" class="upload-btn" id="uploadBtn">Wgraj wideo</button>'
            '<p class="limit-info">Pozostało: <b>' + str(pozostalo) + '</b> / ' + str(LIMIT_FILMOW_MIESIECZNIE) + ' w tym miesiącu</p></form>')
    return ('<!DOCTYPE html><html><head><title>Dodaj - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + top_nav_html(session['uzytkownik']) +
            '<div class="upload-page"><div class="upload-box">'
            '<div class="tabs-dodaj">'
            '<button class="tab-dodaj active" id="tab-film-btn" onclick="pokazTab(\'film\')">🎬 Film</button>'
            '<button class="tab-dodaj" id="tab-relacja-btn" onclick="pokazTab(\'relacja\')">📸 Relacja</button>'
            '</div>'
            '<div id="tab-film"><h2>Wgraj film</h2>' + film_html + '</div>'
            '<div id="tab-relacja" style="display:none;"><h2>Dodaj relację</h2>'
            '<form method="POST" action="/dodaj_relacje" enctype="multipart/form-data" id="relForm">'
            '<label for="relFile" class="file-label"><svg width="20" height="20" viewBox="0 0 24 24"><path fill="#aaa" d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>Wybierz zdjęcie</label>'
            '<input type="file" name="zdjecie" accept="image/*" class="file-input" id="relFile" onchange="document.getElementById(\'relFileName\').textContent=this.files[0].name" required>'
            '<p style="color:#555;font-size:13px;margin:8px 0;" id="relFileName">Nie wybrano pliku</p>'
            '<textarea name="opis" placeholder="Opis (opcjonalnie)..." style="width:100%;background:#222;border:1px solid #333;color:white;padding:12px 16px;border-radius:12px;font-size:14px;outline:none;resize:none;height:70px;margin-bottom:12px;"></textarea>'
            '<select name="widocznosc" class="select-style"><option value="wszyscy">Wszyscy</option><option value="znajomi">Tylko obserwujący</option></select>'
            '<select name="czas" class="select-style">'
            '<option value="1">1 dzień</option><option value="2">2 dni</option>'
            '<option value="7">Tydzień</option><option value="30">Miesiąc</option>'
            '<option value="365">Rok</option><option value="0">Na zawsze</option>'
            '</select>'
            '<button type="submit" class="upload-btn">Opublikuj relację</button>'
            '</form></div>'
            '</div></div>'
            '<script>'
            'document.getElementById("uploadForm")&&document.getElementById("uploadForm").addEventListener("submit",function(){const b=document.getElementById("uploadBtn");if(b){b.disabled=true;b.textContent="Wgrywanie...";}});'
            'function pokazTab(t){'
            'document.getElementById("tab-film").style.display=t==="film"?"block":"none";'
            'document.getElementById("tab-relacja").style.display=t==="relacja"?"block":"none";'
            'document.getElementById("tab-film-btn").className="tab-dodaj"+(t==="film"?" active":"");'
            'document.getElementById("tab-relacja-btn").className="tab-dodaj"+(t==="relacja"?" active":"");}'
            'if(location.hash==="#relacja")pokazTab("relacja");'
            '</script>'
            + bottom_nav_html('dodaj', session['uzytkownik']) + '</body></html>')

@app.route("/dodaj_relacje", methods=["POST"])
def dodaj_relacje():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    plik = request.files.get('zdjecie')
    opis = request.form.get('opis', '')[:200]
    widocznosc = request.form.get('widocznosc', 'wszyscy')
    czas = int(request.form.get('czas', 1))
    if not plik:
        return redirect(url_for('dodaj_page'))
    img = Image.open(plik)
    img = img.convert('RGB')
    img.thumbnail((1080, 1920))
    nazwa = session['uzytkownik'] + '_' + str(random.randint(100000, 999999)) + '.jpg'
    img.save(os.path.join(RELACJE_FOLDER, nazwa), 'JPEG')
    if czas == 0:
        wygasa = None
    else:
        wygasa = (datetime.now() + timedelta(days=czas)).isoformat()
    conn = get_db()
    conn.execute("INSERT INTO relacje (autor, plik, opis, widocznosc, wygasa) VALUES (?,?,?,?,?)",
                 (session['uzytkownik'], nazwa, opis, widocznosc, wygasa))
    conn.commit()
    conn.close()
    return redirect(url_for('strona_glowna'))

@app.route("/relacja_img/<nazwa>")
def relacja_img(nazwa):
    return send_from_directory(RELACJE_FOLDER, nazwa)

@app.route("/ogladaj/<int:film_id>")
def ogladaj(film_id):
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    return redirect(url_for('filmy_page') + '#slide-' + str(film_id))

@app.route("/repostuj/<int:film_id>", methods=["POST"])
def repostuj(film_id):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    conn = get_db()
    czy = conn.execute("SELECT 1 FROM reposty WHERE film_id=? AND uzytkownik=?", (film_id, session['uzytkownik'])).fetchone()
    if czy:
        conn.execute("DELETE FROM reposty WHERE film_id=? AND uzytkownik=?", (film_id, session['uzytkownik']))
        repostuje = False
    else:
        conn.execute("INSERT INTO reposty (film_id, uzytkownik) VALUES (?,?)", (film_id, session['uzytkownik']))
        repostuje = True
    conn.commit()
    reposty = conn.execute("SELECT COUNT(*) as c FROM reposty WHERE film_id=?", (film_id,)).fetchone()['c']
    conn.close()
    return jsonify({'reposty': reposty, 'repostuje': repostuje})

@app.route("/wiadomosci")
def wiadomosci():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    uzytkownik = session['uzytkownik']
    prosby = conn.execute("SELECT * FROM prosby_chat WHERE do=? AND status='oczekuje' ORDER BY data DESC", (uzytkownik,)).fetchall()
    prosby_html = ""
    for p in prosby:
        prosby_html += ('<div class="prosba-card">'
            '<div style="display:flex;align-items:center;gap:10px;">' + avatar_html(p['od'], 'sm') +
            '<div><b>@' + p['od'] + '</b> chce wysłać Ci wiadomość</div></div>'
            '<p class="prosba-msg">' + p['wiadomosc'] + '</p>'
            '<div class="prosba-btns">'
            '<button class="akceptuj-btn" onclick="odpowiedzProsbie(' + str(p['id']) + ',\'zaakceptowana\')">Akceptuj</button>'
            '<button class="odrzuc-btn" onclick="odpowiedzProsbie(' + str(p['id']) + ',\'odrzucona\')">Odrzuć</button>'
            '</div></div>')
    rozm = conn.execute(
        "SELECT CASE WHEN od=? THEN do ELSE od END as rozmowca, MAX(data) as ostatnia, MAX(id) as last_id "
        "FROM wiadomosci WHERE od=? OR do=? GROUP BY rozmowca ORDER BY ostatnia DESC",
        (uzytkownik, uzytkownik, uzytkownik)).fetchall()
    rozm_html = ""
    for r in rozm:
        ost = conn.execute("SELECT * FROM wiadomosci WHERE id=?", (r['last_id'],)).fetchone()
        nieprzeczytane = conn.execute("SELECT COUNT(*) as c FROM wiadomosci WHERE od=? AND do=? AND przeczytana=0",
                                      (r['rozmowca'], uzytkownik)).fetchone()['c']
        if ost['typ'] == 'zdjecie': preview = '📷 Zdjęcie'
        else: preview = (ost['tresc'] or '')[:40]
        rozm_html += ('<a href="/chat/' + r['rozmowca'] + '" class="chat-row ' + ('unread' if nieprzeczytane else '') + '">'
            + avatar_html(r['rozmowca'], 'sm') +
            '<div class="chat-row-info"><p class="chat-row-name">@' + r['rozmowca'] + '</p>'
            '<p class="chat-row-preview ' + ('unread-text' if nieprzeczytane else '') + '">' + preview + '</p></div>'
            '<span class="chat-row-time">' + (ost['data'][11:16] if ost else '') + '</span></a>')
    conn.close()
    return ('<!DOCTYPE html><html><head><title>Wiadomości - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + top_nav_html(uzytkownik) +
            '<div class="chat-page"><div class="chat-list"><h2>Wiadomości</h2>'
            + (('<div style="margin-bottom:16px;"><p style="color:#aaa;font-size:13px;margin-bottom:8px;">Prośby o wiadomość</p>' + prosby_html + '</div>') if prosby_html else '')
            + (rozm_html if rozm_html else '<p style="color:#555;text-align:center;padding:40px;">Brak wiadomości</p>')
            + '</div></div>'
            + bottom_nav_html('wiad', uzytkownik) +
            '<script>function odpowiedzProsbie(id,status){fetch("/odpowiedz_prosbie/"+id,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:status})}).then(r=>r.json()).then(d=>{if(d.ok)location.reload();});}</script>'
            '</body></html>')

@app.route("/odpowiedz_prosbie/<int:pid>", methods=["POST"])
def odpowiedz_prosbie(pid):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    data = request.get_json()
    status = data.get('status')
    if status not in ['zaakceptowana', 'odrzucona']:
        return jsonify({}), 400
    conn = get_db()
    prosba = conn.execute("SELECT * FROM prosby_chat WHERE id=? AND do=?", (pid, session['uzytkownik'])).fetchone()
    if not prosba:
        conn.close()
        return jsonify({}), 403
    conn.execute("UPDATE prosby_chat SET status=? WHERE id=?", (status, pid))
    if status == 'zaakceptowana':
        conn.execute("INSERT INTO wiadomosci (od, do, tresc, typ) VALUES (?,?,?,'tekst')",
                     (prosba['od'], session['uzytkownik'], prosba['wiadomosc']))
        conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?,?,'chat_zaakceptowany',0)",
                     (prosba['od'], session['uzytkownik']))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route("/wyslij_prosbe/<do>", methods=["POST"])
def wyslij_prosbe(do):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    data = request.get_json()
    wiadomosc = data.get('wiadomosc', '').strip()
    if not wiadomosc or not do:
        return jsonify({'error': 'Napisz wiadomość'}), 400
    conn = get_db()
    istniejaca = conn.execute("SELECT * FROM prosby_chat WHERE od=? AND do=?", (session['uzytkownik'], do)).fetchone()
    if istniejaca:
        conn.close()
        return jsonify({'error': 'Prośba już wysłana'}), 400
    conn.execute("INSERT INTO prosby_chat (od, do, wiadomosc) VALUES (?,?,?)", (session['uzytkownik'], do, wiadomosc))
    conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?,?,'prosba_chat',0)", (do, session['uzytkownik']))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route("/chat/<rozmowca>")
def chat(rozmowca):
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    uzytkownik = session['uzytkownik']
    moze = czy_moze_pisac(uzytkownik, rozmowca, conn)
    if not moze:
        prosba = conn.execute("SELECT * FROM prosby_chat WHERE od=? AND do=?", (uzytkownik, rozmowca)).fetchone()
        conn.close()
        if prosba and prosba['status'] == 'oczekuje':
            return ('<!DOCTYPE html><html><head><title>Chat</title><meta name="viewport" content="width=device-width, initial-scale=1">'
                    + STYLE + '</head><body>' + top_nav_html(uzytkownik) +
                    '<div class="upload-page"><div style="max-width:500px;margin:40px auto;padding:0 16px;text-align:center;">'
                    '<p style="color:#aaa;font-size:16px;">Prośba wysłana do @' + rozmowca + '</p>'
                    '<p style="color:#555;font-size:14px;margin-top:8px;">Poczekaj aż zaakceptuje</p>'
                    '<a href="/wiadomosci" style="display:inline-block;margin-top:20px;color:#fe2c55;">← Wróć</a>'
                    '</div></div>' + bottom_nav_html('wiad', uzytkownik) + '</body></html>')
        elif prosba and prosba['status'] == 'odrzucona':
            conn.close()
            return ('<!DOCTYPE html><html><head><title>Chat</title><meta name="viewport" content="width=device-width, initial-scale=1">'
                    + STYLE + '</head><body>' + top_nav_html(uzytkownik) +
                    '<div class="upload-page"><div style="max-width:500px;margin:40px auto;padding:0 16px;text-align:center;">'
                    '<p style="color:#fe2c55;font-size:16px;">@' + rozmowca + ' odrzucił Twoją prośbę</p>'
                    '<a href="/wiadomosci" style="display:inline-block;margin-top:20px;color:#fe2c55;">← Wróć</a>'
                    '</div></div>' + bottom_nav_html('wiad', uzytkownik) + '</body></html>')
        else:
            conn.close()
            return ('<!DOCTYPE html><html><head><title>Chat</title><meta name="viewport" content="width=device-width, initial-scale=1">'
                    + STYLE + '</head><body>' + top_nav_html(uzytkownik) +
                    '<div class="upload-page"><div class="prosba-send-box">'
                    '<h2>Napisz do @' + rozmowca + '</h2>'
                    '<p style="color:#888;font-size:13px;margin-bottom:10px;">Wyślij prośbę — @' + rozmowca + ' musi ją zaakceptować</p>'
                    '<textarea id="prosba-msg" placeholder="Napisz pierwszą wiadomość..."></textarea>'
                    '<button class="prosba-send-btn" onclick="wyslijProsbe()">Wyślij prośbę</button>'
                    '</div></div>'
                    '<script>function wyslijProsbe(){const msg=document.getElementById("prosba-msg").value.trim();if(!msg)return;'
                    'fetch("/wyslij_prosbe/' + rozmowca + '",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({wiadomosc:msg})})'
                    '.then(r=>r.json()).then(d=>{if(d.ok)location.reload();else alert(d.error||"Błąd");});}</script>'
                    + bottom_nav_html('wiad', uzytkownik) + '</body></html>')
    wiad = conn.execute(
        "SELECT * FROM wiadomosci WHERE (od=? AND do=?) OR (od=? AND do=?) ORDER BY data ASC",
        (uzytkownik, rozmowca, rozmowca, uzytkownik)).fetchall()
    conn.execute("UPDATE wiadomosci SET przeczytana=1 WHERE od=? AND do=?", (rozmowca, uzytkownik))
    conn.commit()
    conn.close()
    msgs_html = ""
    last_id = 0
    for w in wiad:
        jest_moja = w['od'] == uzytkownik
        klasa = "sent" if jest_moja else "received"
        if w['typ'] == 'zdjecie':
            tresc_html = '<img src="/chat_img/' + w['tresc'] + '" alt="zdjęcie">'
        else:
            tresc_html = w['tresc']
        reakcja_html = ''
        if w['reakcja']:
            rk = '' if jest_moja else 'left'
            reakcja_html = '<span class="msg-reakcja ' + rk + '">' + w['reakcja'] + '</span>'
        elif not jest_moja:
            reakcja_html = '<span class="msg-reakcja left" onclick="pokazPicker(' + str(w['id']) + ')">＋</span>'
        msgs_html += ('<div class="msg-bubble ' + klasa + '" id="msg-' + str(w['id']) + '">'
            + tresc_html + '<div class="msg-time">' + w['data'][11:16] + '</div>' + reakcja_html + '</div>')
        last_id = max(last_id, w['id'])
    return ('<!DOCTYPE html><html><head><title>@' + rozmowca + '</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>'
            '<div class="conv-page">'
            '<div class="conv-header">'
            '<a href="/wiadomosci" class="conv-back"><svg viewBox="0 0 24 24"><path fill="white" d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg></a>'
            + avatar_html(rozmowca, 'sm') +
            '<p class="conv-header-name">@' + rozmowca + '</p>'
            '<a href="/profil/' + rozmowca + '" style="margin-left:auto;color:#aaa;font-size:13px;">Profil</a>'
            '</div>'
            '<div class="conv-messages" id="msgs">' + msgs_html + '</div>'
            '<div class="reakcja-picker" id="picker">'
            '<span class="reakcja-opt" onclick="dajReakcje(currentMsgId,\'❤️\')">❤️</span>'
            '<span class="reakcja-opt" onclick="dajReakcje(currentMsgId,\'😂\')">😂</span>'
            '<span class="reakcja-opt" onclick="dajReakcje(currentMsgId,\'😮\')">😮</span>'
            '<span class="reakcja-opt" onclick="dajReakcje(currentMsgId,\'🔥\')">🔥</span>'
            '<span class="reakcja-opt" onclick="dajReakcje(currentMsgId,\'👏\')">👏</span>'
            '</div>'
            '<div class="conv-input-bar">'
            '<label class="conv-img-btn" for="img-input">'
            '<svg viewBox="0 0 24 24"><path fill="white" d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>'
            '</label>'
            '<input type="file" id="img-input" accept="image/*" style="display:none" onchange="wyslijZdjecie(this)">'
            '<input type="text" class="conv-input" id="msg-input" placeholder="Napisz wiadomość..." onkeydown="if(event.key===\'Enter\')wyslijWiad()">'
            '<button class="conv-send-btn" onclick="wyslijWiad()">'
            '<svg viewBox="0 0 24 24"><path fill="white" d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>'
            '</button></div></div>'
            '<script>'
            'const rozmowca="' + rozmowca + '";'
            'let lastId=' + str(last_id) + ';'
            'let currentMsgId=null;'
            'const msgs=document.getElementById("msgs");'
            'msgs.scrollTop=msgs.scrollHeight;'
            'function wyslijWiad(){const inp=document.getElementById("msg-input");if(!inp.value.trim())return;const txt=inp.value;inp.value="";'
            'fetch("/wyslij_wiad",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({do:rozmowca,tresc:txt})})'
            '.then(r=>r.json()).then(d=>{msgs.insertAdjacentHTML("beforeend","<div class=\'msg-bubble sent\' id=\'msg-"+d.id+"\'><span>"+d.tresc+"</span><div class=\'msg-time\'>"+d.czas+"</div></div>");msgs.scrollTop=msgs.scrollHeight;lastId=Math.max(lastId,d.id);});}'
            'function wyslijZdjecie(inp){if(!inp.files[0])return;const fd=new FormData();fd.append("zdjecie",inp.files[0]);fd.append("do",rozmowca);'
            'fetch("/wyslij_zdjecie",{method:"POST",body:fd}).then(r=>r.json()).then(d=>{msgs.insertAdjacentHTML("beforeend","<div class=\'msg-bubble sent\'><img src=\'/chat_img/"+d.nazwa+"\'><div class=\'msg-time\'>"+d.czas+"</div></div>");msgs.scrollTop=msgs.scrollHeight;});}'
            'function pokazPicker(id){currentMsgId=id;document.getElementById("picker").classList.add("open");}'
            'document.addEventListener("click",function(e){if(!e.target.closest(".reakcja-picker")&&!e.target.closest(".msg-reakcja"))document.getElementById("picker").classList.remove("open");});'
            'function dajReakcje(id,emoji){fetch("/reakcja/"+id,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reakcja:emoji})}).then(r=>r.json()).then(()=>{const el=document.getElementById("msg-"+id);if(el){let r=el.querySelector(".msg-reakcja");if(r)r.textContent=emoji;else el.insertAdjacentHTML("beforeend","<span class=\'msg-reakcja left\'>"+emoji+"</span>");}document.getElementById("picker").classList.remove("open");});}'
            'function pollChat(){fetch("/poll_chat/"+rozmowca+"?od="+lastId).then(r=>r.json()).then(d=>{const typing=d.pisze;let tInd=document.getElementById("typing-ind");'
            'if(typing&&!tInd){msgs.insertAdjacentHTML("beforeend","<div id=\'typing-ind\' class=\'msg-bubble received\' style=\'padding:10px 16px;\'><span class=\'typing-dots\'><span></span><span></span><span></span></span></div>");msgs.scrollTop=msgs.scrollHeight;}'
            'else if(!typing&&tInd)tInd.remove();'
            'd.wiad.forEach(w=>{if(!document.getElementById("msg-"+w.id)){let t=w.typ==="zdjecie"?"<img src=\'/chat_img/"+w.tresc+"\' style=\'max-width:200px;border-radius:12px;\'>":w.tresc;'
            'msgs.insertAdjacentHTML("beforeend","<div class=\'msg-bubble received\' id=\'msg-"+w.id+"\'><span>"+t+"</span><div class=\'msg-time\'>"+w.data.slice(11,16)+"</div><span class=\'msg-reakcja left\' onclick=\'pokazPicker("+w.id+")\'>＋</span></div>");'
            'msgs.scrollTop=msgs.scrollHeight;lastId=Math.max(lastId,w.id);}});});}'
            'setInterval(pollChat,2000);'
            'document.getElementById("msg-input").addEventListener("input",function(){fetch("/pisze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({do:rozmowca,pisze:this.value.length>0});});});'
            '</script></body></html>')

@app.route("/wyslij_wiad", methods=["POST"])
def wyslij_wiad():
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    data = request.get_json()
    do = data.get('do')
    tresc = data.get('tresc', '').strip()
    if not tresc or not do:
        return jsonify({}), 400
    conn = get_db()
    if not czy_moze_pisac(session['uzytkownik'], do, conn):
        conn.close()
        return jsonify({}), 403
    cur = conn.execute("INSERT INTO wiadomosci (od, do, tresc, typ) VALUES (?,?,?,'tekst')",
                       (session['uzytkownik'], do, tresc))
    conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?,?,'wiadomosc',0)", (do, session['uzytkownik']))
    conn.execute("INSERT OR REPLACE INTO ustawienia VALUES (?,?)", ('pisze_' + session['uzytkownik'] + '_do_' + do, '0'))
    conn.commit()
    wid = cur.lastrowid
    czas = conn.execute("SELECT data FROM wiadomosci WHERE id=?", (wid,)).fetchone()['data'][11:16]
    conn.close()
    return jsonify({'id': wid, 'tresc': tresc, 'czas': czas})

@app.route("/wyslij_zdjecie", methods=["POST"])
def wyslij_zdjecie():
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    do = request.form.get('do')
    plik = request.files.get('zdjecie')
    if not plik or not do:
        return jsonify({}), 400
    conn = get_db()
    if not czy_moze_pisac(session['uzytkownik'], do, conn):
        conn.close()
        return jsonify({}), 403
    img = Image.open(plik)
    img = img.convert('RGB')
    img.thumbnail((800, 800))
    nazwa = session['uzytkownik'] + '_' + str(random.randint(10000, 99999)) + '.jpg'
    img.save(os.path.join(CHAT_FOLDER, nazwa), 'JPEG')
    cur = conn.execute("INSERT INTO wiadomosci (od, do, tresc, typ) VALUES (?,?,?,'zdjecie')",
                       (session['uzytkownik'], do, nazwa))
    conn.commit()
    wid = cur.lastrowid
    czas = conn.execute("SELECT data FROM wiadomosci WHERE id=?", (wid,)).fetchone()['data'][11:16]
    conn.close()
    return jsonify({'nazwa': nazwa, 'czas': czas, 'id': wid})

@app.route("/chat_img/<nazwa>")
def chat_img(nazwa):
    return send_from_directory(CHAT_FOLDER, nazwa)

@app.route("/reakcja/<int:wid>", methods=["POST"])
def reakcja(wid):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    data = request.get_json()
    em = data.get('reakcja', '')
    conn = get_db()
    conn.execute("UPDATE wiadomosci SET reakcja=? WHERE id=?", (em, wid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route("/poll_chat/<rozmowca>")
def poll_chat(rozmowca):
    if 'uzytkownik' not in session:
        return jsonify({'wiad': [], 'pisze': False})
    conn = get_db()
    uzytkownik = session['uzytkownik']
    ostatni = request.args.get('od', 0, type=int)
    wiad = conn.execute("SELECT * FROM wiadomosci WHERE od=? AND do=? AND id>? ORDER BY data ASC",
                        (rozmowca, uzytkownik, ostatni)).fetchall()
    conn.execute("UPDATE wiadomosci SET przeczytana=1 WHERE od=? AND do=?", (rozmowca, uzytkownik))
    klucz = 'pisze_' + rozmowca + '_do_' + uzytkownik
    val = conn.execute("SELECT wartosc FROM ustawienia WHERE klucz=?", (klucz,)).fetchone()
    pisze = val and val['wartosc'] == '1'
    conn.commit()
    conn.close()
    return jsonify({'wiad': [dict(w) for w in wiad], 'pisze': pisze})

@app.route("/pisze", methods=["POST"])
def pisze():
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    data = request.get_json()
    do = data.get('do')
    czy = data.get('pisze', False)
    conn = get_db()
    klucz = 'pisze_' + session['uzytkownik'] + '_do_' + do
    conn.execute("INSERT OR REPLACE INTO ustawienia VALUES (?,?)", (klucz, '1' if czy else '0'))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route("/profil/<nazwa>")
def profil(nazwa):
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    user = conn.execute("SELECT * FROM uzytkownicy WHERE nazwa=?", (nazwa,)).fetchone()
    if not user:
        conn.close()
        return ('<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
                + STYLE + '</head><body>' + top_nav_html(session['uzytkownik'])
                + '<p style="color:white;text-align:center;padding:40px;">Użytkownik nie istnieje</p>'
                + bottom_nav_html('profil', session['uzytkownik']) + '</body></html>')
    filmy = conn.execute("SELECT * FROM filmy WHERE autor=? ORDER BY data DESC", (nazwa,)).fetchall()
    reposty_raw = conn.execute(
        "SELECT f.* FROM filmy f JOIN reposty r ON f.id=r.film_id WHERE r.uzytkownik=? ORDER BY r.data DESC",
        (nazwa,)).fetchall()
    ile_lajkow = conn.execute(
        "SELECT COUNT(*) as c FROM lajki WHERE film_id IN (SELECT id FROM filmy WHERE autor=?)",
        (nazwa,)).fetchone()['c']
    obserwujacych = conn.execute("SELECT COUNT(*) as c FROM obserwowania WHERE obserwowany=?", (nazwa,)).fetchone()['c']
    obserwuje = conn.execute("SELECT 1 FROM obserwowania WHERE obserwujacy=? AND obserwowany=?",
                             (session['uzytkownik'], nazwa)).fetchone()
    conn.close()
    jest_swoj = session['uzytkownik'] == nazwa

    def grid_item(film, is_repost=False):
        fid = str(film['id'])
        if jest_swoj and not is_repost:
            usun = ('<button class="grid-delete" onclick="usunSwojFilm(event,' + fid + ')">'
                    '<svg viewBox="0 0 24 24"><path fill="#fe2c55" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg></button>')
        else:
            usun = ''
        badge = '<span class="repost-badge">RP</span>' if is_repost else ''
        return ('<a href="/ogladaj/' + fid + '" class="profile-grid-item" id="film-' + fid + '">'
                '<video preload="metadata" muted><source src="' + film['url'] + '"></video>'
                + usun + badge +
                '<div class="grid-overlay"><p class="grid-title">' + film['tytul'] + '</p></div></a>')

    filmy_html = "".join(grid_item(f) for f in filmy)
    reposty_html = "".join(grid_item(f, True) for f in reposty_raw)

    if jest_swoj:
        follow_btn = '<a href="/edytuj_profil"><button class="edit-btn">Edytuj profil</button></a>'
    else:
        obs_class = "follow-btn following" if obserwuje else "follow-btn"
        obs_text = "Obserwujesz" if obserwuje else "Obserwuj"
        follow_btn = ('<button class="' + obs_class + '" id="follow-btn" onclick="toggleObserwuj(\'' + nazwa + '\')">' + obs_text + '</button>'
                      + '<a href="/chat/' + nazwa + '" class="msg-btn"><svg width="16" height="16" viewBox="0 0 24 24"><path fill="white" d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>Napisz</a>')

    aktywna_nav = 'profil' if jest_swoj else ''
    return ('<!DOCTYPE html><html><head><title>@' + nazwa + ' - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + top_nav_html(session['uzytkownik']) +
            '<div class="profile-page"><div class="profile-header"><div class="profile-top">'
            + avatar_html(nazwa, 'lg') +
            '<div><p class="profile-name">@' + nazwa + '</p>'
            '<p class="profile-bio">' + (user['bio'] or 'Brak opisu') + '</p>'
            '<div class="profile-stats">'
            '<div class="stat"><p class="stat-num">' + str(len(filmy)) + '</p><p class="stat-label">filmów</p></div>'
            '<div class="stat"><p class="stat-num">' + str(ile_lajkow) + '</p><p class="stat-label">lajków</p></div>'
            '<div class="stat"><p class="stat-num" id="obserwujacych-count">' + str(obserwujacych) + '</p><p class="stat-label">obserwujących</p></div>'
            '</div>' + follow_btn + '</div></div></div>'
            '<div class="profile-tabs">'
            '<div class="profile-tab active" onclick="pokazTab(\'filmy\',this)">Filmy</div>'
            '<div class="profile-tab" onclick="pokazTab(\'reposty\',this)">Reposty</div>'
            '</div>'
            '<div id="tab-filmy" class="profile-grid">'
            + (filmy_html or '<p style="color:#555;text-align:center;padding:40px;grid-column:1/-1;">Brak filmów</p>') +
            '</div><div id="tab-reposty" class="profile-grid" style="display:none;">'
            + (reposty_html or '<p style="color:#555;text-align:center;padding:40px;grid-column:1/-1;">Brak repostów</p>') +
            '</div></div>'
            + bottom_nav_html(aktywna_nav, session['uzytkownik']) +
            '<script>'
            'function pokazTab(tab,el){document.getElementById("tab-filmy").style.display=tab==="filmy"?"grid":"none";document.getElementById("tab-reposty").style.display=tab==="reposty"?"grid":"none";document.querySelectorAll(".profile-tab").forEach(t=>t.classList.remove("active"));el.classList.add("active");}'
            'function toggleObserwuj(nazwa){fetch("/obserwuj/"+nazwa,{method:"POST"}).then(r=>r.json()).then(d=>{const btn=document.getElementById("follow-btn");btn.textContent=d.obserwuje?"Obserwujesz":"Obserwuj";btn.className="follow-btn"+(d.obserwuje?" following":"");document.getElementById("obserwujacych-count").textContent=d.obserwujacych;});}'
            'function usunSwojFilm(e,fid){e.stopPropagation();e.preventDefault();if(!confirm("Usunąć ten film?"))return;fetch("/usun_film/"+fid,{method:"POST"}).then(r=>r.json()).then(d=>{if(d.ok)document.getElementById("film-"+fid).remove();});}'
            '</script></body></html>')

@app.route("/szukaj")
def szukaj():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    query = request.args.get('q', '').strip()
    uzytkownicy_html = filmy_html = ""
    if query:
        conn = get_db()
        uzytkownicy = conn.execute("SELECT * FROM uzytkownicy WHERE nazwa LIKE ? LIMIT 10", ('%' + query + '%',)).fetchall()
        filmy = conn.execute("SELECT * FROM filmy WHERE tytul LIKE ? OR autor LIKE ? ORDER BY data DESC LIMIT 20",
                             ('%' + query + '%', '%' + query + '%')).fetchall()
        conn.close()
        for u in uzytkownicy:
            uzytkownicy_html += ('<a href="/profil/' + u['nazwa'] + '" class="user-row">' + avatar_html(u['nazwa'], 'sm') +
                '<div class="user-info"><p class="user-name">@' + u['nazwa'] + '</p><p class="user-bio">' + (u['bio'] or 'Brak opisu') + '</p></div></a>')
        for film in filmy:
            filmy_html += ('<a href="/ogladaj/' + str(film['id']) + '" class="video-row">'
                '<div class="video-thumb"><svg width="24" height="24" viewBox="0 0 24 24"><path fill="#fe2c55" d="M8 5v14l11-7z"/></svg></div>'
                '<div><p class="video-row-title">' + film['tytul'] + '</p><p class="video-row-author">@' + film['autor'] + '</p></div></a>')
    wyniki = ""
    if query:
        if uzytkownicy_html: wyniki += '<h3>Użytkownicy</h3>' + uzytkownicy_html
        if filmy_html: wyniki += '<h3>Filmy</h3>' + filmy_html
        if not wyniki: wyniki = '<p style="color:#555;text-align:center;padding:40px;">Brak wyników</p>'
    else:
        wyniki = '<p style="color:#555;text-align:center;padding:40px;">Wpisz czego szukasz</p>'
    return ('<!DOCTYPE html><html><head><title>Szukaj - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + top_nav_html(session['uzytkownik']) +
            '<div class="search-page"><div class="search-box"><form method="GET" action="/szukaj"><div class="search-input-wrap">'
            '<input type="text" name="q" class="search-input" placeholder="Szukaj..." value="' + query + '" autofocus>'
            '<button type="submit" class="search-btn"><svg width="20" height="20" viewBox="0 0 24 24"><path fill="white" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg></button>'
            '</div></form></div><div class="search-section">' + wyniki + '</div></div>'
            + bottom_nav_html('', session['uzytkownik']) + '</body></html>')

@app.route("/film/<int:film_id>")
def film_bezposredni(film_id):
    return redirect(url_for('filmy_page'))

@app.route("/obserwuj/<nazwa>", methods=["POST"])
def obserwuj(nazwa):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    if nazwa == session['uzytkownik']:
        return jsonify({}), 400
    conn = get_db()
    czy = conn.execute("SELECT 1 FROM obserwowania WHERE obserwujacy=? AND obserwowany=?", (session['uzytkownik'], nazwa)).fetchone()
    if czy:
        conn.execute("DELETE FROM obserwowania WHERE obserwujacy=? AND obserwowany=?", (session['uzytkownik'], nazwa))
        obserwuje = False
    else:
        conn.execute("INSERT INTO obserwowania (obserwujacy, obserwowany) VALUES (?,?)", (session['uzytkownik'], nazwa))
        conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?,?,'obserwowanie',0)", (nazwa, session['uzytkownik']))
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
    notifs = conn.execute("SELECT * FROM powiadomienia WHERE dla=? ORDER BY data DESC LIMIT 50", (session['uzytkownik'],)).fetchall()
    conn.execute("UPDATE powiadomienia SET przeczytane=1 WHERE dla=?", (session['uzytkownik'],))
    conn.commit()
    conn.close()
    notifs_html = ""
    for n in notifs:
        if n['typ'] == 'lajk': tekst = '<b>@' + n['od'] + '</b> polubił Twoje wideo'
        elif n['typ'] == 'komentarz': tekst = '<b>@' + n['od'] + '</b> skomentował Twoje wideo'
        elif n['typ'] == 'obserwowanie': tekst = '<b>@' + n['od'] + '</b> zaczął Cię obserwować'
        elif n['typ'] == 'wiadomosc': tekst = '<b>@' + n['od'] + '</b> wysłał Ci wiadomość'
        elif n['typ'] == 'prosba_chat': tekst = '<b>@' + n['od'] + '</b> chce Ci wysłać wiadomość'
        elif n['typ'] == 'chat_zaakceptowany': tekst = '<b>@' + n['od'] + '</b> zaakceptował Twoją prośbę'
        else: tekst = '<b>@' + n['od'] + '</b> zareagował'
        notifs_html += ('<div class="notif-item ' + ('unread' if not n['przeczytane'] else '') + '">'
            + avatar_html(n['od'], 'sm') +
            '<div><p class="notif-text">' + tekst + '</p><p class="notif-time">' + n['data'][:16] + '</p></div></div>')
    return ('<!DOCTYPE html><html><head><title>Powiadomienia - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + top_nav_html(session['uzytkownik']) +
            '<div class="notif-page"><div class="notif-list"><h2>Powiadomienia</h2>'
            + (notifs_html or '<p style="color:#555;text-align:center;padding:40px;">Brak powiadomień</p>')
            + '</div></div>'
            + bottom_nav_html('', session['uzytkownik']) + '</body></html>')

@app.route("/upload_page")
def upload_page():
    return redirect(url_for('dodaj_page'))

@app.route("/upload", methods=["POST"])
def upload():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    if not wgrywanie_aktywne() or filmy_w_tym_miesiacu(session['uzytkownik']) >= LIMIT_FILMOW_MIESIECZNIE:
        return redirect(url_for('strona_glowna'))
    plik = request.files["wideo"]
    tytul = request.form["tytul"]
    plik.seek(0, 2)
    if plik.tell() > 50 * 1024 * 1024:
        return "<h1 style='color:white;text-align:center;padding:40px;'>Plik za duży! Max 50MB.</h1>"
    plik.seek(0)
    wynik = cloudinary.uploader.upload(plik, resource_type="video", folder="olivovid")
    conn = get_db()
    conn.execute("INSERT INTO filmy (cloudinary_id, url, tytul, autor) VALUES (?,?,?,?)",
                 (wynik['public_id'], wynik['secure_url'], tytul, session['uzytkownik']))
    conn.commit()
    conn.close()
    return redirect(url_for('strona_glowna'))

@app.route("/usun_film/<int:film_id>", methods=["POST"])
def usun_film_uzytkownik(film_id):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    conn = get_db()
    film = conn.execute("SELECT * FROM filmy WHERE id=? AND autor=?", (film_id, session['uzytkownik'])).fetchone()
    if not film:
        conn.close()
        return jsonify({}), 403
    if film['cloudinary_id']:
        try: cloudinary.uploader.destroy(film['cloudinary_id'], resource_type="video")
        except: pass
    conn.execute("DELETE FROM filmy WHERE id=?", (film_id,))
    conn.execute("DELETE FROM lajki WHERE film_id=?", (film_id,))
    conn.execute("DELETE FROM komentarze WHERE film_id=?", (film_id,))
    conn.execute("DELETE FROM reposty WHERE film_id=?", (film_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

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
        filmy_html += ('<div class="film-row"><div><p style="font-weight:700;">' + film['tytul'] + '</p>'
            '<p style="color:#888;font-size:13px;">@' + film['autor'] + ' • ' + film['data'][:10] + '</p></div>'
            '<button class="delete-btn" onclick="usunFilm(' + str(film['id']) + ')">Usuń</button></div>')
    return ('<!DOCTYPE html><html><head><title>Admin - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + top_nav_html(session['uzytkownik']) +
            '<div class="admin-page"><div class="admin-panel"><h2>Panel Admina</h2>'
            '<div class="admin-card"><h3>Wgrywanie filmów</h3>'
            '<button class="toggle-btn ' + ('toggle-on' if aktywne else 'toggle-off') + '" onclick="toggleWgrywanie()" id="toggleBtn">'
            + ('Włączone' if aktywne else 'Wyłączone') + '</button></div>'
            '<div class="admin-card"><h3>Wszystkie filmy (' + str(len(filmy)) + ')</h3>'
            + (filmy_html or '<p style="color:#555;">Brak filmów</p>') + '</div></div></div>'
            + bottom_nav_html('', session['uzytkownik']) +
            '<script>'
            'function toggleWgrywanie(){fetch("/admin/toggle_wgrywanie",{method:"POST"}).then(r=>r.json()).then(d=>{const b=document.getElementById("toggleBtn");b.textContent=d.aktywne?"Włączone":"Wyłączone";b.className="toggle-btn "+(d.aktywne?"toggle-on":"toggle-off");});}'
            'function usunFilm(fid){if(!confirm("Usunąć ten film?"))return;fetch("/admin/usun_film/"+fid,{method:"POST"}).then(r=>r.json()).then(d=>{if(d.ok)location.reload();});}'
            '</script></body></html>')

@app.route("/admin/toggle_wgrywanie", methods=["POST"])
def toggle_wgrywanie():
    if not is_admin():
        return jsonify({}), 403
    conn = get_db()
    aktywne = wgrywanie_aktywne()
    conn.execute("UPDATE ustawienia SET wartosc=? WHERE klucz='wgrywanie_aktywne'", ('0' if aktywne else '1',))
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
        try: cloudinary.uploader.destroy(film['cloudinary_id'], resource_type="video")
        except: pass
    conn.execute("DELETE FROM filmy WHERE id=?", (film_id,))
    conn.execute("DELETE FROM lajki WHERE film_id=?", (film_id,))
    conn.execute("DELETE FROM komentarze WHERE film_id=?", (film_id,))
    conn.execute("DELETE FROM reposty WHERE film_id=?", (film_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route("/lajkuj/<int:film_id>", methods=["POST"])
def lajkuj(film_id):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    conn = get_db()
    czy = conn.execute("SELECT 1 FROM lajki WHERE film_id=? AND uzytkownik=?", (film_id, session['uzytkownik'])).fetchone()
    if czy:
        conn.execute("DELETE FROM lajki WHERE film_id=? AND uzytkownik=?", (film_id, session['uzytkownik']))
        lajkuje = False
    else:
        conn.execute("INSERT INTO lajki (film_id, uzytkownik) VALUES (?,?)", (film_id, session['uzytkownik']))
        lajkuje = True
        film = conn.execute("SELECT autor FROM filmy WHERE id=?", (film_id,)).fetchone()
        if film and film['autor'] != session['uzytkownik']:
            conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?,?,'lajk',?)",
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
    czy = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?", (kom_id, session['uzytkownik'])).fetchone()
    if czy:
        conn.execute("DELETE FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?", (kom_id, session['uzytkownik']))
        lajkuje = False
    else:
        conn.execute("INSERT INTO lajki_komentarzy (komentarz_id, uzytkownik) VALUES (?,?)", (kom_id, session['uzytkownik']))
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
    cur = conn.execute("INSERT INTO komentarze (film_id, uzytkownik, tresc, odpowiedz_na) VALUES (?,?,?,?)",
                       (film_id, session['uzytkownik'], tresc, odpowiedz_na))
    conn.commit()
    kom_id = cur.lastrowid
    film = conn.execute("SELECT autor FROM filmy WHERE id=?", (film_id,)).fetchone()
    if film and film['autor'] != session['uzytkownik']:
        conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?,?,'komentarz',?)",
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
            img.save(os.path.join(AVATAR_FOLDER, session['uzytkownik'] + ".jpg"), "JPEG")
        conn.execute("UPDATE uzytkownicy SET bio=? WHERE nazwa=?", (bio, session['uzytkownik']))
        conn.commit()
        conn.close()
        return redirect(url_for('profil', nazwa=session['uzytkownik']))
    user = conn.execute("SELECT * FROM uzytkownicy WHERE nazwa=?", (session['uzytkownik'],)).fetchone()
    conn.close()
    return ('<!DOCTYPE html><html><head><title>Edytuj profil - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + top_nav_html(session['uzytkownik']) +
            '<div class="upload-page"><div style="max-width:500px;margin:20px auto;padding:0 16px;">'
            '<div class="edit-form"><h2>Edytuj profil</h2><form method="POST" enctype="multipart/form-data">'
            '<label>Zdjęcie profilowe</label><br><br>' + avatar_html(session['uzytkownik'], 'lg') +
            '<br><br><input type="file" name="avatar" accept="image/*" style="color:white;margin-bottom:14px;">'
            '<label>Bio (max 150 znaków)</label>'
            '<textarea name="bio" placeholder="Napisz coś o sobie...">' + (user['bio'] or '') + '</textarea>'
            '<button type="submit" class="save-btn">Zapisz</button>'
            '</form></div></div></div>'
            + bottom_nav_html('profil', session['uzytkownik']) + '</body></html>')

@app.route("/avatar/<nazwa>")
def avatar(nazwa):
    return send_from_directory(AVATAR_FOLDER, nazwa + ".jpg")

@app.route("/setup_admin/<klucz>/<nazwa>")
def setup_admin(klucz, nazwa):
    if klucz != "olivovid_tajny_klucz_2026":
        return "Błędny klucz", 403
    conn = get_db()
    conn.execute("UPDATE uzytkownicy SET is_admin=1 WHERE nazwa=?", (nazwa,))
    conn.commit()
    conn.close()
    return "Konto " + nazwa + " jest teraz adminem!"

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
    err_html = "<p class='error'>" + error + "</p>" if error else ""
    return ('<!DOCTYPE html><html><head><title>OlivoVid - Logowanie</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body><div class="center"><div class="card">'
            '<div style="text-align:center;margin-bottom:8px;" class="logo">Olivo<span>Vid</span></div>'
            '<h2>Zaloguj się</h2><form method="POST">'
            '<input type="text" name="nazwa" placeholder="Nazwa użytkownika" required>'
            '<input type="password" name="haslo" placeholder="Hasło" required>'
            + err_html + '<button type="submit" class="btn">Zaloguj się</button></form><hr class="divider">'
            '<p class="sub">Nie masz konta? <a href="/rejestracja" class="link">Zarejestruj się</a></p>'
            '</div></div></body></html>')

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
                conn.execute("INSERT INTO uzytkownicy (nazwa, haslo) VALUES (?,?)", (nazwa, haslo))
                conn.commit()
                conn.close()
                session['uzytkownik'] = nazwa
                return redirect(url_for('strona_glowna'))
            except:
                conn.close()
                error = "Ta nazwa użytkownika jest zajęta!"
    err_html = "<p class='error'>" + error + "</p>" if error else ""
    return ('<!DOCTYPE html><html><head><title>OlivoVid - Rejestracja</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body><div class="center"><div class="card">'
            '<div style="text-align:center;margin-bottom:8px;" class="logo">Olivo<span>Vid</span></div>'
            '<h2>Utwórz konto</h2><form method="POST">'
            '<input type="text" name="nazwa" placeholder="Nazwa użytkownika" required>'
            '<input type="password" name="haslo" placeholder="Hasło" required>'
            + err_html + '<button type="submit" class="btn">Zarejestruj się</button></form><hr class="divider">'
            '<p class="sub">Masz już konto? <a href="/logowanie" class="link">Zaloguj się</a></p>'
            '</div></div></body></html>')

@app.route("/wyloguj")
def wyloguj():
    session.pop('uzytkownik', None)
    return redirect(url_for('logowanie'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)