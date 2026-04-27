# ── movies.py ────────────────────────────────────────────────────────────────
import os
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from surprise import Dataset, Reader, SVD

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))

# ── Use enriched CSV if available, otherwise fall back to original ────────────
ENRICHED_CSV = os.path.join(BASE_DIR, "movies_with_posters.csv")
ORIGINAL_CSV = os.path.join(BASE_DIR, "movies (1).csv")
RATINGS_CSV  = os.path.join(BASE_DIR, "Ratings.csv")

if os.path.exists(ENRICHED_CSV):
    df = pd.read_csv(ENRICHED_CSV)
    HAS_ENRICHED = True
    print("[movies.py] ✅ Using enriched CSV with posters & overviews")
else:
    df = pd.read_csv(ORIGINAL_CSV)
    HAS_ENRICHED = False
    print("[movies.py] ⚠️  Enriched CSV not found — run download_posters.py first!")

ratings = pd.read_csv(RATINGS_CSV)

# ── Data Cleaning ─────────────────────────────────────────────────────────────
df['genres']   = df['genres'].fillna('')
df             = df.rename(columns={"movieId": "movie_id"}) \
                   if "movieId" in df.columns else df
ratings        = ratings.rename(columns={"movieId": "movie_id"}) \
                   if "movieId" in ratings.columns else ratings
df             = df[df['title'].notnull()].reset_index(drop=True)
df['title']    = df['title'].apply(lambda x: x.split('(')[0].strip())

# Fill missing enriched columns so code never crashes
for col, default in [("poster_url",""), ("overview",""), ("year",""), ("tmdb_rating", 0.0)]:
    if col not in df.columns:
        df[col] = default
df['poster_url'] = df['poster_url'].fillna('')
df['overview']   = df['overview'].fillna('')

# Tags for content similarity
df['tags'] = df['genres'].str.replace('|', ' ') * 2 + " " + df['title']

# ── Feature Extraction ────────────────────────────────────────────────────────
cv       = CountVectorizer(max_features=5000, stop_words="english")
vectors  = cv.fit_transform(df["tags"]).toarray()

# ── Cosine Similarity ─────────────────────────────────────────────────────────
similarity = cosine_similarity(vectors)

# ── Collaborative SVD ─────────────────────────────────────────────────────────
reader   = Reader(rating_scale=(1, 5))
data     = Dataset.load_from_df(ratings[['userId', 'movie_id', 'rating']], reader)
trainset = data.build_full_trainset()
model    = SVD()
model.fit(trainset)

# ── All titles for autocomplete ───────────────────────────────────────────────
ALL_TITLES = df['title'].tolist()

def search_titles(query: str, limit: int = 8) -> list:
    q       = query.strip().lower()
    starts  = [t for t in ALL_TITLES if t.lower().startswith(q)]
    contains = [t for t in ALL_TITLES if q in t.lower() and t not in starts]
    matched = (starts + contains)[:limit]
    results = []
    for title in matched:
        row = df[df['title'] == title].iloc[0]
        results.append({
            "title":      title,
            "movie_id":   int(row['movie_id']),
            "genres":     row['genres'].replace("|", ", "),
            "poster_url": row['poster_url'],        # from CSV — instant
        })
    return results

# ── Collaborative Score ───────────────────────────────────────────────
def collab_score(userId, movie_id):
    raw = model.predict(userId, movie_id).est
    return (raw - 1) / 4

# ── Hybeid Reccomendation ───────────────────────────────────────────────
def hybrid_recommend(movie: str, userId: int = 1, alpha: float = 0.8) -> list:
    matches = df[df['title'] == movie]
    if matches.empty:
        return ["Movie not found"]

    query_idx = matches.index[0]
    distances = list(enumerate(similarity[query_idx]))

    results = []
    for idx, content_score in distances:
        if idx == query_idx:
            continue
        row         = df.iloc[idx]
        mid         = row['movie_id']
        cf_norm     = collab_score(userId, mid)
        final_score = alpha * content_score + (1 - alpha) * cf_norm

        results.append({
            "title":         row['title'],
            "movie_id":      int(mid),
            "genres":        row['genres'].replace("|", ", "),
            "poster_url":    row['poster_url'],      # ← from CSV, instant
            "overview":      row['overview'] or "No overview available.",
            "year":          str(row['year']) if row['year'] else "",
            "tmdb_rating":   round(float(row['tmdb_rating'] or 0), 1),
            "content_score": round(content_score, 4),
            "cf_score":      round(cf_norm, 4),
            "hybrid_score":  round(final_score * 5, 1),
        })

    return sorted(results, key=lambda x: x["hybrid_score"], reverse=True)[:5]