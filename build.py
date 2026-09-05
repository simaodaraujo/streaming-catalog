import os
import json
import time
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")

if not TMDB_API_KEY:
    raise ValueError("TMDB_API_KEY não foi encontrada nas variáveis de ambiente.")

session = requests.Session()
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

PROVIDERS = [
    {"id": "netflix", "name": "Netflix", "flix_slug": "netflix", "tmdb_id": 8},
    {"id": "disney", "name": "Disney+", "flix_slug": "disney", "tmdb_id": 337},
    {"id": "prime", "name": "Prime Video", "flix_slug": "amazon-prime", "tmdb_id": 119},
    {"id": "hbo", "name": "HBO", "flix_slug": "hbo", "tmdb_id": 1899},
    {"id": "apple", "name": "Apple TV+", "flix_slug": "apple-tv", "tmdb_id": 350},
    {"id": "skyshowtime", "name": "SkyShowtime", "flix_slug": "skyshowtime", "tmdb_id": 1773}
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
        res = session.get(url, params=params, timeout=5)
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
        print(f"  [!] Erro TMDB ao procurar '{title}': {e}", flush=True)
    return None

def get_tmdb_fallback(tmdb_provider_id, media_type):
    search_type = "movie" if media_type == "movie" else "tv"
    url = f"https://api.themoviedb.org/3/discover/{search_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "watch_region": "PT",
        "with_watch_providers": tmdb_provider_id,
        "with_watch_monetization_types": "flatrate",
        "sort_by": "popularity.desc",
        "language": "pt-PT",
        "page": 1
    }
    items = []
    try:
        res = session.get(url, params=params, timeout=6)
        if res.status_code == 200:
            results = res.json().get("results", [])
            for item in results[:10]:
                tmdb_id = item["id"]
                imdb_id = get_imdb_id(tmdb_id, search_type)
                time.sleep(0.03)
                if imdb_id:
                    name = item.get("title") if search_type == "movie" else item.get("name")
                    items.append({
                        "id": imdb_id,
                        "type": "movie" if media_type == "movie" else "series",
                        "name": name,
                        "poster": f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get("poster_path") else None
                    })
    except Exception as e:
        print(f"  [!] Erro Fallback TMDB: {e}", flush=True)
    return items

