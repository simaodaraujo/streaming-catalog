import os
import json
import time
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "72c63cafe1d6a9c46d4c9ec104883a18")

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

PROVIDERS = [
    {"id": "netflix", "name": "Netflix", "flix_slug": "netflix"},
    {"id": "disney", "name": "Disney+", "flix_slug": "disney"},
    {"id": "prime", "name": "Prime Video", "flix_slug": "amazon-prime"},
    {"id": "hbo", "name": "HBO", "flix_slug": "hbo"}
]

def get_imdb_id(tmdb_id, media_type):
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids"
    try:
        res = session.get(url, params={"api_key": TMDB_API_KEY}, timeout=5)
        if res.status_code == 200:
            return res.json().get("imdb_id")
    except Exception:
        pass
    return None

def search_tmdb_title(title, media_type):
    search_type = "movie" if media_type == "movie" else "tv"
    url = f"https://api.themoviedb.org/3/search/{search_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "pt-PT",
        "page": 1
    }
    try:
        res = session.get(url, params=params, timeout=6)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results:
                best = results[0]
                tmdb_id = best["id"]
                imdb_id = get_imdb_id(tmdb_id, search_type)
                if imdb_id:
                    name = best.get("title") if search_type == "movie" else best.get("name")
                    return {
                        "id": imdb_id,
                        "type": "movie" if media_type == "movie" else "series",
                        "name": name or title,
                        "poster": f"https://image.tmdb.org/t/p/w500{best.get('poster_path')}" if best.get("poster_path") else None
                    }
    except Exception as e:
        print(f"Erro TMDB ({title}): {e}")
    return None

def scrape_flixpatrol(flix_slug):
    url = f"https://flixpatrol.com/top10/{flix_slug}/portugal/today/"
    movies, series = [], []
    try:
        res = session.get(url, timeout=10)
        if res.status_code != 200:
            return movies, series

        soup = BeautifulSoup(res.text, "html.parser")
        tables = soup.select("table")
        
        if len(tables) >= 2:
            movie_rows = tables[0].select("tbody tr")[:10]
            for row in movie_rows:
                title_elem = row.select_one("a")
                if title_elem:
                    movies.append(title_elem.text.strip())

            series_rows = tables[1].select("tbody tr")[:10]
            for row in series_rows:
                title_elem = row.select_one("a")
                if title_elem:
                    series.append(title_elem.text.strip())
    except Exception as e:
        print(f"Erro scraping ({flix_slug}): {e}")

    return movies, series

