import os
import json
import time
import re
import io
import shutil
import itertools
from datetime import datetime, date, timedelta

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
HISTORY_FILE = "dist/history.json"
LOCAL_HISTORY = "history.json"

TMDB_GENRES = {
    28: "Ação", 12: "Aventura", 16: "Animação", 35: "Comédia", 80: "Crime",
    99: "Documentário", 18: "Drama", 10751: "Família", 14: "Fantasia", 36: "História",
    27: "Terror", 10402: "Música", 9648: "Mistério", 10749: "Romance", 878: "Ficção científica",
    10770: "Cinema TV", 53: "Thriller", 10752: "Guerra", 37: "Faroeste",
    10759: "Ação e Aventura", 10762: "Infantil", 10763: "Notícias", 10764: "Reality",
    10765: "Sci-Fi e Fantasia", 10766: "Novela", 10767: "Talk Show", 10768: "Guerra e Política"
}

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
  {"id": "disney", "name": "Disney+", "tmdb_id": 337, "flix_slug": "disney", "jw_pkg": "dnp", "color": "#0063e5"},
  {"id": "prime", "name": "Prime Video", "tmdb_id": 119, "flix_slug": "amazon-prime", "jw_pkg": "prv", "color": "#00a8e1"},
  {"id": "hbo", "name": "HBO", "tmdb_id": 1899, "flix_slug": "hbo-max", "jw_pkg": "hbm", "color": "#a855f7"},
  {"id": "apple", "name": "Apple TV+", "tmdb_id": 350, "flix_slug": "apple-tv", "jw_pkg": "atp", "color": "#ffffff"},
  {"id": "skyshowtime", "name": "SkyShowtime", "tmdb_id": 1773, "flix_slug": "skyshowtime", "jw_pkg": "sst", "color": "#00ff7f"},
]

NETFLIX_COUNTRY_SLUG = "portugal"


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

    query = clean_title(title)
    query_slug = re.sub(r"[^a-z0-9]+", "_", query.casefold()).strip("_")
    if not query_slug:
        return None

    expected_types = {"feature", "movie"} if media_type == "movie" else {"tvSeries", "tvMiniSeries"}
    normalized_query = re.sub(r"\W+", "", query.casefold())
    try:
        res = session.get(
            f"https://v3.sg.media-imdb.com/suggestion/{query_slug[0]}/{query_slug}.json",
            headers=HEADERS,
            timeout=7,
        )
        results = res.json().get("d", []) if res.status_code == 200 else []
        for result in results:
            candidate = result.get("l", "")
            normalized_candidate = re.sub(r"\W+", "", candidate.casefold())
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

def _last_published_sunday(reference=None):
    ref = reference or date.today()
    w = ref.weekday()
    if w == 6:
        days = 7
    elif w == 0:
        days = 8
    else:
        days = w + 1
    return ref - timedelta(days=days)


_last_sunday = _last_published_sunday


def get_netflix_official_top10(media_type):
    """
    media_type: 'films' ou 'tv'
    Tenta as ultimas 3 semanas publicadas.
    """
    candidate_sunday = _last_published_sunday()

    for _ in range(3):
        date_str = candidate_sunday.isoformat()
        url = f"https://top10.netflix.com/{NETFLIX_COUNTRY_SLUG}/{media_type}/{date_str}"
        try:
            res = session.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                table = soup.find("table")
                titles = []
                if table:
                    rows = table.select("tbody tr") or table.find_all("tr")[1:]
                    for row in rows[:10]:
                        cols = row.find_all("td")
                        if cols:
                            # O título está dentro da tag <button> ou precedido pelo ranking
                            btn = cols[0].find("button")
                            title_text = btn.get_text(strip=True) if btn else cols[0].get_text(strip=True)
                            title_text = re.sub(r'^\d+\.?\s*', '', title_text)
                            if title_text:
                                titles.append(title_text)
                if titles:
                    print(f"  [i] Netflix Top 10 ({media_type}) da semana de {date_str} ({len(titles)} títulos)", flush=True)
                    return titles
        except Exception as e:
            print(f"  [!] Erro ao obter Top 10 oficial da Netflix ({date_str}): {e}", flush=True)

        candidate_sunday -= timedelta(days=7)

    return []


