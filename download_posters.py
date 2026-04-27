import os, time, requests, pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

API_KEY    = "2b9b7669b26d34a437e297b5fb784229"
INPUT_CSV  = "movies (1).csv"          # your original file
OUTPUT_CSV = "movies_with_posters.csv" # will be created here

POSTER_BASE = "https://image.tmdb.org/t/p/w500"   # w500 = good quality

# ── Load existing progress so you can resume if interrupted ──────────────────
if os.path.exists(OUTPUT_CSV):
    done_df   = pd.read_csv(OUTPUT_CSV)
    done_ids  = set(done_df['movie_id'].tolist())
    print(f"Resuming — {len(done_ids)} already done.")
else:
    done_df  = pd.DataFrame()
    done_ids = set()

df = pd.read_csv(INPUT_CSV)
df = df[~df['movie_id'].isin(done_ids)]   # skip already-fetched rows
total = len(df)
print(f"Fetching {total} movies from TMDB …")

# ── Fetch one movie ───────────────────────────────────────────────────────────
def fetch(row):
    mid = int(row['movie_id'])
    for attempt in range(4):
        try:
            url  = f"https://api.themoviedb.org/3/movie/{mid}?api_key={API_KEY}"
            data = requests.get(url, timeout=10).json()
            path = data.get("poster_path") or ""
            return {
                "movie_id":    mid,
                "title":       row['title'],
                "genres":      row['genres'],
                "poster_url":  (POSTER_BASE + path) if path else "",
                "overview":    (data.get("overview") or "").strip(),
                "year":        (data.get("release_date") or "")[:4],
                "tmdb_rating": round(data.get("vote_average") or 0, 1),
            }
        except Exception as e:
            if attempt == 3:
                print(f"  ✗ Failed id={mid}: {e}")
                return {
                    "movie_id": mid, "title": row['title'],
                    "genres": row['genres'], "poster_url": "",
                    "overview": "", "year": "", "tmdb_rating": 0,
                }
            time.sleep(1.0 * (attempt + 1))

# ── Batch-fetch with 6 threads, save every 200 rows ──────────────────────────
rows   = df.to_dict('records')
buffer = []
done   = 0

with ThreadPoolExecutor(max_workers=6) as ex:
    futures = {ex.submit(fetch, row): row for row in rows}
    for future in as_completed(futures):
        result = future.result()
        buffer.append(result)
        done  += 1

        if done % 50 == 0 or done == total:
            pct = round(done / total * 100, 1)
            print(f"  {done}/{total}  ({pct}%)")

        # Save every 200 rows so progress is not lost on crash
        if len(buffer) >= 200 or done == total:
            chunk = pd.DataFrame(buffer)
            combined = pd.concat([done_df, chunk], ignore_index=True) \
                       if not done_df.empty else chunk
            combined.to_csv(OUTPUT_CSV, index=False)
            done_df = combined
            buffer  = []

print(f"\n✅  Done! Saved to  {OUTPUT_CSV}")
print(f"    Rows with poster : {(done_df['poster_url'] != '').sum()}")
print(f"    Rows without     : {(done_df['poster_url'] == '').sum()}")
