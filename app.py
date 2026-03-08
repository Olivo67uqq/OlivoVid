from flask import Flask, request, send_from_directory, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os
import sqlite3
import random

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
    c.execute('''CREATE TABLE IF NOT EXISTS reposty
                 (id INTEGER PRIMARY KEY, film_id INTEGER, uzytkownik TEXT,
                  data TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(film_id, uzytkownik))''')
    conn.commit()
    for col in [("bio", "TEXT DEFAULT ''"), ("avatar", "TEXT DEFAULT ''"), ("is_admin", "INTEGER DEFAULT 0")]:
        try:
            conn.execute("ALTER TABLE uzytkownicy ADD COLUMN " + col[0] + " " + col[1])
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
    n = conn.execute("SELECT COUNT(*) as c FROM powiadomienia WHERE dla=? AND przeczytane=0",
                     (uzytkownik,)).fetchone()['c']
    conn.close()
    return n

def avatar_html(nazwa, size="sm"):
    path = os.path.join(AVATAR_FOLDER, nazwa + ".jpg")
    if os.path.exists(path):
        return '<img src="/avatar/' + nazwa + '" class="avatar-' + size + '" alt="' + nazwa + '">'
    return '<div class="avatar-' + size + '-placeholder">' + nazwa[0].upper() + '</div>'

def nav_html(uzytkownik):
    if is_admin():
        admin_link = '<a href="/admin" class="nav-icon-btn"><svg viewBox="0 0 24 24"><path fill="white" d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/></svg></a>'
    else:
        admin_link = ''
    n = ile_powiadomien(uzytkownik)
    notif_badge = '<span class="notif-badge">' + str(n) + '</span>' if n > 0 else ''
    return '''<div class="nav">
        <a href="/" style="text-decoration:none;" class="logo">Olivo<span>Vid</span></a>
        <div class="nav-right">
            <a href="/szukaj" class="nav-icon-btn"><svg viewBox="0 0 24 24"><path fill="white" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg></a>
            <a href="/powiadomienia" class="nav-icon-btn" style="position:relative;"><svg viewBox="0 0 24 24"><path fill="white" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>''' + notif_badge + '''</a>
            <a href="/upload_page" class="nav-icon-btn"><svg viewBox="0 0 24 24"><path fill="white" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg></a>
            <a href="/profil/''' + uzytkownik + '''" class="nav-link">''' + avatar_html(uzytkownik, "sm") + ''' <span class="nav-username">''' + uzytkownik + '''</span></a>
            <a href="/wyloguj" class="nav-icon-btn"><svg viewBox="0 0 24 24"><path fill="white" d="M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z"/></svg></a>
            ''' + admin_link + '''
        </div>
    </div>'''

