import os
import json
import time
import re
import io
import shutil
import itertools
import random
from datetime import datetime

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    HTTPAdapter = None
    Retry = None
    BeautifulSoup = None

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageOps = None

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")
BASE_URL = os.environ.get("BASE_URL", "https://top-streaming-pt.vercel.app").rstrip("/")

TMDB_GENRES = {
    28: "Ação", 12: "Aventura", 16: "Animação", 35: "Comédia", 80: "Crime",
    99: "Documentário", 18: "Drama", 10751: "Família", 14: "Fantasia", 36: "História",
    27: "Terror", 10402: "Música", 9648: "Mistério", 10749: "Romance", 878: "Ficção científica",
    10770: "Cinema TV", 53: "Thriller", 10752: "Guerra", 37: "Faroeste",
    10759: "Ação e Aventura", 10762: "Infantil", 10763: "Notícias", 10764: "Reality",
    10765: "Sci-Fi e Fantasia", 10766: "Novela", 10767: "Talk Show", 10768: "Guerra e Política"
}

GENRE_MAP = {
    "Ação": ["Ação", "Ação e Aventura", "Action", "Action & Adventure"],
    "Aventura": ["Aventura", "Ação e Aventura", "Adventure", "Action & Adventure"],
    "Animação": ["Animação", "Animation"],
    "Comédia": ["Comédia", "Comedy"],
    "Crime": ["Crime"],
    "Documentário": ["Documentário", "Documentary"],
    "Drama": ["Drama"],
    "Família": ["Família", "Infantil", "Family", "Kids"],
    "Fantasia": ["Fantasia", "Sci-Fi e Fantasia", "Fantasy", "Sci-Fi & Fantasy"],
    "Ficção científica": ["Ficção científica", "Sci-Fi e Fantasia", "Sci-Fi", "Science Fiction", "Sci-Fi & Fantasy"],
    "Guerra": ["Guerra", "Guerra e Política", "War", "War & Politics"],
    "História": ["História", "History"],
    "Mistério": ["Mistério", "Mystery"],
    "Música": ["Música", "Music"],
    "Reality": ["Reality"],
    "Romance": ["Romance"],
    "Terror": ["Terror", "Horror"],
    "Thriller": ["Thriller", "Suspense"],
    "Faroeste": ["Faroeste", "Western"],
}

ALL_GENRES = list(GENRE_MAP.keys())

ENGLISH_GENRE_MAP = {
    "Action": "Ação",
    "Adventure": "Aventura",
    "Animation": "Animação",
    "Comedy": "Comédia",
    "Crime": "Crime",
    "Documentary": "Documentário",
    "Drama": "Drama",
    "Family": "Família",
    "Fantasy": "Fantasia",
    "Sci-Fi": "Ficção científica",
    "Science Fiction": "Ficção científica",
    "War": "Guerra",
    "History": "História",
    "Mystery": "Mistério",
    "Music": "Música",
    "Reality": "Reality",
    "Romance": "Romance",
    "Horror": "Terror",
    "Thriller": "Thriller",
    "Western": "Faroeste",
}


def filter_items_by_genre(items, genre_name):
    """Filtra itens procurando correspondências de géneros, incluindo variantes de TV e sinónimos."""
    aliases = {a.casefold() for a in GENRE_MAP.get(genre_name, [genre_name])}
    matched = []
    for item in items:
        item_genres = {g.casefold() for g in item.get("genres", [])}
        if aliases & item_genres:
            matched.append(item)
    return matched