# ---------------------------------------------------------------------------
# JUSTWATCH — rankings reais de streaming em Portugal
# 100% gratuito, oficial para Portugal, sem necessidade de chaves pagas.
# ---------------------------------------------------------------------------
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
        "movie": ("top 10 movies", "top ranked movies"),
        "series": ("top 10 tv shows", "top ranked tv shows"),
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


def get_flixpatrol_top10(platform_slug, media_type):
    """Recolhe o ranking FlixPatrol exclusivamente através do ScraperAPI."""
    if not session or not BeautifulSoup:
        return []
    url = f"https://flixpatrol.com/top10/{platform_slug}/portugal/"
    try:
        if not SCRAPER_API_KEY:
            print("  [!] SCRAPER_API_KEY não configurada; não foi possível consultar FlixPatrol.", flush=True)
            return []

        response = None
        try:
          response = session.get(
            "https://api.scraperapi.com/",
            # A ScraperAPI exige que o URL de destino seja o último parâmetro.
            params={"api_key": SCRAPER_API_KEY, "render": "false", "url": url},
            headers=HEADERS,
            timeout=30,
          )
        except Exception as exc:
          print(f"  [!] FlixPatrol proxy sem render falhou: {exc}", flush=True)
        if response is not None and response.status_code != 200:
          print(f"  [!] ScraperAPI respondeu HTTP {response.status_code} sem render ({platform_slug})", flush=True)
        titles = parse_flixpatrol_titles(response.text, media_type) if response is not None and response.status_code == 200 else []
        if response is not None and response.status_code == 200 and not titles:
          print(f"  [!] ScraperAPI respondeu sem a secção Top 10 ({platform_slug}, {media_type})", flush=True)
        if not titles:
          try:
            rendered = session.get(
              "https://api.scraperapi.com/",
              params={
                "api_key": SCRAPER_API_KEY,
                "render": "true",
                "wait_for_selector": "h3",
                "url": url,
              },
              headers=HEADERS,
              timeout=75,
            )
            if rendered.status_code == 200:
              titles = parse_flixpatrol_titles(rendered.text, media_type)
              if titles:
                print(f"  [i] FlixPatrol renderizado ({platform_slug}, {media_type})", flush=True)
            else:
              print(f"  [!] ScraperAPI respondeu HTTP {rendered.status_code} com render ({platform_slug})", flush=True)
          except Exception as exc:
            print(f"  [!] FlixPatrol proxy renderizado falhou: {exc}", flush=True)
        if titles:
            print(f"  [i] FlixPatrol via ScraperAPI ({platform_slug}, {media_type}): {len(titles)} títulos", flush=True)
        return titles
    except Exception as exc:
        print(f"  [!] Erro FlixPatrol ({platform_slug}): {exc}", flush=True)
        return []


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
            items.append(item)
        elif not item:
            print(f"  [!] Título descartado do catálogo {media_type}: {title}", flush=True)
        time.sleep(0.03)
    return items


# ---------------------------------------------------------------------------
# BADGES DE RANKING E HISTÓRICO DE VARIAÇÃO (+1, -1, =, NOVO)
# ---------------------------------------------------------------------------
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


