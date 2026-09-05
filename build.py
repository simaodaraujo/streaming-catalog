import os
import json
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "72c63cafe1d6a9c46d4c9ec104883a18")

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

PROVIDERS = [
    {"id": "netflix", "name": "Netflix", "provider_id": 8, "region": "PT"},
    {"id": "disney", "name": "Disney+", "provider_id": 337, "region": "PT"},
    {"id": "prime", "name": "Prime Video", "provider_id": 119, "region": "PT"},
    {"id": "hbo", "name": "Hbo", "provider_id": 1899, "region": "PT"},
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

def get_tmdb_popular(provider_id, media_type, region="PT"):
    url = f"https://api.themoviedb.org/3/discover/{media_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "watch_region": region,
        "with_watch_providers": provider_id,
        "sort_by": "popularity.desc",
        "language": "pt-PT",
        "page": 1
    }
    try:
        res = session.get(url, params=params, timeout=10)
        if res.status_code == 200:
            results = res.json().get("results", [])
            items = []
            for item in results[:10]:
                title = item.get("title") if media_type == "movie" else item.get("name")
                tmdb_id = item["id"]
                imdb_id = get_imdb_id(tmdb_id, media_type)
                time.sleep(0.08)
                if imdb_id:
                    items.append({
                        "id": imdb_id,
                        "type": "movie" if media_type == "movie" else "series",
                        "name": title,
                        "poster": f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get("poster_path") else None
                    })
            return items
    except Exception as e:
        print(f"Erro TMDB: {e}")
    return []

def create_landing_page():
    html_content = """<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Top Streaming — Stremio</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Geist', -apple-system, sans-serif;
            background: #000000;
            color: #ededed;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
            -webkit-font-smoothing: antialiased;
        }

        .wrapper {
            width: 100%;
            max-width: 440px;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            font-size: 12px;
            font-weight: 500;
            color: #888;
            letter-spacing: 0.02em;
            padding: 4px 12px 4px 8px;
            border-radius: 99px;
            border: 1px solid #222;
            background: #0a0a0a;
            margin-bottom: 28px;
        }

        .flag-icon {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            overflow: hidden;
            display: inline-flex;
        }

        h1 {
            font-size: 26px;
            font-weight: 600;
            letter-spacing: -0.03em;
            color: #fff;
            margin-bottom: 8px;
        }

        p.desc {
            font-size: 14px;
            color: #888;
            line-height: 1.5;
            font-weight: 400;
            margin-bottom: 32px;
        }

        .tags {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            justify-content: center;
            margin-bottom: 36px;
        }

        .tag {
            font-size: 11px;
            font-weight: 500;
            color: #777;
            background: #0c0c0c;
            border: 1px solid #1c1c1c;
            padding: 4px 10px;
            border-radius: 6px;
            letter-spacing: -0.01em;
        }

        .btn-install {
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            background: #ededed;
            color: #000;
            text-decoration: none;
            padding: 13px 20px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.15s ease;
            margin-bottom: 12px;
        }

        .btn-install:hover {
            background: #ffffff;
            transform: translateY(-1px);
        }

        .copy-trigger {
            background: none;
            border: none;
            color: #666;
            font-size: 12px;
            cursor: pointer;
            padding: 8px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: color 0.15s ease;
            font-family: inherit;
        }

        .copy-trigger:hover {
            color: #aaa;
        }

        .copy-trigger svg {
            width: 13px;
            height: 13px;
            stroke-width: 1.8;
        }
    </style>
</head>
<body>
    <div class="wrapper">
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
        <p class="desc">Top 10 diário de Filmes e Séries das principais plataformas para o teu Stremio.</p>

        <div class="tags">
            <span class="tag">Netflix</span>
            <span class="tag">Disney+</span>
            <span class="tag">Prime</span>
            <span class="tag">Hbo</span>
        </div>

        <a id="install-btn" href="#" class="btn-install">
            Instalar no Stremio
        </a>

        <button id="copy-btn" class="copy-trigger" onclick="copyUrl()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
            <span id="copy-text">Copiar link do manifesto</span>
        </button>
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
        print(f"A descarregar {prov['name']}...")
        movies = get_tmdb_popular(prov["provider_id"], "movie", prov["region"])
        print(f"  -> Filmes: {len(movies)}")
        if movies:
            cat_id = f"{prov['id']}_pt_movies"
            with open(f"dist/catalog/movie/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": movies}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "movie",
                "id": cat_id,
                "name": f"{prov['name']} top 10 movies"
            })

        series = get_tmdb_popular(prov["provider_id"], "tv", prov["region"])
        print(f"  -> Séries: {len(series)}")
        if series:
            cat_id = f"{prov['id']}_pt_series"
            with open(f"dist/catalog/series/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": series}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "series",
                "id": cat_id,
                "name": f"{prov['name']} top 10 tvshows"
            })

    manifest = {
        "id": "org.portugal.streaming.top",
        "version": "1.0.0",
        "name": "Streaming Portugal Populares",
        "description": "Filmes e Séries populares em Portugal (Netflix, Disney+, Prime, Hbo, Paramount+, Hulu)",
        "resources": ["catalog"],
        "types": ["movie", "series"],
        "catalogs": manifest_catalogs
    }

    with open("dist/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    create_landing_page()
    print(f"Finalizado: {len(manifest_catalogs)} catálogos registados.")

if __name__ == "__main__":
    main()