STYLE = '''<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #000; font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: white; overflow: hidden; }
    .logo { font-size: 22px; font-weight: 900; color: white; letter-spacing: -1px; }
    .logo span { color: #fe2c55; }
    .nav { padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; position: fixed; top: 0; left: 0; right: 0; z-index: 100; background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent); }
    .nav-right { display: flex; align-items: center; gap: 6px; }
    .nav-link { color: white; text-decoration: none; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
    .nav-username { display: none; }
    @media(min-width:500px){ .nav-username { display: inline; } }
    .nav-icon-btn { display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: 50%; background: rgba(255,255,255,0.1); color: white; text-decoration: none; position: relative; }
    .nav-icon-btn svg { width: 22px; height: 22px; }
    .nav-icon-btn:active { background: rgba(255,255,255,0.2); }
    .notif-badge { position: absolute; top: 4px; right: 4px; background: #fe2c55; color: white; font-size: 9px; font-weight: 700; width: 14px; height: 14px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
    .avatar-sm { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; border: 2px solid #fe2c55; }
    .avatar-sm-placeholder { width: 32px; height: 32px; border-radius: 50%; background: #333; border: 2px solid #fe2c55; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; color: #fe2c55; flex-shrink: 0; }
    .feed { height: 100vh; overflow-y: scroll; scroll-snap-type: y mandatory; scrollbar-width: none; }
    .feed::-webkit-scrollbar { display: none; }
    .video-slide { height: 100vh; scroll-snap-align: start; position: relative; display: flex; align-items: center; justify-content: center; background: #000; }
    .video-slide video { height: 100vh; width: 100%; object-fit: contain; cursor: pointer; }
    .repost-label { position: absolute; top: 64px; left: 16px; display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.5); padding: 5px 10px; border-radius: 20px; font-size: 12px; color: #aaa; }
    .repost-label svg { width: 14px; height: 14px; }
    .repost-label a { color: #fe2c55; text-decoration: none; font-weight: 700; }
    .video-overlay { position: absolute; bottom: 100px; left: 16px; right: 90px; pointer-events: none; }
    .video-overlay-author { font-size: 16px; font-weight: 700; color: white; text-shadow: 0 1px 4px rgba(0,0,0,0.9); }
    .video-overlay-title { font-size: 14px; color: rgba(255,255,255,0.9); margin-top: 5px; text-shadow: 0 1px 4px rgba(0,0,0,0.9); }
    .video-side-actions { position: absolute; right: 10px; bottom: 100px; display: flex; flex-direction: column; align-items: center; gap: 24px; }
    .side-btn { display: flex; flex-direction: column; align-items: center; gap: 5px; cursor: pointer; background: none; border: none; color: white; padding: 4px; }
    .side-count { font-size: 13px; color: white; text-shadow: 0 1px 3px rgba(0,0,0,0.9); font-weight: 700; }
    .icon-heart { width: 48px; height: 48px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8)); transition: transform 0.15s; }
    .icon-comment { width: 46px; height: 46px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }
    .icon-share { width: 42px; height: 42px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }
    .icon-repost { width: 42px; height: 42px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8)); transition: transform 0.15s; }
    .side-btn:active .icon-heart { transform: scale(1.3); }
    .side-btn:active .icon-repost { transform: scale(1.2); }
    .pause-indicator { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); opacity: 0; transition: opacity 0.2s; pointer-events: none; background: rgba(0,0,0,0.4); border-radius: 50%; padding: 16px; }
    .pause-indicator svg { width: 56px; height: 56px; }
    .pause-indicator.show { opacity: 1; }
    .overlay-avatar { pointer-events: all; }
    .avatar-overlay-sm { width: 44px; height: 44px; border-radius: 50%; object-fit: cover; border: 2px solid white; }
    .avatar-overlay-sm-placeholder { width: 44px; height: 44px; border-radius: 50%; background: #333; border: 2px solid white; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700; color: white; }
    .comments-panel { display: none; position: fixed; bottom: 0; left: 0; right: 0; height: 65vh; background: #111; border-radius: 20px 20px 0 0; z-index: 200; padding: 16px 16px 0; }
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
    .share-panel { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #111; border-radius: 20px 20px 0 0; z-index: 200; padding: 16px; }
    .share-panel.open { display: block; }
    .share-link { background: #222; border-radius: 10px; padding: 14px 16px; font-size: 13px; color: #aaa; word-break: break-all; margin-bottom: 12px; }
    .share-copy-btn { width: 100%; background: #fe2c55; color: white; border: none; padding: 14px; border-radius: 12px; font-size: 15px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; }
    .overlay-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 199; }
    .overlay-backdrop.open { display: block; }
    .search-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
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
    .profile-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
    .profile-header { max-width: 600px; margin: 16px auto; padding: 0 16px; }
    .profile-top { display: flex; align-items: center; gap: 20px; margin-bottom: 16px; }
    .avatar-lg { width: 76px; height: 76px; border-radius: 50%; object-fit: cover; border: 3px solid #fe2c55; }
    .avatar-lg-placeholder { width: 76px; height: 76px; border-radius: 50%; background: #222; border: 3px solid #fe2c55; display: flex; align-items: center; justify-content: center; font-size: 26px; font-weight: 700; color: #fe2c55; flex-shrink: 0; }
    .profile-name { font-size: 20px; font-weight: 700; }
    .profile-bio { color: #aaa; font-size: 13px; margin-top: 5px; line-height: 1.4; }
    .profile-stats { display: flex; gap: 20px; margin-top: 10px; }
    .stat { text-align: center; }
    .stat-num { font-size: 17px; font-weight: 700; }
    .stat-label { font-size: 11px; color: #aaa; }
    .edit-btn { background: #222; color: white; border: 1px solid #444; padding: 9px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 10px; margin-right: 8px; }
    .follow-btn { background: #fe2c55; color: white; border: none; padding: 9px 22px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 10px; font-weight: 700; }
    .follow-btn.following { background: #333; color: white; border: 1px solid #555; }
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
    .upload-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
    .upload-box { background: #111; border: 2px dashed #333; border-radius: 16px; padding: 24px; max-width: 500px; margin: 24px auto; text-align: center; }
    .upload-box input[type=text] { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 14px 16px; border-radius: 12px; font-size: 15px; margin-bottom: 12px; outline: none; }
    .file-input { display: none; }
    .file-label { display: inline-flex; align-items: center; gap: 8px; background: #222; color: #aaa; padding: 12px 22px; border-radius: 12px; cursor: pointer; font-size: 14px; margin-bottom: 8px; border: 1px solid #333; }
    .upload-btn { background: #fe2c55; color: white; border: none; padding: 14px 32px; border-radius: 12px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 10px; width: 100%; }
    .upload-btn:disabled { background: #555; cursor: not-allowed; }
    .limit-info { color: #888; font-size: 13px; margin-top: 10px; }
    .limit-warn { color: #fe2c55; font-size: 14px; }
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
    .notif-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
    .notif-list { max-width: 600px; margin: 20px auto; padding: 0 16px 40px; }
    .notif-item { background: #111; border-radius: 12px; padding: 14px 16px; margin: 10px 0; display: flex; align-items: center; gap: 12px; }
    .notif-item.unread { border-left: 3px solid #fe2c55; }
    .notif-text { font-size: 14px; color: #ddd; line-height: 1.4; }
    .notif-text b { color: #fe2c55; }
    .notif-time { font-size: 12px; color: #555; margin-top: 4px; }
    .admin-page { height: 100vh; overflow-y: auto; padding-top: 70px; }
    .admin-panel { max-width: 600px; margin: 20px auto; padding: 0 16px 40px; }
    .admin-card { background: #111; border: 1px solid #222; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
    .admin-card h3 { font-size: 16px; margin-bottom: 12px; color: #aaa; }
    .toggle-btn { padding: 12px 24px; border-radius: 10px; border: none; cursor: pointer; font-size: 14px; font-weight: 700; }
    .toggle-on { background: #fe2c55; color: white; }
    .toggle-off { background: #333; color: #aaa; }
    .film-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #222; }
    .film-row:last-child { border-bottom: none; }
    .delete-btn { background: #1a1a1a; color: #fe2c55; border: 1px solid #fe2c55; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; }
    .toast { position: fixed; bottom: 90px; left: 50%; transform: translateX(-50%); background: rgba(50,50,50,0.95); color: white; padding: 12px 24px; border-radius: 24px; font-size: 14px; font-weight: 600; z-index: 999; opacity: 0; transition: opacity 0.3s; pointer-events: none; white-space: nowrap; }
    .toast.show { opacity: 1; }
    .empty { text-align: center; padding: 60px 20px; color: #444; font-size: 18px; line-height: 1.6; }
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

def build_feed(conn):
    filmy = conn.execute("SELECT * FROM filmy").fetchall()
    if not filmy:
        return []
    repost_film_ids = set(r['film_id'] for r in conn.execute("SELECT film_id FROM reposty").fetchall())
    pool = []
    for film in filmy:
        waga = 4 if film['id'] in repost_film_ids else 3
        pool.extend([dict(film)] * waga)
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
        "SELECT * FROM komentarze WHERE film_id=? AND odpowiedz_na IS NULL ORDER BY data ASC",
        (film_id,)).fetchall()
    html = ""
    for kom in komentarze:
        lk = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (kom['id'],)).fetchone()['c']
        czy_lk = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?", (kom['id'], uzytkownik)).fetchone()
        odpowiedzi = conn.execute("SELECT * FROM komentarze WHERE odpowiedz_na=? ORDER BY data ASC", (kom['id'],)).fetchall()
        odp_html = ""
        for odp in odpowiedzi:
            lok = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (odp['id'],)).fetchone()['c']
            czy_lok = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?", (odp['id'], uzytkownik)).fetchone()
            lk_fill = "#fe2c55" if czy_lok else "#666"
            odp_html += ('<div class="comment reply">'
                '<a href="/profil/' + odp['uzytkownik'] + '" class="comment-author">@' + odp['uzytkownik'] + '</a>'
                '<p class="comment-text">' + odp['tresc'] + '</p>'
                '<div class="comment-actions">'
                '<button class="comment-like-btn ' + ('liked' if czy_lok else '') + '" onclick="lajkujKomentarz(' + str(odp['id']) + ', this)">'
                '<svg width="16" height="16" viewBox="0 0 24 24"><path fill="' + lk_fill + '" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>'
                ' ' + str(lok) + '</button></div></div>')
        kom_fill = "#fe2c55" if czy_lk else "#666"
        html += ('<div class="comment" id="kom-' + str(kom['id']) + '">'
            '<a href="/profil/' + kom['uzytkownik'] + '" class="comment-author">@' + kom['uzytkownik'] + '</a>'
            '<p class="comment-text">' + kom['tresc'] + '</p>'
            '<div class="comment-actions">'
            '<button class="comment-like-btn ' + ('liked' if czy_lk else '') + '" onclick="lajkujKomentarz(' + str(kom['id']) + ', this)">'
            '<svg width="16" height="16" viewBox="0 0 24 24"><path fill="' + kom_fill + '" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>'
            ' ' + str(lk) + '</button>'
            '<button class="reply-toggle" onclick="pokazOdpowiedz(' + str(kom['id']) + ')">Odpowiedz</button>'
            '</div>'
            '<div class="reply-form" id="reply-' + str(kom['id']) + '">'
            '<input type="text" placeholder="Odpowiedź..." id="reply-input-' + str(kom['id']) + '">'
            '<button onclick="wyslijOdpowiedz(' + str(film_id) + ', ' + str(kom['id']) + ')">Wyślij</button>'
            '</div>' + odp_html + '</div>')
    return html

@app.route("/")
def strona_glowna():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    uzytkownik = session['uzytkownik']
    filmy = build_feed(conn)
    filmy_html = ""
    for film in filmy:
        fid = film['id']
        lajki = conn.execute("SELECT COUNT(*) as c FROM lajki WHERE film_id=?", (fid,)).fetchone()['c']
        czy_lajk = conn.execute("SELECT 1 FROM lajki WHERE film_id=? AND uzytkownik=?", (fid, uzytkownik)).fetchone()
        ile_kom = conn.execute("SELECT COUNT(*) as c FROM komentarze WHERE film_id=?", (fid,)).fetchone()['c']
        ile_repostow = conn.execute("SELECT COUNT(*) as c FROM reposty WHERE film_id=?", (fid,)).fetchone()['c']
        czy_repost = conn.execute("SELECT 1 FROM reposty WHERE film_id=? AND uzytkownik=?", (fid, uzytkownik)).fetchone()
        repost_info = conn.execute(
            "SELECT r.uzytkownik FROM reposty r JOIN obserwowania o ON r.uzytkownik = o.obserwowany "
            "WHERE r.film_id=? AND o.obserwujacy=? AND r.uzytkownik != ? LIMIT 1",
            (fid, uzytkownik, film['autor'])).fetchone()
        komentarze_html = render_komentarze(conn, fid, uzytkownik)
        autor_avatar = avatar_html(film['autor'], 'overlay-sm')
        film_url = "https://olivovid.onrender.com/film/" + str(fid)
        repost_label = ""
        if repost_info:
            repost_label = ('<div class="repost-label">'
                '<svg viewBox="0 0 24 24"><path fill="#aaa" d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/></svg>'
                'Repost od <a href="/profil/' + repost_info['uzytkownik'] + '">@' + repost_info['uzytkownik'] + '</a>'
                '</div>')
        filmy_html += ('<div class="video-slide" id="slide-' + str(fid) + '">'
            '<video loop playsinline preload="metadata" id="video-' + str(fid) + '"><source src="' + film['url'] + '"></video>'
            '<div class="pause-indicator" id="pause-' + str(fid) + '"><svg viewBox="0 0 24 24"><path fill="white" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg></div>'
            + repost_label +
            '<div class="video-overlay">'
            '<a href="/profil/' + film['autor'] + '" class="overlay-avatar">' + autor_avatar + '</a>'
            '<p class="video-overlay-author">@' + film['autor'] + '</p>'
            '<p class="video-overlay-title">' + film['tytul'] + '</p>'
            '</div>'
            '<div class="video-side-actions">'
            '<button class="side-btn" id="like-' + str(fid) + '" onclick="lajkuj(' + str(fid) + ', this)">'
            + heart_svg(bool(czy_lajk)) +
            '<span class="side-count" id="like-count-' + str(fid) + '">' + str(lajki) + '</span></button>'
            '<button class="side-btn" onclick="toggleKomentarze(' + str(fid) + ')">'
            + comment_svg() +
            '<span class="side-count">' + str(ile_kom) + '</span></button>'
            '<button class="side-btn" id="repost-' + str(fid) + '" onclick="repostuj(' + str(fid) + ', this)">'
            + repost_svg(bool(czy_repost)) +
            '<span class="side-count" id="repost-count-' + str(fid) + '">' + str(ile_repostow) + '</span></button>'
            '<button class="side-btn" onclick="pokazUdostepnij(' + str(fid) + ')">' + share_svg() + '</button>'
            '</div>'
            '<div class="overlay-backdrop" id="backdrop-' + str(fid) + '" onclick="zamknijWszystko(' + str(fid) + ')"></div>'
            '<div class="comments-panel" id="panel-' + str(fid) + '">'
            '<div class="panel-handle"></div><p class="panel-title">Komentarze</p>'
            '<div class="comments-scroll" id="komentarze-' + str(fid) + '">' + komentarze_html + '</div>'
            '<div class="comment-form">'
            '<input type="text" placeholder="Dodaj komentarz..." id="kom-input-' + str(fid) + '">'
            '<button onclick="wyslijKomentarz(' + str(fid) + ')">Wyślij</button>'
            '</div></div>'
            '<div class="share-panel" id="share-' + str(fid) + '">'
            '<div class="panel-handle"></div><p class="panel-title">Udostępnij</p>'
            '<p class="share-link">' + film_url + '</p>'
            '<button class="share-copy-btn" onclick="kopiujLink(\'' + film_url + '\', ' + str(fid) + ')">'
            '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="white" d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>'
            'Kopiuj link</button></div></div>')
    conn.close()
    if not filmy_html:
        filmy_html = '<div class="video-slide"><p class="empty">Brak filmów<br>Wgraj pierwszy!</p></div>'
    js = '''<script>
    function pokazToast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000);}
    const slides=document.querySelectorAll('.video-slide');
    const observer=new IntersectionObserver((entries)=>{entries.forEach(e=>{const v=e.target.querySelector('video');if(!v)return;if(e.isIntersecting)v.play();else{v.pause();v.currentTime=0;}});},{threshold:0.7});
    slides.forEach(s=>observer.observe(s));
    slides.forEach(slide=>{
        const video=slide.querySelector('video');
        const id=slide.id.replace('slide-','');
        const indicator=document.getElementById('pause-'+id);
        if(video){video.addEventListener('click',function(e){
            if(e.target.closest('.video-side-actions')||e.target.closest('.video-overlay'))return;
            if(video.paused){video.play();indicator.classList.remove('show');}
            else{video.pause();indicator.classList.add('show');setTimeout(()=>indicator.classList.remove('show'),800);}
        });}
    });
    document.addEventListener('keydown',function(e){
        if(e.code==='Space'&&e.target.tagName!=='INPUT'){e.preventDefault();
            const visible=Array.from(slides).find(s=>{const r=s.getBoundingClientRect();return r.top>=-50&&r.top<=50;});
            if(visible){const video=visible.querySelector('video');const id=visible.id.replace('slide-','');const indicator=document.getElementById('pause-'+id);
                if(video.paused){video.play();indicator.classList.remove('show');}
                else{video.pause();indicator.classList.add('show');setTimeout(()=>indicator.classList.remove('show'),800);}
            }
        }
    });
    slides.forEach(slide=>{let lastTap=0;slide.addEventListener('touchend',function(e){
        if(e.target.closest('.video-side-actions')||e.target.closest('.comments-panel')||e.target.closest('.share-panel'))return;
        const now=Date.now();if(now-lastTap<300){const id=slide.id.replace('slide-','');lajkuj(parseInt(id),document.getElementById('like-'+id));}
        lastTap=now;
    });});
    function lajkuj(filmId,btn){fetch('/lajkuj/'+filmId,{method:'POST'}).then(r=>r.json()).then(d=>{document.getElementById('like-count-'+filmId).textContent=d.lajki;btn.querySelector('path').setAttribute('fill',d.lajkuje?'#fe2c55':'white');});}
    function repostuj(filmId,btn){fetch('/repostuj/'+filmId,{method:'POST'}).then(r=>r.json()).then(d=>{document.getElementById('repost-count-'+filmId).textContent=d.reposty;btn.querySelector('path').setAttribute('fill',d.repostuje?'#fe2c55':'white');pokazToast(d.repostuje?'Repostowano!':'Usunięto repost');});}
    function toggleKomentarze(filmId){document.getElementById('panel-'+filmId).classList.toggle('open');document.getElementById('backdrop-'+filmId).classList.toggle('open');}
    function pokazUdostepnij(filmId){document.getElementById('share-'+filmId).classList.add('open');document.getElementById('backdrop-'+filmId).classList.add('open');}
    function zamknijWszystko(filmId){document.getElementById('panel-'+filmId).classList.remove('open');document.getElementById('share-'+filmId).classList.remove('open');document.getElementById('backdrop-'+filmId).classList.remove('open');}
    function kopiujLink(url,filmId){navigator.clipboard.writeText(url).then(()=>pokazToast('Link skopiowany!'));zamknijWszystko(filmId);}
    function lajkujKomentarz(komId,btn){fetch('/lajkuj_komentarz/'+komId,{method:'POST'}).then(r=>r.json()).then(d=>{btn.querySelector('path').setAttribute('fill',d.lajkuje?'#fe2c55':'#666');btn.childNodes[2].textContent=' '+d.lajki;btn.classList.toggle('liked',d.lajkuje);});}
    function wyslijKomentarz(filmId){const input=document.getElementById('kom-input-'+filmId);if(!input.value.trim())return;
        fetch('/komentarz/'+filmId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tresc:input.value})}).then(r=>r.json()).then(d=>{
            document.getElementById('komentarze-'+filmId).insertAdjacentHTML('beforeend','<div class="comment" id="kom-'+d.id+'"><a href="/profil/'+d.uzytkownik+'" class="comment-author">@'+d.uzytkownik+'</a><p class="comment-text">'+d.tresc+'</p><div class="comment-actions"><button class="comment-like-btn" onclick="lajkujKomentarz('+d.id+', this)"><svg width="16" height="16" viewBox="0 0 24 24"><path fill="#666" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg> 0</button><button class="reply-toggle" onclick="pokazOdpowiedz('+d.id+')">Odpowiedz</button></div><div class="reply-form" id="reply-'+d.id+'"><input type="text" placeholder="Odpowiedź..." id="reply-input-'+d.id+'"><button onclick="wyslijOdpowiedz('+filmId+','+d.id+')">Wyślij</button></div></div>');
            input.value='';
        });
    }
    function pokazOdpowiedz(komId){document.getElementById('reply-'+komId).classList.toggle('active');}
    function wyslijOdpowiedz(filmId,komId){const input=document.getElementById('reply-input-'+komId);if(!input.value.trim())return;
        fetch('/komentarz/'+filmId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tresc:input.value,odpowiedz_na:komId})}).then(r=>r.json()).then(d=>{
            document.getElementById('kom-'+komId).insertAdjacentHTML('beforeend','<div class="comment reply"><a href="/profil/'+d.uzytkownik+'" class="comment-author">@'+d.uzytkownik+'</a><p class="comment-text">'+d.tresc+'</p></div>');
            input.value='';document.getElementById('reply-'+komId).classList.remove('active');
        });
    }
    </script>'''
    return ('<!DOCTYPE html><html><head><title>OlivoVid</title><meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + nav_html(uzytkownik) + '<div class="feed" id="feed">' + filmy_html + '</div>'
            + '<div class="toast" id="toast"></div>' + js + '</body></html>')

@app.route("/ogladaj/<int:film_id>")
def ogladaj(film_id):
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    film = conn.execute("SELECT * FROM filmy WHERE id=?", (film_id,)).fetchone()
    conn.close()
    if not film:
        return redirect(url_for('strona_glowna'))
    return redirect(url_for('strona_glowna') + '#slide-' + str(film_id))

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
        conn.execute("INSERT INTO reposty (film_id, uzytkownik) VALUES (?, ?)", (film_id, session['uzytkownik']))
        repostuje = True
    conn.commit()
    reposty = conn.execute("SELECT COUNT(*) as c FROM reposty WHERE film_id=?", (film_id,)).fetchone()['c']
    conn.close()
    return jsonify({'reposty': reposty, 'repostuje': repostuje})

@app.route("/profil/<nazwa>")
def profil(nazwa):
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    user = conn.execute("SELECT * FROM uzytkownicy WHERE nazwa=?", (nazwa,)).fetchone()
    if not user:
        conn.close()
        return ('<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
                + STYLE + '</head><body>' + nav_html(session['uzytkownik'])
                + '<p style="color:white;text-align:center;padding:40px;">Użytkownik nie istnieje</p></body></html>')
    filmy = conn.execute("SELECT * FROM filmy WHERE autor=? ORDER BY data DESC", (nazwa,)).fetchall()
    reposty_raw = conn.execute(
        "SELECT f.* FROM filmy f JOIN reposty r ON f.id = r.film_id WHERE r.uzytkownik=? ORDER BY r.data DESC",
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
        url = film['url']
        tytul = film['tytul']
        if jest_swoj and not is_repost:
            usun = ('<button class="grid-delete" onclick="usunSwojFilm(event,' + fid + ')">'
                    '<svg viewBox="0 0 24 24"><path fill="#fe2c55" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>'
                    '</button>')
        else:
            usun = ''
        badge = '<span class="repost-badge">RP</span>' if is_repost else ''
        return ('<a href="/ogladaj/' + fid + '" class="profile-grid-item" id="film-' + fid + '">'
                '<video preload="metadata" muted><source src="' + url + '"></video>'
                + usun + badge +
                '<div class="grid-overlay"><p class="grid-title">' + tytul + '</p></div>'
                '</a>')

    filmy_html = "".join(grid_item(f) for f in filmy)
    reposty_html = "".join(grid_item(f, True) for f in reposty_raw)

    if jest_swoj:
        follow_btn = '<a href="/edytuj_profil"><button class="edit-btn">Edytuj profil</button></a>'
    else:
        obs_class = "follow-btn following" if obserwuje else "follow-btn"
        obs_text = "Obserwujesz" if obserwuje else "Obserwuj"
        follow_btn = '<button class="' + obs_class + '" id="follow-btn" onclick="toggleObserwuj(\'' + nazwa + '\')">' + obs_text + '</button>'

    html = ('<!DOCTYPE html><html><head><title>@' + nazwa + ' - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + nav_html(session['uzytkownik']) +
            '<div class="profile-page">'
            '<div class="profile-header"><div class="profile-top">'
            + avatar_html(nazwa, 'lg') +
            '<div><p class="profile-name">@' + nazwa + '</p>'
            '<p class="profile-bio">' + (user['bio'] or 'Brak opisu') + '</p>'
            '<div class="profile-stats">'
            '<div class="stat"><p class="stat-num">' + str(len(filmy)) + '</p><p class="stat-label">filmów</p></div>'
            '<div class="stat"><p class="stat-num">' + str(ile_lajkow) + '</p><p class="stat-label">lajków</p></div>'
            '<div class="stat"><p class="stat-num" id="obserwujacych-count">' + str(obserwujacych) + '</p><p class="stat-label">obserwujących</p></div>'
            '</div>' + follow_btn + '</div></div></div>'
            '<div class="profile-tabs">'
            '<div class="profile-tab active" onclick="pokazTab(\'filmy\', this)">Filmy</div>'
            '<div class="profile-tab" onclick="pokazTab(\'reposty\', this)">Reposty</div>'
            '</div>'
            '<div id="tab-filmy" class="profile-grid">'
            + (filmy_html if filmy_html else '<p style="color:#555;text-align:center;padding:40px;grid-column:1/-1;">Brak filmów</p>') +
            '</div>'
            '<div id="tab-reposty" class="profile-grid" style="display:none;">'
            + (reposty_html if reposty_html else '<p style="color:#555;text-align:center;padding:40px;grid-column:1/-1;">Brak repostów</p>') +
            '</div></div>'
            '<script>'
            'function pokazTab(tab,el){document.getElementById("tab-filmy").style.display=tab==="filmy"?"grid":"none";document.getElementById("tab-reposty").style.display=tab==="reposty"?"grid":"none";document.querySelectorAll(".profile-tab").forEach(t=>t.classList.remove("active"));el.classList.add("active");}'
            'function toggleObserwuj(nazwa){fetch("/obserwuj/"+nazwa,{method:"POST"}).then(r=>r.json()).then(d=>{const btn=document.getElementById("follow-btn");btn.textContent=d.obserwuje?"Obserwujesz":"Obserwuj";btn.className="follow-btn"+(d.obserwuje?" following":"");document.getElementById("obserwujacych-count").textContent=d.obserwujacych;});}'
            'function usunSwojFilm(e,filmId){e.stopPropagation();e.preventDefault();if(!confirm("Usunąć ten film?"))return;fetch("/usun_film/"+filmId,{method:"POST"}).then(r=>r.json()).then(d=>{if(d.ok)document.getElementById("film-"+filmId).remove();});}'
            '</script></body></html>')
    return html

@app.route("/szukaj")
def szukaj():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    query = request.args.get('q', '').strip()
    uzytkownicy_html = ""
    filmy_html = ""
    if query:
        conn = get_db()
        uzytkownicy = conn.execute("SELECT * FROM uzytkownicy WHERE nazwa LIKE ? LIMIT 10", ('%' + query + '%',)).fetchall()
        filmy = conn.execute("SELECT * FROM filmy WHERE tytul LIKE ? OR autor LIKE ? ORDER BY data DESC LIMIT 20",
                             ('%' + query + '%', '%' + query + '%')).fetchall()
        conn.close()
        for u in uzytkownicy:
            uzytkownicy_html += ('<a href="/profil/' + u['nazwa'] + '" class="user-row">'
                + avatar_html(u['nazwa'], 'sm') +
                '<div class="user-info"><p class="user-name">@' + u['nazwa'] + '</p>'
                '<p class="user-bio">' + (u['bio'] or 'Brak opisu') + '</p></div></a>')
        for film in filmy:
            filmy_html += ('<a href="/ogladaj/' + str(film['id']) + '" class="video-row">'
                '<div class="video-thumb"><svg width="24" height="24" viewBox="0 0 24 24"><path fill="#fe2c55" d="M8 5v14l11-7z"/></svg></div>'
                '<div><p class="video-row-title">' + film['tytul'] + '</p>'
                '<p class="video-row-author">@' + film['autor'] + '</p></div></a>')
    wyniki = ""
    if query:
        if uzytkownicy_html: wyniki += '<h3>Użytkownicy</h3>' + uzytkownicy_html
        if filmy_html: wyniki += '<h3>Filmy</h3>' + filmy_html
        if not uzytkownicy_html and not filmy_html:
            wyniki = '<p style="color:#555;text-align:center;padding:40px;">Brak wyników dla "' + query + '"</p>'
    else:
        wyniki = '<p style="color:#555;text-align:center;padding:40px;">Wpisz czego szukasz</p>'
    return ('<!DOCTYPE html><html><head><title>Szukaj - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + nav_html(session['uzytkownik']) +
            '<div class="search-page"><div class="search-box">'
            '<form method="GET" action="/szukaj"><div class="search-input-wrap">'
            '<input type="text" name="q" class="search-input" placeholder="Szukaj..." value="' + query + '" autofocus>'
            '<button type="submit" class="search-btn">'
            '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="white" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>'
            '</button></div></form></div>'
            '<div class="search-section">' + wyniki + '</div></div></body></html>')

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
        conn.execute("DELETE FROM obserwowania WHERE obserwujacy=? AND obserwowany=?", (session['uzytkownik'], nazwa))
        obserwuje = False
    else:
        conn.execute("INSERT INTO obserwowania (obserwujacy, obserwowany) VALUES (?, ?)", (session['uzytkownik'], nazwa))
        conn.execute("INSERT INTO powiadomienia (dla, od, typ, film_id) VALUES (?, ?, 'obserwowanie', 0)", (nazwa, session['uzytkownik']))
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
        else: tekst = '<b>@' + n['od'] + '</b> zareagował'
        notifs_html += ('<div class="notif-item ' + ('unread' if not n['przeczytane'] else '') + '">'
            + avatar_html(n['od'], 'sm') +
            '<div><p class="notif-text">' + tekst + '</p>'
            '<p class="notif-time">' + n['data'][:16] + '</p></div></div>')
    return ('<!DOCTYPE html><html><head><title>Powiadomienia - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + nav_html(session['uzytkownik']) +
            '<div class="notif-page"><div class="notif-list"><h2>Powiadomienia</h2>'
            + (notifs_html if notifs_html else '<p style="color:#555;text-align:center;padding:40px;">Brak powiadomień</p>')
            + '</div></div></body></html>')

@app.route("/upload_page")
def upload_page():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    aktywne = wgrywanie_aktywne()
    fwm = filmy_w_tym_miesiacu(session['uzytkownik'])
    if not aktywne:
        upload_html = '<p class="limit-warn">Wgrywanie filmów jest tymczasowo wyłączone.</p>'
    elif fwm >= LIMIT_FILMOW_MIESIECZNIE:
        upload_html = '<p class="limit-warn">Osiągnąłeś limit ' + str(LIMIT_FILMOW_MIESIECZNIE) + ' filmów w tym miesiącu.</p>'
    else:
        pozostalo = LIMIT_FILMOW_MIESIECZNIE - fwm
        upload_html = ('<form method="POST" action="/upload" enctype="multipart/form-data" id="uploadForm">'
            '<input type="text" name="tytul" placeholder="Tytuł wideo" required><br>'
            '<label for="fileInput" class="file-label">'
            '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="#aaa" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>'
            'Wybierz wideo</label>'
            '<input type="file" name="wideo" accept="video/*" class="file-input" id="fileInput"'
            ' onchange="document.getElementById(\'fileName\').textContent=this.files[0].name">'
            '<p style="color:#555;font-size:13px;margin:8px 0;" id="fileName">Nie wybrano pliku</p>'
            '<button type="submit" class="upload-btn" id="uploadBtn">Wgraj wideo</button>'
            '<p class="limit-info">Pozostało: <b>' + str(pozostalo) + '</b> / ' + str(LIMIT_FILMOW_MIESIECZNIE) + ' filmów w tym miesiącu</p>'
            '</form>')
    return ('<!DOCTYPE html><html><head><title>Wgraj - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + nav_html(session['uzytkownik']) +
            '<div class="upload-page"><div class="upload-box"><h2>Wgraj wideo</h2>'
            + upload_html + '</div></div>'
            '<script>document.getElementById("uploadForm")&&document.getElementById("uploadForm").addEventListener("submit",function(){const btn=document.getElementById("uploadBtn");if(btn){btn.disabled=true;btn.textContent="Wgrywanie...";}});</script>'
            '</body></html>')

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
    if plik.tell() > 50 * 1024 * 1024:
        return "<h1 style='color:white;text-align:center;padding:40px;'>Plik za duży! Max 50MB.</h1>"
    plik.seek(0)
    wynik = cloudinary.uploader.upload(plik, resource_type="video", folder="olivovid")
    conn = get_db()
    conn.execute("INSERT INTO filmy (cloudinary_id, url, tytul, autor) VALUES (?, ?, ?, ?)",
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
        filmy_html += ('<div class="film-row"><div>'
            '<p style="font-weight:700;">' + film['tytul'] + '</p>'
            '<p style="color:#888;font-size:13px;">@' + film['autor'] + ' • ' + film['data'][:10] + '</p>'
            '</div><button class="delete-btn" onclick="usunFilm(' + str(film['id']) + ')">Usuń</button></div>')
    return ('<!DOCTYPE html><html><head><title>Admin - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + nav_html(session['uzytkownik']) +
            '<div class="admin-page"><div class="admin-panel"><h2>Panel Admina</h2>'
            '<div class="admin-card"><h3>Wgrywanie filmów</h3>'
            '<button class="toggle-btn ' + ('toggle-on' if aktywne else 'toggle-off') + '" onclick="toggleWgrywanie()" id="toggleBtn">'
            + ('Włączone' if aktywne else 'Wyłączone') + '</button></div>'
            '<div class="admin-card"><h3>Wszystkie filmy (' + str(len(filmy)) + ')</h3>'
            + (filmy_html if filmy_html else '<p style="color:#555;">Brak filmów</p>') +
            '</div></div></div>'
            '<script>'
            'function toggleWgrywanie(){fetch("/admin/toggle_wgrywanie",{method:"POST"}).then(r=>r.json()).then(d=>{const btn=document.getElementById("toggleBtn");btn.textContent=d.aktywne?"Włączone":"Wyłączone";btn.className="toggle-btn "+(d.aktywne?"toggle-on":"toggle-off");});}'
            'function usunFilm(filmId){if(!confirm("Usunąć ten film?"))return;fetch("/admin/usun_film/"+filmId,{method:"POST"}).then(r=>r.json()).then(d=>{if(d.ok)location.reload();});}'
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
    czy = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?", (kom_id, session['uzytkownik'])).fetchone()
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
            img.save(os.path.join(AVATAR_FOLDER, session['uzytkownik'] + ".jpg"), "JPEG")
        conn.execute("UPDATE uzytkownicy SET bio=? WHERE nazwa=?", (bio, session['uzytkownik']))
        conn.commit()
        conn.close()
        return redirect(url_for('profil', nazwa=session['uzytkownik']))
    user = conn.execute("SELECT * FROM uzytkownicy WHERE nazwa=?", (session['uzytkownik'],)).fetchone()
    conn.close()
    return ('<!DOCTYPE html><html><head><title>Edytuj profil - OlivoVid</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + STYLE + '</head><body>' + nav_html(session['uzytkownik']) +
            '<div class="upload-page"><div style="max-width:500px;margin:20px auto;padding:0 16px;">'
            '<div class="edit-form"><h2>Edytuj profil</h2>'
            '<form method="POST" enctype="multipart/form-data">'
            '<label>Zdjęcie profilowe</label><br><br>'
            + avatar_html(session['uzytkownik'], 'lg') +
            '<br><br><input type="file" name="avatar" accept="image/*" style="color:white;margin-bottom:14px;">'
            '<label>Bio (max 150 znaków)</label>'
            '<textarea name="bio" placeholder="Napisz coś o sobie...">' + (user['bio'] or '') + '</textarea>'
            '<button type="submit" class="save-btn">Zapisz</button>'
            '</form></div></div></div></body></html>')

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
            '<h2>Zaloguj się</h2>'
            '<form method="POST">'
            '<input type="text" name="nazwa" placeholder="Nazwa użytkownika" required>'
            '<input type="password" name="haslo" placeholder="Hasło" required>'
            + err_html +
            '<button type="submit" class="btn">Zaloguj się</button>'
            '</form><hr class="divider">'
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
                conn.execute("INSERT INTO uzytkownicy (nazwa, haslo) VALUES (?, ?)", (nazwa, haslo))
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
            '<h2>Utwórz konto</h2>'
            '<form method="POST">'
            '<input type="text" name="nazwa" placeholder="Nazwa użytkownika" required>'
            '<input type="password" name="haslo" placeholder="Hasło" required>'
            + err_html +
            '<button type="submit" class="btn">Zarejestruj się</button>'
            '</form><hr class="divider">'
            '<p class="sub">Masz już konto? <a href="/logowanie" class="link">Zaloguj się</a></p>'
            '</div></div></body></html>')

@app.route("/wyloguj")
def wyloguj():
    session.pop('uzytkownik', None)
    return redirect(url_for('logowanie'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)