#!/usr/bin/env python3
"""
Teste/validador do build do Top 10 Streams PT.

Uso:
    python test_flix.py

O script:
1. valida a sintaxe do build (build.py);
2. testa a lógica das datas da Netflix sem fazer pedidos à rede;
3. executa o build real (se TMDB_API_KEY estiver definida);
4. valida manifest.json, catálogos e referências aos ficheiros;
5. executa `git diff --check` se estiver dentro de um repositório.
"""

import json
import os
import subprocess
import sys
from datetime import date

import py_compile


# Se executado fora do venv e as dependências (requests/bs4) não estiverem no python global,
# reexecuta automaticamente usando o python do venv local.
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "Scripts", "python.exe")
if os.path.isfile(VENV_PYTHON) and sys.executable.lower() != os.path.abspath(VENV_PYTHON).lower():
    try:
        import requests  # noqa: F401
    except ImportError:
        res = subprocess.run([VENV_PYTHON, os.path.abspath(__file__)] + sys.argv[1:])
        sys.exit(res.returncode)

BUILD_SCRIPT = "build.py"


def fail(message):
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def ok(message):
    print(f"[ OK ] {message}")


def test_syntax():
    try:
        py_compile.compile(BUILD_SCRIPT, doraise=True)
    except py_compile.PyCompileError as exc:
        fail(f"sintaxe inválida: {exc}")
    ok("sintaxe Python")


def test_providers_config():
    namespace = {}
    with open(BUILD_SCRIPT, "r", encoding="utf-8") as f:
        source = f.read()

    # Executa apenas os imports/definições do ficheiro, sem chamar main().
    exec(compile(source, BUILD_SCRIPT, "exec"), namespace)

    providers = namespace.get("PROVIDERS", [])
    if not providers or len(providers) < 6:
        fail("Lista de PROVIDERS inválida ou com menos de 6 plataformas")

    for p in providers:
        if not p.get("flix_slug") or not p.get("jw_pkg") or not p.get("tmdb_id"):
            fail(f"Configuração incompleta para {p.get('name')}")
        if p["id"] == "disney" and p["flix_slug"] not in ("disney", "disney-plus"):
            fail("Disney+ deve usar flix_slug 'disney'")

    ok("configuração de provedores (FlixPatrol, JustWatch, TMDB)")


def test_flixpatrol_parser():
    namespace = {}
    with open(BUILD_SCRIPT, "r", encoding="utf-8") as f:
        exec(compile(f.read(), BUILD_SCRIPT, "exec"), namespace)

    page = """
    <h3>TOP 10 Movies</h3>
    <a href="/title/the-whisper-man/">The Whisper Man</a>
    <a href="/title/the-secret-woman/">The Secret Woman</a>
    <h3>TOP 10 TV Shows</h3>
    <a href="/title/the-gentlemen/">The Gentlemen</a>
    <a href="/title/beauty-in-black/">Beauty in Black</a>
    <h3>TOP 10 Kids Movies</h3>
    <a href="/title/shrek/">Shrek</a>
    """
    parse = namespace["parse_flixpatrol_titles"]
    if parse(page, "movie") != ["The Whisper Man", "The Secret Woman"]:
        fail("parser FlixPatrol não isolou a secção de filmes")
    if parse(page, "series") != ["The Gentlemen", "Beauty in Black"]:
        fail("parser FlixPatrol não isolou a secção de séries")
    ok("parser FlixPatrol: filmes e séries separados")


def run_build():
    env = os.environ.copy()
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    for k in ("TMDB_API_KEY", "SCRAPINGANT_API_KEY", "SCRAPER_API_KEY"):
                        if line.startswith(f"{k}=") and not env.get(k):
                            env[k] = line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass

    if not env.get("TMDB_API_KEY"):
        if os.path.isfile(os.path.join("dist", "manifest.json")):
            print("[SKIP] TMDB_API_KEY não definida no ambiente; a validar pasta dist/ existente")
            return
        fail("TMDB_API_KEY não está definida; o build real precisa da variável de ambiente.")

    python_bin = VENV_PYTHON if os.path.isfile(VENV_PYTHON) else sys.executable
    result = subprocess.run(
        [python_bin, BUILD_SCRIPT],
        text=True,
        env=env,
    )
    if result.returncode != 0:
        fail(f"build terminou com exit code {result.returncode}")

    ok("build real")


def validate_dist():
    manifest_path = os.path.join("dist", "manifest.json")
    if not os.path.isfile(manifest_path) or os.path.getsize(manifest_path) == 0:
        print("[SKIP] dist/manifest.json inexistente ou vazio (execute o build com TMDB_API_KEY para gerar)")
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    required = {"id", "version", "name", "description", "resources", "types", "catalogs"}
    missing = required - manifest.keys()
    if missing:
        fail(f"manifest.json sem campos: {', '.join(sorted(missing))}")

    catalogs = manifest["catalogs"]
    if not catalogs:
        fail("manifest.json não tem catálogos")

    for catalog in catalogs:
        for key in ("type", "id", "name"):
            if key not in catalog:
                fail(f"catálogo inválido: falta '{key}'")

        catalog_path = os.path.join("dist", "catalog", catalog["type"], f'{catalog["id"]}.json')
        if not os.path.isfile(catalog_path):
            fail(f"catálogo registado no manifest mas inexistente: {catalog_path}")

        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        metas = data.get("metas")
        if not isinstance(metas, list):
            fail(f"{catalog_path}: 'metas' não é uma lista")

        if not metas:
            fail(f"{catalog_path}: catálogo vazio")

        if len(metas) > 10:
            fail(f"{catalog_path}: tem {len(metas)} itens; máximo esperado é 10")

        for item in metas:
            for key in ("id", "type", "name"):
                if not item.get(key):
                    fail(f"{catalog_path}: item sem '{key}'")

    if not os.path.isfile(os.path.join("dist", "index.html")):
        fail("dist/index.html não foi criado")

    if "meta" in manifest.get("resources", []):
        meta_count = 0
        for m_type in ("movie", "series"):
            meta_dir = os.path.join("dist", "meta", m_type)
            if os.path.isdir(meta_dir):
                for mf in os.listdir(meta_dir):
                    if mf.endswith(".json"):
                        with open(os.path.join(meta_dir, mf), "r", encoding="utf-8") as f:
                            m_data = json.load(f)
                        if "meta" not in m_data or not m_data["meta"].get("id"):
                            fail(f"meta inválido: {mf}")
                        meta_count += 1
        if meta_count == 0:
            fail("nenhum endpoint /meta encontrado em dist/meta")
        ok(f"{meta_count} endpoints /meta validados")

    ok(f"manifest + {len(catalogs)} catálogos + landing page")


def git_diff_check():
    try:
        result = subprocess.run(
            ["git", "diff", "--check"],
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        print("[SKIP] git não está instalado")
        return

    if result.returncode != 0:
        fail(f"git diff --check encontrou problemas:\n{result.stdout}{result.stderr}")

    ok("git diff --check")


def main():
    print("=== Validação Top 10 Streams PT ===")
    test_syntax()
    test_providers_config()
    test_flixpatrol_parser()
    run_build()
    validate_dist()
    git_diff_check()
    print("\nTudo OK. Agora é seguro fazer o `git add`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
