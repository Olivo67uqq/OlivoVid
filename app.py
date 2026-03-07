from flask import Flask, request, send_from_directory
import os

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/")
def strona_glowna():
    filmy = os.listdir(UPLOAD_FOLDER)
    filmy_html = ""
    for film in filmy:
        filmy_html += f'''
        <div style="background:#111; border-radius:12px; padding:16px; margin:20px auto; max-width:340px;">
            <video style="width:100%; border-radius:8px;" controls>
                <source src="/wideo/{film}">
            </video>
            <p style="color:white; margin-top:8px;">🎵 {film}</p>
        </div>
        '''
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Mini-TikTok</title>
        <style>
            body {{ background: #000; font-family: Arial; text-align: center; }}
            h1 {{ color: white; padding: 20px; }}
            input[type=file] {{ color: white; margin: 10px; }}
            button {{ background: #fe2c55; color: white; border: none;
                     padding: 10px 24px; border-radius: 6px;
                     font-size: 16px; cursor: pointer; }}
            button:hover {{ background: #d4244a; }}
        </style>
    </head>
    <body>
        <h1>🎵 Mini-TikTok</h1>
        <form method="POST" action="/upload" enctype="multipart/form-data">
            <input type="file" name="wideo" accept="video/*"><br>
            <button type="submit">⬆️ Wgraj wideo</button>
        </form>
        <hr style="border-color:#333; margin:30px;">
        {filmy_html}
    </body>
    </html>
    '''

@app.route("/upload", methods=["POST"])
def upload():
    plik = request.files["wideo"]
    plik.save(os.path.join(UPLOAD_FOLDER, plik.filename))
    return '''
    <!DOCTYPE html>
    <html>
    <head><style>body{{background:#000; text-align:center; font-family:Arial;}}</style></head>
    <body>
        <h1 style="color:white; padding:40px;">Wideo wgrane! ✅</h1>
        <a href="/" style="color:#fe2c55; font-size:18px;">⬅️ Wróć</a>
    </body>
    </html>
    '''

@app.route("/wideo/<nazwa>")
def wideo(nazwa):
    return send_from_directory(UPLOAD_FOLDER, nazwa)

if __name__ == "__main__":
    app.run(debug=True)