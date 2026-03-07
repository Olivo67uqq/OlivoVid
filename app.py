from flask import Flask, request, send_from_directory, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sqlite3

app = Flask(__name__)
app.secret_key = "olivovid_secret_123"
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect('baza.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS uzytkownicy
                 (id INTEGER PRIMARY KEY, nazwa TEXT UNIQUE, haslo TEXT)''')
    conn.commit()
    conn.close()

init_db()

STYLE = '''
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; }
    .logo { font-size: 28px; font-weight: 900; color: white; letter-spacing: -1px; }
    .logo span { color: #fe2c55; }
    .card { background: #111; border: 1px solid #222; border-radius: 16px; padding: 40px; width: 100%; max-width: 380px; margin: 0 auto; }
    .center { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
    input { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 14px 16px; border-radius: 10px; font-size: 15px; margin: 6px 0; outline: none; transition: border 0.2s; }
    input:focus { border-color: #fe2c55; }
    input::placeholder { color: #666; }
    .btn { width: 100%; background: #fe2c55; color: white; border: none; padding: 14px; border-radius: 10px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 12px; transition: background 0.2s; }
    .btn:hover { background: #d4244a; }
    .link { color: #fe2c55; text-decoration: none; font-weight: 600; }
    .link:hover { text-decoration: underline; }
    p { color: #888; font-size: 14px; margin-top: 20px; }
    .error { color: #fe2c55; font-size: 14px; margin: 8px 0; text-align: center; }
    .divider { border: none; border-top: 1px solid #222; margin: 20px 0; }
    .nav { background: #111; border-bottom: 1px solid #222; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
    .nav-right { display: flex; align-items: center; gap: 16px; }
    .nav-user { color: #aaa; font-size: 14px; }
    .nav-user b { color: white; }
    .logout { color: #fe2c55; text-decoration: none; font-size: 14px; font-weight: 600; }
    .upload-box { background: #111; border: 2px dashed #333; border-radius: 16px; padding: 30px; max-width: 400px; margin: 30px auto; text-align: center; transition: border 0.2s; }
    .upload-box:hover { border-color: #fe2c55; }
    .upload-btn { background: #fe2c55; color: white; border: none; padding: 12px 28px; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; margin-top: 12px; transition: background 0.2s; }
    .upload-btn:hover { background: #d4244a; }
    .upload-label { color: #888; font-size: 14px; margin-top: 8px; }
    .video-grid { max-width: 420px; margin: 0 auto; padding: 0 16px 40px; }
    .video-card { background: #111; border: 1px solid #222; border-radius: 16px; padding: 16px; margin: 16px 0; }
    .video-card video { width: 100%; border-radius: 10px; }
    .video-name { color: #aaa; font-size: 13px; margin-top: 10px; }
    .file-input { display: none; }
    .file-label { display: inline-block; background: #222; color: #aaa; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-bottom: 8px; border: 1px solid #333; }
    .file-label:hover { background: #2a2a2a; }
    h2 { color: white; font-size: 22px; font-weight: 700; margin: 12px 0 20px; }
    .main-content { padding-top: 20px; }
</style>
'''

@app.route("/")
def strona_glowna():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    filmy = os.listdir(UPLOAD_FOLDER)
    filmy_html = ""
    for film in filmy:
        filmy_html += f'''
        <div class="video-card">
            <video controls>
                <source src="/wideo/{film}">
            </video>
            <p class="video-name">🎵 {film}</p>
        </div>
        '''
    return f'''
    <!DOCTYPE html>
    <html>
    <head><title>OlivoVid</title>{STYLE}</head>
    <body>
        <div class="nav">
            <div class="logo">Olivo<span>Vid</span></div>
            <div class="nav-right">
                <span class="nav-user">Cześć, <b>{session['uzytkownik']}</b></span>
                <a href="/wyloguj" class="logout">Wyloguj</a>
            </div>
        </div>
        <div class="main-content">
            <div class="upload-box">
                <form method="POST" action="/upload" enctype="multipart/form-data" id="uploadForm">
                    <label for="fileInput" class="file-label">📁 Wybierz wideo</label>
                    <input type="file" name="wideo" accept="video/*" class="file-input" id="fileInput"
                           onchange="document.getElementById('fileName').textContent = this.files[0].name">
                    <p class="upload-label" id="fileName">Nie wybrano pliku</p>
                    <button type="submit" class="upload-btn">⬆️ Wgraj wideo</button>
                </form>
            </div>
            <div class="video-grid">
                {filmy_html}
            </div>
        </div>
    </body>
    </html>
    '''

@app.route("/logowanie", methods=["GET", "POST"])
def logowanie():
    error = ""
    if request.method == "POST":
        nazwa = request.form["nazwa"]
        haslo = request.form["haslo"]
        conn = sqlite3.connect('baza.db')
        c = conn.cursor()
        c.execute("SELECT haslo FROM uzytkownicy WHERE nazwa=?", (nazwa,))
        wynik = c.fetchone()
        conn.close()
        if wynik and check_password_hash(wynik[0], haslo):
            session['uzytkownik'] = nazwa
            return redirect(url_for('strona_glowna'))
        error = "Błędny login lub hasło!"
    return f'''
    <!DOCTYPE html>
    <html>
    <head><title>OlivoVid - Logowanie</title>{STYLE}</head>
    <body>
        <div class="center">
            <div class="card">
                <div style="text-align:center; margin-bottom:8px;" class="logo">Olivo<span>Vid</span></div>
                <h2 style="text-align:center;">Zaloguj się</h2>
                <form method="POST">
                    <input type="text" name="nazwa" placeholder="Nazwa użytkownika" required>
                    <input type="password" name="haslo" placeholder="Hasło" required>
                    {"<p class='error'>"+error+"</p>" if error else ""}
                    <button type="submit" class="btn">Zaloguj się</button>
                </form>
                <hr class="divider">
                <p style="text-align:center;">Nie masz konta? <a href="/rejestracja" class="link">Zarejestruj się</a></p>
            </div>
        </div>
    </body>
    </html>
    '''

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
            conn = sqlite3.connect('baza.db')
            c = conn.cursor()
            try:
                c.execute("INSERT INTO uzytkownicy (nazwa, haslo) VALUES (?, ?)", (nazwa, haslo))
                conn.commit()
                conn.close()
                session['uzytkownik'] = nazwa
                return redirect(url_for('strona_glowna'))
            except:
                conn.close()
                error = "Ta nazwa użytkownika jest zajęta!"
    return f'''
    <!DOCTYPE html>
    <html>
    <head><title>OlivoVid - Rejestracja</title>{STYLE}</head>
    <body>
        <div class="center">
            <div class="card">
                <div style="text-align:center; margin-bottom:8px;" class="logo">Olivo<span>Vid</span></div>
                <h2 style="text-align:center;">Utwórz konto</h2>
                <form method="POST">
                    <input type="text" name="nazwa" placeholder="Nazwa użytkownika" required>
                    <input type="password" name="haslo" placeholder="Hasło" required>
                    {"<p class='error'>"+error+"</p>" if error else ""}
                    <button type="submit" class="btn">Zarejestruj się</button>
                </form>
                <hr class="divider">
                <p style="text-align:center;">Masz już konto? <a href="/logowanie" class="link">Zaloguj się</a></p>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route("/wyloguj")
def wyloguj():
    session.pop('uzytkownik', None)
    return redirect(url_for('logowanie'))

@app.route("/upload", methods=["POST"])
def upload():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    plik = request.files["wideo"]
    plik.save(os.path.join(UPLOAD_FOLDER, plik.filename))
    return redirect(url_for('strona_glowna'))

@app.route("/wideo/<nazwa>")
def wideo(nazwa):
    return send_from_directory(UPLOAD_FOLDER, nazwa)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)