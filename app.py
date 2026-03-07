from flask import Flask, request, send_from_directory, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sqlite3

app = Flask(__name__)
app.secret_key = "olivovid_secret_123"
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    conn = sqlite3.connect('baza.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS uzytkownicy
                 (id INTEGER PRIMARY KEY, nazwa TEXT UNIQUE, haslo TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS filmy
                 (id INTEGER PRIMARY KEY, nazwa_pliku TEXT, tytul TEXT,
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
    conn.commit()
    conn.close()

init_db()

STYLE = '''
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; color: white; }
    .logo { font-size: 28px; font-weight: 900; color: white; letter-spacing: -1px; }
    .logo span { color: #fe2c55; }
    .card { background: #111; border: 1px solid #222; border-radius: 16px; padding: 40px; width: 100%; max-width: 380px; margin: 0 auto; }
    .center { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
    input[type=text], input[type=password] { width: 100%; background: #222; border: 1px solid #333; color: white; padding: 14px 16px; border-radius: 10px; font-size: 15px; margin: 6px 0; outline: none; transition: border 0.2s; }
    input:focus { border-color: #fe2c55; }
    input::placeholder { color: #666; }
    .btn { width: 100%; background: #fe2c55; color: white; border: none; padding: 14px; border-radius: 10px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 12px; transition: background 0.2s; }
    .btn:hover { background: #d4244a; }
    .link { color: #fe2c55; text-decoration: none; font-weight: 600; }
    p.sub { color: #888; font-size: 14px; margin-top: 20px; }
    .error { color: #fe2c55; font-size: 14px; margin: 8px 0; text-align: center; }
    .divider { border: none; border-top: 1px solid #222; margin: 20px 0; }
    .nav { background: #111; border-bottom: 1px solid #222; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
    .nav-right { display: flex; align-items: center; gap: 16px; }
    .nav-user { color: #aaa; font-size: 14px; }
    .nav-user b { color: white; }
    .logout { color: #fe2c55; text-decoration: none; font-size: 14px; font-weight: 600; }
    .upload-box { background: #111; border: 2px dashed #333; border-radius: 16px; padding: 30px; max-width: 500px; margin: 30px auto; text-align: center; }
    .upload-box input[type=text] { margin-bottom: 10px; }
    .upload-btn { background: #fe2c55; color: white; border: none; padding: 12px 28px; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; margin-top: 12px; }
    .upload-btn:hover { background: #d4244a; }
    .file-input { display: none; }
    .file-label { display: inline-block; background: #222; color: #aaa; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-bottom: 8px; border: 1px solid #333; }
    .video-grid { max-width: 500px; margin: 0 auto; padding: 0 16px 40px; }
    .video-card { background: #111; border: 1px solid #222; border-radius: 16px; padding: 16px; margin: 20px 0; }
    .video-card video { width: 100%; border-radius: 10px; }
    .video-title { font-size: 17px; font-weight: 700; margin: 12px 0 4px; }
    .video-author { color: #888; font-size: 13px; margin-bottom: 12px; }
    .actions { display: flex; gap: 12px; margin: 12px 0; }
    .like-btn { background: none; border: 1px solid #333; color: #aaa; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-size: 14px; display: flex; align-items: center; gap: 6px; transition: all 0.2s; }
    .like-btn:hover { border-color: #fe2c55; color: #fe2c55; }
    .like-btn.liked { background: #fe2c5522; border-color: #fe2c55; color: #fe2c55; }
    .comments-section { margin-top: 16px; border-top: 1px solid #222; padding-top: 16px; }
    .comment { background: #1a1a1a; border-radius: 10px; padding: 10px 14px; margin: 8px 0; }
    .comment.reply { margin-left: 24px; background: #161616; border-left: 2px solid #333; }
    .comment-author { font-size: 13px; font-weight: 700; color: #fe2c55; }
    .comment-text { font-size: 14px; color: #ddd; margin: 4px 0; }
    .comment-actions { display: flex; gap: 12px; margin-top: 6px; }
    .comment-btn { background: none; border: none; color: #666; font-size: 12px; cursor: pointer; padding: 0; }
    .comment-btn:hover { color: #fe2c55; }
    .comment-btn.liked { color: #fe2c55; }
    .comment-form { display: flex; gap: 8px; margin-top: 12px; }
    .comment-form input { flex: 1; background: #222; border: 1px solid #333; color: white; padding: 10px 14px; border-radius: 8px; font-size: 14px; outline: none; }
    .comment-form input:focus { border-color: #fe2c55; }
    .comment-form button { background: #fe2c55; color: white; border: none; padding: 10px 16px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 700; }
    .reply-form { display: none; margin-top: 8px; }
    .reply-form.active { display: flex; gap: 8px; }
    .reply-form input { flex: 1; background: #222; border: 1px solid #333; color: white; padding: 8px 12px; border-radius: 8px; font-size: 13px; outline: none; }
    .reply-form button { background: #333; color: white; border: none; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; }
    h2 { color: white; font-size: 22px; font-weight: 700; margin: 12px 0 20px; text-align: center; }
</style>
'''

@app.route("/")
def strona_glowna():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    conn = get_db()
    filmy = conn.execute("SELECT * FROM filmy ORDER BY data DESC").fetchall()
    filmy_html = ""
    for film in filmy:
        lajki = conn.execute("SELECT COUNT(*) as c FROM lajki WHERE film_id=?", (film['id'],)).fetchone()['c']
        czy_lajk = conn.execute("SELECT 1 FROM lajki WHERE film_id=? AND uzytkownik=?",
                                (film['id'], session['uzytkownik'])).fetchone()
        komentarze = conn.execute(
            "SELECT * FROM komentarze WHERE film_id=? AND odpowiedz_na IS NULL ORDER BY data ASC",
            (film['id'],)).fetchall()
        komentarze_html = ""
        for kom in komentarze:
            lk = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (kom['id'],)).fetchone()['c']
            czy_lk = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?",
                                  (kom['id'], session['uzytkownik'])).fetchone()
            odpowiedzi = conn.execute(
                "SELECT * FROM komentarze WHERE odpowiedz_na=? ORDER BY data ASC", (kom['id'],)).fetchall()
            odp_html = ""
            for odp in odpowiedzi:
                lok = conn.execute("SELECT COUNT(*) as c FROM lajki_komentarzy WHERE komentarz_id=?", (odp['id'],)).fetchone()['c']
                czy_lok = conn.execute("SELECT 1 FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?",
                                       (odp['id'], session['uzytkownik'])).fetchone()
                odp_html += f'''
                <div class="comment reply">
                    <span class="comment-author">@{odp['uzytkownik']}</span>
                    <p class="comment-text">{odp['tresc']}</p>
                    <div class="comment-actions">
                        <button class="comment-btn {'liked' if czy_lok else ''}"
                                onclick="lajkujKomentarz({odp['id']}, this)">
                            ❤️ {lok}
                        </button>
                    </div>
                </div>'''
            komentarze_html += f'''
            <div class="comment" id="kom-{kom['id']}">
                <span class="comment-author">@{kom['uzytkownik']}</span>
                <p class="comment-text">{kom['tresc']}</p>
                <div class="comment-actions">
                    <button class="comment-btn {'liked' if czy_lk else ''}"
                            onclick="lajkujKomentarz({kom['id']}, this)">
                        ❤️ {lk}
                    </button>
                    <button class="comment-btn" onclick="pokazOdpowiedz({kom['id']})">
                        💬 Odpowiedz
                    </button>
                </div>
                <div class="reply-form" id="reply-{kom['id']}">
                    <input type="text" placeholder="Napisz odpowiedź..." id="reply-input-{kom['id']}">
                    <button onclick="wyslijOdpowiedz({film['id']}, {kom['id']})">Wyślij</button>
                </div>
                {odp_html}
            </div>'''
        filmy_html += f'''
        <div class="video-card">
            <video controls><source src="/wideo/{film['nazwa_pliku']}"></video>
            <p class="video-title">{film['tytul']}</p>
            <p class="video-author">@{film['autor']}</p>
            <div class="actions">
                <button class="like-btn {'liked' if czy_lajk else ''}" id="like-{film['id']}"
                        onclick="lajkuj({film['id']}, this)">
                    ❤️ <span>{lajki}</span>
                </button>
            </div>
            <div class="comments-section">
                <div id="komentarze-{film['id']}">{komentarze_html}</div>
                <div class="comment-form">
                    <input type="text" placeholder="Dodaj komentarz..." id="kom-input-{film['id']}">
                    <button onclick="wyslijKomentarz({film['id']})">Wyślij</button>
                </div>
            </div>
        </div>'''
    conn.close()
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
        <div class="upload-box">
            <form method="POST" action="/upload" enctype="multipart/form-data">
                <input type="text" name="tytul" placeholder="Tytuł wideo" required>
                <label for="fileInput" class="file-label">📁 Wybierz wideo</label>
                <input type="file" name="wideo" accept="video/*" class="file-input" id="fileInput"
                       onchange="document.getElementById('fileName').textContent = this.files[0].name">
                <p style="color:#666; font-size:13px;" id="fileName">Nie wybrano pliku</p>
                <button type="submit" class="upload-btn">⬆️ Wgraj wideo</button>
            </form>
        </div>
        <div class="video-grid">{filmy_html}</div>
        <script>
        function lajkuj(filmId, btn) {{
            fetch('/lajkuj/' + filmId, {{method: 'POST'}})
            .then(r => r.json())
            .then(d => {{
                btn.querySelector('span').textContent = d.lajki;
                btn.classList.toggle('liked', d.lajkuje);
            }});
        }}
        function lajkujKomentarz(komId, btn) {{
            fetch('/lajkuj_komentarz/' + komId, {{method: 'POST'}})
            .then(r => r.json())
            .then(d => {{
                btn.textContent = '❤️ ' + d.lajki;
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
                const div = document.getElementById('komentarze-' + filmId);
                div.insertAdjacentHTML('beforeend', `
                    <div class="comment">
                        <span class="comment-author">@${{d.uzytkownik}}</span>
                        <p class="comment-text">${{d.tresc}}</p>
                        <div class="comment-actions">
                            <button class="comment-btn" onclick="lajkujKomentarz(${{d.id}}, this)">❤️ 0</button>
                            <button class="comment-btn" onclick="pokazOdpowiedz(${{d.id}})">💬 Odpowiedz</button>
                        </div>
                        <div class="reply-form" id="reply-${{d.id}}">
                            <input type="text" placeholder="Napisz odpowiedź..." id="reply-input-${{d.id}}">
                            <button onclick="wyslijOdpowiedz(${{filmId}}, ${{d.id}})">Wyślij</button>
                        </div>
                    </div>`);
                input.value = '';
            }});
        }}
        function pokazOdpowiedz(komId) {{
            const form = document.getElementById('reply-' + komId);
            form.classList.toggle('active');
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
                const kom = document.getElementById('kom-' + komId);
                kom.insertAdjacentHTML('beforeend', `
                    <div class="comment reply">
                        <span class="comment-author">@${{d.uzytkownik}}</span>
                        <p class="comment-text">${{d.tresc}}</p>
                        <div class="comment-actions">
                            <button class="comment-btn" onclick="lajkujKomentarz(${{d.id}}, this)">❤️ 0</button>
                        </div>
                    </div>`);
                input.value = '';
                document.getElementById('reply-' + komId).classList.remove('active');
            }});
        }}
        </script>
    </body>
    </html>
    '''

@app.route("/upload", methods=["POST"])
def upload():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    plik = request.files["wideo"]
    tytul = request.form["tytul"]
    plik.save(os.path.join(UPLOAD_FOLDER, plik.filename))
    conn = get_db()
    conn.execute("INSERT INTO filmy (nazwa_pliku, tytul, autor) VALUES (?, ?, ?)",
                 (plik.filename, tytul, session['uzytkownik']))
    conn.commit()
    conn.close()
    return redirect(url_for('strona_glowna'))

@app.route("/lajkuj/<int:film_id>", methods=["POST"])
def lajkuj(film_id):
    if 'uzytkownik' not in session:
        return jsonify({}), 401
    conn = get_db()
    czy = conn.execute("SELECT 1 FROM lajki WHERE film_id=? AND uzytkownik=?",
                       (film_id, session['uzytkownik'])).fetchone()
    if czy:
        conn.execute("DELETE FROM lajki WHERE film_id=? AND uzytkownik=?",
                     (film_id, session['uzytkownik']))
        lajkuje = False
    else:
        conn.execute("INSERT INTO lajki (film_id, uzytkownik) VALUES (?, ?)",
                     (film_id, session['uzytkownik']))
        lajkuje = True
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
        conn.execute("DELETE FROM lajki_komentarzy WHERE komentarz_id=? AND uzytkownik=?",
                     (kom_id, session['uzytkownik']))
        lajkuje = False
    else:
        conn.execute("INSERT INTO lajki_komentarzy (komentarz_id, uzytkownik) VALUES (?, ?)",
                     (kom_id, session['uzytkownik']))
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
    cur = conn.execute(
        "INSERT INTO komentarze (film_id, uzytkownik, tresc, odpowiedz_na) VALUES (?, ?, ?, ?)",
        (film_id, session['uzytkownik'], tresc, odpowiedz_na))
    conn.commit()
    kom_id = cur.lastrowid
    conn.close()
    return jsonify({'id': kom_id, 'uzytkownik': session['uzytkownik'], 'tresc': tresc})

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
    return f'''
    <!DOCTYPE html>
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
                <p class="sub" style="text-align:center;">Nie masz konta? <a href="/rejestracja" class="link">Zarejestruj się</a></p>
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
    return f'''
    <!DOCTYPE html>
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
                <p class="sub" style="text-align:center;">Masz już konto? <a href="/logowanie" class="link">Zaloguj się</a></p>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route("/wyloguj")
def wyloguj():
    session.pop('uzytkownik', None)
    return redirect(url_for('logowanie'))

@app.route("/wideo/<nazwa>")
def wideo(nazwa):
    return send_from_directory(UPLOAD_FOLDER, nazwa)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)