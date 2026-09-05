import os
import json
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TMDB_API_KEY = "72c63cafe1d6a9c46d4c9ec104883a18"

# Sessão com pooling de conexões e retries automáticos
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

PROVIDERS = [
    {"id": "netflix", "name": "Netflix", "provider_id": 8},
    {"id": "disney", "name": "Disney+", "provider_id": 337},
    {"id": "prime", "name": "Prime Video", "provider_id": 119},
    {"id": "hbo", "name": "Max (HBO)", "provider_id": 1899}
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

def get_tmdb_popular(provider_id, media_type):
    url = f"https://api.themoviedb.org/3/discover/{media_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "watch_region": "PT",
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
                time.sleep(0.08)  # Evita atingir o rate-limit do socket
                
                if imdb_id:
                    items.append({
                        "id": imdb_id,
                        "type": "movie" if media_type == "movie" else "series",
                        "name": title,
                        "poster": f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get("poster_path") else None
                    })
            return items
    except Exception as e:
        print(f"Erro ao consultar TMDB ({media_type}): {e}")
    return []

def main():
    os.makedirs("dist/catalog/movie", exist_ok=True)
    os.makedirs("dist/catalog/series", exist_ok=True)

    manifest_catalogs = []

    for prov in PROVIDERS:
        print(f"A descarregar dados de {prov['name']} (Portugal)...")
        
        # Filmes
        movies = get_tmdb_popular(prov["provider_id"], "movie")
        print(f"  -> Filmes: {len(movies)}")
        if movies:
            cat_id = f"{prov['id']}_pt_movies"
            with open(f"dist/catalog/movie/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": movies}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "movie",
                "id": cat_id,
                "name": f"{prov['name']} PT - Filmes"
            })

        # Séries
        series = get_tmdb_popular(prov["provider_id"], "tv")
        print(f"  -> Séries: {len(series)}")
        if series:
            cat_id = f"{prov['id']}_pt_series"
            with open(f"dist/catalog/series/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": series}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "series",
                "id": cat_id,
                "name": f"{prov['name']} PT - Séries"
            })

    manifest = {
        "id": "org.portugal.streaming.top",
        "version": "1.0.0",
        "name": "Streaming Portugal Populares",
        "description": "Filmes e Séries populares em Portugal (Netflix, Disney+, Prime, Max)",
        "resources": ["catalog"],
        "types": ["movie", "series"],
        "catalogs": manifest_catalogs
    }

    with open("dist/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nConcluído! {len(manifest_catalogs)} catálogos gerados com sucesso.")

if __name__ == "__main__":
    main()