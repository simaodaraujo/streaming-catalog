import os
import json
import time
import re
import shutil
import requests
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

if not TMDB_API_KEY:
    raise ValueError("TMDB_API_KEY não foi encontrada nas variáveis de ambiente.")

session = requests.Session()
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

PROVIDERS = [
    {"id": "netflix", "name": "Netflix", "tmdb_id": 8, "is_netflix": True},
    {"id": "disney", "name": "Disney+", "tmdb_id": 337, "is_netflix": False},
    {"id": "prime", "name": "Prime Video", "tmdb_id": 119, "is_netflix": False},
    {"id": "hbo", "name": "HBO", "tmdb_id": 1899, "is_netflix": False},
    {"id": "apple", "name": "Apple TV+", "tmdb_id": 350, "is_netflix": False},
    {"id": "skyshowtime", "name": "SkyShowtime", "tmdb_id": 1773, "is_netflix": False}
]

def clean_title(title):
    cleaned = re.sub(r'(?i)\b(season|temporada|series)\s+\d+\b', '', title)
    cleaned = re.sub(r'[\(\[].*?[\)\]]', '', cleaned)
    cleaned = re.sub(r'\s*[-:–—|]\s*$', '', cleaned)
    return cleaned.strip(' :-–—|')

def get_imdb_id(tmdb_id, media_type):
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids"
    try:
        res = session.get(url, params={"api_key": TMDB_API_KEY}, timeout=7)
        if res.status_code == 200:
            return res.json().get("imdb_id")
    except Exception:
        pass
    return None

def search_tmdb_title(title, media_type):
    search_type = "movie" if media_type == "movie" else "tv"
    query = clean_title(title)
    
    url = f"https://api.themoviedb.org/3/search/{search_type}"
    params = {"api_key": TMDB_API_KEY, "query": query, "language": "pt-PT", "page": 1}
    
    try:
        res = session.get(url, params=params, timeout=7)
        results = res.json().get("results", []) if res.status_code == 200 else []
        
        if not results:
            params.pop("language", None)
            res = session.get(url, params=params, timeout=7)
            results = res.json().get("results", []) if res.status_code == 200 else []

        if not results and search_type == "tv":
            multi_url = "https://api.themoviedb.org/3/search/multi"
            res = session.get(multi_url, params={"api_key": TMDB_API_KEY, "query": query, "page": 1}, timeout=7)
            multi_res = res.json().get("results", []) if res.status_code == 200 else []
            results = [r for r in multi_res if r.get("media_type") in ["tv", "movie"]]

        if results:
            best = results[0]
            actual_type = best.get("media_type", search_type)
            tmdb_id = best["id"]
            imdb_id = get_imdb_id(tmdb_id, actual_type)
            
            if imdb_id:
                name = best.get("name") if actual_type == "tv" else best.get("title")
                return {
                    "id": imdb_id,
                    "type": "series" if actual_type == "tv" else "movie",
                    "name": name or title,
                    "poster": f"https://image.tmdb.org/t/p/w500{best.get('poster_path')}" if best.get("poster_path") else None
                }
    except Exception as e:
        print(f"  [!] Erro TMDB ao procurar '{title}': {e}", flush=True)
        
    return None

def get_netflix_official_top10(media_type):
    """
    Vai buscar diretamente o Top 10 oficial e público da Netflix para Portugal.
    media_type: 'films' (filmes) ou 'shows' (séries)
    """
    url = "https://www.netflix.com/tudum/top10/portugal"
    # A Netflix fornece os dados num JSON embutido na página ou podemos usar a API pública de top10 deles
    api_url = f"https://www.netflix.com/tudum/top10/data/portugal?week="
    
    # Alternativa mais direta e limpa via endpoint de dados do Tudum da Netflix:
    try:
        # Vamos buscar a página principal do Tudum Portugal para extrair os dados atuais
        res = session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # O site do tudum carrega os dados numa tag script com o JSON state ou numa tabela
            # Vamos usar uma abordagem segura via requests ao endpoint de JSON da Netflix se disponível, 
            # ou ler diretamente a tabela HTML do Tudum Portugal:
            tables = soup.find_all("table")
            titles = []
            
            # Identificar a tabela correta (Filmes vs Séries)
            target_table_idx = 0 if media_type == "films" else 1
            if len(tables) > target_table_idx:
                rows = tables[target_table_idx].select("tbody tr")
                for row in rows[:10]:
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        title_text = cols[1].get_text(strip=True)
                        if title_text:
                            titles.append(title_text)
            return titles
    except Exception as e:
        print(f"  [!] Erro ao obter Top 10 oficial da Netflix: {e}", flush=True)
        
    return []

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
        res = session.get(url, params=params, timeout=7)
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