def scrape_flixpatrol(flix_slug):
    movies, series = [], []
    target_url = f"https://flixpatrol.com/top10/{flix_slug}/portugal/today/"

    if not SCRAPER_API_KEY:
        print(f"  [i] SCRAPER_API_KEY não definida. A saltar scraping direto...", flush=True)
        return movies, series

    payload = {
        "api_key": SCRAPER_API_KEY,
        "url": target_url,
        "render": "false"
    }

    print(f"  -> A contactar ScraperAPI para {flix_slug}...", flush=True)
    try:
        res = requests.get("https://api.scraperapi.com/", params=payload, timeout=15)
        if res.status_code != 200:
            print(f"  [!] ScraperAPI devolveu status HTTP {res.status_code}", flush=True)
            return movies, series

        soup = BeautifulSoup(res.text, "html.parser")
        tables = soup.find_all("table")

        for idx, table in enumerate(tables):
            extracted = []
            for row in table.select("tbody tr") or table.select("tr"):
                if len(extracted) >= 10:
                    break
                for a in row.find_all("a"):
                    href = a.get("href", "")
                    text = a.get_text(strip=True)
                    if "/title/" in href and text and not text.isdigit():
                        if text not in extracted:
                            extracted.append(text)
                        break

            if idx == 0 and not movies:
                movies = extracted
            elif idx == 1 and not series:
                series = extracted

        print(f"  -> FlixPatrol: {len(movies)} filmes e {len(series)} séries encontrados.", flush=True)

    except Exception as e:
        print(f"  [!] Timeout ou erro no ScraperAPI: {e}", flush=True)

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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #09090b;
            color: #fafafa;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
            -webkit-font-smoothing: antialiased;
        }
        .container { width: 100%; max-width: 400px; }
        .header { margin-bottom: 24px; }
        .meta-line { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
        .flag { width: 13px; height: 13px; border-radius: 50%; display: inline-block; overflow: hidden; flex-shrink: 0; }
        .meta-text { font-size: 11px; font-weight: 500; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }
        h1 { font-size: 20px; font-weight: 600; letter-spacing: -0.02em; color: #ffffff; margin-bottom: 6px; }
        p.desc { font-size: 13px; line-height: 1.5; color: #71717a; }
        .platforms { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid #18181b; }
        .platform { font-size: 11px; color: #a1a1aa; background: #121215; border: 1px solid #27272a; border-radius: 5px; padding: 3px 8px; }
        .actions { display: flex; flex-direction: column; gap: 8px; }
        .btn { width: 100%; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px 14px; border-radius: 7px; font-size: 13px; font-weight: 500; cursor: pointer; text-decoration: none; transition: opacity 0.15s ease, background 0.15s ease; font-family: inherit; }
        .btn-primary { background: #ffffff; color: #09090b; border: 1px solid #ffffff; }
        .btn-primary:hover { opacity: 0.9; }
        .btn-secondary { background: transparent; color: #a1a1aa; border: 1px solid #27272a; }
        .btn-secondary:hover { color: #fafafa; background: #141417; }
        .footer-note { margin-top: 24px; font-size: 11px; color: #52525b; display: flex; align-items: center; justify-content: space-between; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="meta-line">
                <span class="flag">
                    <svg viewBox="0 0 600 400" width="100%" height="100%">
                        <rect width="240" height="400" fill="#046A38"/>
                        <rect x="240" width="360" height="400" fill="#DA291C"/>
                        <circle cx="240" cy="200" r="80" fill="#FFC72C"/>
                        <circle cx="240" cy="200" r="50" fill="#DA291C"/>
                        <rect x="215" y="175" width="50" height="50" rx="6" fill="#FFFFFF"/>
                    </svg>
                </span>
                <span class="meta-text">Portugal · Stremio</span>
            </div>
            <h1>Top Streaming</h1>
            <p class="desc">Top 10 diário real dos filmes e séries mais populares em streaming em Portugal.</p>
        </div>

        <div class="platforms">
            <span class="platform">Netflix</span>
            <span class="platform">Disney+</span>
            <span class="platform">Prime</span>
            <span class="platform">HBO</span>
            <span class="platform">Apple TV+</span>
            <span class="platform">SkyShowtime</span>
        </div>

        <div class="actions">
            <a id="install-btn" href="#" class="btn btn-primary">
                Instalar no Stremio
            </a>
            <button id="copy-btn" class="btn btn-secondary" onclick="copyManifestUrl()">
                Copiar manifesto
            </button>
        </div>

        <div class="footer-note">
            <span>v1.0.3</span>
            <span>Atualização diária (09:30 UTC)</span>
        </div>
    </div>

    <script>
        const manifestUrl = window.location.origin + window.location.pathname.replace(/\\/?$/, '/') + 'manifest.json';
        const stremioUrl = manifestUrl.replace(/^https?:\\/\\//, 'stremio://');
        
        document.getElementById('install-btn').href = stremioUrl;

        function copyManifestUrl() {
            navigator.clipboard.writeText(manifestUrl);
            const btn = document.getElementById('copy-btn');
            const original = btn.textContent;
            btn.textContent = 'Copiado';
            setTimeout(() => {
                btn.textContent = original;
            }, 1800);
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
        print(f"\n--- A processar {prov['name']} ---", flush=True)
        movie_titles, series_titles = scrape_flixpatrol(prov["flix_slug"])

        # Filmes
        movie_items = []
        for title in movie_titles:
            item = search_tmdb_title(title, "movie")
            if item:
                movie_items.append(item)
            time.sleep(0.03)

        if not movie_items:
            print(f"  [i] A usar fallback TMDB (Filmes)...", flush=True)
            movie_items = get_tmdb_fallback(prov["tmdb_id"], "movie")

        print(f"  -> Filmes guardados: {len(movie_items)}/10", flush=True)
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

        # Séries
        series_items = []
        for title in series_titles:
            item = search_tmdb_title(title, "series")
            if item:
                series_items.append(item)
            time.sleep(0.03)

        if not series_items:
            print(f"  [i] A usar fallback TMDB (Séries)...", flush=True)
            series_items = get_tmdb_fallback(prov["tmdb_id"], "series")

        print(f"  -> Séries guardadas: {len(series_items)}/10", flush=True)
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
        "version": "1.0.3",
        "name": "Streaming Portugal Populares",
        "description": "Top 10 diário real da Netflix, Disney+, Prime, HBO, Apple TV+ e SkyShowtime em Portugal",
        "resources": ["catalog"],
        "types": ["movie", "series"],
        "catalogs": manifest_catalogs
    }

    with open("dist/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    create_landing_page()
    print(f"\nFinalizado com sucesso! {len(manifest_catalogs)} catálogos registados.", flush=True)

if __name__ == "__main__":
    main()