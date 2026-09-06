import os
import json
import time
import re
import io
import shutil
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
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")
BASE_URL = os.environ.get("BASE_URL", "https://top-streaming-pt.vercel.app").rstrip("/")
HISTORY_FILE = "dist/history.json"
LOCAL_HISTORY = "history.json"

# Tenta carregar .env se não estiver no ambiente (para execução/teste local)
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

# Plataformas de streaming em Portugal.
PROVIDERS = [
  {"id": "netflix", "name": "Netflix", "tmdb_id": 8, "flix_slug": "netflix", "jw_pkg": "nfx", "color": "#E50914"},
  {"id": "disney", "name": "Disney+", "tmdb_id": 337, "flix_slug": "disney", "jw_pkg": "dnp", "color": "#0063e5"},
  {"id": "prime", "name": "Prime Video", "tmdb_id": 119, "flix_slug": "amazon-prime", "jw_pkg": "prv", "color": "#00a8e1"},
  {"id": "hbo", "name": "HBO", "tmdb_id": 1899, "flix_slug": "hbo", "jw_pkg": "hbm", "color": "#a855f7"},
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

        # Se não encontrou, tenta o outro tipo (ex: minissérie listada como movie ou tv)
        if not results:
            other_type = "tv" if search_type == "movie" else "movie"
            res = session.get(f"https://api.themoviedb.org/3/search/{other_type}", params={"api_key": TMDB_API_KEY, "query": query, "page": 1}, timeout=7)
            results = res.json().get("results", []) if res.status_code == 200 else []
            if results:
                search_type = other_type

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


# ---------------------------------------------------------------------------
# NETFLIX - fonte 100% oficial e publica (top10.netflix.com)
# ---------------------------------------------------------------------------
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
  """Extrai títulos de uma página FlixPatrol, separando filmes e séries."""
  soup = BeautifulSoup(html, "html.parser")
  titles = []
  fallback_titles = []
  seen = set()
  fallback_seen = set()
  section_terms = {
    "movie": ("movie", "movies", "filme", "filmes"),
    "series": ("tv", "show", "shows", "series", "série", "séries"),
  }
  for link in soup.select("a[href]"):
    href = link.get("href", "")
    text = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()
    if "/title/" not in href or not text or len(text) < 2:
      continue
    if text.lower() in {"more", "details", "watch now", "trailer"}:
      continue
    key = text.casefold()
    if key not in fallback_seen:
      fallback_seen.add(key)
      fallback_titles.append(text)
    headings = link.find_all_previous(["h1", "h2", "h3", "h4"], limit=1)
    heading = headings[0].get_text(" ", strip=True).casefold() if headings else ""
    if any(term in heading for term in section_terms.get(media_type, ())) and key not in seen:
      seen.add(key)
      titles.append(text)
    if len(titles) >= 10:
      break
  return titles or fallback_titles[:10]


def get_flixpatrol_top10(platform_slug, media_type):
    """Tenta scraping direto e usa ScraperAPI apenas como fallback."""
    if not session or not BeautifulSoup:
        return []
    url = f"https://flixpatrol.com/top10/{platform_slug}/portugal/"
    try:
        direct = session.get(url, headers=HEADERS, timeout=15)
        if direct.status_code == 200:
            titles = parse_flixpatrol_titles(direct.text, media_type)
            if titles:
                print(f"  [i] FlixPatrol direto ({platform_slug}, {media_type}): {len(titles)} títulos", flush=True)
                return titles
        if not SCRAPER_API_KEY:
            return []

        response = session.get(
            "https://api.scraperapi.com/",
            params={"api_key": SCRAPER_API_KEY, "url": url, "render": "false"},
            headers=HEADERS,
            timeout=30,
        )
        if response.status_code != 200:
            print(f"  [!] FlixPatrol direto/proxy respondeu HTTP {response.status_code}", flush=True)
            return []
        titles = parse_flixpatrol_titles(response.text, media_type)
        if not titles:
          rendered = session.get(
            "https://api.scraperapi.com/",
            params={"api_key": SCRAPER_API_KEY, "url": url, "render": "true"},
            headers=HEADERS,
            timeout=45,
          )
          if rendered.status_code == 200:
            titles = parse_flixpatrol_titles(rendered.text, media_type)
            if titles:
              print(f"  [i] FlixPatrol renderizado ({platform_slug}, {media_type})", flush=True)
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
                    items.append({
                        "id": imdb_id,
                        "type": "movie" if media_type == "movie" else "series",
                        "name": name,
                        "poster": f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get("poster_path") else None
                    })
    except Exception as e:
        print(f"  [!] Erro Fallback TMDB: {e}", flush=True)
    return items


def resolve_titles_to_items(titles, media_type):
    items = []
    for title in titles:
        item = search_tmdb_title(title, media_type)
        if item and not any(existing["id"] == item["id"] for existing in items):
            items.append(item)
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
  Desenha uma pílula compacta com a variação de ranking no canto superior esquerdo.
    """
    if not Image or not ImageDraw or not ImageFont:
        return poster_bytes

    try:
        img = Image.open(io.BytesIO(poster_bytes)).convert("RGBA")
        w, h = img.size

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        scale = w / 500.0
        margin_x = int(26 * scale)
        margin_y = int(24 * scale)
        badge_h = max(24, int(29 * scale))
        radius = badge_h // 2

        if variation.startswith('+'):
            var_text = f"▲ {variation}"
            var_color = (74, 222, 128, 255)
            outline_color = (74, 222, 128, 110)
            fill_color = (12, 24, 16, 235)
        elif variation.startswith('-'):
            var_text = f"▼ {variation}"
            var_color = (248, 113, 113, 255)
            outline_color = (248, 113, 113, 110)
            fill_color = (26, 12, 14, 235)
        elif variation == 'NOVO':
            var_text = "★ NOVO"
            var_color = (250, 204, 21, 255)
            outline_color = (250, 204, 21, 110)
            fill_color = (26, 22, 10, 235)
        else:
            var_text = "="
            var_color = (203, 213, 225, 255)
            outline_color = (203, 213, 225, 65)
            fill_color = (15, 17, 23, 235)

        font_badge = get_badge_font(max(11, int(13.5 * scale)), bold=True)
        text_bbox = draw.textbbox((0, 0), var_text, font=font_badge)
        text_w = text_bbox[2] - text_bbox[0]
        pad_x = int(13 * scale) if var_text == "=" else int(10 * scale)
        badge_w = max(badge_h, text_w + (2 * pad_x))
        box = [margin_x, margin_y, margin_x + badge_w, margin_y + badge_h]
        draw.rounded_rectangle(
          box,
          radius=radius,
          fill=fill_color,
          outline=outline_color,
          width=max(1, int(1.2 * scale))
        )
        try:
          draw.text((margin_x + badge_w / 2, margin_y + badge_h / 2), var_text, font=font_badge, fill=var_color, anchor="mm")
        except TypeError:
          text_h = text_bbox[3] - text_bbox[1]
          draw.text((margin_x + (badge_w - text_w) / 2, margin_y + (badge_h - text_h) / 2), var_text, font=font_badge, fill=var_color)

        final_img = Image.alpha_composite(img, overlay).convert("RGB")
        output = io.BytesIO()
        final_img.save(output, format="JPEG", quality=88)
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


def apply_badges_to_catalog(items, cat_id, history_dict):
    """
    Calcula variações de ranking, desenha badges nos posters e guarda em dist/posters.
    """
    os.makedirs("dist/posters", exist_ok=True)
    new_cat_history = {}
    updated_items = []

    for rank, item in enumerate(items, 1):
        item_copy = dict(item)
        item_id = item_copy.get("id")
        old_rank = history_dict.get(item_id) if history_dict else None

        if old_rank is None:
            variation = "NOVO"
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
                    # Se o badge falhou, mantém o poster TMDB original
            except Exception as e:
                print(f"  [!] Aviso: Não foi possível aplicar badge em '{item_copy.get('name')}': {e}", flush=True)
                # Mantém o poster TMDB original em caso de erro

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

    # Três rows horizontais criam o mosaico; cada row recebe uma fatia intercalada.
    rows_html = []
    for row_index in range(3):
      row_cards = ""
      for item in mixed_items[:18][row_index * 6:(row_index + 1) * 6]:
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
        rows_html.append(f'        <div class="peek-track peek-track-{row_index}">\n{row_cards}        </div>')
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
      max-width: 480px;
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
      padding: 8px 0 10px;
      margin: 0 -24px;
      -webkit-mask-image: linear-gradient(to right, transparent, #000 4%, #000 96%, transparent);
      mask-image: linear-gradient(to right, transparent, #000 4%, #000 96%, transparent);
    }}
    .peek-gallery-drift {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      grid-auto-rows: 48px;
      gap: 6px;
      animation: gallery-drift 34s ease-in-out infinite alternate;
      will-change: transform;
    }}
    @keyframes gallery-drift {{
      from {{ transform: translateX(-5px); }}
      to {{ transform: translateX(5px); }}
    }}
    .peek-track {{
      display: contents;
    }}
    .peek-card {{
      position: relative;
      width: auto;
      background: transparent;
      border-radius: 5px;
      overflow: hidden;
      text-align: left;
    }}
    .peek-card:nth-child(1), .peek-card:nth-child(6) {{ grid-column: span 2; grid-row: span 2; }}
    .peek-card:nth-child(3), .peek-card:nth-child(9) {{ grid-row: span 2; }}
    .peek-card:nth-child(4) {{ grid-column: span 2; }}
    .peek-poster-box {{
      position: relative;
      height: 100%;
      width: 100%;
      background: #202024;
      overflow: hidden;
    }}
    .peek-poster-box img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
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
        padding-left: 2px;
        padding-right: 2px;
      }}
      .peek-gallery-drift {{
        grid-template-columns: repeat(4, minmax(0, 1fr));
        grid-auto-rows: 42px;
        gap: 5px;
      }}
    }}
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
      <span class="version">v1.0.8</span>
    </div>
  </div>

  <script>
    const manifestUrl = window.location.origin + window.location.pathname.replace(/\\/?$/, '/') + 'manifest.json';
    const stremioUrl = manifestUrl.replace(/^https?:\\/\\//, 'stremio://');

    document.getElementById('install-btn').href = stremioUrl;

    function openStremioLink(e) {{
      e.preventDefault();
      window.location.href = stremioUrl;
    }}

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
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY não foi encontrada nas variáveis de ambiente.")

    os.makedirs("dist/catalog/movie", exist_ok=True)
    os.makedirs("dist/catalog/series", exist_ok=True)
    os.makedirs("dist/posters", exist_ok=True)

    # Gerar vercel.json com CORS headers para o Stremio conseguir ler os catálogos
    vercel_config = {
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
    print("[i] vercel.json com CORS headers gerado.", flush=True)

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
            movie_items, cat_hist = apply_badges_to_catalog(movie_items, cat_id, history.get(cat_id, {}))
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

            with open(f"dist/catalog/movie/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": movie_items}, f, ensure_ascii=False)
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
            series_items, cat_hist = apply_badges_to_catalog(series_items, cat_id, history.get(cat_id, {}))
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

            with open(f"dist/catalog/series/{cat_id}.json", "w", encoding="utf-8") as f:
                json.dump({"metas": series_items}, f, ensure_ascii=False)
            manifest_catalogs.append({
                "type": "series",
                "id": cat_id,
                "name": f"{prov['name']} Top 10",
                "extra": [{"name": "skip", "isRequired": False}]
            })

    save_history(new_history)

    manifest = {
        "id": "org.portugal.streaming.top",
        "version": "1.0.8",
        "name": "TOP 10 Portugal (Filmes & Séries)",
        "description": "Top 10 real da Netflix, Disney+, Prime, HBO, Apple TV+ e SkyShowtime em Portugal",
        "logo": "logo.png",
        "resources": ["catalog"],
        "types": ["movie", "series"],
        "catalogs": manifest_catalogs
    }

    with open("dist/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    create_landing_page(featured_items)
    print(f"\nFinalizado com sucesso! {len(manifest_catalogs)} catálogos registados.", flush=True)


if __name__ == "__main__":
    main()