def create_landing_page():
    now_iso = datetime.utcnow().isoformat() + "Z"
    
    html_content = f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Top 10 Streams PT - Stremio extension</title>
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
      display: block;
      margin: 0 auto 20px;
      max-width: 100%;
      height: auto;
      image-rendering: -webkit-optimize-contrast;
      image-rendering: crisp-edges;
      user-select: none;
      -webkit-user-drag: none;
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
    .btn svg {{ width: 20px; height: 20px; }}
    
    .recommendations {{
      margin-top: 36px;
      padding-top: 24px;
      border-top: 1px solid #27272a;
      text-align: left;
    }}
    .rec-title {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #71717a;
      margin-bottom: 12px;
      text-align: center;
    }}
    .rec-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .rec-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background-color: #27272a;
      border: 1px solid #3f3f46;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 12px;
      color: #e4e4e7;
      text-decoration: none;
      transition: all 0.15s ease;
    }}
    .rec-item:hover {{
      background-color: #323238;
      border-color: #52525b;
      color: #ffffff;
    }}
    .rec-item span.badge {{
      font-size: 10px;
      color: #a1a1aa;
      background: #18181b;
      padding: 2px 6px;
      border-radius: 4px;
    }}

    .footer {{
      margin-top: 32px;
      font-size: 12px;
      color: #52525b;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
    }}
    .schedule {{ color: #71717a; }}
    .version {{ color: #3f3f46; font-size: 11px; margin-top: 4px; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <img src="logo.png" alt="Top 10 Streams PT" class="main-logo" draggable="false" onerror="this.style.display='none'">
    
    <p class="subtitle">Extensão para ver o TOP 10 filmes e séries de várias plataformas de streaming em Portugal.</p>

    <div class="tags">
      <div class="tag">
        <svg viewBox="0 0 24 24" style="color: #E50914;"><path d="M6.3 21.5L6.3 2.5L9.5 2.5L16.5 15.5L16.5 2.5L19.7 2.5L19.7 21.5L16.5 21.5L9.5 8.5L9.5 21.5Z"/></svg>
        Netflix
      </div>
      <div class="tag">
        <svg viewBox="0 0 24 24" style="color: #0063e5;">
           <path d="M12.92 11.23c-.73-.24-1.78-.45-2.9-.6-1.08 1.4-2.4 2.87-4.14 4.02-1.2.78-2.22 1.14-2.92 1.14-.65 0-1.02-.32-1.02-.9 0-.82.68-1.98 1.96-3.32 1.36-1.44 3.1-2.6 4.95-3.46C7.54 5.92 6.55 4.7 6.55 3.8c0-.6.38-1 1.1-1 .78 0 1.83.6 2.86 1.7.53-.1.97-.15 1.3-.15 1.15 0 2 .3 2.37.82.4.52.44 1.13.13 1.7-.12.22-.3.42-.55.62 1.63.15 3.14.4 4.4.78 1.67.5 2.65 1.1 2.65 1.75 0 .5-.47.92-1.28 1.17-.6.18-1.34.3-2.12.3-.57 0-1.15-.04-1.73-.13.1.25.17.5.17.77 0 .5-.15.93-.43 1.3-.28.37-.67.55-1.17.55-.47 0-.9-.16-1.27-.47zm-1.8-1.5c-1.37.95-2.73 2.1-3.97 3.32-.82.8-1.25 1.5-1.25 1.95 0 .15.07.25.2.25.26 0 .9-.28 1.75-.82 1.34-.84 2.4-1.95 3.12-3.1-1.07-.46-2.02-1-2.8-1.57zm1.1-1.98c.5-.83 1-1.77 1.4-2.74-.83.35-1.6.85-2.3 1.48.33.4.63.83.9 1.26zm3.22 1.98c-1.08-.34-2.38-.55-3.8-.65-.18.77-.45 1.5-.83 2.15 1.3-.14 2.32-.38 3-.73.47-.2.7-.42.7-.63 0-.1-.13-.23-.38-.34l-1.3-.4-.14.6z"/>
           <path d="M22.5 10h-2.5V7.5h-1.5V10h-2.5v1.5h2.5v2.5h1.5v-2.5h2.5z"/>
        </svg>
        Disney+
      </div>
      <div class="tag">
        <svg viewBox="0 0 24 24" style="color: #00a8e1;"><path d="M12 18C7.5 18 4 15.5 3 12C4.5 14.5 8 16 12 16C16 16 19.5 14.5 21 12C20 15.5 16.5 18 12 18Z"/></svg>
        Prime Video
      </div>
      <div class="tag">
        <svg viewBox="0 0 24 24" style="color: #ffffff;">
           <path d="M13.6 15.39h-2.92V8.61h2.92c1.78 0 2.82.95 2.82 2.38v.03c0 .87-.4 1.54-1.07 1.97.83.35 1.34 1.12 1.34 2.06v.03c0 1.5-1.12 2.5-3.1 2.5zm-1.17-3.8h.98c.84 0 1.32-.4 1.32-1.02v-.03c0-.68-.5-.98-1.28-.98h-1.02v2.03zm0 2.65h1.16c.86 0 1.45-.44 1.45-1.1v-.02c0-.75-.62-1.12-1.46-1.12h-1.15v2.24zM8.33 15.39H6.58v-2.85H2.9v2.85H1.15V8.61H2.9v2.66h3.68V8.61h1.75v6.78zM19.14 15.5c2.14 0 3.7-1.57 3.7-3.48v-.03c0-1.92-1.55-3.5-3.7-3.5s-3.7 1.57-3.7 3.48v.03c0 1.92 1.55 3.5 3.7 3.5zm0-1.47c-1.15 0-1.94-.92-1.94-2.01v-.03c0-1.1.8-2.02 1.94-2.02s1.95.91 1.95 2.01v.03c0 1.1-.8 2.02-1.95 2.02z"/>
        </svg>
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
      <svg viewBox="0 0 24 24" style="fill: currentColor;">
        <path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5a2.5 2.5 0 0 1 0 5H2v4c0 1.1.9 2 2 2h3.8v-1.5a2.5 2.5 0 0 1 5 0V21H17c1.1 0 2-.9 2-2v-4h1.5a2.5 2.5 0 0 0 0-5z"/>
      </svg>
      Instalar Addon
    </a>
    
    <button id="copy-btn" onclick="copyManifestUrl()" class="btn btn-outline">
      <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
        <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
      </svg>
      Copiar manifest
    </button>

    <div class="recommendations">
      <div class="rec-title">Extensões que recomendo</div>
      <div class="rec-list">
        <a href="https://real-debrid.com/" target="_blank" rel="noopener" class="rec-item">
          <span>Real-Debrid</span>
          <span class="badge">Debrid</span>
        </a>
        <a href="https://subdl.strem.top/configure" target="_blank" rel="noopener" class="rec-item">
          <span>SubDL Subtitles</span>
          <span class="badge">Legendas</span>
        </a>
        <a href="https://opensubtitles-v3.strem.io/" target="_blank" rel="noopener" class="rec-item">
          <span>OpenSubtitles v3</span>
          <span class="badge">Legendas</span>
        </a>
        <a href="https://stremio-addons.net/addons/imdb-ratings" target="_blank" rel="noopener" class="rec-item">
          <span>IMDb Ratings</span>
          <span class="badge">Avaliações</span>
        </a>
      </div>
    </div>

    <div class="footer">
      <span id="time-ago" data-time="{now_iso}">Atualizado recentemente</span>
      <span class="schedule">Atualiza todos os dias às 09h30</span>
      <span class="version">v1.0.7</span>
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
        btn.innerHTML = `
          <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" style="width: 20px; height: 20px;">
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
            <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
          </svg>
          Copiar manifest
        `;
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
    setInterval(updateTime, 60000);
  </script>
</body>
</html>
"""
    with open("dist/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

def main():
    os.makedirs("dist/catalog/movie", exist_ok=True)
    os.makedirs("dist/catalog/series", exist_ok=True)

    if os.path.exists("img/logo.png"):
        shutil.copy("img/logo.png", "dist/logo.png")

    manifest_catalogs = []

    for prov in PROVIDERS:
        print(f"\n--- A processar {prov['name']} ---", flush=True)

        # 1. Obter Filmes
        if prov["is_netflix"]:
            print("  -> A recolher Top 10 oficial da Netflix (Filmes)...", flush=True)
            netflix_titles = get_netflix_official_top10("films")
            movie_items = []
            for title in netflix_titles:
                item = search_tmdb_title(title, "movie")
                if item and not any(m["id"] == item["id"] for m in movie_items):
                    movie_items.append(item)
                time.sleep(0.03)
            if not movie_items:
                print("  [i] Falha no oficial da Netflix, a usar fallback TMDB...", flush=True)
                movie_items = get_tmdb_fallback(prov["tmdb_id"], "movie")
        else:
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

        # 2. Obter Séries
        if prov["is_netflix"]:
            print("  -> A recolher Top 10 oficial da Netflix (Séries)...", flush=True)
            netflix_titles = get_netflix_official_top10("shows")
            series_items = []
            for title in netflix_titles:
                item = search_tmdb_title(title, "series")
                if item and not any(s["id"] == item["id"] for s in series_items):
                    series_items.append(item)
                time.sleep(0.03)
            if not series_items:
                print("  [i] Falha no oficial da Netflix, a usar fallback TMDB...", flush=True)
                series_items = get_tmdb_fallback(prov["tmdb_id"], "series")
        else:
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
        "version": "1.0.7",
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