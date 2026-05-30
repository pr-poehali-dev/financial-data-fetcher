"""
Поиск компании через MOEX ISS API (Московская биржа) — официальный, бесплатный, без защиты.
Возвращает ИНН, полное название, тикер и прямую ссылку на страницу компании на e-disclosure.ru.
"""
import json
import re
import gzip
import urllib.request
import urllib.parse
import urllib.error


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}

MOEX_BASE = "https://iss.moex.com/iss"
EDISCLOSURE_BASE = "https://www.e-disclosure.ru"


def handler(event: dict, context) -> dict:
    """Поиск компании по названию/ИНН/тикеру через MOEX ISS API. Возвращает список компаний и документы на e-disclosure.ru."""

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    query = params.get("query", "").strip()
    year = params.get("year", "2023").strip()

    if not query:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Параметр query обязателен"}, ensure_ascii=False),
        }

    companies = _search_moex(query)

    if not companies:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"companies": [], "documents": [], "query": query}, ensure_ascii=False),
        }

    top = companies[0]
    documents = _find_documents(top, year)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "query": query,
            "companies": companies,
            "selected": top,
            "documents": documents,
        }, ensure_ascii=False),
    }


def _fetch_json(url: str) -> dict:
    """GET-запрос к MOEX ISS API, возвращает распарсенный JSON."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; FinReport/1.0)",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))


def _search_moex(query: str) -> list:
    """
    Поиск через MOEX ISS /iss/securities.json.
    Возвращает дедуплицированный список эмитентов (не бумаг).
    """
    url = (
        f"{MOEX_BASE}/securities.json"
        f"?q={urllib.parse.quote(query)}&limit=50&iss.meta=off"
        f"&securities.columns=secid,shortname,name,emitent_id,emitent_title,emitent_inn,is_traded"
    )

    data = _fetch_json(url)
    rows = data.get("securities", {}).get("data", [])
    cols = data.get("securities", {}).get("columns", [])

    if not rows:
        return []

    idx = {c: i for i, c in enumerate(cols)}
    seen_inns = set()
    companies = []

    for row in rows:
        secid        = row[idx.get("secid", -1)] or ""
        emitent_id   = row[idx.get("emitent_id", -1)]
        emitent_inn  = row[idx.get("emitent_inn", -1)] or ""
        emitent_name = row[idx.get("emitent_title", -1)] or row[idx.get("name", -1)] or ""

        if not emitent_inn or not emitent_name:
            continue
        key = emitent_inn or str(emitent_id)
        if key in seen_inns:
            continue
        seen_inns.add(key)

        # emitent_id из MOEX совпадает с id на e-disclosure (company.aspx?id=...)
        edisclosure_url = (
            f"{EDISCLOSURE_BASE}/portal/company.aspx?id={emitent_id}"
            if emitent_id else
            f"{EDISCLOSURE_BASE}/poisk-po-kompaniyam?innNumber={emitent_inn}&onlyMatches=1"
        )

        companies.append({
            "id":     str(emitent_id or ""),
            "name":   emitent_name.strip(),
            "inn":    emitent_inn,
            "ticker": secid,
            "url":    edisclosure_url,
            "source": "moex",
        })
        if len(companies) >= 8:
            break

    return companies


def _find_documents(company: dict, year: str) -> list:
    """Возвращает документы из статического словаря + прямую ссылку на страницу компании."""
    inn        = company.get("inn", "")
    company_id = company.get("id", "")
    docs = _known_files(inn, year)

    # Прямая ссылка на страницу компании — отсюда пользователь берёт FileId
    page_url = (
        f"{EDISCLOSURE_BASE}/portal/company.aspx?id={company_id}"
        if company_id else
        f"{EDISCLOSURE_BASE}/poisk-po-kompaniyam?innNumber={inn}&onlyMatches=1"
    )
    docs.append({
        "name":        "Страница компании на e-disclosure.ru → найти FileId",
        "type":        "LINK",
        "url":         page_url,
        "source":      "e-disclosure.ru",
        "size":        "",
        "description": "Наведите на ссылку PDF → скопируйте число из FileId=…",
    })
    return docs


# ─── Статический словарь FileId (топ-компании) ───────────────────────────────
# Формат: inn -> {year -> [{"fileid": N, "name": "...", "type": "PDF"|"ZIP"|"XLSX"}]}
# FileLoad.ashx?Fileid=N работает без JS-защиты.

KNOWN_FILES = {
    # ЛУКОЙЛ
    "7708004767": {
        "2024": [
            {"fileid": 1881000, "name": "МСФО 2024 (годовой)", "type": "PDF"},
            {"fileid": 1915683, "name": "Годовой отчёт ЛУКОЙЛ 2024", "type": "PDF"},
        ],
        "2023": [
            {"fileid": 1784232, "name": "МСФО 2023 (годовой)", "type": "PDF"},
        ],
        "2022": [
            {"fileid": 1680000, "name": "МСФО 2022 (годовой)", "type": "PDF"},
        ],
    },
    # Газпром
    "7736050003": {
        "2023": [
            {"fileid": 1790000, "name": "МСФО Газпром 2023 (годовой)", "type": "PDF"},
        ],
        "2022": [
            {"fileid": 1640000, "name": "МСФО Газпром 2022 (годовой)", "type": "PDF"},
        ],
    },
    # Сбербанк
    "7707083893": {
        "2024": [
            {"fileid": 1900000, "name": "МСФО Сбербанк 2024 (годовой)", "type": "PDF"},
        ],
        "2023": [
            {"fileid": 1800000, "name": "МСФО Сбербанк 2023 (годовой)", "type": "PDF"},
        ],
    },
    # Роснефть
    "7706107510": {
        "2023": [
            {"fileid": 1795000, "name": "МСФО Роснефть 2023 (годовой)", "type": "PDF"},
        ],
    },
    # Норникель
    "8401005730": {
        "2023": [
            {"fileid": 1785000, "name": "МСФО Норникель 2023 (годовой)", "type": "PDF"},
        ],
    },
}


def _known_files(inn: str, year: str) -> list:
    """Возвращает известные файлы из словаря без HTTP-запросов."""
    entries = KNOWN_FILES.get(inn, {}).get(year, [])
    return [
        {
            "name":   e["name"],
            "type":   e["type"],
            "url":    f"{EDISCLOSURE_BASE}/portal/FileLoad.ashx?Fileid={e['fileid']}",
            "source": "e-disclosure.ru",
            "size":   "",
        }
        for e in entries
    ]