def create_landing_page():
    html_content = """<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Top Streaming Portugal — Stremio</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #090d14;
            --card-bg: rgba(17, 24, 39, 0.65);
            --card-border: rgba(255, 255, 255, 0.08);
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Geist', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-base);
            background-image: 
                radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.07) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(99, 102, 241, 0.08) 0px, transparent 50%),
                radial-gradient(at 50% 50%, rgba(15, 23, 42, 0.5) 0px, transparent 100%);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
            -webkit-font-smoothing: antialiased;
        }

        .container {
            width: 100%;
            max-width: 460px;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }

        .hero-card {
            width: 100%;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-radius: 20px;
            padding: 32px 28px;
            box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
            margin-bottom: 24px;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            font-weight: 500;
            color: var(--text-secondary);
            padding: 5px 12px 5px 8px;
            border-radius: 99px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            background: rgba(255, 255, 255, 0.03);
            margin-bottom: 20px;
        }

        .flag-icon {
            width: 15px;
            height: 15px;
            border-radius: 50%;
            overflow: hidden;
            display: inline-flex;
        }

        h1 {
            font-size: 24px;
            font-weight: 600;
            letter-spacing: -0.03em;
            color: #ffffff;
            margin-bottom: 8px;
        }

        p.desc {
            font-size: 13.5px;
            color: var(--text-secondary);
            line-height: 1.55;
            margin-bottom: 24px;
        }

        .tags {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            justify-content: center;
            margin-bottom: 28px;
        }

        .tag {
            font-size: 11.5px;
            font-weight: 500;
            color: #cbd5e1;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 4px 10px;
            border-radius: 6px;
        }

        .btn-install {
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            background: #f8fafc;
            color: #090d14;
            text-decoration: none;
            padding: 13px 20px;
            border-radius: 12px;
            font-size: 13.5px;
            font-weight: 600;
            transition: all 0.15s ease;
            margin-bottom: 12px;
        }

        .btn-install:hover {
            background: #ffffff;
            transform: translateY(-1px);
            box-shadow: 0 4px 16px rgba(255, 255, 255, 0.12);
        }

        .copy-trigger {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 12px;
            cursor: pointer;
            padding: 6px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: color 0.15s ease;
            font-family: inherit;
        }

        .copy-trigger:hover { color: var(--text-secondary); }
        .copy-trigger svg { width: 13px; height: 13px; stroke-width: 1.8; }

        .addons-section {
            width: 100%;
            text-align: left;
        }

        .addons-title {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 10px;
            padding-left: 4px;
        }

        .addon-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .addon-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 14px;
            border-radius: 12px;
            background: rgba(17, 24, 39, 0.45);
            border: 1px solid var(--card-border);
            text-decoration: none;
            color: inherit;
            transition: background 0.15s, border-color 0.15s, transform 0.15s;
        }

        .addon-card:hover {
            background: rgba(30, 41, 59, 0.5);
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateY(-1px);
        }

        .addon-info {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .addon-name {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .addon-desc {
            font-size: 11.5px;
            color: var(--text-secondary);
        }

        .arrow-icon {
            color: var(--text-muted);
            width: 14px;
            height: 14px;
            stroke-width: 2;
            flex-shrink: 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="hero-card">
            <div class="badge">
                <span class="flag-icon">
                    <svg viewBox="0 0 600 400" width="100%" height="100%">
                        <rect width="240" height="400" fill="#046A38"/>
                        <rect x="240" width="360" height="400" fill="#DA291C"/>
                        <circle cx="240" cy="200" r="80" fill="#FFC72C"/>
                        <circle cx="240" cy="200" r="50" fill="#DA291C"/>
                        <rect x="215" y="175" width="50" height="50" rx="6" fill="#FFFFFF"/>
                    </svg>
                </span>
                Portugal
            </div>

            <h1>Top Streaming</h1>
            <p class="desc">Top 10 diário real dos filmes e séries mais vistos em Portugal para o teu Stremio.</p>

            <div class="tags">
                <span class="tag">Netflix</span>
                <span class="tag">Disney+</span>
                <span class="tag">Prime</span>
                <span class="tag">HBO</span>
            </div>

            <a id="install-btn" href="#" class="btn-install">
                Instalar no Stremio
            </a>

            <button id="copy-btn" class="copy-trigger" onclick="copyUrl()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
                <span id="copy-text">Copiar link do manifesto</span>
            </button>
        </div>

        <div class="addons-section">
            <div class="addons-title">Recomendações para combinar</div>
            <div class="addon-list">
                <a href="https://torrentio.strem.fun/configure" target="_blank" class="addon-card">
                    <div class="addon-info">
                        <span class="addon-name">Torrentio + Real-Debrid</span>
                        <span class="addon-desc">Streams rápidos sem buffering via cache Debrid</span>
                    </div>
                    <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M7 17l9.2-9.2M17 17V8H8"/></svg>
                </a>

                <a href="https://subdl-stremio.vercel.app/" target="_blank" class="addon-card">
                    <div class="addon-info">
                        <span class="addon-name">SubDL Subtitles</span>
                        <span class="addon-desc">Legendas sincronizadas com suporte dedicado PT-PT</span>
                    </div>
                    <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M7 17l9.2-9.2M17 17V8H8"/></svg>
                </a>

                <a href="https://stremio-addons.net/ratings" target="_blank" class="addon-card">
                    <div class="addon-info">
                        <span class="addon-name">IMDb Ratings</span>
                        <span class="addon-desc">Notas do IMDb e Rotten Tomatoes visíveis nos posters</span>
                    </div>
                    <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M7 17l9.2-9.2M17 17V8H8"/></svg>
                </a>
            </div>
        </div>
    </div>

    <script>
        const manifestUrl = window.location.origin + window.location.pathname.replace(/\\/?$/, '/') + 'manifest.json';
        const stremioUrl = manifestUrl.replace(/^https?:\\/\\//, 'stremio://');
        
        document.getElementById('install-btn').href = stremioUrl;

        function copyUrl() {
            navigator.clipboard.writeText(manifestUrl);
            const text = document.getElementById('copy-text');
            text.textContent = 'Copiado para a área de transferência';
            setTimeout(() => {
                text.textContent = 'Copiar link do manifesto';
            }, 2000);
        }
    </script>
</body>
</html>
"""
    with open("dist/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

def main():
    os.makedirs("dist/catalog/movie", exist_ok=True)
    os.makedirs("dist/catalog/series", exist_ok=True)

    manifest_catalogs = []

    for prov in PROVIDERS:
        print(f"\nA processar {prov['name']} via FlixPatrol (PT)...")
        movie_titles, series_titles = scrape_flixpatrol(prov["flix_slug"])
        
        movie_items = []
        for title in movie_titles:
            item = search_tmdb_title(title, "movie")
            if item:
                movie_items.append(item)
            time.sleep(0.08)

        print(f"  -> Filmes encontrados: {len(movie_items)}/10")
        if movie_items:
            cat_id = f"{prov['id']}_pt_movies"
            with open(f"dist/catalog/movie/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": movie_items}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "movie",
                "id": cat_id,
                "name": f"{prov['name']} Top 10",
                "extra": [{"name": "skip", "isRequired": False}]
            })

        series_items = []
        for title in series_titles:
            item = search_tmdb_title(title, "series")
            if item:
                series_items.append(item)
            time.sleep(0.08)

        print(f"  -> Séries encontradas: {len(series_items)}/10")
        if series_items:
            cat_id = f"{prov['id']}_pt_series"
            with open(f"dist/catalog/series/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": series_items}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "series",
                "id": cat_id,
                "name": f"{prov['name']} Top 10",
                "extra": [{"name": "skip", "isRequired": False}]
            })

    manifest = {
        "id": "org.portugal.streaming.top",
        "version": "1.0.2",
        "name": "Streaming Portugal Populares",
        "description": "Top 10 diário real da Netflix, Disney+, Prime e HBO em Portugal",
        "resources": ["catalog"],
        "types": ["movie", "series"],
        "catalogs": manifest_catalogs
    }

    with open("dist/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    create_landing_page()
    print(f"\nFinalizado com sucesso! {len(manifest_catalogs)} catálogos registados.")

if __name__ == "__main__":
    main()