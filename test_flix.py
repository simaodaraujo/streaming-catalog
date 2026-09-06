import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def test_scrape(slug="netflix"):
    url = f"https://flixpatrol.com/top10/{slug}/portugal/today/"
    print(f"[*] A tentar aceder a: {url}")

    movies = []
    series = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-PT"
        )
        page = context.new_page()

        # Aplica o stealth usando a classe instanciada
        stealth_sync = Stealth()
        stealth_sync.apply_stealth_sync(page)

        try:
            print("[*] A carregar página e a contornar verificações...")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            for i in range(12):
                time.sleep(1)
                title = page.title()
                if "Um momento" not in title and "Just a moment" not in title and title != "":
                    break
            
            print(f"[*] Título da página após validação: {page.title()}")

            html = page.content()
            if "Um momento" in page.title() or "Just a moment" in page.title():
                print("[!] O Cloudflare ainda reteve o browser no ecrã de desafio.")
            else:
                soup = BeautifulSoup(html, "html.parser")
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

        except Exception as e:
            print(f"[!] Erro durante o scraping: {e}")
        finally:
            browser.close()

    print("\n--- RESULTADOS ---")
    print(f"Filmes ({len(movies)}):", movies)
    print(f"Séries ({len(series)}):", series)

if __name__ == "__main__":
    test_scrape("netflix")