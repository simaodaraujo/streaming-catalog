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
<html lang="pt" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Top Streaming Portugal — Stremio</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                    }
                }
            }
        }
    </script>
    <style>
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: #07090e;
        }
        .bg-grid {
            background-image: radial-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
            background-size: 24px 24px;
        }
    </style>
</head>
<body class="min-h-screen text-zinc-100 flex flex-col items-center justify-center p-6 sm:p-10 relative selection:bg-indigo-500/20 selection:text-indigo-300">
    <div class="fixed inset-0 bg-grid pointer-events-none opacity-80"></div>
    <div class="fixed top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[550px] h-[300px] bg-indigo-500/10 blur-[130px] rounded-full pointer-events-none"></div>

    <main class="w-full max-w-[440px] relative z-10 flex flex-col gap-6">
        <div class="relative bg-zinc-900/60 border border-zinc-800/80 backdrop-blur-xl rounded-2xl p-7 shadow-2xl shadow-black/60">
            <div class="flex items-center justify-between mb-5">
                <span class="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-800/80 border border-zinc-700/60 text-zinc-300 tracking-wide">
                    <span class="w-3.5 h-3.5 rounded-full overflow-hidden flex items-center justify-center border border-white/20">
                        <svg viewBox="0 0 600 400" class="w-full h-full object-cover">
                            <rect width="240" height="400" fill="#046A38"/>
                            <rect x="240" width="360" height="400" fill="#DA291C"/>
                            <circle cx="240" cy="200" r="80" fill="#FFC72C"/>
                            <circle cx="240" cy="200" r="50" fill="#DA291C"/>
                            <rect x="215" y="175" width="50" height="50" rx="6" fill="#FFFFFF"/>
                        </svg>
                    </span>
                    Portugal
                </span>
                <span class="text-[11px] font-mono text-zinc-400 bg-zinc-800/40 px-2 py-0.5 rounded border border-zinc-800">v1.0.2</span>
            </div>

            <h1 class="text-2xl font-bold tracking-tight text-white mb-2">Streaming Top 10</h1>
            <p class="text-sm text-zinc-400 leading-relaxed mb-6 font-normal">
                Tops oficiais diários de filmes e séries nas plataformas de streaming em Portugal para o teu Stremio.
            </p>

            <div class="flex flex-wrap gap-1.5 mb-7">
                <span class="text-xs px-2.5 py-1 rounded-md bg-zinc-800/40 border border-zinc-800 text-zinc-300 font-medium">Netflix</span>
                <span class="text-xs px-2.5 py-1 rounded-md bg-zinc-800/40 border border-zinc-800 text-zinc-300 font-medium">Disney+</span>
                <span class="text-xs px-2.5 py-1 rounded-md bg-zinc-800/40 border border-zinc-800 text-zinc-300 font-medium">Prime Video</span>
                <span class="text-xs px-2.5 py-1 rounded-md bg-zinc-800/40 border border-zinc-800 text-zinc-300 font-medium">HBO</span>
            </div>

            <div class="flex flex-col gap-2.5">
                <a id="install-btn" href="#" class="w-full inline-flex items-center justify-center gap-2 bg-zinc-100 hover:bg-white text-zinc-950 font-semibold text-sm py-3 px-4 rounded-xl transition duration-150 active:scale-[0.99] shadow-sm">
                    <svg class="w-4 h-4 text-zinc-950" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
                    Instalar no Stremio
                </a>
                
                <button id="copy-btn" onclick="copyUrl()" class="w-full inline-flex items-center justify-center gap-2 bg-zinc-800/50 hover:bg-zinc-800/80 border border-zinc-800 text-zinc-400 hover:text-zinc-200 text-xs py-2.5 px-3 rounded-xl transition duration-150">
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
                    <span id="copy-text">Copiar link do manifesto</span>
                </button>
            </div>
        </div>

        <div class="flex flex-col gap-2.5">
            <h2 class="text-xs font-semibold uppercase tracking-wider text-zinc-400 px-1">Complementos Recomendados</h2>
            
            <div class="flex flex-col gap-2">
                <a href="https://torrentio.strem.fun/configure" target="_blank" class="group flex items-center justify-between p-3.5 rounded-xl bg-zinc-900/40 hover:bg-zinc-900/80 border border-zinc-800/60 hover:border-zinc-700 transition duration-150">
                    <div class="flex flex-col gap-0.5">
                        <span class="text-sm font-medium text-zinc-200 group-hover:text-white transition">Torrentio + Real-Debrid</span>
                        <span class="text-xs text-zinc-400">Streams instantâneos sem buffer via cache Debrid</span>
                    </div>
                    <svg class="w-4 h-4 text-zinc-400 group-hover:text-zinc-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition duration-150" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17l9.2-9.2M17 17V8H8"/></svg>
                </a>

                <a href="https://subdl-stremio.vercel.app/" target="_blank" class="group flex items-center justify-between p-3.5 rounded-xl bg-zinc-900/40 hover:bg-zinc-900/80 border border-zinc-800/60 hover:border-zinc-700 transition duration-150">
                    <div class="flex flex-col gap-0.5">
                        <span class="text-sm font-medium text-zinc-200 group-hover:text-white transition">SubDL Subtitles</span>
                        <span class="text-xs text-zinc-400">Legendas sincronizadas com filtragem nativa PT-PT</span>
                    </div>
                    <svg class="w-4 h-4 text-zinc-400 group-hover:text-zinc-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition duration-150" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17l9.2-9.2M17 17V8H8"/></svg>
                </a>

                <a href="https://stremio-addons.net/ratings" target="_blank" class="group flex items-center justify-between p-3.5 rounded-xl bg-zinc-900/40 hover:bg-zinc-900/80 border border-zinc-800/60 hover:border-zinc-700 transition duration-150">
                    <div class="flex flex-col gap-0.5">
                        <span class="text-sm font-medium text-zinc-200 group-hover:text-white transition">IMDb Ratings</span>
                        <span class="text-xs text-zinc-400">Classificações do IMDb e Rotten Tomatoes no catálogo</span>
                    </div>
                    <svg class="w-4 h-4 text-zinc-400 group-hover:text-zinc-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition duration-150" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17l9.2-9.2M17 17V8H8"/></svg>
                </a>
            </div>
        </div>

        <footer class="text-center">
            <span class="text-[11px] text-zinc-400">Atualizado diariamente às 09:30 UTC</span>
        </footer>
    </main>

    <script>
        const manifestUrl = window.location.origin + window.location.pathname.replace(/\\/?$/, '/') + 'manifest.json';
        const stremioUrl = manifestUrl.replace(/^https?:\\/\\//, 'stremio://');
        
        document.getElementById('install-btn').href = stremioUrl;

        function copyUrl() {
            navigator.clipboard.writeText(manifestUrl);
            const text = document.getElementById('copy-text');
            text.textContent = 'Copiado!';
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