if not TMDB_API_KEY and os.path.exists(".env"):
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TMDB_API_KEY="):
                    TMDB_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["TMDB_API_KEY"] = TMDB_API_KEY
                elif line.startswith("BASE_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"').strip("'").rstrip("/")
                    os.environ["BASE_URL"] = BASE_URL
                elif line.startswith("SCRAPER_API_KEY="):
                  SCRAPER_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                  os.environ["SCRAPER_API_KEY"] = SCRAPER_API_KEY
    except Exception:
        pass

if requests:
    session = requests.Session()
    retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
else:
    session = None

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Plataformas de streaming em Portugal
PROVIDERS = [
  {"id": "netflix", "name": "Netflix", "tmdb_id": 8, "flix_slug": "netflix", "jw_pkg": "nfx", "color": "#E50914"},
  {"id": "disney", "name": "Disney+", "tmdb_id": 337, "flix_slug": "disney-plus", "jw_pkg": "dnp", "color": "#0063e5"},
  {"id": "prime", "name": "Prime Video", "tmdb_id": 119, "flix_slug": "amazon-prime", "jw_pkg": "prv", "color": "#00a8e1"},
  {"id": "hbo", "name": "HBO", "tmdb_id": 1899, "flix_slug": "hbo-max", "jw_pkg": "hbm", "color": "#a855f7"},
  {"id": "apple", "name": "Apple TV+", "tmdb_id": 350, "flix_slug": "apple-tv", "jw_pkg": "atp", "color": "#ffffff"},
  {"id": "skyshowtime", "name": "SkyShowtime", "tmdb_id": 1773, "flix_slug": "skyshowtime", "jw_pkg": "sst", "color": "#00ff7f"},
]



def clean_title(title):
    cleaned = re.sub(r'^\d+\.?\s*', '', title)
    cleaned = re.sub(r'(?i)\b(season|temporada|series|limited series)\s*(\d+)?\b', '', cleaned)
    cleaned = re.sub(r'[\(\[].*?[\)\]]', '', cleaned)
    cleaned = re.sub(r'\s*[-:–—|]\s*$', '', cleaned)
    return cleaned.strip(' :-–—|')


def get_imdb_id(tmdb_id, media_type):
    if not TMDB_API_KEY:
        return None
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids"
    try:
        res = session.get(url, params={"api_key": TMDB_API_KEY}, timeout=7)
        if res.status_code == 200:
            return res.json().get("imdb_id")
    except Exception:
        pass
    return None


def search_tmdb_title(title, media_type):
    if not TMDB_API_KEY:
        return None
    search_type = "movie" if media_type == "movie" else "tv"
    queries = []
    for candidate in (title, clean_title(title)):
        if candidate and candidate.casefold() not in {query.casefold() for query in queries}:
            queries.append(candidate)

    try:
        results = []
        for query in queries:
            for language in ("pt-PT", "en-US", None):
                params = {"api_key": TMDB_API_KEY, "query": query, "page": 1}
                if language:
                    params["language"] = language
                res = session.get(
                    f"https://api.themoviedb.org/3/search/{search_type}",
                    params=params,
                    timeout=7,
                )
                results = res.json().get("results", []) if res.status_code == 200 else []
                if results:
                    break
            if results:
                break

        # Se não encontrou, tenta o outro tipo (ex: minissérie listada como movie ou tv).
        if not results:
            other_type = "tv" if search_type == "movie" else "movie"
            for query in queries:
                res = session.get(
                    f"https://api.themoviedb.org/3/search/{other_type}",
                    params={"api_key": TMDB_API_KEY, "query": query, "language": "en-US", "page": 1},
                    timeout=7,
                )
                results = res.json().get("results", []) if res.status_code == 200 else []
                if results:
                    search_type = other_type
                    break

        if results:
            best = results[0]
            actual_type = best.get("media_type", search_type)
            tmdb_id = best["id"]
            imdb_id = get_imdb_id(tmdb_id, actual_type)

            if imdb_id:
                name = best.get("name") if actual_type == "tv" else best.get("title")
                genre_ids = best.get("genre_ids", [])
                genres = [TMDB_GENRES[gid] for gid in genre_ids if gid in TMDB_GENRES]
                year_str = (best.get("release_date") or best.get("first_air_date") or "")[:4]
                vote_avg = best.get("vote_average")
                rating_str = str(round(vote_avg, 1)) if vote_avg and vote_avg > 0 else None
                backdrop_path = best.get("backdrop_path")
                background = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else None
                poster_path = best.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                overview = (best.get("overview") or "").strip()

                return {
                    "id": imdb_id,
                    "type": "series" if actual_type == "tv" else "movie",
                    "name": name or title,
                    "poster": poster_url,
                    "background": background,
                    "overview": overview,
                    "genres": genres,
                    "releaseInfo": year_str if year_str else None,
                    "imdbRating": rating_str,
                    "tmdb_id": tmdb_id,
                }
    except Exception as e:
        print(f"  [!] Erro TMDB ao procurar '{title}': {e}", flush=True)

    print(f"  [!] TMDB não resolveu '{title}' como {media_type}", flush=True)
    return None


def search_imdb_title(title, media_type):
    """Resolve títulos muito recentes que ainda não chegaram ao TMDB."""
    if not session:
        return None

    import unicodedata
    query = clean_title(title)
    query_unaccented = unicodedata.normalize('NFKD', query).encode('ascii', 'ignore').decode('ascii')
    query_slug = re.sub(r"[^a-z0-9]+", "_", query_unaccented.casefold()).strip("_")
    if not query_slug:
        return None

    expected_types = {"feature", "movie"} if media_type == "movie" else {"tvSeries", "tvMiniSeries"}
    normalized_query = re.sub(r"\W+", "", query_unaccented.casefold())
    try:
        res = session.get(
            f"https://v3.sg.media-imdb.com/suggestion/{query_slug[0]}/{query_slug}.json",
            headers=HEADERS,
            timeout=7,
        )
        results = res.json().get("d", []) if res.status_code == 200 else []
        for result in results:
            candidate = result.get("l", "")
            candidate_unaccented = unicodedata.normalize('NFKD', candidate).encode('ascii', 'ignore').decode('ascii')
            normalized_candidate = re.sub(r"\W+", "", candidate_unaccented.casefold())
            if normalized_candidate != normalized_query or result.get("qid") not in expected_types:
                continue
            imdb_id = result.get("id", "")
            if not re.fullmatch(r"tt\d+", imdb_id):
                continue
            image = result.get("i", {})
            year_val = result.get("y")
            print(f"  [i] IMDb resolveu '{title}' ({imdb_id})", flush=True)
            return {
                "id": imdb_id,
                "type": "movie" if media_type == "movie" else "series",
                "name": candidate or title,
                "poster": image.get("imageUrl"),
                "releaseInfo": str(year_val) if year_val else None,
                "overview": "",
                "genres": [],
            }
    except Exception as e:
        print(f"  [!] Erro IMDb ao procurar '{title}': {e}", flush=True)
    return None

def get_justwatch_top10(package_code, media_type):
    """
    Recolhe o Top 10 real de Portugal para a plataforma indicada via JustWatch GraphQL.
    """
    obj_type = "MOVIE" if media_type == "movie" else "SHOW"
    query = f"""
    {{
      popularTitles(country: PT, first: 10, filter: {{packages: ["{package_code}"], objectTypes: [{obj_type}]}}) {{
        edges {{
          node {{
            content(country: PT, language: "pt") {{
              title
            }}
          }}
        }}
      }}
    }}
    """
    try:
        res = session.post(
            "https://apis.justwatch.com/graphql",
            json={"query": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Content-Type": "application/json"},
            timeout=10
        )
        if res.status_code == 200:
            edges = res.json().get("data", {}).get("popularTitles", {}).get("edges", [])
            titles = [e["node"]["content"]["title"] for e in edges if e.get("node", {}).get("content", {}).get("title")]
            if titles:
                print(f"  [i] JustWatch Portugal ({package_code}): {len(titles)} títulos reais encontrados", flush=True)
                return titles
    except Exception as e:
        print(f"  [!] Erro JustWatch ({package_code}): {e}", flush=True)

    return []


def parse_flixpatrol_titles(html, media_type):
    """Extrai apenas a secção principal de filmes ou séries do FlixPatrol."""
    soup = BeautifulSoup(html, "html.parser")
    section_terms = {
        "movie": ("top 10 movies", "top ranked movies", "top 10 films", "top 10 movie"),
        "series": ("top 10 tv shows", "top ranked tv shows", "top 10 tv", "top 10 series", "top 10 shows"),
    }
    heading = next(
        (
            tag for tag in soup.find_all(["h2", "h3", "h4"])
            if any(term in tag.get_text(" ", strip=True).casefold() for term in section_terms[media_type])
        ),
        None,
    )
    if not heading:
        return []

    titles = []
    seen = set()
    for element in heading.find_all_next():
        if element is not heading and element.name in {"h2", "h3", "h4"}:
            break
        if element.name != "a" or "/title/" not in element.get("href", ""):
            continue
        title = re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()
        if len(title) < 2 or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        titles.append(title)
        if len(titles) == 10:
            break
    return titles


def get_flixpatrol_platform_data(platform_slug):
    """
    Recolhe simultaneamente os rankings oficiais de filmes e series da FlixPatrol num unico pedido.
    1. Tenta primeiro sem render (1 credito).
    2. Se nao obtiver os titulos (pois a FlixPatrol requer JS), tenta 1 vez com render (5 creditos)
       para garantir o Top 10 real oficial das plataformas em vez de aproximacoes por cliques.
    3. Se falhar, o script usa JustWatch PT como rede de seguranca.
    """
    if not session or not BeautifulSoup:
        return [], []
    if not SCRAPER_API_KEY:
        print("  [!] SCRAPER_API_KEY nao configurada.", flush=True)
        return [], []

    url = f"https://flixpatrol.com/top10/{platform_slug}/portugal/"

    # 1. Tentativa sem render (apenas 1 credito)
    try:
        response = session.get(
            "https://api.scraperapi.com/",
            params={"api_key": SCRAPER_API_KEY, "render": "false", "url": url},
            headers=HEADERS,
            timeout=25,
        )
        if response.status_code == 200:
            movie_titles = parse_flixpatrol_titles(response.text, "movie")
            series_titles = parse_flixpatrol_titles(response.text, "series")
            if movie_titles or series_titles:
                print(f"  [i] FlixPatrol ({platform_slug}) obtido sem render (1 credito)", flush=True)
                return movie_titles, series_titles
    except Exception as exc:
        print(f"  [!] FlixPatrol ({platform_slug}) tentativa sem render: {exc}", flush=True)

    # 2. Se sem render nao veio a tabela (Cloudflare ou JS rendering), faz 1 tentativa com render (5 creditos)
    try:
        print(f"  [i] A obter Top 10 real FlixPatrol ({platform_slug}) com render...", flush=True)
        rendered = session.get(
            "https://api.scraperapi.com/",
            params={
                "api_key": SCRAPER_API_KEY,
                "render": "true",
                "wait_for_selector": "h3, h2, a[href*='/title/']",
                "url": url,
            },
            headers=HEADERS,
            timeout=50,
        )
        if rendered.status_code == 200:
            movie_titles = parse_flixpatrol_titles(rendered.text, "movie")
            series_titles = parse_flixpatrol_titles(rendered.text, "series")
            if movie_titles or series_titles:
                print(f"  [i] FlixPatrol ({platform_slug}) Top 10 real obtido com sucesso via render", flush=True)
                return movie_titles, series_titles
    except Exception as exc:
        print(f"  [!] Erro FlixPatrol render ({platform_slug}): {exc}", flush=True)

    return [], []
def get_flixpatrol_top10(platform_slug, media_type):
    """Wrapper de retrocompatibilidade."""
    movies, series = get_flixpatrol_platform_data(platform_slug)
    return movies if media_type == "movie" else series


# Fallback via TMDB caso alguma fonte externa esteja indisponível
def get_tmdb_fallback(tmdb_provider_id, media_type):
    if not TMDB_API_KEY:
        return []
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
                    genre_ids = item.get("genre_ids", [])
                    genres = [TMDB_GENRES[gid] for gid in genre_ids if gid in TMDB_GENRES]
                    year_str = (item.get("release_date") or item.get("first_air_date") or "")[:4]
                    vote_avg = item.get("vote_average")
                    rating_str = str(round(vote_avg, 1)) if vote_avg and vote_avg > 0 else None
                    backdrop_path = item.get("backdrop_path")
                    background = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else None
                    poster_path = item.get("poster_path")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                    overview = (item.get("overview") or "").strip()

                    items.append({
                        "id": imdb_id,
                        "type": "movie" if media_type == "movie" else "series",
                        "name": name,
                        "poster": poster_url,
                        "background": background,
                        "overview": overview,
                        "genres": genres,
                        "releaseInfo": year_str if year_str else None,
                        "imdbRating": rating_str,
                        "tmdb_id": tmdb_id,
                    })
    except Exception as e:
        print(f"  [!] Erro Fallback TMDB: {e}", flush=True)
    return items


def resolve_titles_to_items(titles, media_type):
    items = []
    for title in titles:
        item = search_tmdb_title(title, media_type)
        if not item:
            item = search_imdb_title(title, media_type)
        if item and not any(existing["id"] == item["id"] for existing in items):
            item["type"] = media_type
            items.append(item)
        elif not item:
            print(f"  [!] Título descartado do catálogo {media_type}: {title}", flush=True)
        time.sleep(0.03)
    return items

def get_badge_font(size, bold=False):
    candidates = ['arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf', 'FreeSansBold.ttf'] if bold else ['arial.ttf', 'DejaVuSans.ttf', 'FreeSans.ttf']
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def draw_rank_badge(poster_bytes, rank):
    """
    Desenha uma pílula com o número de ranking (#1 a #10) no canto superior direito (evitando sobreposicao com o visto de reproducao do Stremio no canto esquerdo).
    Padroniza todos os posters para o rácio 2:3 exato (600x900px), garantindo posição
    100% idêntica e milimétrica do badge em qualquer filme ou série.
    """
    if not Image or not ImageDraw or not ImageFont:
        return poster_bytes

    try:
        raw_img = Image.open(io.BytesIO(poster_bytes))
        if raw_img.mode != "RGB":
            raw_img = raw_img.convert("RGB")

        TARGET_W, TARGET_H = 600, 900
        try:
            if ImageOps:
                img = ImageOps.fit(raw_img, (TARGET_W, TARGET_H), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            else:
                img = raw_img.resize((TARGET_W, TARGET_H), Image.Resampling.LANCZOS)
        except Exception:
            img = raw_img.resize((TARGET_W, TARGET_H), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS)

        overlay = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        margin_y = 28
        badge_h = 76
        radius = badge_h // 2  # 38px

        rank_text = f"#{rank}"
        accent_color = (255, 255, 255, 255)
        outline_color = (255, 255, 255, 120)
        fill_color = (10, 10, 20, 235)

        font_badge = get_badge_font(48, bold=True)
        text_bbox = draw.textbbox((0, 0), rank_text, font=font_badge)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        pad_x = 26
        badge_w = max(100, text_w + (2 * pad_x))

        # Canto superior direito (para nao colidir com o visto de visto/assistido do Stremio no canto superior esquerdo)
        margin_x = TARGET_W - badge_w - 28

        # Sombra suave para contraste em capas claras
        shadow_box = [
            margin_x + 3,
            margin_y + 4,
            margin_x + badge_w + 3,
            margin_y + badge_h + 4
        ]
        draw.rounded_rectangle(shadow_box, radius=radius, fill=(0, 0, 0, 160))

        # Pílula principal
        box = [margin_x, margin_y, margin_x + badge_w, margin_y + badge_h]
        draw.rounded_rectangle(
            box,
            radius=radius,
            fill=fill_color,
            outline=outline_color,
            width=3
        )

        # Texto centrado
        try:
            draw.text(
                (margin_x + badge_w / 2, margin_y + badge_h / 2),
                rank_text,
                font=font_badge,
                fill=accent_color,
                anchor="mm"
            )
        except TypeError:
            draw.text(
                (margin_x + (badge_w - text_w) / 2, margin_y + (badge_h - text_h) / 2),
                rank_text,
                font=font_badge,
                fill=accent_color
            )

        img_rgba = img.convert("RGBA")
        final_img = Image.alpha_composite(img_rgba, overlay).convert("RGB")
        output = io.BytesIO()
        final_img.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"  [!] Erro ao desenhar badge: {e}", flush=True)
        return poster_bytes


def apply_badges_to_catalog(items, cat_id, provider_name="Streaming"):
    """
    Desenha badges de ranking (#1-#10) nos posters e guarda em dist/posters.
    Mantém os metadados (géneros, sinopse, rating) originais e limpos para o Cinemeta/Stremio.
    """
    os.makedirs("dist/posters", exist_ok=True)
    new_cat_history = {}
    updated_items = []

    for rank, item in enumerate(items, 1):
        item_copy = dict(item)
        item_id = item_copy.get("id")

        if item_id:
            new_cat_history[item_id] = rank

        # Mantém a descrição original limpa se existir overview
        if "overview" in item_copy and not item_copy.get("description"):
            item_copy["description"] = item_copy["overview"]

        original_poster = item_copy.get("poster")
        if original_poster and Image and session:
            poster_filename = f"{cat_id}_{rank}.jpg"
            poster_path = f"dist/posters/{poster_filename}"
            try:
                res = session.get(original_poster, timeout=8)
                if res.status_code == 200:
                    badged_bytes = draw_rank_badge(res.content, rank)
                    if badged_bytes and len(badged_bytes) > 0:
                        with open(poster_path, "wb") as f:
                            f.write(badged_bytes)
                        if BASE_URL:
                            item_copy["poster"] = f"{BASE_URL}/posters/{poster_filename}"
                        else:
                            item_copy["poster"] = f"/posters/{poster_filename}"
            except Exception as e:
                print(f"  [!] Aviso: Não foi possível aplicar badge em '{item_copy.get('name')}': {e}", flush=True)

        updated_items.append(item_copy)

    return updated_items


def create_landing_page(featured_items=None):
    now_iso = datetime.utcnow().isoformat() + "Z"

    # Se não foram fornecidos itens, usa todos os posters dos catálogos locais.
    if not featured_items:
        featured_items = []
        for prov in PROVIDERS:
            cat_movie = f"dist/catalog/movie/{prov['id']}_pt_movies.json"
            cat_series = f"dist/catalog/series/{prov['id']}_pt_series.json"
            for catalog_path, media_label, cat_id in (
                (cat_movie, "Filme", f"{prov['id']}_pt_movies"),
                (cat_series, "Série", f"{prov['id']}_pt_series"),
            ):
                if not os.path.exists(catalog_path):
                    continue
                try:
                    with open(catalog_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
                for rank, item in enumerate(data.get("metas", []), 1):
                    local_poster = f"posters/{cat_id}_{rank}.jpg"
                    poster_src = local_poster if os.path.exists(f"dist/{local_poster}") else item.get("poster")
                    featured_items.append({
                        "platform": prov["name"],
                        "color": prov.get("color", "#7b5bf5"),
                        "title": item.get("name", "Destaque"),
                        "type": media_label,
                        "rank": rank,
                        "poster": poster_src,
                        "fallback_poster": item.get("poster")
                    })

    # Baralha e intercala itens para misturar completamente plataformas e posições de ranking (#1 a #10)
    rng = random.Random()
    pool_by_platform = {}
    for item in featured_items:
        pool_by_platform.setdefault(item.get("platform", "Streaming"), []).append(item)

    for p_items in pool_by_platform.values():
        rng.shuffle(p_items)

    mixed_items = []
    platforms = list(pool_by_platform.keys())
    rng.shuffle(platforms)

    last_platform = None
    last_rank = None
    while any(pool_by_platform.values()):
        avail = [p for p in platforms if pool_by_platform[p]]
        cand_platform = [p for p in avail if p != last_platform]
        pool_cand = cand_platform if cand_platform else avail
        cand_diff_rank = [p for p in pool_cand if pool_by_platform[p][0].get("rank") != last_rank]
        final_cand = cand_diff_rank if cand_diff_rank else pool_cand
        chosen = rng.choice(final_cand)
        item = pool_by_platform[chosen].pop(0)
        mixed_items.append(item)
        last_platform = chosen
        last_rank = item.get("rank")

    # Duas faixas horizontais contínuas; cada uma recebe títulos intercalados e variados.
    rows_html = []
    cards_per_row = 10
    total_needed = cards_per_row * 2
    marquee_pool = mixed_items[:total_needed] if len(mixed_items) >= total_needed else mixed_items
    for row_index in range(2):
      row_cards = ""
      for item in marquee_pool[row_index * cards_per_row:(row_index + 1) * cards_per_row]:
        title = item.get("title", "")
        poster = item.get("poster", "")
        fallback = item.get("fallback_poster", "")
        row_cards += (
          '          <article class="peek-card">\n'
          '            <div class="peek-poster-box">\n'
          f'              <img src="{poster}" alt="{title}" loading="eager" decoding="async" onerror="this.src=\'{fallback}\'">\n'
          '            </div>\n'
          '          </article>\n'
        )
      if row_cards:
        rows_html.append(f'        <div class="peek-track peek-track-{row_index}">\n{row_cards}{row_cards}        </div>')
    rows_html = "\n".join(rows_html)

    style_css = """* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background-color: #1c1c1e;
  color: #f5f5f7;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  -webkit-font-smoothing: antialiased;
}
.wrapper {
  max-width: 900px;
  width: 100%;
  text-align: center;
  margin: 0 auto;
}
.main-logo {
  display: block;
  margin: 0 auto 20px;
  max-width: 100%;
  height: auto;
  image-rendering: -webkit-optimize-contrast;
  image-rendering: crisp-edges;
  user-select: none;
  -webkit-user-drag: none;
}
p.subtitle {
  font-size: 14px;
  color: #a1a1aa;
  margin-bottom: 16px;
  line-height: 1.5;
}
.features-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
}
.feature-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background-color: #27272a;
  border: 1px solid #3f3f46;
  color: #a1a1aa;
  font-size: 12px;
  font-weight: 500;
  padding: 5px 12px;
  border-radius: 9999px;
}
.feature-pill svg {
  width: 13px;
  height: 13px;
  opacity: 0.8;
  flex-shrink: 0;
}
.platform-customizer {
  width: 100%;
  max-width: 480px;
  margin: 0 auto 20px auto;
}
.customizer-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  background-color: #27272a;
  border: 1px solid #3f3f46;
  color: #e4e4e7;
  padding: 11px 15px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  font-family: inherit;
  outline: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.customizer-btn:hover {
  background-color: #323238;
  border-color: #52525b;
  color: #ffffff;
}
.customizer-btn:active {
  transform: scale(0.99);
}
.customizer-btn.open {
  border-color: #52525b;
  background-color: #2e2e33;
}
.customizer-btn-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.customizer-btn-left svg {
  width: 17px;
  height: 17px;
  color: #a1a1aa;
  flex-shrink: 0;
}
.customizer-btn-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.customizer-counter {
  font-size: 11px;
  font-weight: 600;
  background: #18181b;
  border: 1px solid #3f3f46;
  color: #4ade80;
  padding: 2px 8px;
  border-radius: 9999px;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}
.customizer-chevron {
  width: 15px;
  height: 15px;
  color: #a1a1aa;
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.customizer-btn.open .customizer-chevron {
  transform: rotate(180deg);
}
.customizer-drawer {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  transition: max-height 0.3s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s ease, margin 0.25s ease;
  margin-top: 0;
}
.customizer-drawer.open {
  max-height: 350px;
  opacity: 1;
  margin-top: 10px;
}
.customizer-panel {
  background-color: #222226;
  border: 1px solid #38383e;
  border-radius: 10px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
.customizer-hint {
  font-size: 11px;
  color: #71717a;
  margin-bottom: 8px;
  text-align: center;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background-color: #1f1f23;
  border: 1px solid #38383e;
  color: #d4d4d8;
  font-size: 11px;
  font-weight: 500;
  padding: 7px 12px;
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
  font-family: inherit;
  outline: none;
}
.tag svg { height: 12px; width: auto; opacity: 0.9; fill: currentColor; }
.tag:hover {
  background-color: #2a2a2f;
  border-color: #52525b;
  color: #ffffff;
  transform: translateY(-1px);
}
.tag:active {
  transform: scale(0.96);
}
.tag.inactive {
  opacity: 0.35;
  background-color: #18181b;
  border: 1px dashed #2e2e33;
  color: #71717a;
  filter: grayscale(100%);
  text-decoration: line-through;
  transform: none;
}
.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
  padding: 14px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  border: none;
  font-family: inherit;
}
.btn:active {
  transform: scale(0.98);
}
.btn.disabled {
  opacity: 0.4;
  pointer-events: none;
  cursor: not-allowed;
}
.btn-stremio {
  background-color: #7b5bf5;
  color: #ffffff;
  margin-bottom: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}
.btn-stremio:hover {
  background-color: #6a4ce0;
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
}
.btn-outline {
  background-color: #27272a;
  color: #a1a1aa;
  border: 1px solid #3f3f46;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.btn-outline:hover {
  background-color: #323238;
  border-color: #52525b;
  color: #f5f5f7;
  transform: translateY(-1px);
}
.btn svg { width: 20px; height: 20px; }
.sneak-peek-section {
  margin-top: 32px;
  text-align: center;
}
.peek-marquee {
  position: relative;
  overflow: hidden;
  padding: 8px 0 12px;
  margin: 0 -12px;
  -webkit-mask-image: linear-gradient(to right, transparent, #000 4%, #000 96%, transparent);
  mask-image: linear-gradient(to right, transparent, #000 4%, #000 96%, transparent);
}
.peek-gallery-drift {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.peek-track {
  display: flex;
  width: max-content;
  gap: 8px;
  animation: gallery-drift 140s linear infinite;
  will-change: transform;
}
.peek-track-1 { animation-duration: 155s; animation-direction: reverse; }
.peek-marquee:hover .peek-track { animation-play-state: paused; }
@keyframes gallery-drift {
  from { transform: translateX(0); }
  to { transform: translateX(calc(-50% - 4px)); }
}
.peek-card {
  position: relative;
  width: auto;
  background: transparent;
  border-radius: 6px;
  overflow: hidden;
  text-align: left;
}
.peek-poster-box {
  position: relative;
  width: 108px;
  height: 162px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #15151a;
  border-radius: 6px;
  border: 1px solid #2e2e33;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease;
}
.peek-card:hover .peek-poster-box {
  transform: scale(1.03);
  border-color: #52525b;
}
.peek-poster-box img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
  display: block;
}
.footer {
  margin-top: 32px;
  font-size: 12px;
  color: #52525b;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.schedule { color: #71717a; }
.version { color: #3f3f46; font-size: 11px; margin-top: 4px; }
@media (max-width: 520px) {
  .peek-marquee {
    margin: 0 -8px;
    padding-top: 6px;
  }
  .peek-poster-box {
    width: 82px;
    height: 123px;
  }
}"""

    html_content = f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Top 10 Streams PT - Stremio extension</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <div class="wrapper">
    <img src="logo.png" alt="Top 10 Streams PT" class="main-logo" draggable="false" onerror="this.style.display='none'">

    <p class="subtitle">Extensão para o Stremio com o TOP 10 do momento nas principais plataformas de streaming em Portugal.</p>
    <div class="features-row">
      <div class="feature-pill">
        <svg viewBox="0 0 20 20" fill="currentColor"><path d="M2 4a1 1 0 011-1h14a1 1 0 010 2H3a1 1 0 01-1-1zm0 5a1 1 0 011-1h14a1 1 0 010 2H3a1 1 0 01-1-1zm0 5a1 1 0 011-1h8a1 1 0 010 2H3a1 1 0 01-1-1z"/></svg>
        Top 10 por plataforma
      </div>
      <div class="feature-pill">
        <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 3a1 1 0 011-1h12a1 1 0 011 1v3a1 1 0 01-.293.707L12 11.414V15a1 1 0 01-.553.894l-4 2A1 1 0 016 17v-5.586L3.293 6.707A1 1 0 013 6V3z" clip-rule="evenodd"/></svg>
        Filtro por género
      </div>
    </div>
    <div class="platform-customizer">
      <button type="button" class="customizer-btn" id="customizer-toggle" onclick="toggleCustomizer()" aria-expanded="false">
        <div class="customizer-btn-left">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
            <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span>Personalizar Plataformas</span>
        </div>
        <div class="customizer-btn-right">
          <span class="customizer-counter" id="platform-counter">6 de 6 ativas</span>
          <svg viewBox="0 0 20 20" fill="currentColor" class="customizer-chevron" id="customizer-chevron">
            <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
          </svg>
        </div>
      </button>

      <div class="customizer-drawer" id="customizer-drawer">
        <div class="customizer-panel">
          <p class="customizer-hint">Clica numa plataforma para incluir ou retirar do teu addon:</p>
          <div class="tags" id="platform-tags" title="Clica numa plataforma para incluir ou retirar do addon">
          <button type="button" class="tag" data-provider="netflix" onclick="toggleProvider(this)">
            <svg viewBox="0 0 24 24" style="color: #E50914;"><path fill="currentColor" d="M6.3 21.5L6.3 2.5L9.5 2.5L16.5 15.5L16.5 2.5L19.7 2.5L19.7 21.5L16.5 21.5L9.5 8.5L9.5 21.5Z"/></svg>
            Netflix
          </button>

          <button type="button" class="tag" data-provider="disney" onclick="toggleProvider(this)">
            <svg viewBox="0 0 24 24" style="color: #0063e5;">
              <path fill="currentColor" d="M12.92 11.23c-.73-.24-1.78-.45-2.9-.6-1.08 1.4-2.4 2.87-4.14 4.02-1.2.78-2.22 1.14-2.92 1.14-.65 0-1.02-.32-1.02-.9 0-.82.68-1.98 1.96-3.32 1.36-1.44 3.1-2.6 4.95-3.46C7.54 5.92 6.55 4.7 6.55 3.8c0-.6.38-1 1.1-1 .78 0 1.83.6 2.86 1.7.53-.1.97-.15 1.3-.15 1.15 0 2 .3 2.37.82.4.52.44 1.13.13 1.7-.12.22-.3.42-.55.62 1.63.15 3.14.4 4.4.78 1.67.5 2.65 1.1 2.65 1.75 0 .5-.47.92-1.28 1.17-.6.18-1.34.3-2.12.3-.57 0-1.15-.04-1.73-.13.1.25.17.5.17.77 0 .5-.15.93-.43 1.3-.28.37-.67.55-1.17.55-.47 0-.9-.16-1.27-.47zm-1.8-1.5c-1.37.95-2.73 2.1-3.97 3.32-.82.8-1.25 1.5-1.25 1.95 0 .15.07.25.2.25.26 0 .9-.28 1.75-.82 1.34-.84 2.4-1.95 3.12-3.1-1.07-.46-2.02-1-2.8-1.57zm1.1-1.98c.5-.83 1-1.77 1.4-2.74-.83.35-1.6.85-2.3 1.48.33.4.63.83.9 1.26zm3.22 1.98c-1.08-.34-2.38-.55-3.8-.65-.18.77-.45 1.5-.83 2.15 1.3-.14 2.32-.38 3-.73.47-.2.7-.42.7-.63 0-.1-.13-.23-.38-.34l-1.3-.4-.14.6z"/>
              <path fill="currentColor" d="M22.5 10h-2.5V7.5h-1.5V10h-2.5v1.5h2.5v2.5h1.5v-2.5h2.5z"/>
            </svg>
            Disney+
          </button>

          <button type="button" class="tag" data-provider="prime" onclick="toggleProvider(this)">
            <svg viewBox="0 0 24 24" style="color: #00a8e1;"><path fill="currentColor" d="M12 18C7.5 18 4 15.5 3 12C4.5 14.5 8 16 12 16C16 16 19.5 14.5 21 12C20 15.5 16.5 18 12 18Z"/></svg>
            Prime Video
          </button>

          <button type="button" class="tag" data-provider="hbo" onclick="toggleProvider(this)">
            <svg viewBox="0 0 24 24" style="color: #a855f7;">
              <path fill="currentColor" d="M13.6 15.39h-2.92V8.61h2.92c1.78 0 2.82.95 2.82 2.38v.03c0 .87-.4 1.54-1.07 1.97.83.35 1.34 1.12 1.34 2.06v.03c0 1.5-1.12 2.5-3.1 2.5zm-1.17-3.8h.98c.84 0 1.32-.4 1.32-1.02v-.03c0-.68-.5-.98-1.28-.98h-1.02v2.03zm0 2.65h1.16c.86 0 1.45-.44 1.45-1.1v-.02c0-.75-.62-1.12-1.46-1.12h-1.15v2.24zM8.33 15.39H6.58v-2.85H2.9v2.85H1.15V8.61H2.9v2.66h3.68V8.61h1.75v6.78zM19.14 15.5c2.14 0 3.7-1.57 3.7-3.48v-.03c0-1.92-1.55-3.5-3.7-3.5s-3.7 1.57-3.7 3.48v.03c0 1.92 1.55 3.5 3.7 3.5zm0-1.47c-1.15 0-1.94-.92-1.94-2.01v-.03c0-1.1.8-2.02 1.94-2.02s1.95.91 1.95 2.01v.03c0 1.1-.8 2.02-1.95 2.02z"/>
            </svg>
            HBO
          </button>

          <button type="button" class="tag" data-provider="apple" onclick="toggleProvider(this)">
            <svg viewBox="0 0 384 512" style="color: #ffffff;"><path fill="currentColor" d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z"/></svg>
            Apple TV+
          </button>

          <button type="button" class="tag" data-provider="skyshowtime" onclick="toggleProvider(this)">
            <svg viewBox="0 0 24 24" style="color: #00ff7f;"><path fill="currentColor" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            SkyShowtime
          </button>
        </div>
        </div>
      </div>
    </div>

    <a id="install-btn" href="#" class="btn btn-stremio">
      <svg viewBox="0 0 24 24" style="fill: currentColor;">
        <path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5a2.5 2.5 0 0 1 0 5H2v4c0 1.1.9 2 2 2h3.8v-1.5a2.5 2.5 0 0 1 5 0V21H17c1.1 0 2-.9 2-2v-4h1.5a2.5 2.5 0 0 0 0-5z"/>
      </svg>
      Instalar no Stremio
    </a>

    <button id="copy-btn" onclick="copyManifestUrl()" class="btn btn-outline">
      <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
        <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
      </svg>
      Copiar Manifest
    </button>

    <div class="sneak-peek-section">
      <div class="peek-marquee" aria-label="Títulos em destaque">
        <div class="peek-gallery-drift">
      {rows_html}
        </div>
      </div>
    </div>

    <div class="footer">
      <span id="time-ago" data-time="{now_iso}">Atualizado recentemente</span>
      <span class="schedule">Atualiza todos os dias às 12h30 UTC</span>
      <span class="version">v1.1.0</span>
    </div>
  </div>

  <script>
    const ALL_PROVIDERS = ['apple', 'disney', 'hbo', 'netflix', 'prime', 'skyshowtime'];
    let currentManifestUrl = '';

    function getBaseHostUrl() {{
      return window.location.origin;
    }}

    function toggleCustomizer() {{
      const btn = document.getElementById('customizer-toggle');
      const drawer = document.getElementById('customizer-drawer');
      const isOpen = drawer.classList.toggle('open');
      btn.classList.toggle('open', isOpen);
      btn.setAttribute('aria-expanded', isOpen);
    }}

    function toggleProvider(element) {{
      element.classList.toggle('inactive');
      updateManifestUrls();
    }}

    function updateManifestUrls() {{
      const activeTags = Array.from(document.querySelectorAll('.tag:not(.inactive)'));
      const selected = activeTags.map(el => el.getAttribute('data-provider')).sort();
      const installBtn = document.getElementById('install-btn');
      const copyBtn = document.getElementById('copy-btn');
      const counter = document.getElementById('platform-counter');
      const origin = getBaseHostUrl();

      if (counter) {{
        counter.textContent = `${{selected.length}} de ${{ALL_PROVIDERS.length}} ativas`;
        if (selected.length === ALL_PROVIDERS.length) {{
          counter.style.color = '#34d399';
          counter.style.background = 'rgba(16, 185, 129, 0.1)';
          counter.style.borderColor = 'rgba(16, 185, 129, 0.25)';
        }} else if (selected.length > 0) {{
          counter.style.color = '#fbbf24';
          counter.style.background = 'rgba(245, 158, 11, 0.1)';
          counter.style.borderColor = 'rgba(245, 158, 11, 0.25)';
        }} else {{
          counter.style.color = '#f87171';
          counter.style.background = 'rgba(239, 68, 68, 0.1)';
          counter.style.borderColor = 'rgba(239, 68, 68, 0.25)';
        }}
      }}

      if (selected.length === 0) {{
        installBtn.classList.add('disabled');
        installBtn.removeAttribute('href');
        copyBtn.classList.add('disabled');
        currentManifestUrl = '';
        return;
      }}

      installBtn.classList.remove('disabled');
      copyBtn.classList.remove('disabled');

      if (selected.length === ALL_PROVIDERS.length) {{
        currentManifestUrl = origin + '/manifest.json';
      }} else {{
        currentManifestUrl = origin + '/c/' + selected.join(',') + '/manifest.json';
      }}

      const stremioUrl = currentManifestUrl.replace(/^https?:\\/\\//, 'stremio://');
      installBtn.href = stremioUrl;
    }}

    function copyManifestUrl() {{
      if (!currentManifestUrl) return;
      navigator.clipboard.writeText(currentManifestUrl);
      const btn = document.getElementById('copy-btn');
      btn.innerHTML = '<span style="color:#34d399; display:inline-flex; align-items:center; gap:6px;">✔ Link Copiado!</span>';
      setTimeout(() => {{
        btn.innerHTML = `
          <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;">
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
            <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
          </svg>
          Copiar Manifest
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

    function initFromUrl() {{
      const path = window.location.pathname;
      const match = path.match(/\\/c\\/([^\\/]+)/);
      const urlParams = new URLSearchParams(window.location.search);
      const queryP = urlParams.get('p') || urlParams.get('platforms');

      const configStr = match ? match[1] : queryP;
      if (configStr) {{
        const allowed = configStr.toLowerCase().split(',');
        document.querySelectorAll('.tag').forEach(el => {{
          const prov = el.getAttribute('data-provider');
          if (allowed.includes(prov)) {{
            el.classList.remove('inactive');
          }} else {{
            el.classList.add('inactive');
          }}
        }});
      }}
      updateManifestUrls();
    }}

    initFromUrl();
    updateTime();
    setInterval(updateTime, 60000);
  </script>
</body>
</html>
"""
    with open("dist/style.css", "w", encoding="utf-8") as f:
        f.write(style_css)

    with open("dist/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    with open("dist/configure.html", "w", encoding="utf-8") as f:
        f.write(html_content)



def main():
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY não foi encontrada nas variáveis de ambiente.")

    os.makedirs("dist/catalog/movie", exist_ok=True)
    os.makedirs("dist/catalog/series", exist_ok=True)
    os.makedirs("dist/posters", exist_ok=True)
    os.makedirs("dist/c", exist_ok=True)

    # Gerar vercel.json com Rewrites para URLs personalizadas e CORS headers
    vercel_config = {
        "rewrites": [
            {"source": "/c/:config/catalog/:path*", "destination": "/catalog/:path*"},
            {"source": "/c/:config/posters/:path*", "destination": "/posters/:path*"},
            {"source": "/c/:config/logo.png", "destination": "/logo.png"},
            {"source": "/c/:config/style.css", "destination": "/style.css"},
            {"source": "/c/:config/configure", "destination": "/index.html"},
            {"source": "/c/:config", "destination": "/index.html"},
            {"source": "/configure", "destination": "/index.html"}
        ],
        "headers": [
            {
                "source": "/posters/(.*)",
                "headers": [
                    {"key": "Access-Control-Allow-Origin", "value": "*"},
                    {"key": "Access-Control-Allow-Methods", "value": "GET, HEAD, OPTIONS"},
                    {"key": "Cache-Control", "value": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400"}
                ]
            },
            {
                "source": "/catalog/(.*)",
                "headers": [
                    {"key": "Access-Control-Allow-Origin", "value": "*"},
                    {"key": "Access-Control-Allow-Methods", "value": "GET, HEAD, OPTIONS"},
                    {"key": "Cache-Control", "value": "public, max-age=1800, s-maxage=86400, stale-while-revalidate=86400"}
                ]
            },
            {
                "source": "/(.*)manifest.json",
                "headers": [
                    {"key": "Access-Control-Allow-Origin", "value": "*"},
                    {"key": "Access-Control-Allow-Methods", "value": "GET, HEAD, OPTIONS"},
                    {"key": "Cache-Control", "value": "public, max-age=1800, s-maxage=86400, stale-while-revalidate=86400"}
                ]
            },
            {
                "source": "/(.*)",
                "headers": [
                    {"key": "Access-Control-Allow-Origin", "value": "*"},
                    {"key": "Access-Control-Allow-Methods", "value": "GET, HEAD, OPTIONS"},
                    {"key": "Cache-Control", "value": "public, max-age=1800, s-maxage=86400, stale-while-revalidate=86400"}
                ]
            }
        ]
    }
    with open("dist/vercel.json", "w", encoding="utf-8") as f:
        json.dump(vercel_config, f, indent=2)
    print("[i] vercel.json com rewrites e CORS headers gerado.", flush=True)

    if os.path.exists("img/logo.png"):
        shutil.copy("img/logo.png", "dist/logo.png")

    manifest_catalogs = []
    featured_items = []

    for prov in PROVIDERS:
        print(f"\n--- A processar {prov['name']} ---", flush=True)

        # Se for um push de codigo normal (nao o agendamento diario) e ja existirem dados gerados,
        # reutiliza os catalogos para poupar 100% das moedas da ScraperAPI.
        existing_movie_cat = f"dist/catalog/movie/{prov['id']}_pt_movies.json"
        existing_series_cat = f"dist/catalog/series/{prov['id']}_pt_series.json"
        should_reuse_local = (
            os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("FORCE_SCRAPE", "").lower() != "true"
            and os.path.exists(existing_movie_cat)
            and os.path.exists(existing_series_cat)
        )

        movie_titles = []
        series_titles = []

        if should_reuse_local:
            try:
                with open(existing_movie_cat, "r", encoding="utf-8") as f:
                    movie_titles = [m.get("name") for m in json.load(f).get("metas", []) if m.get("name")]
                with open(existing_series_cat, "r", encoding="utf-8") as f:
                    series_titles = [s.get("name") for s in json.load(f).get("metas", []) if s.get("name")]
                if movie_titles or series_titles:
                    print(f"  [i] Catalogo local reutilizado para {prov['name']} (0 moedas gastas no git push).", flush=True)
            except Exception:
                movie_titles, series_titles = [], []

        if not movie_titles and not series_titles:
            movie_titles, series_titles = get_flixpatrol_platform_data(prov["flix_slug"])
        if movie_titles:
            print(f"  [i] FlixPatrol ({prov['flix_slug']}, movie): {len(movie_titles)} títulos", flush=True)
        else:
            print("  [i] FlixPatrol indisponível para filmes; a usar fallback JustWatch...", flush=True)
            movie_titles = get_justwatch_top10(prov.get("jw_pkg", ""), "movie") if prov.get("jw_pkg") else []

        if series_titles:
            print(f"  [i] FlixPatrol ({prov['flix_slug']}, series): {len(series_titles)} títulos", flush=True)
        else:
            print("  [i] FlixPatrol indisponível para séries; a usar fallback JustWatch...", flush=True)
            series_titles = get_justwatch_top10(prov.get("jw_pkg", ""), "series") if prov.get("jw_pkg") else []

        movie_items = resolve_titles_to_items(movie_titles, "movie")
        if not movie_items:
            print(f"  [i] Sem dados reais, a usar fallback TMDB ({prov['name']} Filmes)...", flush=True)
            movie_items = get_tmdb_fallback(prov["tmdb_id"], "movie")

        print(f"  -> Filmes encontrados: {len(movie_items)}/10", flush=True)
        if movie_items:
            cat_id = f"{prov['id']}_pt_movies"
            movie_items = apply_badges_to_catalog(movie_items, cat_id, prov["name"])
            for rank, item in enumerate(movie_items, 1):
              featured_items.append({
                "platform": prov["name"],
                "color": prov.get("color", "#7b5bf5"),
                "title": item["name"],
                "type": "Filme",
                "rank": rank,
                "poster": item.get("poster") or f"posters/{cat_id}_{rank}.jpg",
                "fallback_poster": item.get("poster")
              })

            clean_movie_items = []
            for it in movie_items:
                clean_movie_items.append({k: v for k, v in it.items() if not k.startswith("_") and v is not None})

            with open(f"dist/catalog/movie/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": clean_movie_items}, f, ensure_ascii=False)

            # Gerar catálogos filtrados para TODOS os géneros possíveis
            os.makedirs(f"dist/catalog/movie/{cat_id}", exist_ok=True)
            for genre in ALL_GENRES:
                genre_items = filter_items_by_genre(clean_movie_items, genre)
                with open(f"dist/catalog/movie/{cat_id}/genre={genre}.json", "w", encoding="utf-8") as f:
                    json.dump({"metas": genre_items}, f, ensure_ascii=False)

            # Também cria ficheiros para aliases em inglês (ex: Action, Drama, Horror) para compatibilidade universal
            for en_genre, pt_genre in ENGLISH_GENRE_MAP.items():
                en_items = filter_items_by_genre(clean_movie_items, pt_genre)
                with open(f"dist/catalog/movie/{cat_id}/genre={en_genre}.json", "w", encoding="utf-8") as f:
                    json.dump({"metas": en_items}, f, ensure_ascii=False)

            genre_extra = [{"name": "genre", "isRequired": False, "options": ALL_GENRES}]
            manifest_catalogs.append({
                "type": "movie",
                "id": cat_id,
                "name": f"{prov['name']} Top 10",
                "pageSize": 10,
                "showInHome": True,
                "extra": genre_extra + [{"name": "skip", "isRequired": False}]
            })

        series_items = resolve_titles_to_items(series_titles, "series")
        if not series_items:
            print(f"  [i] Sem dados reais, a usar fallback TMDB ({prov['name']} Séries)...", flush=True)
            series_items = get_tmdb_fallback(prov["tmdb_id"], "series")

        print(f"  -> Séries encontradas: {len(series_items)}/10", flush=True)
        if series_items:
            cat_id = f"{prov['id']}_pt_series"
            series_items = apply_badges_to_catalog(series_items, cat_id, prov["name"])
            for rank, item in enumerate(series_items, 1):
              featured_items.append({
                "platform": prov["name"],
                "color": prov.get("color", "#7b5bf5"),
                "title": item["name"],
                "type": "Série",
                "rank": rank,
                "poster": item.get("poster") or f"posters/{cat_id}_{rank}.jpg",
                "fallback_poster": item.get("poster")
              })

            clean_series_items = []
            for it in series_items:
                clean_series_items.append({k: v for k, v in it.items() if not k.startswith("_") and v is not None})

            with open(f"dist/catalog/series/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": clean_series_items}, f, ensure_ascii=False)

            # Gerar catálogos filtrados para TODOS os géneros possíveis
            os.makedirs(f"dist/catalog/series/{cat_id}", exist_ok=True)
            for genre in ALL_GENRES:
                genre_items = filter_items_by_genre(clean_series_items, genre)
                with open(f"dist/catalog/series/{cat_id}/genre={genre}.json", "w", encoding="utf-8") as f:
                    json.dump({"metas": genre_items}, f, ensure_ascii=False)

            # Também cria ficheiros para aliases em inglês (ex: Action, Drama, Horror) para compatibilidade universal
            for en_genre, pt_genre in ENGLISH_GENRE_MAP.items():
                en_items = filter_items_by_genre(clean_series_items, pt_genre)
                with open(f"dist/catalog/series/{cat_id}/genre={en_genre}.json", "w", encoding="utf-8") as f:
                    json.dump({"metas": en_items}, f, ensure_ascii=False)

            genre_extra = [{"name": "genre", "isRequired": False, "options": ALL_GENRES}]
            manifest_catalogs.append({
                "type": "series",
                "id": cat_id,
                "name": f"{prov['name']} Top 10",
                "pageSize": 10,
                "showInHome": True,
                "extra": genre_extra + [{"name": "skip", "isRequired": False}]
            })

    # 1. Manifest Padrão (todas as plataformas)
    manifest = {
        "id": "pt.top-streaming",
        "version": "1.1.0",
        "name": "TOP 10 Portugal (Filmes & Séries)",
        "description": "TOP 10 do momento na Netflix, Disney+, Prime Video, HBO, Apple TV+ e SkyShowtime em Portugal",
        "logo": f"{BASE_URL}/logo.png",
        "resources": [
            "catalog"
        ],
        "types": [
            "movie",
            "series"
        ],
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False
        },
        "catalogs": manifest_catalogs
    }

    with open("dist/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 2. Gerar manifests personalizados para todas as combinações possíveis de plataformas
    all_provider_ids = sorted([p["id"] for p in PROVIDERS])
    combos_count = 0
    for r in range(1, len(all_provider_ids) + 1):
        for combo in itertools.combinations(all_provider_ids, r):
            combo_key = ",".join(combo)
            combo_dir = f"dist/c/{combo_key}"
            os.makedirs(combo_dir, exist_ok=True)

            selected_set = set(combo)
            filtered_catalogs = [
                cat for cat in manifest_catalogs
                if any(cat["id"].startswith(f"{pid}_pt_") for pid in selected_set)
            ]

            names = [p["name"] for p in PROVIDERS if p["id"] in selected_set]
            names_str = ", ".join(names)

            custom_manifest = {
                "id": f"pt.top-streaming.{combo_key.replace(',', '.')}",
                "version": "1.1.0",
                "name": "TOP 10 Portugal",
                "description": f"TOP 10 do momento ({names_str}) em Portugal",
                "logo": f"{BASE_URL}/logo.png",
                "resources": [
                    "catalog"
                ],
                "types": [
                    "movie",
                    "series"
                ],
                "behaviorHints": {
                    "configurable": True,
                    "configurationRequired": False
                },
                "catalogs": filtered_catalogs
            }

            with open(f"{combo_dir}/manifest.json", "w", encoding="utf-8") as f:
                json.dump(custom_manifest, f, ensure_ascii=False, indent=2)
            combos_count += 1

    print(f"[i] Gerados {combos_count} manifests personalizados em dist/c/*", flush=True)

    create_landing_page(featured_items)
    print(f"\nFinalizado com sucesso! {len(manifest_catalogs)} catálogos registados.", flush=True)


if __name__ == "__main__":
    main()