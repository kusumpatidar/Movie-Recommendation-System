# ── app.py ────────────────────────────────────────────────────────────────────
from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, os

from movies import hybrid_recommend, search_titles

app = Flask(__name__)
app.secret_key = "secret123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "users.db")

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users
                    (id       INTEGER PRIMARY KEY AUTOINCREMENT,
                     username TEXT    UNIQUE NOT NULL,
                     email    TEXT,
                     password TEXT    NOT NULL)''')
    conn.commit()
    conn.close()

init_db()

# ── HOME ──────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')
    return render_template('index.html', username=session['user'])

# ── REGISTER ──────────────────────────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username,email,password) VALUES (?,?,?)",
                         (request.form['username'], request.form['email'],
                          request.form['password']))
            conn.commit()
            return redirect('/login')
        except sqlite3.IntegrityError:
            return render_template('register.html', error="Username already taken.")
        finally:
            conn.close()
    return render_template('register.html')

# ── LOGIN ─────────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (request.form['username'], request.form['password'])
        ).fetchone()
        conn.close()
        if user:
            session['user']    = user['username']
            session['user_id'] = user['id']
            return redirect('/')
        return render_template('login.html', error="Invalid username or password.")
    return render_template('login.html')

# ── LOGOUT ────────────────────────────────────────────────────────────────────
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ── AUTOCOMPLETE — poster_url already in CSV, no TMDB call ───────────────────
@app.route('/suggestions')
def suggestions():
    query   = request.args.get('q', '').strip()
    results = search_titles(query, limit=8)
    # Rename poster_url → poster so JS stays the same
    for r in results:
        r['poster'] = r.pop('poster_url', '')
    return jsonify(results)

# ── RECOMMEND — everything from CSV, instant response ─────────────────────────
@app.route('/recommend', methods=['POST'])
def recommend_movies():
    movie   = request.form.get('movie', '').strip()
    user_id = session.get('user_id', 1)

    results = hybrid_recommend(movie, user_id)

    if not results or isinstance(results[0], str):
        return render_template('index.html',
                               error=f'No results found for "{movie}" 😢',
                               movies=None,
                               username=session.get('user', ''))

    return render_template('index.html',
        movies         = [r['title']         for r in results],
        posters        = [r['poster_url']    for r in results],   # from CSV
        overviews      = [r['overview']      for r in results],   # from CSV
        years          = [r['year']          for r in results],   # from CSV
        tmdb_ratings   = [r['tmdb_rating']   for r in results],   # from CSV
        genres         = [r['genres']        for r in results],
        content_scores = [r['content_score'] for r in results],
        cf_scores      = [r['cf_score']      for r in results],
        hybrid_scores  = [r['hybrid_score']  for r in results],
        searched       = movie,
        username       = session['user'],
    )

if __name__ == "__main__":
    app.run(debug=True)