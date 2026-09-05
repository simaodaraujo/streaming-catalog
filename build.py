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
    <title>Top Streaming Portugal</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: #16181d;
            background-image: 
                radial-gradient(at 0% 0%, rgba(123, 91, 245, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(255, 255, 255, 0.03) 0px, transparent 50%);
            color: #e2e4e9;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
            -webkit-font-smoothing: antialiased;
        }

        .card {
            width: 100%;
            max-width: 440px;
            background: #20232a;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 20px;
            padding: 36px 32px;
            box-shadow: 
                0 20px 40px -15px rgba(0, 0, 0, 0.45),
                0 0 0 1px rgba(255, 255, 255, 0.02);
        }

        .header {
            margin-bottom: 24px;
        }

        .title-row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }

        .addon-icon {
            width: 38px;
            height: 38px;
            background: rgba(123, 91, 245, 0.15);
            border: 1px solid rgba(123, 91, 245, 0.3);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #9d85f7;
            flex-shrink: 0;
        }

        .addon-icon svg {
            width: 20px;
            height: 20px;
            fill: currentColor;
        }

        h1 {
            font-size: 22px;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: -0.02em;
        }

        p.desc {
            font-size: 14px;
            line-height: 1.55;
            color: #9aa0a6;
        }

        .platforms-label {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #717784;
            margin-bottom: 10px;
        }

        .platforms {
            display: flex;
            flex-wrap: wrap;
            gap: 7px;
            margin-bottom: 30px;
        }

        .platform {
            font-size: 12px;
            font-weight: 500;
            color: #c9cdd4;
            background: #282c35;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            padding: 5px 11px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .platform::before {
            content: '';
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #525866;
        }

        .platform.netflix::before { background: #e50914; }
        .platform.disney::before { background: #113ccf; }
        .platform.prime::before { background: #00a8e1; }
        .platform.hbo::before { background: #9933ff; }
        .platform.apple::before { background: #a2aaad; }
        .platform.skyshowtime::before { background: #00ff7f; }

        .actions {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .btn {
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 13px 18px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
            font-family: inherit;
        }

        /* Cor oficial roxa do ecossistema Stremio */
        .btn-stremio {
            background: #7353f2;
            background: linear-gradient(135deg, #815ff8 0%, #6842ea 100%);
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.15);
            box-shadow: 0 4px 14px rgba(115, 83, 242, 0.35);
        }

        .btn-stremio:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(115, 83, 242, 0.45);
            filter: brightness(1.06);
        }

        .btn-stremio:active {
            transform: translateY(0);
        }

        .btn-stremio svg {
            width: 18px;
            height: 18px;
            fill: #ffffff;
        }

        .btn-secondary {
            background: #282c35;
            color: #c9cdd4;
            border: 1px solid rgba(255, 255, 255, 0.07);
        }

        .btn-secondary:hover {
            background: #2f343f;
            color: #ffffff;
            border-color: rgba(255, 255, 255, 0.14);
        }

        .btn-secondary svg {
            width: 16px;
            height: 16px;
            stroke: currentColor;
            stroke-width: 2;
            fill: none;
        }

        .footer-note {
            margin-top: 26px;
            padding-top: 18px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            font-size: 11px;
            color: #6c7280;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .pulse-dot {
            display: inline-block;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #10b981;
            margin-right: 5px;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <div class="title-row">
                <div class="addon-icon">
                    <svg viewBox="0 0 24 24">
                        <path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5a2.5 2.5 0 0 1 0 5H2v4c0 1.1.9 2 2 2h3.8v-1.5a2.5 2.5 0 0 1 5 0V21H17c1.1 0 2-.9 2-2v-4h1.5a2.5 2.5 0 0 0 0-5z"/>
                    </svg>
                </div>
                <h1>Top Streaming</h1>
            </div>
            <p class="desc">Títulos mais vistos nas principais plataformas de streaming em território nacional, sincronizados diariamente.</p>
        </div>

        <div class="platforms-label">Catálogos incluídos</div>
        <div class="platforms">
            <span class="platform netflix">Netflix</span>
            <span class="platform disney">Disney+</span>
            <span class="platform prime">Prime Video</span>
            <span class="platform hbo">HBO</span>
            <span class="platform apple">Apple TV+</span>
            <span class="platform skyshowtime">SkyShowtime</span>
        </div>

        <div class="actions">
            <a id="install-btn" href="#" class="btn btn-stremio">
                <svg viewBox="0 0 24 24">
                    <path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5a2.5 2.5 0 0 1 0 5H2v4c0 1.1.9 2 2 2h3.8v-1.5a2.5 2.5 0 0 1 5 0V21H17c1.1 0 2-.9 2-2v-4h1.5a2.5 2.5 0 0 0 0-5z"/>
                </svg>
                Instalar Addon
            </a>
            <button id="copy-btn" class="btn btn-secondary" onclick="copyManifestUrl()">
                <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
                Copiar link do manifesto
            </button>
        </div>

        <div class="footer-note">
            <span><span class="pulse-dot"></span>Atualizado diariamente</span>
            <span>v1.0.3</span>
        </div>
    </div>

    <script>
        const manifestUrl = window.location.origin + window.location.pathname.replace(/\\/?$/, '/') + 'manifest.json';
        const stremioUrl = manifestUrl.replace(/^https?:\\/\\//, 'stremio://');
        
        document.getElementById('install-btn').href = stremioUrl;

        function copyManifestUrl() {
            navigator.clipboard.writeText(manifestUrl);
            const btn = document.getElementById('copy-btn');
            const originalHTML = btn.innerHTML;
            
            btn.innerHTML = `
                <svg viewBox="0 0 24 24" stroke="#10b981" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                <span style="color: #10b981;">Copiado com sucesso!</span>
            `;
            
            setTimeout(() => {
                btn.innerHTML = originalHTML;
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