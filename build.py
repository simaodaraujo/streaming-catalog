import os
import json
import time
import re
import shutil
import requests
from datetime import datetime
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

def clean_title(title):
    cleaned = re.sub(r'(?i)\b(season|temporada)\s+\d+\b', '', title)
    cleaned = re.sub(r'[\(\[].*?[\)\]]', '', cleaned)
    return cleaned.strip(' :-–—')

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
    query = clean_title(title)
    
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "pt-PT",
        "page": 1
    }
    
    try:
        res = session.get(url, params=params, timeout=5)
        results = res.json().get("results", []) if res.status_code == 200 else []
        
        if not results:
            params.pop("language", None)
            res = session.get(url, params=params, timeout=5)
            results = res.json().get("results", []) if res.status_code == 200 else []

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
    now_iso = datetime.utcnow().isoformat() + "Z"
    
    html_content = f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Top 10 Filmes e Séries Portugal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: #1c1c1e;
      color: #f5f5f7;
      font-family: 'Inter', -apple-system, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{
      max-width: 440px;
      width: 100%;
      text-align: center;
    }}
    .main-logo {{
      width: 140px;
      height: auto;
      margin: 0 auto 16px;
      display: block;
      filter: drop-shadow(0 4px 12px rgba(0,0,0,0.3));
    }}
    p.subtitle {{
      font-size: 14px;
      color: #a1a1aa;
      margin-bottom: 32px;
      line-height: 1.5;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 8px;
      margin-bottom: 36px;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background-color: #27272a;
      border: 1px solid #3f3f46;
      color: #d4d4d8;
      font-size: 11px;
      font-weight: 500;
      padding: 6px 12px;
      border-radius: 8px;
    }}
    .tag svg {{ height: 12px; width: auto; opacity: 0.9; fill: currentColor; }}
    .btn {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      padding: 14px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.15s ease;
      border: none;
    }}
    .btn-stremio {{
      background-color: #7b5bf5;
      color: #ffffff;
      margin-bottom: 12px;
    }}
    .btn-stremio:hover {{ background-color: #6a4ce0; }}
    .btn-outline {{
      background-color: transparent;
      color: #a1a1aa;
      border: 1px solid #3f3f46;
    }}
    .btn-outline:hover {{
      background-color: #27272a;
      color: #f5f5f7;
    }}
    .btn svg {{ width: 20px; height: 20px; fill: currentColor; }}
    .footer {{
      margin-top: 32px;
      font-size: 12px;
      color: #52525b;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
    }}
    .version {{ color: #3f3f46; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <img src="logo.png" alt="Top 10 Filmes e Séries" class="main-logo" onerror="this.style.display='none'">
    
    <p class="subtitle">Extensão para ver o TOP 10 filmes e séries de várias plataformas de streaming em Portugal.</p>

    <div class="tags">
      <div class="tag">
        <svg viewBox="0 0 24 24" style="color: #E50914;"><path d="M6.3 21.5L6.3 2.5L9.5 2.5L16.5 15.5L16.5 2.5L19.7 2.5L19.7 21.5L16.5 21.5L9.5 8.5L9.5 21.5Z"/></svg>
        Netflix
      </div>
      <div class="tag">
        <svg viewBox="0 0 24 24" style="color: #0063e5;"><path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2ZM13 16H11V10H13V16ZM13 8H11V6H13V8Z"/></svg>
        Disney+
      </div>
      <div class="tag">
        <svg viewBox="0 0 24 24" style="color: #00a8e1;"><path d="M12 18C7.5 18 4 15.5 3 12C4.5 14.5 8 16 12 16C16 16 19.5 14.5 21 12C20 15.5 16.5 18 12 18Z"/></svg>
        Prime Video
      </div>
      <div class="tag">
        <svg viewBox="0 0 40 18" style="color: #ffffff;"><path d="M0 0h4v6.5h8V0h4v18h-4v-7.5H4V18H0V0zm22.5 0c5 0 8.5 3 8.5 9s-3.5 9-8.5 9H17V0h5.5zm-1.5 14c2.5 0 4-1.5 4-5s-1.5-5-4-5h-1v10h1zm17.5-14c4.5 0 8 3.5 8 9s-3.5 9-8 9-8-3.5-8-9 3.5-9 8-9zm0 14c2.5 0 4-2 4-5s-1.5-5-4-5-4 2-4 5 1.5 5 4 5z"/></svg>
        HBO
      </div>
      <div class="tag">
        <svg viewBox="0 0 384 512" style="color: #ffffff;"><path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z"/></svg>
        Apple TV+
      </div>
      <div class="tag">
        <svg viewBox="0 0 24 24" style="color: #00ff7f;"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
        SkyShowtime
      </div>
    </div>

    <a id="install-btn" href="#" class="btn btn-stremio">
      <svg viewBox="0 0 24 24">
        <path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5a2.5 2.5 0 0 1 0 5H2v4c0 1.1.9 2 2 2h3.8v-1.5a2.5 2.5 0 0 1 5 0V21H17c1.1 0 2-.9 2-2v-4h1.5a2.5 2.5 0 0 0 0-5z"/>
      </svg>
      Instalar Addon
    </a>
    
    <button id="copy-btn" onclick="copyManifestUrl()" class="btn btn-outline">
      Copiar link do Manifesto
    </button>

    <div class="footer">
      <span id="time-ago" data-time="{now_iso}">Atualizado recentemente</span>
      <span class="version">v1.0.5</span>
    </div>
  </div>

  <script>
    const manifestUrl = window.location.origin + window.location.pathname.replace(/\\/?$/, '/') + 'manifest.json';
    const stremioUrl = manifestUrl.replace(/^https?:\\/\\//, 'stremio://');
    
    document.getElementById('install-btn').href = stremioUrl;

    function copyManifestUrl() {{
      navigator.clipboard.writeText(manifestUrl);
      const btn = document.getElementById('copy-btn');
      btn.innerHTML = '<span style="color:#4ade80;">✔ Link Copiado!</span>';
      setTimeout(() => {{
        btn.innerHTML = 'Copiar link do Manifesto';
      }}, 2000);
    }}

    function updateTime() {{
      const el = document.getElementById('time-ago');
      const updated = new Date(el.getAttribute('data-time'));
      const diffMins = Math.floor((new Date() - updated) / 60000);
      const diffHrs = Math.floor(diffMins / 60);

      if (diffMins < 1) el.textContent = 'Atualizado agora mesmo';
      else if (diffMins < 60) el.textContent = `Atualizado há ${{diffMins}} minuto${{diffMins > 1 ? 's' : ''}}`;
      else if (diffHrs < 24) el.textContent = `Atualizado há ${{diffHrs}} hora${{diffHrs > 1 ? 's' : ''}}`;
      else el.textContent = `Atualizado há ${{Math.floor(diffHrs/24)}} dia${{Math.floor(diffHrs/24) > 1 ? 's' : ''}}`;
    }}
    
    updateTime();
    setInterval(updateTime, 60000); // Atualiza os minutos sem precisar recarregar a página
  </script>
</body>
</html>
"""
    with open("dist/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

def main():
    os.makedirs("dist/catalog/movie", exist_ok=True)
    os.makedirs("dist/catalog/series", exist_ok=True)

    # Copia a logo automaticamente para a pasta dist para ser lida pelo Stremio e pelo HTML
    if os.path.exists("img/logo.png"):
        shutil.copy("img/logo.png", "dist/logo.png")

    manifest_catalogs = []

    for prov in PROVIDERS:
        print(f"\n--- A processar {prov['name']} ---", flush=True)
        movie_titles, series_titles = scrape_flixpatrol(prov["flix_slug"])

        movie_items = []
        for title in movie_titles:
            item = search_tmdb_title(title, "movie")
            if item and not any(m["id"] == item["id"] for m in movie_items):
                movie_items.append(item)
            time.sleep(0.03)

        if not movie_items:
            print(f"  [i] Erro crasso na fonte. A usar fallback TMDB (Filmes)...", flush=True)
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

        series_items = []
        for title in series_titles:
            item = search_tmdb_title(title, "series")
            if item and not any(s["id"] == item["id"] for s in series_items):
                series_items.append(item)
            time.sleep(0.03)

        if not series_items:
            print(f"  [i] Erro crasso na fonte. A usar fallback TMDB (Séries)...", flush=True)
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
        "version": "1.0.5",
        "name": "TOP 10 Portugal (Filmes & Séries)",
        "description": "Top 10 diário real da Netflix, Disney+, Prime, HBO, Apple TV+ e SkyShowtime em Portugal",
        "logo": "logo.png",
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