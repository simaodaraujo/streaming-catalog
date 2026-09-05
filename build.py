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
<html lang="pt" class="h-full bg-slate-900 text-slate-100 antialiased">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Top Streaming Portugal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
          },
          colors: {
            stremio: {
              DEFAULT: '#7B5BF5',
              hover: '#6D4AEB',
              active: '#5F3BDD',
              subtle: '#2E225A',
            }
          }
        }
      }
    }
  </script>
</head>
<body class="min-h-full flex flex-col justify-between p-6 sm:p-12 bg-gradient-to-b from-slate-900 via-slate-900 to-slate-950 font-sans">
  
  <header class="max-w-xl mx-auto w-full flex items-center justify-between pb-8">
    <div class="flex items-center gap-2.5">
      <div class="w-8 h-8 rounded-lg bg-stremio/20 border border-stremio/40 flex items-center justify-center text-stremio">
        <svg class="w-4 h-4 fill-current" viewBox="0 0 24 24">
          <path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5a2.5 2.5 0 0 1 0 5H2v4c0 1.1.9 2 2 2h3.8v-1.5a2.5 2.5 0 0 1 5 0V21H17c1.1 0 2-.9 2-2v-4h1.5a2.5 2.5 0 0 0 0-5z"/>
        </svg>
      </div>
      <span class="text-sm font-semibold tracking-tight text-slate-200">Addon Catalog</span>
    </div>
    <div class="flex items-center gap-2 text-xs text-slate-400 font-medium">
      <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
      Sincronizado hoje
    </div>
  </header>

  <main class="max-w-xl mx-auto w-full my-auto">
    <div class="space-y-6">
      
      <div class="space-y-2">
        <h1 class="text-3xl sm:text-4xl font-bold tracking-tight text-white">
          Top Streaming Portugal
        </h1>
        <p class="text-base text-slate-400 leading-relaxed">
          Os 10 títulos mais consumidos em território nacional, atualizados diariamente com base nas tabelas oficiais de reprodução.
        </p>
      </div>

      <div class="pt-2">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 block mb-3">Plataformas integradas</span>
        <div class="flex flex-wrap gap-2">
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800/80 border border-slate-700/60 text-slate-300">
            <span class="w-1.5 h-1.5 rounded-full bg-red-500"></span> Netflix
          </span>
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800/80 border border-slate-700/60 text-slate-300">
            <span class="w-1.5 h-1.5 rounded-full bg-blue-500"></span> Disney+
          </span>
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800/80 border border-slate-700/60 text-slate-300">
            <span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span> Prime Video
          </span>
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800/80 border border-slate-700/60 text-slate-300">
            <span class="w-1.5 h-1.5 rounded-full bg-purple-500"></span> Max / HBO
          </span>
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800/80 border border-slate-700/60 text-slate-300">
            <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span> Apple TV+
          </span>
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800/80 border border-slate-700/60 text-slate-300">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> SkyShowtime
          </span>
        </div>
      </div>

      <div class="pt-4 flex flex-col sm:flex-row gap-3">
        <a id="install-btn" href="#" class="inline-flex items-center justify-center gap-2.5 px-5 py-3 rounded-lg text-sm font-semibold text-white bg-stremio hover:bg-stremio-hover active:bg-stremio-active transition-all shadow-lg shadow-stremio/20">
          <svg class="w-4 h-4 fill-current" viewBox="0 0 24 24">
            <path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5a2.5 2.5 0 0 1 0 5H2v4c0 1.1.9 2 2 2h3.8v-1.5a2.5 2.5 0 0 1 5 0V21H17c1.1 0 2-.9 2-2v-4h1.5a2.5 2.5 0 0 0 0-5z"/>
          </svg>
          Instalar Addon
        </a>

        <button id="copy-btn" onclick="copyManifestUrl()" class="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-lg text-sm font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 active:bg-slate-800/60 border border-slate-700 transition">
          <svg class="w-4 h-4 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          <span>Copiar Manifesto</span>
        </button>
      </div>

    </div>
  </main>

  <footer class="max-w-xl mx-auto w-full pt-12 flex items-center justify-between text-xs text-slate-500 border-t border-slate-800/80">
    <span>v1.0.3</span>
    <span>Executado via GitHub Actions</span>
  </footer>

  <script>
    const manifestUrl = window.location.origin + window.location.pathname.replace(/\\/?$/, '/') + 'manifest.json';
    const stremioUrl = manifestUrl.replace(/^https?:\\/\\//, 'stremio://');
    
    document.getElementById('install-btn').href = stremioUrl;

    function copyManifestUrl() {
      navigator.clipboard.writeText(manifestUrl);
      const btn = document.getElementById('copy-btn');
      const originalHTML = btn.innerHTML;
      
      btn.innerHTML = `
        <svg class="w-4 h-4 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        <span class="text-emerald-400">Link copiado!</span>
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