def draw_rank_badge(poster_bytes, rank, variation):
    """
    Desenha uma pílula bem visível no canto superior esquerdo com a indicação de subida/queda/estreia.
    Padroniza todos os posters para o rácio 2:3 exato (600x900px), garantindo posição
    100% idêntica e milimétrica do badge em qualquer filme ou série.
    """
    if not Image or not ImageDraw or not ImageFont:
        return poster_bytes

    try:
        raw_img = Image.open(io.BytesIO(poster_bytes))
        if raw_img.mode != "RGB":
            raw_img = raw_img.convert("RGB")

        # 1. Normalizar dimensões para o formato padrão Stremio 2:3 (600x900)
        # ImageOps.fit corta/redimensiona proporcionalmente mantendo o centro
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

        # 2. Posição e dimensões exatas e fixas em todos os posters
        margin_x = 24
        margin_y = 24
        badge_h = 46
        radius = badge_h // 2  # 23px

        # 3. Configura texto e paleta cromática conforme a variação
        if variation.startswith('+'):
            var_text = f"▲ +{variation[1:]}"
            accent_color = (74, 222, 128, 255)       # Verde vivo
            outline_color = (74, 222, 128, 210)
            fill_color = (8, 26, 15, 240)
        elif variation.startswith('-'):
            var_text = f"▼ {variation[1:]}"
            accent_color = (248, 113, 113, 255)     # Vermelho claro
            outline_color = (248, 113, 113, 210)
            fill_color = (30, 10, 14, 240)
        elif variation in ('NOVO', 'ENTRADA'):
            var_text = "★ ENTRADA"
            accent_color = (250, 204, 21, 255)      # Dourado vivo
            outline_color = (250, 204, 21, 210)
            fill_color = (24, 18, 4, 240)
        else:
            var_text = "● ="
            accent_color = (226, 232, 240, 255)     # Prateado suave
            outline_color = (148, 163, 184, 180)
            fill_color = (15, 23, 42, 240)

        font_badge = get_badge_font(21, bold=True)
        text_bbox = draw.textbbox((0, 0), var_text, font=font_badge)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        pad_x = 16
        badge_w = max(70, text_w + (2 * pad_x))

        # 4. Sombra suave para contraste máximo em capas claras
        shadow_box = [
            margin_x + 2,
            margin_y + 3,
            margin_x + badge_w + 2,
            margin_y + badge_h + 3
        ]
        draw.rounded_rectangle(shadow_box, radius=radius, fill=(0, 0, 0, 140))

        # 5. Pílula principal com rebordo translúcido colorido
        box = [margin_x, margin_y, margin_x + badge_w, margin_y + badge_h]
        draw.rounded_rectangle(
            box,
            radius=radius,
            fill=fill_color,
            outline=outline_color,
            width=2
        )

        # 6. Desenhar texto perfeitamente centrado
        try:
            draw.text(
                (margin_x + badge_w / 2, margin_y + badge_h / 2),
                var_text,
                font=font_badge,
                fill=accent_color,
                anchor="mm"
            )
        except TypeError:
            draw.text(
                (margin_x + (badge_w - text_w) / 2, margin_y + (badge_h - text_h) / 2),
                var_text,
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


def load_history():
    for path in [HISTORY_FILE, LOCAL_HISTORY]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    # O GitHub Actions começa num checkout limpo. Recupera o histórico do último
    # deploy para as setas compararem com o ranking do dia anterior.
    if session and BASE_URL:
        try:
            res = session.get(f"{BASE_URL}/history.json", timeout=10)
            if res.status_code == 200:
                history = res.json()
                if isinstance(history, dict):
                    print("[i] Histórico de rankings recuperado do último deploy.", flush=True)
                    return history
        except Exception as e:
            print(f"[!] Não foi possível recuperar o histórico publicado: {e}", flush=True)
    return {}


def save_history(history):
    os.makedirs("dist", exist_ok=True)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        with open(LOCAL_HISTORY, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [!] Erro ao guardar histórico de rankings: {e}", flush=True)


def apply_badges_to_catalog(items, cat_id, history_dict, provider_name="Streaming"):
    """
    Calcula variações de ranking, desenha badges nos posters e guarda em dist/posters.
    Mantém os metadados (géneros, sinopse, rating) originais e limpos para o Cinemeta/Stremio.
    """
    os.makedirs("dist/posters", exist_ok=True)
    new_cat_history = {}
    updated_items = []

    for rank, item in enumerate(items, 1):
        item_copy = dict(item)
        item_id = item_copy.get("id")
        old_rank = history_dict.get(item_id) if history_dict else None

        if old_rank is None:
            variation = "ENTRADA"
        else:
            diff = old_rank - rank
            if diff > 0:
                variation = f"+{diff}"
            elif diff < 0:
                variation = f"{diff}"
            else:
                variation = "="

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
                    badged_bytes = draw_rank_badge(res.content, rank, variation)
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

    return updated_items, new_cat_history


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
                        "poster": poster_src,
                        "fallback_poster": item.get("poster")
                    })

    # Intercala fornecedores antes de repartir os posters pelas três rows.
    grouped_items = {provider["name"]: [] for provider in PROVIDERS}
    for item in featured_items:
      grouped_items.setdefault(item.get("platform", "Streaming"), []).append(item)
    mixed_items = []
    while any(grouped_items.values()):
      for provider in PROVIDERS:
        provider_items = grouped_items[provider["name"]]
        if provider_items:
          mixed_items.append(provider_items.pop(0))
      extra_platforms = [name for name in grouped_items if name not in {provider["name"] for provider in PROVIDERS}]
      for platform in extra_platforms:
        if grouped_items[platform]:
          mixed_items.append(grouped_items[platform].pop(0))

    # Duas faixas horizontais contínuas; cada uma recebe títulos intercalados.
    rows_html = []
    for row_index in range(2):
      row_cards = ""
      for item in mixed_items[:16][row_index * 8:(row_index + 1) * 8]:
        color = item.get("color", "#7b5bf5")
        platform = item.get("platform", "Streaming")
        title = item.get("title", "")
        m_type = item.get("type", "Top 1")
        poster = item.get("poster", "")
        fallback = item.get("fallback_poster", "")
        row_cards += (
          '          <article class="peek-card">\n'
          '            <div class="peek-poster-box">\n'
          f'              <img src="{poster}" alt="{title}" loading="eager" decoding="async" onerror="this.src=\'{fallback}\'">\n'
          '            </div>\n'
          '            <div class="peek-card-info">\n'
          f'              <div class="peek-card-platform" style="color: {color};">{platform}</div>\n'
          f'              <div class="peek-card-title" title="{title}">{title}</div>\n'
          f'              <div class="peek-card-type">{m_type}</div>\n'
          '            </div>\n'
          '          </article>\n'
        )
      if row_cards:
        rows_html.append(f'        <div class="peek-track peek-track-{row_index}">\n{row_cards}{row_cards}        </div>')
    rows_html = "\n".join(rows_html)

    html_content = f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Top 10 Streams PT - Stremio extension</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
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
      max-width: 900px;
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
      margin-bottom: 24px;
      line-height: 1.5;
    }}
    .tags-heading {{
      font-size: 13px;
      font-weight: 500;
      color: #a1a1aa;
      margin-bottom: 12px;
      letter-spacing: 0.01em;
    }}

    .tags {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 8px;
      margin-bottom: 28px;
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
      cursor: pointer;
      user-select: none;
      transition: all 0.15s ease;
      font-family: inherit;
      outline: none;
    }}
    .tag svg {{ height: 12px; width: auto; opacity: 0.9; fill: currentColor; }}
    .tag:hover {{
      background-color: #323238;
      border-color: #52525b;
      color: #ffffff;
    }}
    .tag.inactive {{
      opacity: 0.3;
      background-color: #18181b;
      border-color: #27272a;
      color: #71717a;
      filter: grayscale(100%);
      text-decoration: line-through;
    }}

    .btn {{
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
      transition: all 0.15s ease;
      border: none;
    }}
    .btn.disabled {{
      opacity: 0.4;
      pointer-events: none;
      cursor: not-allowed;
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

    /* SNEAK PEEK / MINI AD SECTION */
    .sneak-peek-section {{
      margin-top: 32px;
      text-align: center;
    }}
    .peek-header {{
      margin-bottom: 14px;
    }}
    .peek-pill {{
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #c084fc;
      background: rgba(192, 132, 252, 0.12);
      border: 1px solid rgba(192, 132, 252, 0.25);
      padding: 3px 10px;
      border-radius: 999px;
      margin-bottom: 6px;
    }}
    .peek-heading {{
      font-size: 16px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 4px;
    }}
    .peek-desc {{
      font-size: 12px;
      color: #71717a;
    }}
    .peek-grid-container {{
      display: none;
    }}
    .peek-marquee {{
      position: relative;
      overflow: hidden;
      padding: 10px 0 14px;
      margin: 0 -12px;
      -webkit-mask-image: linear-gradient(to right, transparent, #000 4%, #000 96%, transparent);
      mask-image: linear-gradient(to right, transparent, #000 4%, #000 96%, transparent);
    }}
    .peek-gallery-drift {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .peek-track {{
      display: flex;
      width: max-content;
      gap: 8px;
      animation: gallery-drift 140s linear infinite;
      will-change: transform;
    }}
    .peek-track-1 {{ animation-duration: 155s; animation-direction: reverse; }}
    .peek-marquee:hover .peek-track {{ animation-play-state: paused; }}
    @keyframes gallery-drift {{
      from {{ transform: translateX(0); }}
      to {{ transform: translateX(calc(-50% - 4px)); }}
    }}
    .peek-card {{
      position: relative;
      width: auto;
      background: transparent;
      border-radius: 5px;
      overflow: hidden;
      text-align: left;
    }}
    .peek-poster-box {{
      position: relative;
      width: 108px;
      height: 162px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #15151a;
      overflow: hidden;
    }}
    .peek-poster-box img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      object-position: center;
      display: block;
    }}
    .peek-card-info {{
      display: none;
    }}
    .peek-card-platform {{
      font-size: 9px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 2px;
    }}
    .peek-card-title {{
      font-size: 11px;
      font-weight: 600;
      color: #f4f4f5;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .peek-card-type {{
      font-size: 10px;
      color: #71717a;
    }}
    .peek-cta-card {{
      background: rgba(39, 39, 42, 0.94);
      border: 1px solid #52525b;
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-radius: 12px;
      padding: 16px 14px;
      width: 100%;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.6);
      text-align: center;
      margin-top: 8px;
    }}
    .peek-cta-badge {{
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.06em;
      color: #4ade80;
      margin-bottom: 4px;
    }}
    .peek-cta-title {{
      font-size: 13px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 4px;
    }}
    .peek-cta-desc {{
      font-size: 11px;
      color: #a1a1aa;
      line-height: 1.4;
      margin-bottom: 12px;
    }}
    .btn-peek-action {{
      padding: 10px 14px;
      font-size: 12px;
      margin-bottom: 0;
    }}

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
    .referral-note {{
      display: block;
      margin-top: 2px;
      color: #71717a;
      font-size: 10px;
      font-weight: 400;
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
    @media (max-width: 520px) {{
      .peek-marquee {{
        margin: 0 -8px;
        padding-top: 6px;
      }}
      .peek-poster-box {{
        width: 82px;
        height: 123px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <img src="logo.png" alt="Top 10 Streams PT" class="main-logo" draggable="false" onerror="this.style.display='none'">

    <p class="subtitle">Extensão para ver o TOP 10 filmes e séries de várias plataformas de streaming em Portugal.</p>
    <h3 class="tags-heading">Seleciona as plataformas que queres ver:</h3>

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
      Copiar Manifest
    </button>

    <!-- Sneak Peek Section -->
    <div class="sneak-peek-section">
      <div class="peek-header">
        <h2 class="peek-heading">O que está a liderar em Portugal</h2>
        <p class="peek-desc">Espreita os títulos em destaque nas plataformas mais populares</p>
      </div>

      <div class="peek-marquee" aria-label="Títulos em destaque">
        <div class="peek-gallery-drift">
      {rows_html}
        </div>
      </div>
    </div>

    <div class="recommendations">
      <div class="rec-title">Extensões que recomendo</div>
      <div class="rec-list">
        <a href="http://real-debrid.com/?id=10970377" target="_blank" rel="noopener sponsored" class="rec-item">
          <span>Real-Debrid <small class="referral-note">O teu apoio através deste link ajuda o projeto.</small></span>
          <span class="badge">Apoiar</span>
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

    function toggleProvider(element) {{
      element.classList.toggle('inactive');
      updateManifestUrls();
    }}

    function updateManifestUrls() {{
      const activeTags = Array.from(document.querySelectorAll('.tag:not(.inactive)'));
      const selected = activeTags.map(el => el.getAttribute('data-provider')).sort();
      const installBtn = document.getElementById('install-btn');
      const copyBtn = document.getElementById('copy-btn');
      const origin = getBaseHostUrl();

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
      btn.innerHTML = '<span style="color:#4ade80;">✔ Link Copiado!</span>';
      setTimeout(() => {{
        btn.innerHTML = `
          <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" style="width: 20px; height: 20px;">
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
    with open("dist/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # Criar também dist/configure.html para garantir compatibilidade se acedido diretamente
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
            {"source": "/c/:config/configure", "destination": "/index.html"},
            {"source": "/c/:config", "destination": "/index.html"},
            {"source": "/configure", "destination": "/index.html"}
        ],
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
                    {"key": "Access-Control-Allow-Origin", "value": "*"},
                    {"key": "Access-Control-Allow-Methods", "value": "GET, HEAD, OPTIONS"}
                ]
            }
        ]
    }
    with open("dist/vercel.json", "w", encoding="utf-8") as f:
        json.dump(vercel_config, f, indent=2)
    print("[i] vercel.json com rewrites e CORS headers gerado.", flush=True)

    if os.path.exists("img/logo.png"):
        shutil.copy("img/logo.png", "dist/logo.png")

    history = load_history()
    new_history = {}
    manifest_catalogs = []
    featured_items = []

    for prov in PROVIDERS:
        print(f"\n--- A processar {prov['name']} ---", flush=True)

        movie_titles = []
        series_titles = []

        print(f"  -> A recolher rankings FlixPatrol Portugal ({prov['name']})...", flush=True)
        movie_titles = get_flixpatrol_top10(prov["flix_slug"], "movie")
        series_titles = get_flixpatrol_top10(prov["flix_slug"], "series")
        if not movie_titles:
          print("  [i] FlixPatrol indisponível para filmes; a usar fallback JustWatch...", flush=True)
          movie_titles = get_justwatch_top10(prov.get("jw_pkg", ""), "movie") if prov.get("jw_pkg") else []
        if not series_titles:
          print("  [i] FlixPatrol indisponível para séries; a usar fallback JustWatch...", flush=True)
          series_titles = get_justwatch_top10(prov.get("jw_pkg", ""), "series") if prov.get("jw_pkg") else []

        movie_items = resolve_titles_to_items(movie_titles, "movie")
        if not movie_items:
            print(f"  [i] Sem dados reais, a usar fallback TMDB ({prov['name']} Filmes)...", flush=True)
            movie_items = get_tmdb_fallback(prov["tmdb_id"], "movie")

        print(f"  -> Filmes encontrados: {len(movie_items)}/10", flush=True)
        if movie_items:
            cat_id = f"{prov['id']}_pt_movies"
            movie_items, cat_hist = apply_badges_to_catalog(movie_items, cat_id, history.get(cat_id, {}), prov["name"])
            new_history[cat_id] = cat_hist
            for rank, item in enumerate(movie_items, 1):
              featured_items.append({
                "platform": prov["name"],
                "color": prov.get("color", "#7b5bf5"),
                "title": item["name"],
                "type": "Filme",
                "poster": f"posters/{cat_id}_{rank}.jpg",
                "fallback_poster": item.get("poster")
              })

            clean_movie_items = []
            for it in movie_items:
                clean_movie_items.append({k: v for k, v in it.items() if not k.startswith("_") and v is not None})

            with open(f"dist/catalog/movie/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": clean_movie_items}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "movie",
                "id": cat_id,
                "name": f"{prov['name']} Top 10",
                "extra": [{"name": "skip", "isRequired": False}]
            })

        series_items = resolve_titles_to_items(series_titles, "series")
        if not series_items:
            print(f"  [i] Sem dados reais, a usar fallback TMDB ({prov['name']} Séries)...", flush=True)
            series_items = get_tmdb_fallback(prov["tmdb_id"], "series")

        print(f"  -> Séries encontradas: {len(series_items)}/10", flush=True)
        if series_items:
            cat_id = f"{prov['id']}_pt_series"
            series_items, cat_hist = apply_badges_to_catalog(series_items, cat_id, history.get(cat_id, {}), prov["name"])
            new_history[cat_id] = cat_hist
            for rank, item in enumerate(series_items, 1):
              featured_items.append({
                "platform": prov["name"],
                "color": prov.get("color", "#7b5bf5"),
                "title": item["name"],
                "type": "Série",
                "poster": f"posters/{cat_id}_{rank}.jpg",
                "fallback_poster": item.get("poster")
              })

            clean_series_items = []
            for it in series_items:
                clean_series_items.append({k: v for k, v in it.items() if not k.startswith("_") and v is not None})

            with open(f"dist/catalog/series/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": clean_series_items}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "series",
                "id": cat_id,
                "name": f"{prov['name']} Top 10",
                "extra": [{"name": "skip", "isRequired": False}]
            })

    save_history(new_history)

    # 1. Manifest Padrão (todas as plataformas)
    manifest = {
        "id": "pt.top-streaming",
        "version": "1.1.0",
        "name": "TOP 10 Portugal (Filmes & Séries)",
        "description": "Top 10 real da Netflix, Disney+, Prime, HBO, Apple TV+ e SkyShowtime em Portugal",
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
                "description": f"Top 10 real ({names_str}) em Portugal",
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