from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

def test_netflix_scraping():
    url = "https://www.netflix.com/tudum/top10/portugal"
    print(f"[*] A aceder a via curl_cffi: {url}")
    
    headers = {
        "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.netflix.com/"
    }

    try:
        res = cffi_requests.get(url, impersonate="chrome124", headers=headers, timeout=15)
        print(f"[*] Código de resposta HTTP: {res.status_code}")
        
        if res.status_code != 200:
            print("[!] Falha ao aceder à página da Netflix.")
            return

        soup = BeautifulSoup(res.text, "html.parser")
        tables = soup.find_all("table")
        print(f"[*] Tabelas encontradas na página: {len(tables)}")

        for idx, table in enumerate(tables):
            tipo = f"TABELA {idx + 1}"
            print(f"\n--- {tipo} ---")
            
            rows = table.select("tbody tr") or table.select("tr")
            extracted = []
            
            for row in rows:
                # Tenta primeiro extrair de links (onde está o nome do título)
                found = False
                for a in row.find_all("a"):
                    text = a.get_text(strip=True)
                    if text and not text.isdigit() and text not in extracted:
                        extracted.append(text)
                        found = true = True
                        break
                
                # Se não houver link, procura nas colunas de texto puro
                if not found:
                    cols = row.find_all("td")
                    for col in cols:
                        text = col.get_text(strip=True)
                        if text and not text.isdigit() and len(text) > 2 and text not in extracted:
                            extracted.append(text)
                            break

            for i, title in enumerate(extracted[:10], 1):
                print(f"  {i}. {title}")

    except Exception as e:
        print(f"[!] Erro durante o teste: {e}")

if __name__ == "__main__":
    test_netflix_scraping()